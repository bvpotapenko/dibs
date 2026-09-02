"""Integration: the plan -> board applier on a tmp WAL DB (§13 step 8b).

ID minting and the stamped-transaction race are the crown jewels here.
The two hand-checked-[x] cases came from test_transitions with the
contract they now belong to (§13 step 8a).
"""

import threading

import pytest
from conftest import NOW, open_plan, resync

from dibs import planfile, plansync, queries, store, transitions, views
from dibs.records import EventKind, Status
from dibs.runtime import DibsError

SECOND_KEY = 'dibs-0000-1111'
ONE_HAND = 1
WIDE_HAND = 3  # init --max-hand 3 (D6)
EVENT_FLOOD = 100  # a cap above anything a fixture board holds

LATER = 2_000_000_000  # a newer plan mtime, so the CAS fires

FRESH_IDS = ('A1', 'A2', 'A2.1', 'A2.2', 'A3', 'B1')

A1_LINE = '- [ ] Fix off-by-one in the tokenizer'
A1_RETITLED = '- [ ] Fix off-by-two in the tokenizer'
A1_CHECKED = '- [x] Fix off-by-one in the tokenizer'
A1_BODY = '  Repro: token count is 12 for fixtures/one.txt, expected 11.'
A1_REWORDED = '  Repro: the count is off by one on every fixture.'
A1_KEPT = 'Done: count matches and the regression fixture passes.'

LONE_CHILD = '- [ ] Child work\n'
GROWN_PARENT = '- [ ] New parent\n  - [ ] Child work\n'

EXTRA_DOCS = '- [ ] Polish the docs index\n'  # a mid-flight edit (I9)

COUNT_TASKS = 'SELECT count(*) FROM tasks'
COUNT_EVENTS = 'SELECT count(*) FROM events'


def ids_of(ctx):
    """Every task id on the board, in seq order."""
    return tuple(task.task_id for task in queries.board_snapshot(ctx.conn))


def row(ctx, task_id):
    """One task row as it stands now."""
    return next(
        task for task in queries.board_snapshot(ctx.conn)
        if task.task_id == task_id
    )


def counts(ctx):
    """How many task rows and how many events the board holds."""
    return (
        ctx.conn.execute(COUNT_TASKS).fetchone()[0],
        ctx.conn.execute(COUNT_EVENTS).fetchone()[0],
    )


def swapped(text, line, replacement):
    """The plan with one line rewritten in place."""
    return text.replace(line, replacement)


def without(text, line):
    """The plan with one line removed."""
    return ''.join(
        kept for kept in text.splitlines(keepends=True)
        if kept.strip() != line
    )


def race_sync(db_path, text, stamp, gate, applied):
    """Apply one sync on a private connection, in step with the other."""
    conn = store.connect(db_path)
    gate.wait()
    applied.append(plansync.apply_sync(
        conn, NOW, planfile.parse_plan(text), stamp,
    ))


def test_fresh_board_mints_the_preview_ids(board, plan_text):
    """SSoT §8/D21: the ids a fresh sync mints are exactly the ones
    verify promised - section letters in document order, dotted
    children, and the ordinal counting rows under that letter."""
    preview = views.format_preview(planfile.parse_plan(plan_text))

    assert ids_of(board) == FRESH_IDS
    assert tuple(
        line.strip().split('  ')[0] for line in preview[1:]
    ) == FRESH_IDS
    # A new letter per section, in the order the headings appear.
    assert {task.section for task in queries.board_snapshot(board.conn)} == {
        'Parser', 'Docs',
    }


def test_new_rows_carry_status_and_one_event(board):
    """§8: a fresh '[x]' line lands done and owned by the author, a
    '[~ name]' newcomer lands todo (no such owner on this board), and
    every new row writes exactly one event (I6)."""
    assert (row(board, 'A3').status, row(board, 'A3').owner) == (
        Status.DONE, plansync.AUTHOR,
    )
    assert row(board, 'A3').done_note == plansync.AUTHOR_DONE_NOTE
    assert row(board, 'A3').done_at == NOW
    assert (row(board, 'B1').status, row(board, 'B1').owner) == (
        Status.TODO, None,
    )
    assert [
        (event.kind, event.task_id)
        for event in queries.recent_events(board.conn, len(FRESH_IDS) + 1)
        if event.kind == EventKind.SYNC
    ] == [(EventKind.SYNC, task_id) for task_id in reversed(FRESH_IDS)]


def test_stamp_cas_makes_a_repeat_a_no_op(board, plan_text):
    """§6/I9: the mtime CAS is the first statement, so re-applying the
    same file version costs one UPDATE and changes nothing."""
    before = counts(board)

    again = plansync.apply_sync(
        board.conn, NOW, planfile.parse_plan(plan_text), str(LATER),
    )
    third = plansync.apply_sync(
        board.conn, NOW, planfile.parse_plan(plan_text), str(LATER),
    )

    # The stamp moved, so the first call ran - and found nothing to do.
    assert again == plansync.EMPTY_SYNC
    assert third is plansync.EMPTY_SYNC
    assert counts(board) == before


def test_sync_race_exactly_one_applier(board, plan_text):
    """§8/I1: two workers notice the same author edit at the same
    moment; the stamp CAS lets exactly one apply it, so the new line
    becomes one row, never two."""
    edited = plan_text + EXTRA_DOCS
    board.conn.commit()
    gate = threading.Barrier(2)
    applied = []
    racers = [
        threading.Thread(
            target=race_sync,
            args=(board.db_path, edited, str(LATER), gate, applied),
        )
        for _each in range(2)
    ]

    for racer in racers:
        racer.start()
    for racer in racers:
        racer.join()

    assert sum(bool(plan.new) for plan in applied) == 1
    # The loser short-circuited on the stamp itself, not on a lucky
    # snapshot: the CAS is what de-duplicates the two syncs (§6).
    assert any(plan is plansync.EMPTY_SYNC for plan in applied)
    assert ids_of(board) == (*FRESH_IDS, 'B2')


def test_retitle_orphans_and_never_reuses_the_id(board, plan_text):
    """§8/I5: an edited title orphans the old row and creates a new
    one, and the new id counts rows EVER created under that letter -
    orphans included - so A1 is never handed out twice."""
    resync(board, swapped(plan_text, A1_LINE, A1_RETITLED), LATER)

    assert row(board, 'A1').status == Status.ORPHANED
    assert 'A4' in ids_of(board)
    assert row(board, 'A4').title == 'Fix off-by-two in the tokenizer'
    assert [
        (event.kind, event.task_id)
        for event in queries.recent_events(board.conn, 2)
    ] == [(EventKind.SYNC, 'A4'), (EventKind.ORPHAN, 'A1')]


def test_orphaning_a_held_row_frees_the_hand(board, two_agents, plan_text):
    """§8/D6: a line the author deleted leaves the plan even while a
    worker holds it - the owner stays on the row for the record, but
    the row no longer counts against that worker's hand."""
    worker = two_agents[0].agent_id
    transitions.claim(board.conn, worker, NOW, ('A1',))

    resync(board, without(plan_text, A1_LINE), LATER)

    assert row(board, 'A1').status == Status.ORPHANED
    assert row(board, 'A1').owner == worker
    assert transitions.claim(board.conn, worker, NOW)[0].task_id == 'A2.1'


def test_hand_checked_imports_as_author_done(board, plan_text):
    """SSoT §8: a hand-checked [x] over a todo row imports as done with
    owner 'human' and a note, and writes one done event."""
    resync(board, swapped(plan_text, A1_LINE, A1_CHECKED), LATER)
    imported = row(board, 'A1')

    assert imported.status == Status.DONE
    assert imported.owner == plansync.AUTHOR
    assert imported.done_at == NOW
    # planfile's done annotation renders a note, so one must exist.
    assert imported.done_note
    assert [
        (event.kind, event.agent, event.task_id)
        for event in queries.recent_events(board.conn, 1)
    ] == [(EventKind.DONE, plansync.AUTHOR, 'A1')]


def test_hand_checked_never_overrides_live_work(board, two_agents, plan_text):
    """SSoT §8: the DB wins - a row a worker claimed meanwhile is not
    imported, and no error is raised over it."""
    worker = two_agents[0].agent_id
    transitions.claim(board.conn, worker, NOW, ('A1',))

    applied = resync(board, swapped(plan_text, A1_LINE, A1_CHECKED), LATER)

    assert not applied.checked
    assert row(board, 'A1').status == Status.DOING
    assert row(board, 'A1').owner == worker
    assert not any(
        event.kind == EventKind.DONE
        for event in queries.recent_events(board.conn, EVENT_FLOOD)
    )


def test_reparents_under_a_brand_new_parent(tmp_path):
    """§8/D22: a brand-new checkbox above an existing child becomes its
    parent in one pass - the applier resolves the parent LINE to the id
    it has just minted (planfile.ParentUpdate)."""
    ctx = open_plan(tmp_path, LONE_CHILD)

    resync(ctx, GROWN_PARENT, LATER)

    assert ids_of(ctx) == ('A2', 'A1')
    assert row(ctx, 'A2').title == 'New parent'
    assert row(ctx, 'A1').parent_id == 'A2'
    parent, child = (row(ctx, 'A2'), row(ctx, 'A1'))
    assert (parent.seq, child.seq) == (1, 2)


def test_body_refresh_writes_no_event(board, plan_text):
    """§8 (Rev 9)/I6: rewording a briefing is text truth flowing md ->
    db - the row's body changes and the journal does not."""
    before = counts(board)

    applied = resync(board, swapped(plan_text, A1_BODY, A1_REWORDED), LATER)

    reworded = '\n'.join((A1_REWORDED.strip(), A1_KEPT))

    assert applied.refreshed == (('A1', reworded, 'Parser'),)
    assert row(board, 'A1').body == reworded
    assert counts(board) == before


def test_open_board_refuses_a_second_init(board):
    """SSoT §6/I1: opening the board is a compare-and-swap on the
    stored key, so a second init finds one and is refused - with the
    existing key in a runnable steer (D20, I10)."""
    with pytest.raises(DibsError) as refusal:
        plansync.open_board(board.conn, NOW, SECOND_KEY, ONE_HAND)

    assert refusal.value.steer == 'dibs sync --plan dibs-7f3a-9c2e'
    assert refusal.value.steer.startswith('dibs ')
    assert store.read_meta(board.conn, store.BOARD_KEY) == 'dibs-7f3a-9c2e'


def test_open_board_records_key_and_hand(tmp_path):
    """SSoT §6/D6/D20: init stores the key it minted and the hand it
    was given, and writes exactly one init event naming the key."""
    conn = store.connect(tmp_path / '.other.md.dibs')
    store.ensure_schema(conn)

    opened = plansync.open_board(conn, NOW, SECOND_KEY, WIDE_HAND)

    assert store.read_meta(conn, store.BOARD_KEY) == SECOND_KEY
    assert store.read_meta(conn, store.MAX_HAND) == str(WIDE_HAND)
    assert (opened.kind, opened.agent, opened.text) == (
        EventKind.INIT, plansync.AUTHOR, SECOND_KEY,
    )
    assert conn.execute(COUNT_EVENTS).fetchone()[0] == 1
