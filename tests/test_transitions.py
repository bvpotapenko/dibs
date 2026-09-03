"""Integration: write transitions on a tmp WAL DB (§11, §13 step 4).

The CAS race test is the reason dibs exists; land it first, red, then
implement claim against it.
"""

import threading
from contextlib import closing

from dibs import store, transitions
from dibs.records import Agent, EventKind, Status
from tests.boards import (
    NOW,
    held_ids,
    open_children,
    orphan,
    peek_events,
    peek_task,
    set_max_hand,
    todo_ids,
)

LATER = NOW + 100
STALE = NOW + transitions.REAP_TTL_SECONDS + 1  # A1's lease just expired


def ids(tasks) -> list[str]:
    """Task ids in the order claim returned them."""
    return [task.task_id for task in tasks]


def race_claim(db_path, actor, barrier, outcomes):
    """Thread body: own connection, meet at the barrier, claim A1."""
    with closing(store.connect(db_path)) as conn:
        barrier.wait()
        outcomes[actor] = transitions.claim(conn, actor, NOW, ('A1',))


def test_claim_race_exactly_one_winner(board, two_agents):
    """I1/I2: two threads claim the same lone task over one DB file;
    exactly one gets rowcount 1. Use a threading.Barrier so both hit
    the UPDATE together; separate connections per thread."""
    barrier = threading.Barrier(len(two_agents))
    outcomes = {}
    threads = [
        threading.Thread(
            target=race_claim,
            args=(board.db_path, agent.agent_id, barrier, outcomes),
        )
        for agent in two_agents
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    winners = [actor for actor, won in outcomes.items() if won]
    assert len(winners) == 1
    assert peek_task(board, 'A1')['owner'] == winners[0]
    assert len(peek_events(board, EventKind.CLAIM.value)) == 1


def test_claim_bundle_all_or_none(board, two_agents):
    """D6: a bundle with one already-taken member claims nothing, and
    the taken member is identifiable for the steer."""
    otter, elephant = two_agents
    set_max_hand(board, 3)
    first = transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))
    assert ids(first) == ['A1']
    bundle = ('A1', 'A2.1')
    assert not transitions.claim(board.conn, elephant.agent_id, NOW, bundle)
    assert peek_task(board, 'A2.1')['status'] == Status.TODO.value
    taken = {
        task_id: peek_task(board, task_id)['owner']
        for task_id in bundle
        if peek_task(board, task_id)['owner']
    }
    assert taken == {'A1': otter.agent_id}


def test_claim_bundle_must_fit_hand(board, two_agents):
    """D6: a bundle larger than max_hand is refused whole, not trimmed."""
    otter = two_agents[0]
    bundle = ('A1', 'A2.1')  # both available, but max_hand is 1
    assert not transitions.claim(board.conn, otter.agent_id, NOW, bundle)
    assert not held_ids(board, otter.agent_id)
    set_max_hand(board, 2)
    got = transitions.claim(board.conn, otter.agent_id, NOW, bundle)
    assert ids(got) == ['A1', 'A2.1']
    assert held_ids(board, otter.agent_id) == ('A1', 'A2.1')


def test_claim_hand_limit_blocks_second(board, two_agents):
    """D6: with max_hand=1 and one task held, a second claim returns
    zero rows - enforced inside the WHERE, not by Python."""
    otter = two_agents[0]
    assert ids(transitions.claim(board.conn, otter.agent_id, NOW)) == ['A1']
    assert not transitions.claim(board.conn, otter.agent_id, NOW)
    assert not transitions.claim(board.conn, otter.agent_id, NOW, ('A2.1',))
    assert len(peek_events(board, EventKind.CLAIM.value)) == 1


def test_respawn_steered_back_to_held_task(board, two_agents):
    """D6 side benefit: a re-run with the same identity and a full hand
    is refused, and the follow-up read names the held task."""
    otter = two_agents[0]
    transitions.claim(board.conn, otter.agent_id, NOW, ('A2.2',))
    respawned = Agent(agent_id=otter.agent_id, name=otter.name)  # same id
    assert not transitions.claim(board.conn, respawned.agent_id, LATER)
    assert held_ids(board, respawned.agent_id) == ('A2.2',)


def test_claim_prefers_last_section_then_seq(tmp_path, make_board, two_agents):
    """D7: next no-arg claim lands in the caller's last section when one
    is open there, else lowest seq; explicit --task overrides."""
    ctx = make_board(tmp_path / 'affinity', (
        '## Parser\n- [ ] P one\n- [ ] P two\n'
        '## Docs\n- [ ] D one\n- [ ] D two\n'
    ))
    otter = two_agents[0].agent_id
    assert transitions.register_agent(ctx.conn, two_agents[0])
    first = transitions.claim(ctx.conn, otter, NOW, ('B1',))
    assert ids(first) == ['B1']
    transitions.finish(ctx.conn, otter, NOW, 'B1', 'done')
    # Docs is warm: B2 wins over the lower-seq A1.
    assert ids(transitions.claim(ctx.conn, otter, NOW)) == ['B2']
    transitions.finish(ctx.conn, otter, NOW, 'B2', 'done')
    # Docs is empty: fall back to document order.
    assert ids(transitions.claim(ctx.conn, otter, NOW)) == ['A1']
    transitions.finish(ctx.conn, otter, NOW, 'A1', 'done')
    # Explicit --task overrides everything.
    explicit = transitions.claim(ctx.conn, otter, NOW, ('A2',))
    assert ids(explicit) == ['A2']
    ctx.conn.close()


def test_claim_skips_gated_parents(board, two_agents):
    """D22: no-arg claim never picks a task with an open (todo/doing)
    child; it takes the deepest ready work instead."""
    otter = two_agents[0]
    order = []
    for _ in range(6):
        got = transitions.claim(board.conn, otter.agent_id, NOW)
        order.extend(ids(got))
        for task in got:
            transitions.finish(
                board.conn, otter.agent_id, NOW, task.task_id, 'ok',
            )
    assert order == ['A1', 'A2.1', 'A2.2', 'A2', 'B1']
    assert not transitions.claim(board.conn, otter.agent_id, NOW)


def test_claim_gated_parent_names_children(board, two_agents):
    """D22/D6: explicit claim of a gated parent yields zero rows, and
    the follow-up read lists its open children for the steer."""
    otter = two_agents[0]
    assert not transitions.claim(board.conn, otter.agent_id, NOW, ('A2',))
    assert open_children(board, 'A2') == ('A2.1', 'A2.2')
    assert peek_task(board, 'A2')['status'] == Status.TODO.value


def test_claim_ignores_orphaned_children(board, two_agents):
    """D22: orphaned children left the plan; they never gate a parent."""
    otter = two_agents[0]
    orphan(board, 'A2.1', 'A2.2')
    assert not open_children(board, 'A2')
    got = transitions.claim(board.conn, otter.agent_id, NOW, ('A2',))
    assert ids(got) == ['A2']


def test_claim_zero_rows_three_diagnoses(board, two_agents):
    """D6/D22: the same zero-row claim is diagnosed three ways by the
    follow-up read - hand full / nothing available yet / board empty -
    each carrying the data its distinct steer needs."""
    otter, elephant = two_agents
    # 1. Hand full: otter holds A1; the read names what it holds.
    transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))
    refusal = transitions.claim(board.conn, otter.agent_id, NOW)
    assert (refusal, held_ids(board, otter.agent_id)) == ((), ('A1',))
    # 2. Nothing available yet: everything else is held or gated.
    set_max_hand(board, 3)
    bundle = ('A2.1', 'A2.2', 'B1')
    got = transitions.claim(board.conn, elephant.agent_id, NOW, bundle)
    assert ids(got) == list(bundle)
    transitions.finish(board.conn, otter.agent_id, NOW, 'A1', 'ok')
    refusal = transitions.claim(board.conn, otter.agent_id, NOW)
    # A2 is still todo but waits on A2.1 + A2.2, which elephant holds.
    assert (refusal, held_ids(board, otter.agent_id), todo_ids(board)) == (
        (), (), ('A2',),
    )
    # 3. Board empty: no todo rows remain at all.
    for task_id in bundle:
        transitions.finish(board.conn, elephant.agent_id, NOW, task_id, 'ok')
    transitions.claim(board.conn, elephant.agent_id, NOW, ('A2',))
    refusal = transitions.claim(board.conn, otter.agent_id, NOW)
    assert (refusal, held_ids(board, otter.agent_id), todo_ids(board)) == (
        (), (), (),
    )


def test_finish_rejects_non_owner(board, two_agents):
    """I2: WHERE owner=:actor - the other agent's finish is rowcount 0."""
    otter, elephant = two_agents
    transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))
    rejected = transitions.finish(
        board.conn, elephant.agent_id, NOW, 'A1', 'mine',
    )
    assert rejected is None
    row = peek_task(board, 'A1')
    assert row['status'] == Status.DOING.value
    assert row['owner'] == otter.agent_id
    assert not peek_events(board, EventKind.DONE.value)


def test_finish_writes_one_event(board, two_agents):
    """C3/I6: one successful finish = one done event, same transaction."""
    otter = two_agents[0]
    transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))
    task = transitions.finish(
        board.conn, otter.agent_id, LATER, 'A1', 'two files',
    )
    assert (task.status, task.owner) == (Status.DONE, otter.agent_id)
    assert (task.done_at, task.done_note) == (LATER, 'two files')
    events = [
        (row['agent'], row['task_id'], row['text'])
        for row in peek_events(board, EventKind.DONE.value)
    ]
    assert events == [(otter.agent_id, 'A1', 'two files')]
    again = transitions.finish(board.conn, otter.agent_id, LATER, 'A1', 'x')
    assert again is None  # done is terminal: no second event


def test_release_returns_task_to_todo(board, two_agents):
    """SSoT §6 drop: owned doing -> todo, owner cleared, drop event."""
    otter, elephant = two_agents
    transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))
    rejected = transitions.release(
        board.conn, elephant.agent_id, NOW, 'A1', None,
    )
    assert rejected is None
    task = transitions.release(
        board.conn, otter.agent_id, LATER, 'A1', 'blocked on B1',
    )
    assert (task.status, task.owner) == (Status.TODO, None)
    assert task.claimed_at is None
    events = [
        (row['agent'], row['task_id'], row['text'])
        for row in peek_events(board, EventKind.DROP.value)
    ]
    assert events == [(otter.agent_id, 'A1', 'blocked on B1')]
    assert not held_ids(board, otter.agent_id)


def test_housekeeping_reaps_past_ttl(board, two_agents):
    """D9/I8: a claim older than REAP_TTL_SECONDS reverts to todo and
    logs a reap event; younger claims are untouched."""
    otter, elephant = two_agents
    transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))
    transitions.claim(board.conn, elephant.agent_id, STALE - 1, ('A2.1',))
    assert not transitions.housekeeping(board.conn, None, STALE - 1)
    reaped = [
        (event.kind, event.task_id, event.agent, event.text, event.ts)
        for event in transitions.housekeeping(board.conn, None, STALE)
    ]
    assert reaped == [(EventKind.REAP, 'A1', 'system', otter.agent_id, STALE)]
    freed = peek_task(board, 'A1')
    assert (freed['status'], freed['owner']) == (Status.TODO.value, None)
    assert peek_task(board, 'A2.1')['owner'] == elephant.agent_id  # young
    assert len(peek_events(board, EventKind.REAP.value)) == 1


def test_housekeeping_refreshes_callers_lease(board, two_agents):
    """D9: any command from an agent bumps claimed_at on its claims."""
    otter, elephant = two_agents
    transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))
    transitions.claim(board.conn, elephant.agent_id, NOW, ('A2.1',))
    assert not transitions.housekeeping(board.conn, otter.agent_id, LATER)
    assert peek_task(board, 'A1')['claimed_at'] == LATER
    assert peek_task(board, 'A2.1')['claimed_at'] == NOW  # not the caller's
    # Past the TTL the caller's own claim is renewed by its activity and
    # never reaped; the other agent's stale claim is.
    reaped = transitions.housekeeping(board.conn, otter.agent_id, STALE)
    assert [event.task_id for event in reaped] == ['A2.1']
    assert peek_task(board, 'A1')['claimed_at'] == STALE


def test_record_note_broadcast_and_directed(board, two_agents):
    """D10: no --for means to_agent NULL; --for sets it; both append."""
    otter, elephant = two_agents
    shout = transitions.record_note(
        board.conn, otter.agent_id, NOW, 'moving the parser',
    )
    whisper = transitions.record_note(
        board.conn, otter.agent_id, NOW, 'psst', to_name=elephant.name,
    )
    stray = transitions.record_note(
        board.conn, otter.agent_id, NOW, 'hi', to_name='nobody',
    )
    assert (shout.kind, shout.agent) == (EventKind.NOTE, otter.agent_id)
    assert (shout.task_id, shout.to_agent) == (None, None)
    assert (whisper.to_agent, whisper.text) == (elephant.agent_id, 'psst')
    assert stray.to_agent == 'nobody'  # verbatim; the verb warns (SSoT §6)
    logged = [row['id'] for row in peek_events(board, EventKind.NOTE.value)]
    assert logged == [shout.event_id, whisper.event_id, stray.event_id]


def test_import_author_done_owner_human(board):
    """SSoT §8: a hand-checked [x] imports as done with owner 'human'."""
    task = transitions.import_author_done(board.conn, NOW, 'A1')
    assert (task.status, task.owner) == (Status.DONE, 'human')
    assert (task.done_at, task.done_note) == (NOW, None)
    events = [
        (row['agent'], row['task_id'])
        for row in peek_events(board, EventKind.DONE.value)
    ]
    assert events == [('human', 'A1')]
    assert transitions.import_author_done(board.conn, NOW, 'A1') is None
    assert transitions.import_author_done(board.conn, NOW, 'A3') is None


def test_register_agent_false_on_collision(board):
    """I1: second INSERT of the same name returns False via UNIQUE -
    no SELECT-then-INSERT anywhere."""
    otter = Agent(agent_id='brave-otter-1111', name='brave-otter')
    assert transitions.register_agent(board.conn, otter) is True
    same_name = Agent(agent_id='brave-otter-9999', name='brave-otter')
    assert transitions.register_agent(board.conn, same_name) is False
    same_id = Agent(agent_id='brave-otter-1111', name='other-otter')
    assert transitions.register_agent(board.conn, same_id) is False
    joins = peek_events(board, EventKind.JOIN.value)
    assert [(row['agent'], row['text']) for row in joins] == [
        (otter.agent_id, otter.name),
    ]
    cursor = board.conn.execute(
        'SELECT last_event_seen FROM agents WHERE id = ?', (otter.agent_id,),
    ).fetchone()
    assert cursor[0] == joins[0]['id']  # a newcomer starts after its join
