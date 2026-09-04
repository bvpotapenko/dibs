"""Integration: read-side queries on a tmp board (§11, §13 step 6)."""

import pytest

from dibs import queries, transitions
from dibs.output import EVENT_CAP, Refusal, steer
from dibs.records import Agent, EventKind, Status
from dibs.runtime import DibsError
from tests.boards import (
    KEY,
    NOW,
    OTTER,
    peek_cursor,
    peek_task,
    resync,
    set_max_hand,
)

STALE = NOW + transitions.REAP_TTL_SECONDS + 1
STALE_AGAIN = STALE + transitions.REAP_TTL_SECONDS + 1
FOX = Agent(agent_id='calm-fox-3333', name='calm-fox')
NOTES = 20  # more than EVENT_CAP
# The fixture's six titles in reverse document order, flat: seq follows
# the file, so reordering lines is how a human reprioritizes (D7, §8).
REORDERED = """## Docs

- [~ brave-otter] Update the README quickstart

## Parser

- [x] Rename Lexer to Tokenizer
- [ ] Cover the empty file
- [ ] Cover multi-byte input
- [ ] Ship the tokenizer regression suite
- [ ] Fix off-by-one in the tokenizer
"""


def refused(ctx, actor, task_ids=None):
    """Claim, expect zero rows, and read why - the verb's follow-up (§6)."""
    assert not transitions.claim(ctx.conn, actor, NOW, task_ids)
    return queries.claim_refusal(ctx.conn, actor, task_ids)


def finish_all(ctx, actor, *task_ids):
    """Finish every task named, as their owner."""
    for task_id in task_ids:
        assert transitions.finish(ctx.conn, actor, NOW, task_id, 'ok')


def test_deliver_events_advances_cursor(board, two_agents):
    """D10: first call returns unseen events; an immediate second call
    returns nothing - cursor moved in the same transaction. An agent's
    own events are never echoed back; no actor means nothing to deliver."""
    otter, elephant = two_agents
    transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))  # otter's own
    note = transitions.record_note(
        board.conn, elephant.agent_id, NOW, 'heads up',
    )
    got = queries.deliver_events(board.conn, otter.agent_id)
    assert [(event.kind, event.agent) for event in got] == [
        (EventKind.JOIN, elephant.agent_id),  # joined after otter's cursor
        (EventKind.NOTE, elephant.agent_id),
    ]
    assert got[-1] == note
    assert peek_cursor(board, otter.agent_id) == note.event_id
    assert queries.deliver_events(board.conn, otter.agent_id) == ()
    assert queries.deliver_events(board.conn, None) == ()


def test_deliver_events_filters_directed(board, two_agents):
    """D10: a note --for elephant reaches elephant, never a third agent;
    broadcasts reach both; the author gets neither echoed back."""
    otter, elephant = two_agents
    assert transitions.register_agent(board.conn, FOX, NOW)
    transitions.record_note(board.conn, otter.agent_id, NOW, 'to all')
    transitions.record_note(
        board.conn, otter.agent_id, NOW, 'psst', to_name=elephant.name,
    )
    heard = queries.deliver_events(board.conn, elephant.agent_id)
    assert [(event.kind, event.text) for event in heard] == [
        (EventKind.JOIN, FOX.name),
        (EventKind.NOTE, 'to all'),
        (EventKind.NOTE, 'psst'),
    ]
    overheard = queries.deliver_events(board.conn, FOX.agent_id)
    assert [event.text for event in overheard] == ['to all']
    own = queries.deliver_events(board.conn, otter.agent_id)
    assert {event.kind for event in own} == {EventKind.JOIN}  # notes not echoed


def test_prior_claim_reports_reap(board, two_agents):
    """SSoT §6 claim row: a reaped task's re-claimer learns the prior
    claimant (by NAME, I7) and when the reap happened - the LAST reap when
    several."""
    otter, elephant = two_agents
    assert queries.prior_claim(board.conn, 'A1') is None
    transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))
    transitions.housekeeping(board.conn, None, STALE)
    first = queries.prior_claim(board.conn, 'A1')
    assert (first.kind, first.text, first.ts) == (
        EventKind.REAP, otter.name, STALE,
    )
    transitions.claim(board.conn, elephant.agent_id, STALE, ('A1',))
    transitions.housekeeping(board.conn, None, STALE_AGAIN)
    last = queries.prior_claim(board.conn, 'A1')
    assert (last.text, last.ts) == (elephant.name, STALE_AGAIN)
    assert queries.prior_claim(board.conn, 'A2.1') is None


def test_resolve_task_exact_beats_fuzzy(board):
    """D14: an exact id wins even when fuzzier candidates exist; case is
    tolerated (a2.1 is A2.1) - a tolerant form, not a guess."""
    assert queries.resolve_task(board.conn, 'A2', 'done').task_id == 'A2'
    child = queries.resolve_task(board.conn, 'a2.1', 'drop')
    assert (child.task_id, child.status, child.parent_id) == (
        'A2.1', Status.TODO, 'A2',
    )
    assert queries.resolve_task(board.conn, 'A3', 'done').status == Status.DONE


def test_resolve_task_miss_steers(board):
    """I10: a miss raises DibsError whose steer is the caller's own verb
    naming the nearest id ('did you mean A7?'), carrying the arguments
    that verb requires (SSoT §6: done --note). Nearest is the same
    ordinal in another section first (B2 -> A2), else the same section
    by ordinal distance (A9 -> A3), else the first task in the plan."""
    with pytest.raises(DibsError) as caught:
        queries.resolve_task(board.conn, 'B2', 'claim')
    assert 'Unknown task B2' in caught.value.message
    assert 'did you mean A2?' in caught.value.message
    assert caught.value.steer == 'dibs claim --task A2'
    with pytest.raises(DibsError) as caught:
        queries.resolve_task(board.conn, 'A9', 'done')
    assert caught.value.steer == 'dibs done A3 --note "..."'
    with pytest.raises(DibsError) as caught:
        queries.resolve_task(board.conn, 'zzz', 'drop')
    assert caught.value.steer == 'dibs drop A1'


def test_verify_actor_only_this_board(board, two_agents, tmp_path, make_board):
    """D8/D18: a registered id verifies; an invented one, or one minted on
    another board, does not."""
    otter = two_agents[0]
    assert queries.verify_actor(board.conn, otter.agent_id) is True
    assert queries.verify_actor(board.conn, 'calm-fox-9999') is False
    other = make_board(tmp_path / 'other', '- [ ] elsewhere\n')
    assert transitions.register_agent(other.conn, FOX, NOW)
    assert queries.verify_actor(other.conn, FOX.agent_id) is True
    assert queries.verify_actor(board.conn, FOX.agent_id) is False
    other.conn.close()


def test_newly_unlocked_last_child_only(board, two_agents):
    """D22: None while siblings stay open; the parent Task exactly on
    the last child's finish; None for a top-level task."""
    otter = two_agents[0]
    set_max_hand(board, 3)
    transitions.claim(board.conn, otter.agent_id, NOW, ('A1', 'A2.1', 'A2.2'))
    transitions.finish(board.conn, otter.agent_id, NOW, 'A1', 'ok')
    assert queries.newly_unlocked(board.conn, 'A1') is None  # no parent
    transitions.finish(board.conn, otter.agent_id, NOW, 'A2.1', 'ok')
    assert queries.newly_unlocked(board.conn, 'A2.1') is None  # A2.2 open
    transitions.finish(board.conn, otter.agent_id, NOW, 'A2.2', 'ok')
    parent = queries.newly_unlocked(board.conn, 'A2.2')
    assert (parent.task_id, parent.status) == ('A2', Status.TODO)


def test_board_snapshot_in_seq_order(board):
    """§6 list: snapshot follows current seq, not id or insert order - the
    human reorders by moving lines, and sync re-caches seq (D7, I5)."""
    resync(board, REORDERED)
    snapshot = queries.board_snapshot(board.conn)
    assert [task.task_id for task in snapshot.tasks] == [
        'B1', 'A3', 'A2.2', 'A2.1', 'A2', 'A1',
    ]
    assert [task.status for task in snapshot.tasks][:2] == [
        Status.TODO, Status.DONE,
    ]


def test_board_snapshot_carries_meta_and_events(board):
    """§5 Board: the key the board was founded with, max_hand from meta,
    plan_mtime, and the last EVENT_CAP events newest-last."""
    set_max_hand(board, 3)  # founds the board, as init --max-hand 3 does
    for number in range(NOTES):
        transitions.record_note(
            board.conn, OTTER.agent_id, NOW + number, f'note {number}',
        )
    snapshot = queries.board_snapshot(board.conn)
    assert (snapshot.key, snapshot.max_hand, snapshot.plan_mtime) == (
        KEY, 3, board.plan_path.stat().st_mtime_ns,
    )
    assert len(snapshot.events) == EVENT_CAP
    last = NOTES - 1
    assert snapshot.events[-1].text == f'note {last}'
    ids = [event.event_id for event in snapshot.events]
    assert ids == sorted(ids)


def test_claim_refusal_unknown_member(board, two_agents):
    """D14/D6: a member no row carries is an addressing error, not a wait -
    the refusal names it, suggests the nearest id, and steers with a
    runnable claim, even beside a member that is free. Members are matched
    case-insensitively, exactly as resolve_task matches them (SSoT §6)."""
    otter = two_agents[0]
    set_max_hand(board, 3)
    alone = refused(board, otter.agent_id, ('Z9',))
    beside = refused(board, otter.agent_id, ('A1', 'z9'))
    assert alone == (Refusal.UNKNOWN_TASK, ('Z9', 'A3', 'claim'))
    assert beside == alone  # a free A1 does not turn the miss into a wait
    assert steer(*alone).steer == 'dibs claim --task A3'
    assert peek_task(board, 'A1')['status'] == Status.TODO.value
    claimed = transitions.claim(board.conn, otter.agent_id, NOW, ('a1',))
    assert [task.task_id for task in claimed] == ['A1']


def test_claim_refusal_every_kind(board, two_agents):
    """D6/D22/C9: the same zero-row claim is explained as TAKEN (holder
    named), GATED (children named), OVERSIZED (a bundle no hand takes:
    size, hand, first member), HAND_FULL (held ids), WAITING (holders of
    what remaining todo rows wait on), EMPTY - one CASE picks, one names
    query per kind; the names feed output.steer verbatim."""
    otter, elephant = two_agents
    assert transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))
    taken = refused(board, elephant.agent_id, ('A1', 'A2.1'))  # A1 is held
    gated = refused(board, elephant.agent_id, ('A2',))  # open children
    oversized = refused(board, elephant.agent_id, ('A2.2', 'A2.1'))  # hand 1
    hand_full = refused(board, otter.agent_id)  # otter holds A1, max_hand 1
    set_max_hand(board, 3)
    assert transitions.claim(
        board.conn, elephant.agent_id, NOW, ('A2.1', 'A2.2', 'B1'),
    )
    finish_all(board, otter.agent_id, 'A1')
    waiting = refused(board, otter.agent_id)  # A2 waits on elephant's work
    finish_all(board, elephant.agent_id, 'A2.1', 'A2.2', 'B1')
    assert transitions.claim(board.conn, elephant.agent_id, NOW, ('A2',))
    finish_all(board, elephant.agent_id, 'A2')
    empty = refused(board, otter.agent_id)  # no todo rows remain
    seen = [taken, gated, oversized, hand_full, waiting, empty]
    assert seen == [
        (Refusal.TAKEN, ('A1', otter.name)),
        (Refusal.GATED, ('A2', 'A2.1, A2.2', 'A2.1')),
        (Refusal.OVERSIZED, ('2', '1', 'A2.2')),  # first member as typed
        (Refusal.HAND_FULL, ('A1', 'A1', '1')),
        (Refusal.WAITING, ('1', 'A2.1, A2.2', elephant.name)),
        (Refusal.EMPTY, ()),
    ]
    assert all(
        steer(kind, names).steer.startswith('dibs ') for kind, names in seen
    )
