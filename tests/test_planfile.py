"""Unit: the SSoT §8 recognition table, annotation grammar, sync diff.

Pure functions only - no fixtures beyond plan_text (C4 makes this tier
trivial to test; keep it that way).
"""

import dataclasses
import re
from types import MappingProxyType

from dibs.planfile import annotate_lines, compute_sync, parse_plan, title_hash
from dibs.records import Status
from tests.boards import ELEPHANT, OTTER, task_rows

EMPTY_SYNC = MappingProxyType({
    'new': (), 'vanished': (), 'checked': (),
    'reordered': (), 'reparented': (), 'regressed': (),
})
TITLES = (
    'Fix off-by-one in the tokenizer',
    'Ship the tokenizer regression suite',
    'Cover multi-byte input',
    'Cover the empty file',
    'Rename Lexer to Tokenizer',
    'Update the README quickstart',
)
# Checkbox lookalikes outside the §8 state grammar: prose, not tasks.
NON_GRAMMAR = (
    '- [-] cancelled\n',  # a common Markdown 'cancelled' marker
    '- [] blank\n',
    '- [wip] custom state\n',
    '- [ x ] padded\n',
    '- [~] no name\n',
    '- [ ]no space\n',
    '- [ ]\ttab\n',
    '- [ ]\n',
)
# Fixture line numbers (1-based) of the six checkbox lines in plan_text.
FIX = 7
SHIP = 10
MULTI = 12
EMPTY = 14
RENAME = 15
README = 24


def doing(task, agent=OTTER):
    """Copy of a task row as claim leaves it."""
    return dataclasses.replace(
        task, status=Status.DOING, owner=agent.agent_id, claimed_at=1,
    )


def done(task, note, agent=ELEPHANT):
    """Copy of a task row as finish leaves it."""
    return dataclasses.replace(
        task, status=Status.DONE, owner=agent.agent_id, done_note=note,
    )


def only(plan, **expected):
    """Assert a SyncPlan carries exactly the expected non-empty facts."""
    found = {
        field.name: getattr(plan, field.name)
        for field in dataclasses.fields(plan)
    }
    assert found == {**EMPTY_SYNC, **expected}


def test_parse_recognizes_three_checkbox_forms(plan_text):
    """§8: '- [ ]', '- [x]', '- [~ name]' are tasks; states captured."""
    found = parse_plan(plan_text)
    assert tuple(head.checkbox for head in found) == (
        '', '', '', '', 'x', '~ brave-otter',
    )
    assert tuple(head.title for head in found) == TITLES
    assert tuple(head.line_no for head in found) == (
        FIX, SHIP, MULTI, EMPTY, RENAME, README,
    )


def test_parse_attaches_indented_prose_as_body(plan_text):
    """§8: indented non-checkbox lines travel with the task as body."""
    found = parse_plan(plan_text)
    assert found[0].body == (
        'Repro: token count is 12 for fixtures/one.txt, expected 11.\n'
        'Done: count matches and the regression fixture passes.'
    )
    assert found[1].body == 'Cover the cases below once both land.'
    assert found[3].body == ''  # bodiless child (a verify-warning case)
    assert found[5].body == 'Body line for a doing task.'


def test_parse_nested_checkbox_is_child(plan_text):
    """D22: an indented checkbox's parent_line is the nearest
    less-indented checkbox above it, not just any previous line."""
    found = parse_plan(plan_text)
    assert tuple(head.parent_line for head in found) == (
        None, None, SHIP, SHIP, None, None,
    )


def test_parse_nesting_depth_is_free():
    """D22: three-plus levels parse; each child gates only its parent."""
    text = (
        '- [ ] root\n'
        '  - [ ] mid\n'
        '    - [ ] leaf\n'
        '      - [ ] leaflet\n'
        '  - [ ] mid two\n'
        '- [ ] root two\n'
    )
    found = parse_plan(text)
    assert [head.title for head in found] == [
        'root', 'mid', 'leaf', 'leaflet', 'mid two', 'root two',
    ]
    assert [head.parent_line for head in found] == [None, 1, 2, 3, 1, None]


def test_parse_deep_prose_stays_body(plan_text):
    """D22/§11: prose indented deeper than a child is body, not a task."""
    found = parse_plan(plan_text)
    assert tuple(head.title for head in found) == TITLES  # line 13 is no task
    assert found[2].body == 'Body of a child task: paths, symptom, criterion.'


def test_parse_sections_letter_in_order(plan_text):
    """§8: nearest heading is the section; lettered A, B in doc order."""
    found = parse_plan(plan_text)
    assert [head.section for head in found] == [
        'Parser', 'Parser', 'Parser', 'Parser', 'Parser', 'Docs',
    ]
    # Lettering follows first appearance among tasks: the empty title
    # heading '# Demo corrections' holds no task and takes no letter.
    ordered = tuple(dict.fromkeys(head.section for head in found))
    assert ordered == ('Parser', 'Docs')


def test_parse_no_headings_single_section():
    """§8: a plan with no headings gets one implicit section."""
    found = parse_plan('- [ ] one\n- [ ] two\n  - [ ] three\n')
    assert {head.section for head in found} == {''}
    assert [head.title for head in found] == ['one', 'two', 'three']


def test_parse_ignores_plain_bullets_and_prose(plan_text):
    """§8: plain bullets, numbered lines, prose are never tasks."""
    titles = [head.title for head in parse_plan(plan_text)]
    assert tuple(titles) == TITLES
    assert not any('keep this line' in title for title in titles)
    assert not any('numbered' in title for title in titles)
    assert not any('Prose preamble' in title for title in titles)
    assert not any('Demo corrections' in title for title in titles)


def test_parse_fence_lookalike_policy():
    """Decision: the §8 line rule wins even inside code fences.

    A literal '- [ ]' line inside ``` fences IS a task. Fence tracking
    would make the parser smarter than the §8 rules (and annotation
    would need the same tracking to honor I4); authors keep such lines
    out of fences or accept the task. Pinned here; SSoT §8 unchanged.
    """
    text = '- [ ] real\n```text\n- [ ] inside fence\n```\n'
    found = parse_plan(text)
    assert [head.title for head in found] == ['real', 'inside fence']
    assert [head.parent_line for head in found] == [None, None]


def test_parse_rejects_checkbox_lookalikes():
    """§8/I4: the state token is only ' ', 'x'/'X' or '~ <name>', and
    the space after ']' is required. Every other bracket shape is the
    human's prose: never a task, never rewritten (D5, I4).
    """
    for text in NON_GRAMMAR:
        found = parse_plan(text)
        assert found == (), text
        assert annotate_lines(text, task_rows(found)) == text, text
    upper = parse_plan('- [X] Rename Lexer to Tokenizer\n')
    assert (upper[0].checkbox, upper[0].title) == (
        'x', 'Rename Lexer to Tokenizer',
    )


def test_annotate_rewrites_only_grammar_lines(plan_text):
    """I4: every byte outside annotation-grammar lines is preserved."""
    rows = list(task_rows(parse_plan(plan_text)))
    rows[0] = doing(rows[0])  # A1 claimed by otter
    rows[2] = done(rows[2], 'handled')  # A2.1 done by elephant
    before = plan_text.split('\n')
    after = annotate_lines(plan_text, tuple(rows)).split('\n')
    assert len(after) == len(before)
    changed = {
        line_no
        for line_no, (old, new) in enumerate(
            zip(before, after, strict=True), start=1,
        )
        if old != new
    }
    assert changed == {FIX, MULTI, README}  # all three are grammar lines
    assert after[FIX - 1] == '- [~ brave-otter] Fix off-by-one in the tokenizer'
    assert after[MULTI - 1] == (
        '  - [x] Cover multi-byte input  ✓ happy-elephant: handled'
    )
    # DB wins over the hand-written doing marker (B1 is todo in the DB).
    assert after[README - 1] == '- [ ] Update the README quickstart'


def test_annotate_todo_doing_done_forms():
    """§8 grammar: '- [ ] t', '- [~ name] t', '- [x] t  ✓ name: note'.

    Decision: a done row with no done-note (a hand-checked [x] imported
    by sync) renders as the bare '- [x] t' - the tool adds nothing.
    """
    text = '- [ ] a\n  - [ ] b\n- [ ] c\n- [x] d\n'
    rows = list(task_rows(parse_plan(text)))
    rows[1] = doing(rows[1])
    rows[2] = done(rows[2], 'moved it')
    assert annotate_lines(text, tuple(rows)) == (
        '- [ ] a\n'
        '  - [~ brave-otter] b\n'
        '- [x] c  ✓ happy-elephant: moved it\n'
        '- [x] d\n'
    )


def test_annotate_collapses_multiline_notes():
    """§8/I4: the done form is ONE line, so a note carrying newlines
    or a CRLF renders whitespace-collapsed - a stray prose line the
    human never wrote must never appear. The DB keeps the note
    verbatim; only the plan line is single-line (D4).
    """
    text = '- [ ] a\n- [ ] b\n'
    rows = list(task_rows(parse_plan(text)))
    rows[0] = done(rows[0], 'first\nsecond\r\n   third\t')
    once = annotate_lines(text, tuple(rows))
    assert once == (
        '- [x] a  ✓ happy-elephant: first second third\n'
        '- [ ] b\n'
    )
    assert once.count('\n') == text.count('\n')
    assert annotate_lines(once, tuple(rows)) == once


def test_annotate_is_idempotent(plan_text):
    """I4: annotating an already-annotated text changes nothing."""
    rows = list(task_rows(parse_plan(plan_text)))
    rows[0] = doing(rows[0])
    rows[2] = done(rows[2], 'handled: two files')
    once = annotate_lines(plan_text, tuple(rows))
    assert annotate_lines(once, tuple(rows)) == once
    assert once != plan_text


def test_hash_normalizes_case_and_spaces():
    """§8: title_hash('A  B') == title_hash('a b'); stable otherwise."""
    assert title_hash('A  B') == title_hash('a b')
    assert title_hash(' Fix\tit ') == title_hash('fix it')
    assert title_hash('a b') != title_hash('ab')
    assert title_hash('same') == title_hash('same')
    assert re.fullmatch(r'[0-9a-f]{16}', title_hash('anything'))


def test_hash_excludes_done_annotation():
    """§8: the '✓ name: note' suffix never feeds the title hash - and
    ONLY that exact suffix is excluded. A '✓' the author typed inside a
    title is part of the title (D4: plan.md is text truth) and survives
    annotation byte-for-byte (I4).
    """
    found = parse_plan('- [x] Fix it  ✓ brave-otter: done, two files\n')
    assert found[0].title == 'Fix it'
    assert title_hash(found[0].title) == title_hash('Fix it')
    marked = parse_plan('- [~ brave-otter] Fix it\n')
    assert title_hash(marked[0].title) == title_hash('Fix it')
    authored = '- [ ] verify ✓ marks render\n'
    kept = parse_plan(authored)
    assert kept[0].title == 'verify ✓ marks render'
    assert annotate_lines(authored, task_rows(kept)) == authored


def test_sync_new_line_becomes_task(plan_text):
    """§8 sync: a new checkbox line lands in SyncPlan.new."""
    rows = task_rows(parse_plan(plan_text))
    grown = f'{plan_text}- [ ] Write the changelog\n'
    plan = compute_sync(parse_plan(grown), rows)
    assert [head.title for head in plan.new] == ['Write the changelog']
    assert plan.new[0].section == 'Docs'
    only(plan, new=plan.new)


def test_sync_vanished_line_orphaned(plan_text):
    """§8 sync + I5: a removed line is orphaned, never deleted."""
    rows = task_rows(parse_plan(plan_text))
    lines = plan_text.split('\n')
    lines.pop(EMPTY - 1)  # 'Cover the empty file' (A2.2) leaves the plan
    plan = compute_sync(parse_plan('\n'.join(lines)), rows)
    assert plan.vanished == ('A2.2',)
    assert plan.new == ()
    # Later lines shift up one seq slot; IDs are untouched (I5).
    assert plan.reordered == (('A3', 4), ('B1', 5))


def test_sync_hand_checked_imports_done(plan_text):
    """§8 sync: [x] over todo lands in SyncPlan.checked (owner human)."""
    rows = task_rows(parse_plan(plan_text))
    edited = plan_text.replace('- [ ] Fix off-by-one', '- [x] Fix off-by-one')
    plan = compute_sync(parse_plan(edited), rows)
    only(plan, checked=('A1',))  # A3 is already done: not re-imported


def test_sync_reorder_updates_seq_only(plan_text):
    """§8 sync + I5/D7: reordering changes seq; IDs stay untouched."""
    rows = task_rows(parse_plan(plan_text))
    lines = plan_text.split('\n')
    block = lines[FIX - 1:SHIP - 1]  # the task line plus its two body lines
    before = lines[:FIX - 1]
    rest = before + lines[SHIP - 1:]
    at = RENAME - 1 - len(block)  # right after 'Rename Lexer to Tokenizer'
    moved = rest[:at] + block + rest[at:]
    plan = compute_sync(parse_plan('\n'.join(moved)), rows)
    only(plan, reordered=(
        ('A2', 1), ('A2.1', 2), ('A2.2', 3), ('A1', 4),
    ))


def test_sync_reindent_updates_parent(plan_text):
    """§8 sync + D22: re-indenting under another checkbox moves
    parent_id (and back to None at top level); ID untouched."""
    rows = task_rows(parse_plan(plan_text))
    lines = plan_text.split('\n')
    nested = list(lines)
    rename_line = nested[RENAME - 1]
    nested[RENAME - 1] = f'  {rename_line}'  # Rename under Ship
    plan = compute_sync(parse_plan('\n'.join(nested)), rows)
    only(plan, reparented=(('A3', 'A2'),))
    lifted = list(lines)
    lifted[EMPTY - 1] = lifted[EMPTY - 1].lstrip()  # A2.2 to top level
    plan = compute_sync(parse_plan('\n'.join(lifted)), rows)
    only(plan, reparented=(('A2.2', None),))


def test_sync_regressed_checkbox_flagged(plan_text):
    """§8 sync: [ ] over doing/done lands in regressed; DB wins."""
    rows = list(task_rows(parse_plan(plan_text)))
    rows[0] = doing(rows[0])
    rows[2] = done(rows[2], 'handled')
    plan = compute_sync(parse_plan(plan_text), tuple(rows))
    only(plan, regressed=('A1', 'A2.1'))


def test_sync_retitle_is_vanish_plus_new(plan_text):
    """§8 sync: an edited title orphans the old task and adds a new
    one; both flagged (accepted v1 limitation)."""
    rows = task_rows(parse_plan(plan_text))
    edited = plan_text.replace('Fix off-by-one', 'Fix off-by-two')
    plan = compute_sync(parse_plan(edited), rows)
    assert plan.vanished == ('A1',)
    assert [head.title for head in plan.new] == [
        'Fix off-by-two in the tokenizer',
    ]
    assert plan.reordered == ()  # the new line took the old slot


def test_sync_duplicate_titles_match_in_order():
    """§8 sync: identical titles pair up by document order."""
    text = '- [ ] same\n- [ ] same\n- [ ] same\n'
    rows = task_rows(parse_plan(text))
    assert [row.task_id for row in rows] == ['A1', 'A2', 'A3']
    ticked = parse_plan('- [ ] same\n- [x] same\n- [ ] same\n')
    only(compute_sync(ticked, rows), checked=('A2',))
    shorter = compute_sync(parse_plan('- [ ] same\n- [ ] same\n'), rows)
    only(shorter, vanished=('A3',))


def test_mint_id_letters_ordinals_and_children():
    """§8/I5 (§13 step 5): letters by first appearance; ordinal = max
    under the prefix + 1 over ALL rows, orphaned included; a child of A3
    is A3.N; a child of a row minted in the same pass gets its dotted id
    immediately; the 27th section letters AA."""
    raise NotImplementedError('needs planfile.mint_id (§13 step 5)')


def test_sync_rows_refresh_text_keep_state(plan_text):
    """Rev 9 SyncPlan.rows: for every line, in document order - matched
    rows carry refreshed seq/section/parent_id/title/body and untouched
    status/owner/claimed_at/done_*; new rows are todo with minted ids;
    `new` lists their ids; a new [x] line appears in `checked`."""
    raise NotImplementedError('needs SyncPlan.rows (§13 step 5)')
