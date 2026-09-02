"""Integration: read-side queries on a tmp board (§11, §13 step 5)."""

import pytest
from conftest import NOW

from dibs import output, queries, transitions
from dibs.records import EventKind, Status
from dibs.runtime import DibsError

REORDER = 'UPDATE tasks SET seq = ? WHERE id = ?'
FIRST_SEQ = 0  # ahead of every fixture line number, so B1 sorts first
STALE = NOW - transitions.REAP_TTL_SECONDS - 1
SEQ_ORDER = ('B1', 'A1', 'A2', 'A2.1', 'A2.2', 'A3')
EVENT_FLOOD = 100  # a cap far above anything the fixture board holds


def texts(events):
    """The text of each delivered event, in delivery order."""
    return [event.text for event in events]


def test_deliver_events_advances_cursor(board, two_agents):
    """D10/§9: a joiner's cursor starts at the board's high-water mark,
    so the roster init wrote never floods a first feed; your own
    broadcasts are never echoed back; and an immediate second call
    returns nothing - the cursor moved in the same transaction."""
    worker, other = two_agents
    transitions.record_note(board.conn, worker.agent_id, NOW, 'touched it')

    first = queries.deliver_events(board.conn, worker.agent_id)
    second = queries.deliver_events(board.conn, worker.agent_id)

    # Not the six sync events nor the init line below the cursor, not
    # worker's own join, not worker's own note: just the other joiner.
    assert texts(first) == [other.name]
    assert [event.kind for event in first] == [EventKind.JOIN]
    assert not second
    # The note reaches everyone else, exactly once.
    assert texts(queries.deliver_events(board.conn, other.agent_id)) == [
        'touched it',
    ]


def test_deliver_events_without_identity(board, two_agents):
    """§6 step 8: join and a claim that minted its own identity have no
    supplied actor, so they get an empty feed by construction - no
    special case, no cursor moved."""
    otter = two_agents[0]
    transitions.record_note(board.conn, otter.agent_id, NOW, 'broadcast')

    assert not queries.deliver_events(board.conn, None)
    # The note is still there for the agent it was addressed to.
    assert texts(queries.deliver_events(board.conn, two_agents[1].agent_id))


def test_deliver_events_filters_directed(board, two_agents):
    """D10/§9: a note --for otter reaches otter and nobody else; a
    broadcast reaches everyone but its own author, whose command output
    already said it."""
    otter, elephant = two_agents
    queries.deliver_events(board.conn, otter.agent_id)
    queries.deliver_events(board.conn, elephant.agent_id)
    transitions.record_note(
        board.conn, elephant.agent_id, NOW, 'yours alone', otter.name,
    )
    transitions.record_note(board.conn, elephant.agent_id, NOW, 'everyone')

    to_otter = queries.deliver_events(board.conn, otter.agent_id)
    to_elephant = queries.deliver_events(board.conn, elephant.agent_id)

    assert texts(to_otter) == ['yours alone', 'everyone']
    assert not to_elephant


def test_recent_events_filters_and_order(board, two_agents):
    """§6 claim row + list: one statement serves both readers. Filtered
    to a task and a kind it is the reap-history warning; unfiltered it
    is the human's feed, newest first and capped."""
    prior = two_agents[0].agent_id
    transitions.claim(board.conn, prior, STALE, ('A1',))
    transitions.housekeeping(board.conn, None, NOW)

    reaped = queries.recent_events(board.conn, 1, 'A1', EventKind.REAP)[0]

    assert (reaped.kind, reaped.agent, reaped.ts) == (
        EventKind.REAP, prior, NOW,
    )
    assert not queries.recent_events(board.conn, 1, 'B1', EventKind.REAP)
    # Unfiltered: newest first, and the cap is a cap.
    assert [
        event.kind for event in queries.recent_events(board.conn, 2)
    ] == [EventKind.REAP, EventKind.CLAIM]
    assert len(queries.recent_events(board.conn, EVENT_FLOOD)) == len(
        queries.recent_events(board.conn, EVENT_FLOOD * 2),
    )


def test_resolve_task_exact_beats_fuzzy(board):
    """D14: an exact id wins even when a fuzzier candidate exists."""
    exact = queries.resolve_task(board.conn, 'A2')

    assert exact.task_id == 'A2'
    assert exact.title == 'Ship the tokenizer regression suite'
    # Tolerance normalizes case and padding only; it never resolves to
    # a different id - a silent A2 -> A2.1 would claim the wrong work.
    assert queries.resolve_task(board.conn, ' a2.1 ').task_id == 'A2.1'


def test_resolve_task_miss_steers(board):
    """I10: a miss raises DibsError whose steer is a runnable claim
    command naming the nearest id ('did you mean A7?')."""
    with pytest.raises(DibsError) as near_miss:
        queries.resolve_task(board.conn, 'B7')
    with pytest.raises(DibsError) as no_match:
        queries.resolve_task(board.conn, 'ZZZ9')

    assert 'B7' in near_miss.value.message
    assert 'B1' in near_miss.value.message
    assert near_miss.value.steer == output.RECLAIM.format('B1')
    # Nothing close enough to name: the steer still runs (I10).
    assert 'ZZZ9' in no_match.value.message
    assert no_match.value.steer == output.LIST_BOARD


def test_verify_actor_only_this_board(board, two_agents):
    """D8/D18: a registered id verifies; an id from another board (or
    invented) does not."""
    assert queries.verify_actor(board.conn, two_agents[0].agent_id)
    # Same name, another board's numeric suffix (D8) - still unknown.
    assert not queries.verify_actor(board.conn, 'brave-otter-9999')
    assert not queries.verify_actor(board.conn, 'ghost-lemur-0001')


def test_newly_unlocked_last_child_only(board, two_agents):
    """D22: None while siblings stay open; the parent Task exactly on
    the last child's finish."""
    worker = two_agents[0].agent_id
    transitions.claim(board.conn, worker, NOW, ('A2.1',))
    transitions.finish(board.conn, worker, NOW, 'A2.1', 'first child')

    assert queries.newly_unlocked(board.conn, 'A2.1') is None

    transitions.claim(board.conn, worker, NOW, ('A2.2',))
    transitions.finish(board.conn, worker, NOW, 'A2.2', 'last child')
    unlocked = queries.newly_unlocked(board.conn, 'A2.2')

    assert unlocked.task_id == 'A2'
    assert unlocked.status == Status.TODO
    # A1 is top level: finishing it unlocks nothing.
    assert queries.newly_unlocked(board.conn, 'A1') is None


def test_board_snapshot_in_seq_order(board):
    """§6 list: snapshot follows current seq, not id or insert order."""
    board.conn.execute(REORDER, (FIRST_SEQ, 'B1'))
    board.conn.commit()

    snapshot = queries.board_snapshot(board.conn)

    assert tuple(task.task_id for task in snapshot) == SEQ_ORDER
