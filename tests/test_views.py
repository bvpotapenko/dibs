"""Unit: the per-verb views (§11 pure tier; §13 step 8b).

Hand-built records only - views touch no DB, no clock, no file. The
preview cases came from test_output with format_preview (step 8a).
"""

from dataclasses import replace

from dibs import planfile, views
from dibs.records import Event, EventKind, Status, Task

NOW = 1_700_000_000  # fixed clock; nothing here reads a real one
OTTER = 'brave-otter-1111'
ELEPHANT = 'happy-elephant-2222'
KEY = 'dibs-7f3a-9c2e'
ONE_HAND = 1
REAPED_AGO = 20 * views.MINUTE  # 20 minutes, as the warning reports it

# Two tasks share a title, and the second has no body: one document
# exercising both inline warnings (D21).
DUPE_PLAN = """## Chores

- [ ] Water the plants
  Every pot on the balcony.
- [ ] Water the plants
"""

BASE = Task(
    task_id='A1',
    parent_id=None,
    seq=1,
    section='Parser',
    title='Fix the tokenizer',
    body='',
    text_hash=planfile.title_hash('Fix the tokenizer'),
    status=Status.TODO,
    owner=None,
    claimed_at=None,
    done_at=None,
    done_note=None,
)


def task(task_id, title, status=Status.TODO, owner=None, parent_id=None):
    """One board row, as a query hands it back."""
    return replace(
        BASE,
        task_id=task_id,
        title=title,
        status=status,
        owner=owner,
        parent_id=parent_id,
        text_hash=planfile.title_hash(title),
    )


def event(kind, task_id=None, text='', to_agent=None, agent=OTTER):
    """One journal row, as a query hands it back."""
    return Event(1, NOW, agent, kind, task_id, to_agent, text)


def preview_of(text):
    """The verify view for a plan document."""
    return views.format_preview(planfile.parse_plan(text))


def row_for(lines, task_id):
    """The single rendered line whose leading ID is task_id."""
    return next(
        line for line in lines
        if line.strip().split('  ')[0] == task_id
    )


GATED = (
    task('A1', 'Fix the tokenizer'),
    task('A2', 'Ship the regression suite'),
    task('A2.1', 'Cover multi-byte input', Status.DONE, 'human', 'A2'),
    task('A2.2', 'Cover the empty file', Status.DOING, OTTER, 'A2'),
    task('B1', 'Update the README', Status.ORPHANED),
)


def test_preview_shows_tree_and_waits_for(plan_text):
    """D21/D22: format_preview renders sections, would-be IDs, the
    nesting tree, and what each parent waits for."""
    lines = preview_of(plan_text)

    assert lines[0] == 'sections: A Parser, B Docs'
    assert tuple(
        line.strip().split('  ')[0] for line in lines[1:]
    ) == ('A1', 'A2', 'A2.1', 'A2.2', 'A3', 'B1')
    # Nesting is the indent; gating is the derived waits-for (D22).
    assert (
        row_for(lines, 'A2.1').startswith(views.TREE_STEP),
        row_for(lines, 'A2').startswith(views.TREE_STEP),
    ) == (True, False)
    assert (
        row_for(lines, 'A2').endswith('waits for A2.1, A2.2'),
        'waits for' in row_for(lines, 'A1'),
    ) == (True, False)
    # The author's own [x] shows as written, and never as a task dibs
    # is waiting on.
    assert '[x] Rename Lexer to Tokenizer' in row_for(lines, 'A3')


def test_preview_letters_an_unheaded_plan():
    """SSoT §8: no headings means one implicit, nameless section - it
    still gets its letter, and the IDs still start at A1."""
    lines = preview_of('- [ ] Buy milk\n  From the corner shop.\n')

    assert lines == ('sections: A', 'A1  Buy milk')


def test_preview_warns_bodiless_and_dupes(plan_text):
    """D21: bodiless tasks and duplicate titles get inline warnings -
    computed here, not in verbs (C5/C6). PLAN_TEXT's 'Cover the empty
    file' child is the bodiless case."""
    lines = preview_of(plan_text)
    dupes = preview_of(DUPE_PLAN)

    assert (
        views.NO_BODY in row_for(lines, 'A2.2'),
        views.NO_BODY in row_for(lines, 'A2.1'),
    ) == (True, False)
    assert views.DUPLICATE not in ''.join(lines)
    # Both halves of a duplicate pair are flagged, not just the second.
    assert views.DUPLICATE in row_for(dupes, 'A1')
    assert views.DUPLICATE in row_for(dupes, 'A2')
    assert views.NO_BODY in row_for(dupes, 'A2')


def test_board_shows_key_progress_and_orphans():
    """D20/D22: the key heads the view (lost-key recovery), a gated
    parent carries its child progress, an orphaned row says so, and
    owners appear as names, never ids (I7)."""
    lines = views.format_board(GATED, KEY, ())

    assert lines[0] == views.BOARD_HEADER.format(KEY, len(GATED))
    assert (row_for(lines, 'A2').endswith('1/2'), '/' in row_for(
        lines, 'A1',
    )) == (True, False)
    assert row_for(lines, 'A2.2') == (
        'A2.2  doing brave-otter  Cover the empty file'
    )
    # I7: shared surfaces carry names, never session ids.
    assert OTTER not in '\n'.join(lines)
    assert Status.ORPHANED.value in row_for(lines, 'B1')


def test_board_appends_recent_events_oldest_first():
    """§6 list: the human's tail reads in time order, the way the
    piggyback feed does, though the query hands it back newest first."""
    recent = (
        event(EventKind.DONE, 'A1', 'later'),
        event(EventKind.CLAIM, 'A1', 'earlier'),
    )

    plain = views.format_board(GATED, KEY, ())
    with_feed = views.format_board(GATED, KEY, recent)

    assert len(plain) == len(GATED) + 1
    assert with_feed[len(plain):] == (
        views.RECENT_HEADER,
        'claim A1 by brave-otter: "earlier"',
        'done A1 by brave-otter: "later"',
    )


def test_briefing_names_you_and_indents_the_body():
    """D14/D16: the claim response is the whole briefing - who you are,
    what you took, and the body, indented under it."""
    claimed = replace(
        BASE, status=Status.DOING, owner=ELEPHANT,
        body='Repro: counts are off.\nDone: the fixture passes.',
    )

    lines = views.format_briefing(ELEPHANT, NOW, (claimed,), ())

    assert lines == (
        'you are happy-elephant',
        'claimed A1: Fix the tokenizer',
        '  Repro: counts are off.',
        '  Done: the fixture passes.',
    )
    # A bodiless task adds no blank line under its title.
    assert views.format_briefing(ELEPHANT, NOW, (BASE,), ()) == (
        'you are happy-elephant', 'claimed A1: Fix the tokenizer',
    )


def test_briefing_warns_about_a_prior_claimant():
    """SSoT §6 claim row: a task that was reaped names who held it and
    how long ago, so the re-claimer verifies before redoing the work."""
    reap = replace(
        event(EventKind.REAP, 'A1', 'Fix the tokenizer'),
        ts=NOW - REAPED_AGO,
    )

    lines = views.format_briefing(ELEPHANT, NOW, (BASE,), (reap,))

    assert lines[-1] == (
        'previously claimed by brave-otter, reaped 20 min ago '
        + '- verify before redoing'
    )


def test_refusal_no_arg_three_diagnoses():
    """D6/D22: one zero-row claim, three different stories - hand full,
    nothing available yet, board empty - each with a runnable steer."""
    hand_full = views.claim_refusal(GATED, OTTER, (), ONE_HAND)
    waiting = views.claim_refusal(GATED, ELEPHANT, (), ONE_HAND)
    empty = views.claim_refusal(
        tuple(
            replace(row, status=Status.DONE, owner='human') for row in GATED
        ),
        ELEPHANT,
        (),
        ONE_HAND,
    )

    assert (hand_full.message, hand_full.steer) == (
        views.HAND_FULL.format('A2.2'),
        'dibs done A2.2 --note "what changed"',
    )
    assert 'A2.2 (brave-otter)' in waiting.message
    assert (empty.message, empty.steer) == (views.BOARD_EMPTY, 'dibs list')
    assert all(
        refusal.steer.startswith('dibs ')
        for refusal in (hand_full, waiting, empty)
    )


def test_refusal_explicit_names_the_state():
    """D6/D22: an explicit --task is refused with the named task's own
    state - waiting on children, held, done or gone - and a steer that
    points at work the caller can actually take."""
    free = tuple(
        replace(row, owner=None, status=Status.TODO)
        if row.owner == OTTER else row
        for row in GATED
    )

    gated = views.claim_refusal(free, ELEPHANT, ('A2',), ONE_HAND)
    taken = views.claim_refusal(GATED, ELEPHANT, ('A2.2',), ONE_HAND)
    finished = views.claim_refusal(free, ELEPHANT, ('A2.1',), ONE_HAND)
    gone = views.claim_refusal(free, ELEPHANT, ('B1',), ONE_HAND)

    assert (gated.message, gated.steer) == (
        'A2 waits for A2.2.', 'dibs claim --task A2.2',
    )
    assert taken.message == 'A2.2 is held by brave-otter.'
    assert (finished.message, gone.message) == (
        'A2.1 is already done.', 'B1 left the plan.',
    )
    assert all(
        refusal.steer.startswith('dibs claim')
        for refusal in (gated, taken, finished, gone)
    )


def test_refusal_bundle_over_the_hand():
    """D6: a bundle bigger than the hand is refused whole; the steer
    offers a bundle that fits rather than trimming silently."""
    refusal = views.claim_refusal(GATED, ELEPHANT, ('A1', 'A2'), ONE_HAND)

    assert refusal.message == views.OVER_HAND.format(2, ONE_HAND)
    assert refusal.steer == 'dibs claim --task A1'


def test_sync_report_counts_and_warns():
    """§8: the manual sync says what it applied, and flags the rows
    where the board won over a hand-cleared [ ] (D4)."""
    plan = planfile.SyncPlan(
        new=planfile.parse_plan('- [ ] Fresh task\n'),
        vanished=('A9',),
        checked=('A8',),
        reordered=(('A1', 4),),
        reparented=(('A1', 3),),
        refreshed=(('A2', 'new body', 'Parser'),),
        regressed=('A7',),
    )

    lines = views.format_sync(plan)

    assert lines[0] == (
        'sync: 1 new, 1 orphaned, 1 imported [x], 1 reordered, '
        + '1 reparented, 1 refreshed, 1 board wins, line re-annotated'
    )
    assert 'new: Fresh task' in lines
    assert views.SYNC_ROW.format(views.OVERRIDDEN, 'A7') in lines
    assert views.format_sync(
        planfile.SyncPlan((), (), (), (), (), (), ()),
    ) == (views.SYNC_HEADER.format(views.NOTHING),)


def test_outcome_lines_for_done_drop_and_note():
    """D14: one line per confirmation, and a note asked for an unknown
    name still went out - as a broadcast - and says so (D10)."""
    finished = replace(
        BASE, status=Status.DONE, owner=OTTER, done_note='anchored it',
    )
    directed = event(
        EventKind.NOTE, text='renamed util.load', to_agent=ELEPHANT,
    )
    astray = event(EventKind.NOTE, text='renamed util.load')

    assert views.format_outcome('done', task=finished) == (
        'done A1: Fix the tokenizer',
    )
    assert views.format_outcome('drop', task=BASE) == (
        'dropped A1: Fix the tokenizer',
    )
    assert views.format_outcome(
        'note', event=directed, to_name='happy-elephant',
    ) == ('noted to happy-elephant: "renamed util.load"',)
    assert views.format_outcome(
        'note', event=astray, to_name='ghost-lemur',
    ) == (
        'noted: "renamed util.load"',
        views.UNKNOWN_NAME.format('ghost-lemur'),
    )
