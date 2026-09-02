"""Integration: write transitions on a tmp WAL DB (§11, §13 step 4).

The CAS race test is the reason dibs exists; land it first, red, then
implement claim against it.
"""

import threading

import pytest
from conftest import NOW, resync

from dibs import output, store, transitions
from dibs.records import Agent, Event, EventKind, Status, Task
from dibs.runtime import DibsError

SELECT_TASK = 'SELECT * FROM tasks WHERE id = ?'
SELECT_EVENTS = 'SELECT * FROM events ORDER BY id'
SELECT_HELD = """
SELECT * FROM tasks WHERE owner = ? AND status = 'doing' ORDER BY seq
"""
SELECT_OPEN_CHILDREN = """
SELECT * FROM tasks
WHERE parent_id = ? AND status IN ('todo', 'doing') ORDER BY seq
"""
COUNT_TODO = "SELECT count(*) FROM tasks WHERE status = 'todo'"
SET_MAX_HAND = "UPDATE meta SET value = ? WHERE key = 'max_hand'"
ORPHAN_TASK = "UPDATE tasks SET status = 'orphaned' WHERE id = ?"
COUNT_AGENTS = 'SELECT count(*) FROM agents'
GATED_LEFT = 1  # A2 stays todo while its children are held

# Appended to the fixture plan, so it lands last in Docs with the
# highest seq on the board: only section affinity reaches it (D7).
EXTRA_DOCS_LINE = '- [ ] Polish the docs index\n'
LATER_STAMP = 2_000_000_000  # a newer plan mtime, so the sync CAS fires
STALE = NOW - transitions.REAP_TTL_SECONDS - 1
RECENT = NOW - 100


def load(conn, task_id):
    """The task row as it stands now."""
    return Task(*conn.execute(SELECT_TASK, (task_id,)).fetchone())


def rows_of(conn, sql, *binds):
    """Task rows a read returns, in the read's own order."""
    return tuple(Task(*row) for row in conn.execute(sql, binds))


def journal(conn):
    """Every event on the board, oldest first."""
    return tuple(Event(*row) for row in conn.execute(SELECT_EVENTS))


def kinds(conn, kind):
    """Events of one kind, oldest first."""
    return tuple(event for event in journal(conn) if event.kind == kind)


def set_hand(conn, size):
    """Widen the per-board hand limit (D6, init --max-hand)."""
    conn.execute(SET_MAX_HAND, (str(size),))
    conn.commit()


def race_claim(db_path, actor, gate, won):
    """Claim A1 on a private connection, in step with the other thread."""
    conn = store.connect(db_path)
    gate.wait()
    won.extend(transitions.claim(conn, actor, NOW, ('A1',)))


def diagnose(conn, actor):
    """What the follow-up read sees after a zero-row claim (D6, D22).

    The three steers differ by exactly these facts: what the caller
    holds, and whether any todo work remains at all.
    """
    return (
        transitions.claim(conn, actor, NOW),
        tuple(task.task_id for task in rows_of(conn, SELECT_HELD, actor)),
        conn.execute(COUNT_TODO).fetchone()[0],
    )


def drain(conn, actor):
    """Claim until the board refuses; return the ids taken, in order."""
    taken = []
    while True:
        got = transitions.claim(conn, actor, NOW)
        if not got:
            return tuple(taken)
        taken.extend(task.task_id for task in got)


def test_claim_race_exactly_one_winner(board, two_agents):
    """I1/I2: two threads claim the same lone task over one DB file;
    exactly one gets rowcount 1. Use a threading.Barrier so both hit
    the UPDATE together; separate connections per thread."""
    gate = threading.Barrier(len(two_agents))
    won = []
    racers = [
        threading.Thread(
            target=race_claim,
            args=(board.db_path, agent.agent_id, gate, won),
        )
        for agent in two_agents
    ]

    for racer in racers:
        racer.start()
    for racer in racers:
        racer.join()

    assert len(won) == 1
    assert load(board.conn, 'A1').status == Status.DOING
    assert load(board.conn, 'A1').owner == won[0].owner
    assert len(kinds(board.conn, EventKind.CLAIM)) == 1


def test_claim_bundle_all_or_none(board, two_agents):
    """D6: a bundle with one already-taken member claims nothing, and
    the taken member is identifiable for the steer."""
    holder, latecomer = two_agents
    set_hand(board.conn, 2)
    transitions.claim(board.conn, holder.agent_id, NOW, ('A1',))

    taken = transitions.claim(
        board.conn, latecomer.agent_id, NOW, ('A1', 'A2.1'),
    )

    assert not taken
    assert load(board.conn, 'A2.1').status == Status.TODO
    assert load(board.conn, 'A1').owner == holder.agent_id


def test_claim_bundle_must_fit_hand(board, two_agents):
    """D6: a bundle larger than max_hand is refused whole, not trimmed."""
    worker = two_agents[0].agent_id

    taken = transitions.claim(board.conn, worker, NOW, ('A1', 'A2.1'))

    assert not taken
    assert load(board.conn, 'A1').status == Status.TODO
    assert load(board.conn, 'A2.1').status == Status.TODO
    assert not kinds(board.conn, EventKind.CLAIM)


def test_claim_hand_limit_blocks_second(board, two_agents):
    """D6: with max_hand=1 and one task held, a second claim returns
    zero rows - enforced inside the WHERE, not by Python."""
    worker = two_agents[0].agent_id

    first = transitions.claim(board.conn, worker, NOW)
    second = transitions.claim(board.conn, worker, NOW)

    assert len(first) == 1
    assert not second
    assert len(rows_of(board.conn, SELECT_HELD, worker)) == 1


def test_respawn_steered_back_to_held_task(board, two_agents):
    """D6 side benefit: a re-run with the same identity and a full hand
    is refused, and the follow-up read names the held task."""
    worker = two_agents[0].agent_id
    held = transitions.claim(board.conn, worker, NOW)

    respawned = transitions.claim(board.conn, worker, NOW)

    assert not respawned
    assert [
        task.task_id for task in rows_of(board.conn, SELECT_HELD, worker)
    ] == [held[0].task_id]


def test_claim_prefers_last_section_then_seq(board, two_agents, plan_text):
    """D7: next no-arg claim lands in the caller's last section when one
    is open there, else lowest seq; explicit --task overrides."""
    worker = two_agents[0].agent_id
    set_hand(board.conn, 4)
    resync(board, plan_text + EXTRA_DOCS_LINE, LATER_STAMP)

    transitions.claim(board.conn, worker, NOW, ('B1',))
    affinity = transitions.claim(board.conn, worker, NOW)
    fallback = transitions.claim(board.conn, worker, NOW)
    explicit = transitions.claim(board.conn, worker, NOW, ('A2.2',))

    # B2 has the highest seq on the board; only affinity reaches it.
    assert affinity[0].task_id == 'B2'
    assert fallback[0].task_id == 'A1'
    assert explicit[0].task_id == 'A2.2'


def test_claim_skips_gated_parents(board, two_agents):
    """D22: no-arg claim never picks a task with an open (todo/doing)
    child; it takes the deepest ready work instead."""
    set_hand(board.conn, 9)

    taken = drain(board.conn, two_agents[0].agent_id)

    assert 'A2' not in taken
    assert set(taken) == {'A1', 'A2.1', 'A2.2', 'B1'}
    assert load(board.conn, 'A2').status == Status.TODO


def test_claim_gated_parent_names_children(board, two_agents):
    """D22/D6: explicit claim of a gated parent yields zero rows, and
    the follow-up read lists its open children for the steer."""
    refused = transitions.claim(
        board.conn, two_agents[0].agent_id, NOW, ('A2',),
    )

    assert not refused
    assert load(board.conn, 'A2').status == Status.TODO
    assert [
        child.task_id
        for child in rows_of(board.conn, SELECT_OPEN_CHILDREN, 'A2')
    ] == ['A2.1', 'A2.2']


def test_claim_ignores_orphaned_children(board, two_agents):
    """D22: orphaned children left the plan; they never gate a parent."""
    board.conn.execute(ORPHAN_TASK, ('A2.1',))
    board.conn.execute(ORPHAN_TASK, ('A2.2',))
    board.conn.commit()

    taken = transitions.claim(
        board.conn, two_agents[0].agent_id, NOW, ('A2',),
    )

    assert [task.task_id for task in taken] == ['A2']


def test_claim_zero_rows_three_diagnoses(board, two_agents):
    """D6/D22: the same zero-row claim is diagnosed three ways by the
    follow-up read - hand full / nothing available yet / board empty -
    each carrying the data its distinct steer needs."""
    worker, other = (agent.agent_id for agent in two_agents)
    set_hand(board.conn, 4)
    taken = drain(board.conn, worker)

    # Hand full: the caller holds work, so the steer can name it.
    assert diagnose(board.conn, worker) == ((), taken, GATED_LEFT)
    # Nothing available yet: A2 is todo but waits on held children.
    assert diagnose(board.conn, other) == ((), (), GATED_LEFT)

    for task_id in taken:
        transitions.finish(board.conn, worker, NOW, task_id, 'done')
    transitions.finish(
        board.conn, other, NOW,
        transitions.claim(board.conn, other, NOW)[0].task_id, 'done',
    )

    # Board empty: nothing is todo at all, so the steer says stop.
    assert diagnose(board.conn, other) == ((), (), 0)


def test_finish_rejects_non_owner(board, two_agents):
    """I2: WHERE owner=:actor - the other agent's finish is rowcount 0."""
    owner, stranger = two_agents
    claimed = transitions.claim(board.conn, owner.agent_id, NOW)

    with pytest.raises(DibsError):
        transitions.finish(
            board.conn, stranger.agent_id, NOW, claimed[0].task_id, 'nope',
        )

    assert load(board.conn, claimed[0].task_id).status == Status.DOING
    assert not kinds(board.conn, EventKind.DONE)


def test_finish_writes_one_event(board, two_agents):
    """C3/I6: one successful finish = one done event, same transaction."""
    worker = two_agents[0].agent_id
    claimed = transitions.claim(board.conn, worker, NOW)
    before = len(journal(board.conn))

    finished = transitions.finish(
        board.conn, worker, NOW, claimed[0].task_id, 'shipped it',
    )

    assert finished.status == Status.DONE
    assert finished.done_note == 'shipped it'
    assert finished.done_at == NOW
    assert len(journal(board.conn)) == before + 1
    assert [
        (event.task_id, event.text)
        for event in kinds(board.conn, EventKind.DONE)
    ] == [(claimed[0].task_id, 'shipped it')]


def test_release_returns_task_to_todo(board, two_agents):
    """SSoT §6 drop: owned doing -> todo, owner cleared, drop event."""
    worker = two_agents[0].agent_id
    claimed = transitions.claim(board.conn, worker, NOW)

    dropped = transitions.release(
        board.conn, worker, NOW, claimed[0].task_id, 'blocked on A2',
    )

    assert dropped.status == Status.TODO
    assert dropped.owner is None
    assert load(board.conn, claimed[0].task_id).claimed_at is None
    assert [
        event.text for event in kinds(board.conn, EventKind.DROP)
    ] == ['blocked on A2']


def test_housekeeping_reaps_past_ttl(board, two_agents):
    """D9/I8: a claim older than REAP_TTL_SECONDS reverts to todo and
    logs a reap event; younger claims are untouched."""
    worker = two_agents[0].agent_id
    set_hand(board.conn, 2)
    transitions.claim(board.conn, worker, STALE, ('A1',))
    transitions.claim(board.conn, worker, NOW, ('A2.1',))

    reaped = transitions.housekeeping(board.conn, None, NOW)

    assert [event.task_id for event in reaped] == ['A1']
    # 8a: the reap is directed at the former owner - the one agent who
    # must learn about it, whatever its cursor has passed (D9, D10).
    assert [(event.agent, event.to_agent) for event in reaped] == [
        (worker, worker),
    ]
    assert (
        load(board.conn, 'A1').status, load(board.conn, 'A1').owner,
    ) == (Status.TODO, None)
    assert load(board.conn, 'A2.1').status == Status.DOING
    assert len(kinds(board.conn, EventKind.REAP)) == 1


def test_housekeeping_refreshes_callers_lease(board, two_agents):
    """D9: any command from an agent bumps claimed_at on its claims."""
    worker, other = (agent.agent_id for agent in two_agents)
    transitions.claim(board.conn, worker, RECENT, ('A1',))
    transitions.claim(board.conn, other, RECENT, ('A2.1',))

    transitions.housekeeping(board.conn, worker, NOW)

    assert load(board.conn, 'A1').claimed_at == NOW
    assert load(board.conn, 'A2.1').claimed_at == RECENT
    assert not kinds(board.conn, EventKind.REAP)


def test_record_note_broadcast_and_directed(board, two_agents):
    """D10: no --for means to_agent NULL; --for sets it; both append."""
    speaker, listener = two_agents

    broadcast = transitions.record_note(
        board.conn, speaker.agent_id, NOW, 'touched the lexer',
    )
    directed = transitions.record_note(
        board.conn, speaker.agent_id, NOW, 'yours', listener.name,
    )
    unknown = transitions.record_note(
        board.conn, speaker.agent_id, NOW, 'to nobody', 'ghost-lemur',
    )

    assert broadcast.to_agent is None
    assert directed.to_agent == listener.agent_id
    assert unknown.to_agent is None
    assert [
        event.text for event in kinds(board.conn, EventKind.NOTE)
    ] == ['touched the lexer', 'yours', 'to nobody']


def test_refusal_wording_comes_from_output(board, two_agents):
    """C5/C7: transitions raise DibsError but build no wording of
    their own - message and steer both come from output, and the steer
    is a runnable command (D14, I10)."""
    stranger = two_agents[1]
    claimed = transitions.claim(board.conn, two_agents[0].agent_id, NOW)
    task_id = claimed[0].task_id

    with pytest.raises(DibsError) as refusal:
        transitions.finish(board.conn, stranger.agent_id, NOW, task_id, 'no')

    assert refusal.value.message == output.NOT_OWNER.format(task_id)
    assert refusal.value.steer == output.RECLAIM.format(task_id)
    assert refusal.value.steer.startswith('dibs ')


def test_register_agent_false_on_collision(board):
    """I1: second INSERT of the same name returns False via UNIQUE -
    no SELECT-then-INSERT anywhere."""
    first = transitions.register_agent(
        board.conn, Agent('brave-otter-1111', 'brave-otter'),
    )
    reroll = transitions.register_agent(
        board.conn, Agent('brave-otter-9999', 'brave-otter'),
    )

    assert first is True
    assert reroll is False
    assert board.conn.execute(COUNT_AGENTS).fetchone()[0] == 1
    assert len(kinds(board.conn, EventKind.JOIN)) == 1


def test_register_agent_replay_is_silent(board):
    """I6: re-registering an identity that already exists changes
    nothing and appends no second join event - the rowcount is the
    whole truth (I1, C3)."""
    same = Agent('brave-otter-1111', 'brave-otter')

    minted = transitions.register_agent(board.conn, same)
    replay = transitions.register_agent(board.conn, same)

    assert minted is True
    assert replay is False
    assert board.conn.execute(COUNT_AGENTS).fetchone()[0] == 1
    assert len(kinds(board.conn, EventKind.JOIN)) == 1
