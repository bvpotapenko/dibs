"""Property/metamorphic tier for the pure plan functions (§11).

Use seeded stdlib random document generation (a local generator
helper, seeds 0..N) - dev deps stay at flake8/WPS/ruff/pytest. If
hypothesis is ever adopted, these become @given strategies; amend
pyproject dev extras first.

The seeded generator draws on conftest.pick rather than the random
module: ruff's bandit bundle flags random for non-crypto use (S311) and
the tests per-file-ignores cover only S101/D.
"""

from dataclasses import replace

from conftest import AUTHOR, pick

from dibs import planfile
from dibs.records import Status, Task

SEEDS = 100
DOC_LINES = 40

LINE_POOL = (
    'Plain prose line {0}.',
    '# Heading {0}',
    '## Section {0}',
    '- plain bullet {0}',
    '1. numbered line {0}',
    '```',
    '    fenced-looking code {0}',
    '\tTabbed prose {0}',
    'Unicode: naïve café 日本語 {0}',
    'Prose with trailing spaces {0}   ',
    '- [ ]   Padded task {0}   ',
    '',
    '   ',
    '> quoted text {0}',
    '- [ ] Task {0}',
    '  - [ ] Child {0}',
    '    Body prose for {0}',
    '- [x] Done task {0}',
    '- [~ brave-otter] Doing task {0}',
    # Ordinary markdown the §8 tokens exclude: never a task, never
    # rewritten (F1 / D5).
    '- [link text {0}](https://example.invalid/{0})',
    '- [-] not a task {0}',
)

TASK_ID = 'T{0}'  # test-local ids; planfile never mints them
NEW_ID = 'N{0}'  # ids the applier mints for SyncPlan.new, keyed by line

STATUSES = (Status.TODO, Status.DOING, Status.DONE)
EMPTY_SYNC = planfile.SyncPlan((), (), (), (), (), (), ())

INSERTED = '- [ ] Inserted parent line'  # unique against LINE_POOL titles
IMPORT_NOTE = 'checked by the plan author'
NEST = '  {0}'  # one re-indent step, enough to become a child (D22)
PAIR = 2  # the two checkbox lines swap_lines exchanges
REWORD = '    Reworded briefing for {0}'  # a body edit, nothing more
RENAME = '# Renamed heading {0}'  # a section edit, nothing more


def imported(entry):
    """Status a sync applier gives a freshly parsed line (§8)."""
    if entry.checkbox == planfile.DONE_STATE:
        return Status.DONE
    return Status.TODO


def generate_document(seed):
    """One pseudo-random plan-like document for this seed."""
    return '\n'.join(
        LINE_POOL[pick(seed, index, len(LINE_POOL))].format(index)
        for index in range(DOC_LINES)
    )


def tasks_for(text, seed=None):
    """Task rows for a document; seed None means sync-applier statuses."""
    by_line = {}
    rows = []
    for index, entry in enumerate(planfile.parse_plan(text)):
        by_line[entry.line_no] = TASK_ID.format(index)
        status = (
            imported(entry) if seed is None
            else STATUSES[pick(seed, index, len(STATUSES))]
        )
        rows.append(Task(
            task_id=by_line[entry.line_no],
            parent_id=by_line.get(entry.parent_line),
            seq=entry.line_no,
            section=entry.section,
            title=entry.title,
            body=entry.body,
            text_hash=planfile.title_hash(entry.title),
            status=status,
            owner=None if status == Status.TODO else 'brave-otter-1111',
            claimed_at=None,
            done_at=None,
            done_note='did it' if status == Status.DONE else None,
        ))
    return tuple(rows)


def as_row(entry, task_id):
    """A freshly created row for one new plan line (parent resolved later)."""
    return Task(
        task_id=task_id,
        parent_id=None,
        seq=entry.line_no,
        section=entry.section,
        title=entry.title,
        body=entry.body,
        text_hash=planfile.title_hash(entry.title),
        status=imported(entry),
        owner=AUTHOR if imported(entry) == Status.DONE else None,
        claimed_at=None,
        done_at=None,
        done_note=IMPORT_NOTE if imported(entry) == Status.DONE else None,
    )


def applied(plan, rows):
    """The rows a sync applier leaves behind for this SyncPlan (§8).

    Stands in for step 8's real applier and does what it must do, in
    one pass: create the new lines, orphan the vanished ones, import
    hand [x], update seq, then - because seq IS the line number once
    reordering is applied - resolve every parent LINE to the id now
    sitting on that line (ParentUpdate).
    """
    by_id = {row.task_id: row for row in rows}
    for gone in plan.vanished:
        by_id[gone] = replace(by_id[gone], status=Status.ORPHANED)
    for hand_done in plan.checked:
        by_id[hand_done] = replace(
            by_id[hand_done],
            status=Status.DONE, owner=AUTHOR, done_note=IMPORT_NOTE,
        )
    for entry in plan.new:
        by_id[NEW_ID.format(entry.line_no)] = as_row(
            entry, NEW_ID.format(entry.line_no),
        )
    for task_id, seq in plan.reordered:
        by_id[task_id] = replace(by_id[task_id], seq=seq)
    for task_id, body, section in plan.refreshed:
        by_id[task_id] = replace(
            by_id[task_id], body=body, section=section,
        )
    at_line = {
        row.seq: row.task_id for row in by_id.values()
        if row.status != Status.ORPHANED
    }
    moves = plan.reparented + tuple(
        (NEW_ID.format(fresh.line_no), fresh.parent_line)
        for fresh in plan.new
    )
    for moved, parent_line in moves:
        by_id[moved] = replace(
            by_id[moved], parent_id=at_line.get(parent_line),
        )
    return tuple(by_id.values())


def join(lines):
    """The document these lines make up."""
    return '\n'.join(lines)


def spliced(lines, index, replacement):
    """Lines with the one at index replaced by these lines."""
    tail = lines[index + 1:]
    return lines[:index] + list(replacement) + tail


def checkbox_spots(lines):
    """Indexes of the lines the §8 recognition table calls tasks."""
    return [
        index for index, line in enumerate(lines)
        if planfile.CHECKBOX_RE.match(line)
    ]


def unchanged(text):
    """The document as written - the no-edit control."""
    return text


def insert_parent(text):
    """Put a brand-new top-level checkbox above the first nested one."""
    lines = text.split('\n')
    for index in checkbox_spots(lines):
        if lines[index].startswith(' '):
            return join(spliced(lines, index, (INSERTED, lines[index])))
    return text


def reindent_line(text):
    """Push a top-level checkbox under the checkbox above it."""
    lines = text.split('\n')
    for index in checkbox_spots(lines)[1:]:
        if not lines[index].startswith(' '):
            nested = NEST.format(lines[index])
            return join(spliced(lines, index, (nested,)))
    return text


def delete_line(text):
    """Remove the first checkbox line, children and all left behind."""
    spots = checkbox_spots(text.split('\n'))
    if spots:
        return join(spliced(text.split('\n'), spots[0], ()))
    return text


def reword_body(text):
    """Replace the line under the first checkbox with fresh prose."""
    lines = text.split('\n')
    for index in checkbox_spots(lines):
        below = lines[index + 1:index + 2]
        if below and not checkbox_spots(below):
            return join(spliced(
                lines, index + 1, (REWORD.format(index),),
            ))
    return text


def rename_heading(text):
    """Rename the first heading; every task under it changes section."""
    lines = text.split('\n')
    for index, line in enumerate(lines):
        if line.startswith('#'):
            return join(spliced(lines, index, (RENAME.format(index),)))
    return text


def swap_lines(text):
    """Swap the first two checkbox lines (D7 reprioritizing by hand)."""
    lines = text.split('\n')
    spots = checkbox_spots(lines)[:PAIR]
    if len(spots) < PAIR:
        return text
    first, second = spots
    swapped = spliced(lines, first, (lines[second],))
    return join(spliced(swapped, second, (lines[first],)))


MUTATIONS = (
    unchanged,
    insert_parent,
    reindent_line,
    delete_line,
    swap_lines,
    reword_body,
    rename_heading,
)


def shape(parsed):
    """Everything a parsed item is, except its checkbox state."""
    return tuple(
        (
            entry.line_no,
            entry.parent_line,
            entry.title,
            entry.section,
            entry.body,
        )
        for entry in parsed
    )


def test_annotate_preserves_nongrammar_bytes():
    """I4 crown jewel: across generated documents (prose, fences,
    weird indentation, unicode), annotate_lines changes no byte outside
    its own grammar lines. Generator + seeds 0-99."""
    rewritten = 0
    for seed in range(SEEDS):
        text = generate_document(seed)
        before = text.split('\n')
        after = planfile.annotate_lines(text, tasks_for(text, seed)).split('\n')
        assert len(before) == len(after)
        for old, new in zip(before, after, strict=True):
            assert old == new or planfile.CHECKBOX_RE.match(old)
            rewritten += old != new

    assert rewritten


def test_annotate_preserves_line_terminators():
    """I4: with rows already in the file's own state, annotation is a
    byte-for-byte no-op - CRLF terminators, trailing whitespace and an
    unterminated final line included. Generator + seeds 0-99."""
    for seed in range(SEEDS):
        rows = tasks_for(generate_document(seed), seed)
        # Annotate once so every grammar line already shows its row's
        # state, then hand the file back in CRLF.
        canonical = planfile.annotate_lines(
            generate_document(seed), rows,
        ).replace('\n', '\r\n')

        assert planfile.annotate_lines(canonical, rows) == canonical


def test_annotate_then_parse_is_stable():
    """Metamorphic: parse(annotate(text, tasks)) finds the same items
    (titles, parents, sections) as parse(text) - only checkbox state
    tokens differ."""
    for seed in range(SEEDS):
        text = generate_document(seed)
        after = planfile.annotate_lines(text, tasks_for(text, seed))

        assert shape(planfile.parse_plan(after)) == shape(
            planfile.parse_plan(text),
        )


def test_refreshed_fires_exactly_on_text_edits():
    """§8 (Rev 9): body and section are text truth flowing md -> db.
    An untouched document refreshes nothing; rewording a body or
    renaming a heading refreshes rows and touches no other field - no
    task is created, orphaned, reordered, imported or regressed by an
    edit that only changed prose (D4, I6). The exact payload is pinned
    by test_planfile, and applying it is covered by the idempotence
    case below, which now mutates both ways too."""
    landed = 0
    for seed in range(SEEDS):
        text = generate_document(seed)
        rows = tasks_for(text)

        assert not planfile.compute_sync(
            planfile.parse_plan(text), rows,
        ).refreshed

        for edit in (reword_body, rename_heading):
            once = planfile.compute_sync(
                planfile.parse_plan(edit(text)), rows,
            )
            landed += len(once.refreshed)

            assert (once.new, once.vanished) == ((), ())
            assert (once.reordered, once.reparented) == ((), ())
            assert (once.checked, once.regressed) == ((), ())

    assert landed


def test_compute_sync_is_idempotent():
    """§8: applying a computed SyncPlan to the rows, then recomputing
    against the same text, yields an empty SyncPlan - across the seeded
    documents and across hand edits of them (a new parent above an
    existing child, a re-indent, a deletion, a swap)."""
    for seed in range(SEEDS):
        text = generate_document(seed)
        parsed = planfile.parse_plan(text)
        rows = tasks_for(text)

        assert planfile.compute_sync(parsed, ()).new == parsed
        assert planfile.compute_sync(parsed, rows) == EMPTY_SYNC
        for mutate in MUTATIONS:
            edited = planfile.parse_plan(mutate(text))
            once = planfile.compute_sync(edited, rows)

            assert planfile.compute_sync(
                edited, applied(once, rows),
            ) == EMPTY_SYNC
