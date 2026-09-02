"""Unit: the SSoT §8 recognition table, annotation grammar, sync diff.

Pure functions only - no fixtures beyond plan_text (C4 makes this tier
trivial to test; keep it that way).
"""

from dataclasses import replace

from dibs import planfile
from dibs.records import Status, Task

NESTED_TEXT = """- [ ] Top deliverable
  - [ ] Middle piece
    - [ ] Leaf unit
"""

FENCE_TEXT = """Prose before the fence.

```
- [ ] Lookalike inside a fence
```

- [ ] Real task after the fence
"""

NO_HEADING_TEXT = """- [ ] First chore
- [ ] Second chore
"""

SWAPPED_TEXT = """- [ ] Second chore
- [ ] First chore
"""

BOUNDARY_TEXT = """  - [ ] Indented task
  Prose at the task's own indent
    Prose indented past it
"""

DUPLICATE_TEXT = """- [ ] Same title
- [x] Same title
"""

# Same title twice, both open: annotation must tell the two rows apart
# by document order, the way §8 sync does.
DUPLICATE_TWICE_TEXT = """- [ ] Same title
- [ ] Same title
"""

# Every line here is ordinary markdown that §8 does not recognize: a
# link bullet, an unlisted state token, uppercase X, a two-space box,
# and a missing separator space. All are prose (D5).
NOT_TASKS_TEXT = """- [Docs](https://example.invalid/x)
- [-] dash is not a state
- [X] uppercase is not a state
- [  ] two spaces
- [ ]NoSpace
"""

# Real tasks whose titles are exactly what NOT_TASKS_TEXT would parse
# to if the recognition pattern were loose: the annotation decoys.
LOOKALIKE_TITLES_TEXT = """- [ ] (https://example.invalid/x)
- [ ] dash is not a state
- [ ] uppercase is not a state
- [ ] two spaces
- [ ] NoSpace
"""

# A CRLF document: the CR belongs to the file, not to any title.
CRLF_TEXT = '- [ ] Alpha\r\nprose line\r\n  indented body\r\n'

TASK_ID = 'T{0}'  # test-local ids; planfile never mints them

DONE_TEXT = '- [x] Rename Lexer to Tokenizer  ✓ brave-otter: renamed\n'

PLAN_TITLES = (
    'Fix off-by-one in the tokenizer',
    'Ship the tokenizer regression suite',
    'Cover multi-byte input',
    'Cover the empty file',
    'Rename Lexer to Tokenizer',
    'Update the README quickstart',
)

BASE_TASK = Task(
    task_id='T0',
    parent_id=None,
    seq=0,
    section='Parser',
    title='Ship it',
    body='',
    text_hash=planfile.title_hash('Ship it'),
    status=Status.TODO,
    owner=None,
    claimed_at=None,
    done_at=None,
    done_note=None,
)


def titles(parsed):
    """Titles of parsed parsed, in document order."""
    return tuple(entry.title for entry in parsed)


def titled(parsed, title):
    """The one parsed item carrying this title."""
    return next(entry for entry in parsed if entry.title == title)


def seed_tasks(parsed):
    """Task rows built from parsed the way sync's applier will."""
    by_line = {}
    rows = []
    for index, entry in enumerate(parsed):
        done = entry.checkbox == planfile.DONE_STATE
        by_line[entry.line_no] = TASK_ID.format(index)
        rows.append(Task(
            task_id=by_line[entry.line_no],
            parent_id=by_line.get(entry.parent_line),
            seq=entry.line_no,
            section=entry.section,
            title=entry.title,
            body=entry.body,
            text_hash=planfile.title_hash(entry.title),
            status=Status.DONE if done else Status.TODO,
            owner='human' if done else None,
            claimed_at=None,
            done_at=None,
            done_note='checked in plan' if done else None,
        ))
    return tuple(rows)


def retitled(parsed, old, new):
    """Copy of parsed with one title replaced."""
    return tuple(
        replace(entry, title=new) if entry.title == old else entry
        for entry in parsed
    )


def reboxed(parsed, title, checkbox):
    """Copy of parsed with one item's checkbox token replaced."""
    return tuple(
        replace(entry, checkbox=checkbox) if entry.title == title else entry
        for entry in parsed
    )


def reparented(parsed, title, parent_line):
    """Copy of parsed with one item's parent_line replaced."""
    return tuple(
        replace(entry, parent_line=parent_line)
        if entry.title == title else entry
        for entry in parsed
    )


def test_parse_recognizes_three_checkbox_forms(plan_text):
    """§8: '- [ ]', '- [x]', '- [~ name]' are tasks; states captured."""
    states = {
        entry.title: entry.checkbox
        for entry in planfile.parse_plan(plan_text)
    }

    assert states['Fix off-by-one in the tokenizer'] == ''
    assert states['Rename Lexer to Tokenizer'] == 'x'
    assert states['Update the README quickstart'] == '~ brave-otter'


def test_parse_attaches_indented_prose_as_body(plan_text):
    """§8: indented non-checkbox lines travel with the task as body."""
    parsed = planfile.parse_plan(plan_text)

    assert titled(parsed, PLAN_TITLES[0]).body == (
        'Repro: token count is 12 for fixtures/one.txt, expected 11.\n'
        + 'Done: count matches and the regression fixture passes.'
    )
    assert titled(parsed, PLAN_TITLES[3]).body == ''


def test_parse_nested_checkbox_is_child(plan_text):
    """D22: an indented checkbox's parent_line is the nearest
    less-indented checkbox above it, not just any previous line."""
    parsed = planfile.parse_plan(plan_text)
    parent = titled(parsed, PLAN_TITLES[1])

    assert parent.parent_line is None
    assert titled(parsed, PLAN_TITLES[2]).parent_line == parent.line_no
    assert titled(parsed, PLAN_TITLES[3]).parent_line == parent.line_no


def test_parse_nesting_depth_is_free():
    """D22: three-plus levels parse; each child gates only its parent."""
    parsed = planfile.parse_plan(NESTED_TEXT)

    assert titles(parsed) == ('Top deliverable', 'Middle piece', 'Leaf unit')
    assert tuple(entry.parent_line for entry in parsed) == (
        None, parsed[0].line_no, parsed[1].line_no,
    )


def test_parse_deep_prose_stays_body(plan_text):
    """D22/§11: prose indented deeper than a child is body, not a task."""
    parsed = planfile.parse_plan(plan_text)

    assert titled(parsed, PLAN_TITLES[2]).body == (
        'Body of a child task: paths, symptom, criterion.'
    )
    assert titles(parsed) == PLAN_TITLES
    # Body starts one column past the checkbox, never at its own indent.
    edge = planfile.parse_plan(BOUNDARY_TEXT)
    assert titles(edge) == ('Indented task',)
    assert edge[0].body == 'Prose indented past it'


def test_parse_sections_letter_in_order(plan_text):
    """§8: nearest heading is the section; lettered A, B in doc order."""
    parsed = planfile.parse_plan(plan_text)

    assert titled(parsed, PLAN_TITLES[0]).section == 'Parser'
    assert titled(parsed, PLAN_TITLES[5]).section == 'Docs'
    assert tuple(dict.fromkeys(entry.section for entry in parsed)) == (
        'Parser', 'Docs',
    )


def test_parse_no_headings_single_section():
    """§8: a plan with no headings gets one implicit section."""
    parsed = planfile.parse_plan(NO_HEADING_TEXT)

    assert titles(parsed) == ('First chore', 'Second chore')
    assert {entry.section for entry in parsed} == {''}


def test_parse_ignores_plain_bullets_and_prose(plan_text):
    """§8: plain bullets, numbered lines, prose are never tasks."""
    assert titles(planfile.parse_plan(plan_text)) == PLAN_TITLES


def test_parse_fence_lookalike_policy():
    """Open point: a literal '- [ ]' inside a code fence matches the §8
    line rule. Decide (probably: line rule wins, documented), pin the
    behavior here, and note the decision in SSoT §8 if it deviates.

    Decision: the §8 line rule wins. §8 defines recognition per line and
    forbids inventing structure from prose; fence tracking would be such
    an invention, and D21 verify makes the consequence visible pre-init.
    """
    assert titles(planfile.parse_plan(FENCE_TEXT)) == (
        'Lookalike inside a fence',
        'Real task after the fence',
    )


def test_parse_rejects_lookalike_bracket_lines():
    """§8: only ' ', 'x' and '~ <name>' are checkbox tokens; every
    other bracket line is prose, so it is neither a task nor rewritten
    (D5, I4)."""
    decoys = seed_tasks(planfile.parse_plan(LOOKALIKE_TITLES_TEXT))

    assert not planfile.parse_plan(NOT_TASKS_TEXT)
    # Even with rows whose titles match the lookalike text, byte-exact.
    assert planfile.annotate_lines(NOT_TASKS_TEXT, decoys) == NOT_TASKS_TEXT


def test_parse_bare_checkbox_still_recognized():
    """§8: '- [ ]' with no title is still a task, with an empty one."""
    parsed = planfile.parse_plan('- [ ]\n')

    assert titles(parsed) == ('',)


def test_annotate_rewrites_only_grammar_lines(plan_text):
    """I4: every byte outside annotation-grammar lines is preserved."""
    tasks = seed_tasks(planfile.parse_plan(plan_text))
    claimed = replace(tasks[0], status=Status.DOING, owner='brave-otter-1111')

    after = planfile.annotate_lines(plan_text, (claimed, *tasks[1:]))

    before_lines = plan_text.split('\n')
    after_lines = after.split('\n')
    assert len(before_lines) == len(after_lines)
    assert before_lines != after_lines
    for old, new in zip(before_lines, after_lines, strict=True):
        assert old == new or planfile.CHECKBOX_RE.match(old)


def test_annotate_todo_doing_done_forms():
    """§8 grammar: '- [ ] t', '- [~ name] t', '- [x] t  ✓ name: note'."""
    text = '- [ ] Ship it\n'
    doing = replace(BASE_TASK, status=Status.DOING, owner='brave-otter-1111')
    done = replace(
        BASE_TASK,
        status=Status.DONE,
        owner='happy-elephant-2222',
        done_note='shipped in r8',
    )

    assert planfile.annotate_lines(text, (BASE_TASK,)) == text
    assert planfile.annotate_lines(text, (doing,)) == (
        '- [~ brave-otter] Ship it\n'
    )
    assert planfile.annotate_lines(text, (done,)) == (
        '- [x] Ship it  ✓ happy-elephant: shipped in r8\n'
    )


def test_annotate_keeps_crlf_terminators():
    """I4: a rewritten line keeps the terminator the file uses, so a
    CRLF plan never comes back with mixed line endings."""
    tasks = seed_tasks(planfile.parse_plan(CRLF_TEXT))
    working = replace(tasks[0], status=Status.DOING, owner='brave-otter-1111')

    assert planfile.annotate_lines(CRLF_TEXT, tasks) == CRLF_TEXT
    assert planfile.annotate_lines(CRLF_TEXT, (working,)) == (
        '- [~ brave-otter] Alpha\r\nprose line\r\n  indented body\r\n'
    )


def test_annotate_renders_the_title_from_the_line():
    """D4: plan.md is authoritative for text. A hash-equal title the
    human re-cased or re-spaced survives annotation verbatim; only the
    state token and the done suffix come from the DB."""
    tasks = seed_tasks(planfile.parse_plan('- [ ] fix the parser\n'))
    edited = '- [ ] Fix The Parser\n'
    working = replace(tasks[0], status=Status.DOING, owner='brave-otter-1111')

    assert planfile.annotate_lines(edited, tasks) == edited
    assert planfile.annotate_lines(edited, (working,)) == (
        '- [~ brave-otter] Fix The Parser\n'
    )


def test_annotate_keeps_a_mark_inside_the_title():
    """I4: the done suffix is '  ✓ <name>: <note>', matched whole - a
    title that merely contains the mark is not a suffix and survives
    parse and annotation untouched."""
    text = '- [ ] has ✓ mark in title\n'
    parsed = planfile.parse_plan(text)

    assert titles(parsed) == ('has ✓ mark in title',)
    assert planfile.annotate_lines(text, seed_tasks(parsed)) == text


def test_annotate_pairs_duplicate_titles_in_order():
    """§8: duplicates are matched by order, for annotation as much as
    for sync - only the line whose row is done carries the ✓ suffix,
    so the done-notes stay a usable review checklist (D4)."""
    tasks = seed_tasks(planfile.parse_plan(DUPLICATE_TWICE_TEXT))
    finished = replace(
        tasks[0],
        status=Status.DONE, owner='brave-otter-1111', done_note='shipped',
    )

    assert planfile.annotate_lines(
        DUPLICATE_TWICE_TEXT, (finished, tasks[1]),
    ) == '- [x] Same title  ✓ brave-otter: shipped\n- [ ] Same title\n'
    assert planfile.annotate_lines(
        DUPLICATE_TWICE_TEXT, (tasks[0], replace(finished, task_id='T1')),
    ) == '- [ ] Same title\n- [x] Same title  ✓ brave-otter: shipped\n'


def test_annotate_note_stays_one_line():
    """§8 grammar is one line per task: a done-note carrying newlines
    is collapsed on the way into the file, so annotation never injects
    a non-grammar line and stays idempotent (I4)."""
    wordy = replace(
        BASE_TASK,
        status=Status.DONE,
        owner='happy-elephant-2222',
        done_note='shipped in r8\nand tagged\n\ttwice',
    )

    once = planfile.annotate_lines('- [ ] Ship it\n', (wordy,))

    assert once == (
        '- [x] Ship it  ✓ happy-elephant: shipped in r8 and tagged twice\n'
    )
    assert planfile.annotate_lines(once, (wordy,)) == once


def test_annotate_is_idempotent(plan_text):
    """I4: annotating an already-annotated text changes nothing."""
    tasks = seed_tasks(planfile.parse_plan(plan_text))
    claimed = replace(tasks[0], status=Status.DOING, owner='brave-otter-1111')

    once = planfile.annotate_lines(plan_text, (claimed, *tasks[1:]))

    assert planfile.annotate_lines(once, (claimed, *tasks[1:])) == once


def test_hash_normalizes_case_and_spaces():
    """§8: title_hash('A  B') == title_hash('a b'); stable otherwise."""
    assert planfile.title_hash('A  B') == planfile.title_hash('a b')
    assert planfile.title_hash(' Trim  me ') == planfile.title_hash('trim me')
    assert planfile.title_hash('A B') != planfile.title_hash('A C')


def test_hash_excludes_done_annotation():
    """§8: the '✓ name: note' suffix never feeds the title hash."""
    parsed = planfile.parse_plan(DONE_TEXT)

    assert titles(parsed) == ('Rename Lexer to Tokenizer',)
    assert planfile.title_hash(parsed[0].title) == planfile.title_hash(
        'Rename Lexer to Tokenizer',
    )


def test_sync_new_line_becomes_task(plan_text):
    """§8 sync: a new checkbox line lands in SyncPlan.new."""
    parsed = planfile.parse_plan(plan_text)

    diff = planfile.compute_sync(parsed, seed_tasks(parsed[:-1]))

    assert titles(diff.new) == (PLAN_TITLES[5],)
    assert not diff.vanished
    assert not diff.reordered


def test_sync_vanished_line_orphaned(plan_text):
    """§8 sync + I5: a removed line is orphaned, never deleted."""
    parsed = planfile.parse_plan(plan_text)
    kept = tuple(
        entry for entry in parsed if entry.title != PLAN_TITLES[4]
    )

    diff = planfile.compute_sync(kept, seed_tasks(parsed))

    assert diff.vanished == ('T4',)
    assert not diff.new


def test_sync_hand_checked_imports_done(plan_text):
    """§8 sync: [x] over todo lands in SyncPlan.checked (owner human)."""
    parsed = planfile.parse_plan(plan_text)
    all_todo = tuple(
        replace(task, status=Status.TODO, owner=None, done_note=None)
        for task in seed_tasks(parsed)
    )

    diff = planfile.compute_sync(parsed, all_todo)

    assert diff.checked == ('T4',)
    assert not diff.regressed


def test_sync_reorder_updates_seq_only():
    """§8 sync + I5/D7: reordering changes seq; IDs stay untouched."""
    tasks = seed_tasks(planfile.parse_plan(NO_HEADING_TEXT))

    diff = planfile.compute_sync(planfile.parse_plan(SWAPPED_TEXT), tasks)

    assert tuple(task.seq for task in tasks) == (1, 2)
    assert diff.reordered == (('T1', 1), ('T0', 2))
    assert not diff.new
    assert not diff.vanished
    assert not diff.reparented


def test_sync_reindent_updates_parent(plan_text):
    """§8 sync + D22: re-indenting under another checkbox moves the
    parent (named by its LINE, D4) and back to None at top level; ID
    untouched."""
    parsed = planfile.parse_plan(plan_text)
    tasks = seed_tasks(parsed)
    promoted = reparented(parsed, PLAN_TITLES[3], None)
    demoted = reparented(parsed, PLAN_TITLES[4], parsed[0].line_no)

    assert planfile.compute_sync(promoted, tasks).reparented == (('T3', None),)
    assert planfile.compute_sync(demoted, tasks).reparented == (
        ('T4', parsed[0].line_no),
    )


def test_sync_reparents_under_a_brand_new_parent():
    """§8 + D22: a new checkbox line inserted above an existing child
    becomes its parent in the SAME SyncPlan - the parent has no id yet,
    so reparented names its line and the applier resolves it."""
    tasks = seed_tasks(planfile.parse_plan('- [ ] child\n'))
    grown = planfile.parse_plan('- [ ] new parent\n  - [ ] child\n')

    diff = planfile.compute_sync(grown, tasks)

    assert titles(diff.new) == ('new parent',)
    assert diff.reordered == (('T0', 2),)
    assert diff.reparented == (('T0', 1),)


def test_sync_vanished_parent_promotes_its_child():
    """§8 + D22: when a parent line leaves the plan its child follows
    the text back to top level rather than pointing at an orphan."""
    parsed = planfile.parse_plan('- [ ] parent\n  - [ ] child\n')
    tasks = seed_tasks(parsed)

    diff = planfile.compute_sync(planfile.parse_plan('- [ ] child\n'), tasks)

    assert diff.vanished == ('T0',)
    assert diff.reparented == (('T1', None),)


def test_sync_regressed_checkbox_flagged(plan_text):
    """§8 sync: [ ] over doing/done lands in regressed; DB wins."""
    parsed = planfile.parse_plan(plan_text)
    tasks = seed_tasks(parsed)
    working = replace(tasks[0], status=Status.DOING, owner='brave-otter-1111')
    unchecked = reboxed(parsed, PLAN_TITLES[4], '')

    diff = planfile.compute_sync(parsed, (working, *tasks[1:]))

    assert diff.regressed == ('T0',)
    assert not diff.checked
    # DB wins for a finished task too, not only a claimed one (§8).
    assert planfile.compute_sync(unchecked, tasks).regressed == ('T4',)


def test_sync_retitle_is_vanish_plus_new(plan_text):
    """§8 sync: an edited title orphans the old task and adds a new
    one; both flagged (accepted v1 limitation)."""
    parsed = planfile.parse_plan(plan_text)
    edited = retitled(parsed, PLAN_TITLES[0], 'Fix the off-by-two')

    diff = planfile.compute_sync(edited, seed_tasks(parsed))

    assert titles(diff.new) == ('Fix the off-by-two',)
    assert diff.vanished == ('T0',)


def test_sync_duplicate_titles_match_in_order():
    """§8 sync: identical titles pair up by document order."""
    parsed = planfile.parse_plan(DUPLICATE_TEXT)
    all_todo = tuple(
        replace(task, status=Status.TODO, owner=None, done_note=None)
        for task in seed_tasks(parsed)
    )

    diff = planfile.compute_sync(parsed, all_todo)

    assert diff.checked == ('T1',)
    assert not diff.new
    assert not diff.vanished
