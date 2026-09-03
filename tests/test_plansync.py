"""Integration: author-side writes on a tmp WAL DB (§11, §13 step 7).

From this step on tests/boards.build_board seeds through apply_sync and
its raw INSERT is gone (ARCHITECTURE §11); the fixture board stays
unfounded so found_board can be exercised here from its first call.
"""

import threading
from contextlib import closing

from dibs import planfile, plansync, store, transitions, views
from dibs.records import EventKind
from dibs.runtime import Context
from tests.boards import NOW, peek_events, peek_meta, peek_task, peek_tree

KEY = 'dibs-7f3a-9c2e'
LATER = NOW + 100
MTIME = 1_700_000_000_000_000_000  # an st_mtime_ns
IDS = ('A1', 'A2', 'A2.1', 'A2.2', 'A3', 'B1')
STATE = ('status', 'owner', 'claimed_at', 'done_at', 'done_note')
FIX_BLOCK = (
    '- [ ] Fix off-by-one in the tokenizer\n'
    '  Repro: token count is 12 for fixtures/one.txt, expected 11.\n'
    '  Done: count matches and the regression fixture passes.\n'
)


def resync(ctx, text):
    """Write text to the fixture's plan and apply it, as the pipeline would."""
    ctx.plan_path.write_text(text)
    return plansync.apply_sync(
        ctx.conn, LATER, planfile.parse_plan(text),
        ctx.plan_path.stat().st_mtime_ns,
    )


def state_of(ctx):
    """id -> state columns of every row (the columns sync must not touch)."""
    return {
        row['id']: tuple(row[column] for column in STATE)
        for row in peek_tree(ctx)
    }


def race_sync(db_path, plan_items, barrier, outcomes):
    """Thread body: own connection, meet at the barrier, apply the same text."""
    with closing(store.connect(db_path)) as conn:
        barrier.wait()
        outcomes.append(plansync.apply_sync(conn, LATER, plan_items, MTIME))


def test_found_board_wins_once(board):
    """I1/D20: first call True + INIT event; second call False, no event,
    key unchanged; max_hand stamped from the argument (D6)."""
    assert plansync.found_board(board.conn, NOW, KEY, 3) is True
    assert plansync.found_board(board.conn, LATER, 'dibs-0000-0000', 5) is False
    assert (peek_meta(board, 'board_key'), peek_meta(board, 'max_hand')) == (
        KEY, '3',
    )
    inits = [
        (row['agent'], row['text'], row['ts'])
        for row in peek_events(board, EventKind.INIT.value)
    ]
    assert inits == [('human', KEY, NOW)]


def test_apply_sync_empty_board_is_init(tmp_path, plan_text):
    """D24: on an empty board every line is new; rows land with minted ids
    in seq order, a hand [x] imports as done by 'human' with one DONE
    event, one SYNC event follows, plan_mtime is stamped."""
    db_path = tmp_path / '.plan.md.dibs'
    with closing(store.connect(db_path)) as conn:
        store.ensure_schema(conn)
        plan = plansync.apply_sync(
            conn, NOW, planfile.parse_plan(plan_text), MTIME,
        )
        ctx = Context(conn, tmp_path / 'plan.md', db_path, None, NOW)
        assert (plan.new, plan.checked, plan.vanished, plan.regressed) == (
            IDS, ('A3',), (), (),
        )
        assert [row['id'] for row in peek_tree(ctx)] == list(IDS)
        imported = peek_task(ctx, 'A3')
        assert tuple(imported[column] for column in STATE) == (
            'done', 'human', None, NOW, None,
        )
        events = [
            (row['kind'], row['agent'], row['task_id'], row['ts'])
            for row in peek_events(ctx)
        ]
        assert events == [
            ('done', 'human', 'A3', NOW), ('sync', 'human', None, NOW),
        ]
        assert peek_meta(ctx, 'plan_mtime') == str(MTIME)


def test_apply_sync_imports_hand_checked_as_human(board, plan_text):
    """SSoT §8: a hand-checked [x] imports as done by 'human' with one DONE
    event (the fixture's A3 came through this path); a later [x] imports
    once, and re-syncing the same text never re-imports."""
    imported = peek_task(board, 'A3')
    assert tuple(imported[column] for column in STATE) == (
        'done', 'human', None, NOW, None,
    )
    edited = plan_text.replace('- [ ] Fix off-by-one', '- [x] Fix off-by-one')
    assert resync(board, edited).checked == ('A1',)  # A3 not re-imported
    dones = [
        (row['agent'], row['task_id'], row['ts'])
        for row in peek_events(board, EventKind.DONE.value)
    ]
    assert dones == [('human', 'A3', NOW), ('human', 'A1', LATER)]
    assert resync(board, edited).checked == ()
    again = peek_events(board, EventKind.DONE.value)
    assert [row['task_id'] for row in again] == ['A3', 'A1']  # no re-import


def test_apply_sync_same_text_only_journals(board, plan_text):
    """§8 idempotence: a second apply_sync on unchanged text changes no
    row and appends exactly one SYNC event carrying format_sync's text (C3)."""
    before = [tuple(row) for row in peek_tree(board)]
    journal = len(peek_events(board))
    plan = resync(board, plan_text)
    assert (plan.new, plan.vanished, plan.checked, plan.regressed) == (
        (), (), (), (),
    )
    assert [tuple(row) for row in peek_tree(board)] == before
    assert len(peek_events(board)) == journal + 1
    sync = peek_events(board)[-1]
    assert (sync['kind'], sync['agent'], sync['ts']) == (
        'sync', 'human', LATER,
    )
    assert sync['text'] == '\n'.join(views.format_sync(plan))


def test_apply_sync_refreshes_cached_text_only(board, two_agents, plan_text):
    """D4/C11: reword a body, rename a heading, re-indent, reorder while a
    task is doing -> body/section/parent_id/seq refreshed, status/owner/
    claimed_at untouched, id unchanged; the [ ] over doing is flagged."""
    otter = two_agents[0]
    transitions.claim(board.conn, otter.agent_id, NOW, ('A1',))
    before = state_of(board)
    parser, docs = plan_text.split('## Docs\n')
    edited = (
        f'## Docs\n{docs}{parser}'  # Docs section first: every seq moves
        .replace('## Parser', '## Lexer')  # heading renamed
        .replace('token count is 12', 'token count is 13')  # body reworded
        .replace('- [x] Rename Lexer', '  - [x] Rename Lexer')  # under Ship
    )
    plan = resync(board, edited)
    assert state_of(board) == before
    held = peek_task(board, 'A1')
    first_body_line = held['body'].split('\n')[0]
    assert (held['section'], first_body_line, held['owner']) == (
        'Lexer',
        'Repro: token count is 13 for fixtures/one.txt, expected 11.',
        otter.agent_id,
    )
    assert peek_task(board, 'A3')['parent_id'] == 'A2'
    assert [row['id'] for row in peek_tree(board)] == [
        'B1', 'A1', 'A2', 'A2.1', 'A2.2', 'A3',
    ]
    assert plan.regressed == ('A1',)


def test_apply_sync_orphans_and_reserves_ids(board, plan_text):
    """I5: a removed line -> orphaned (never deleted); a new line in that
    section takes the NEXT ordinal, never the orphan's."""
    retitled = plan_text.replace(FIX_BLOCK, '- [ ] Fix off-by-two\n')
    plan = resync(board, retitled)
    assert (plan.vanished, plan.new) == (('A1',), ('A4',))
    assert peek_task(board, 'A1')['status'] == 'orphaned'
    fresh = peek_task(board, 'A4')
    assert (fresh['title'], fresh['seq'], fresh['status']) == (
        'Fix off-by-two', 1, 'todo',
    )
    grown = f'{retitled}- [ ] Fix off-by-three\n'  # lands in Docs, not Parser
    assert resync(board, grown).new == ('B2',)
    assert sorted(row['id'] for row in peek_tree(board)) == [
        'A1', 'A2', 'A2.1', 'A2.2', 'A3', 'A4', 'B1', 'B2',
    ]


def test_apply_sync_converges_under_contention(board, plan_text):
    """C11: two connections apply the same edit; BEGIN IMMEDIATE serializes
    them and the second finds nothing new - one row set, no duplicate
    ids, two SYNC events."""
    edited = f'{plan_text}- [ ] Write the changelog\n'
    board.plan_path.write_text(edited)
    plan_items = planfile.parse_plan(edited)
    barrier = threading.Barrier(2)
    outcomes = []
    threads = [
        threading.Thread(
            target=race_sync,
            args=(board.db_path, plan_items, barrier, outcomes),
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(plan.new for plan in outcomes) == [(), ('B2',)]
    ids = [row['id'] for row in peek_tree(board)]
    grown = len(IDS) + 1  # exactly one B2, minted once
    assert len(set(ids)) == len(ids) == grown
    assert 'B2' in ids
    syncs = peek_events(board, EventKind.SYNC.value)
    assert len(syncs) == 1 + len(threads)  # the build's, then one each
