"""Unit: the SSoT §8 recognition table, annotation grammar, sync diff.

Pure functions only - no fixtures beyond plan_text (C4 makes this tier
trivial to test; keep it that way).
"""

import dataclasses
import re
from types import MappingProxyType

from dibs.planfile import (
    PlanItem,
    annotate_lines,
    compute_sync,
    mint_id,
    parse_plan,
    title_hash,
)
from dibs.records import Status
from tests.boards import ELEPHANT, NOW, OTTER, init_rows

# The facts a SyncPlan reports besides rows (rows are never empty).
EMPTY_FACTS = MappingProxyType({
    'new': (), 'vanished': (), 'checked': (), 'regressed': (),
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
# Ids init mints for plan_text, in document order (SSoT §8, §13).
IDS = ('A1', 'A2', 'A2.1', 'A2.2', 'A3', 'B1')


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
    """Assert a SyncPlan reports exactly the expected non-empty facts."""
    found = {
        field.name: getattr(plan, field.name)
        for field in dataclasses.fields(plan)
        if field.name != 'rows'
    }
    assert found == {**EMPTY_FACTS, **expected}


def ordered(plan):
    """Ids in document order, once seq is seen to count 1..n along it."""
    seqs = [row.seq for row in plan.rows]
    assert seqs == list(range(1, len(seqs) + 1))
    return [row.task_id for row in plan.rows]


def parents(plan):
    """task_id -> parent_id of every row."""
    return {row.task_id: row.parent_id for row in plan.rows}


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
    assert tuple(row.task_id for row in init_rows(plan_text)) == IDS


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
        assert parse_plan(text) == (), text
        assert annotate_lines(text, init_rows(text)) == text, text
    upper = parse_plan('- [X] Rename Lexer to Tokenizer\n')
    assert (upper[0].checkbox, upper[0].title) == (
        'x', 'Rename Lexer to Tokenizer',
    )


def test_annotate_rewrites_only_grammar_lines(plan_text):
    """I4: every byte outside annotation-grammar lines is preserved."""
    rows = list(init_rows(plan_text))
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
    rows = list(init_rows(text))
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
    rows = list(init_rows(text))
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
    rows = list(init_rows(plan_text))
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
    assert annotate_lines(authored, init_rows(authored)) == authored


def test_sync_new_line_becomes_task(plan_text):
    """§8 sync: a new checkbox line becomes a fresh todo row with the
    next id in its section, at its document seq; its id lands in new."""
    grown = f'{plan_text}- [ ] Write the changelog\n'
    plan = compute_sync(parse_plan(grown), init_rows(plan_text))
    only(plan, new=('B2',))
    fresh = plan.rows[-1]
    assert (fresh.task_id, fresh.title, fresh.section, fresh.seq) == (
        'B2', 'Write the changelog', 'Docs', 7,
    )
    assert (fresh.status, fresh.owner, fresh.parent_id) == (
        Status.TODO, None, None,
    )
    assert fresh.text_hash == title_hash('Write the changelog')


def test_sync_vanished_line_orphaned(plan_text):
    """§8 sync + I5: a removed line is orphaned, never deleted; later
    rows shift up one seq slot with their ids untouched."""
    lines = plan_text.split('\n')
    lines.pop(EMPTY - 1)  # 'Cover the empty file' (A2.2) leaves the plan
    plan = compute_sync(parse_plan('\n'.join(lines)), init_rows(plan_text))
    only(plan, vanished=('A2.2',))
    assert ordered(plan) == ['A1', 'A2', 'A2.1', 'A3', 'B1']


def test_sync_hand_checked_imports_done(plan_text):
    """§8 sync: [x] over todo lands in SyncPlan.checked and its row already
    says done by human - the one state the diff decides, so verify shows
    what init creates (D21, D24); apply_sync's import stamps done_at."""
    edited = plan_text.replace('- [ ] Fix off-by-one', '- [x] Fix off-by-one')
    plan = compute_sync(parse_plan(edited), init_rows(plan_text))
    only(plan, checked=('A1',))  # A3 is already done: not re-imported
    ticked = plan.rows[0]
    assert (ticked.status, ticked.owner, ticked.done_at) == (
        Status.DONE, 'human', None,
    )


def test_sync_reorder_updates_seq_only(plan_text):
    """§8 sync + I5/D7: reordering refreshes seq in rows; ids stay
    untouched and no other fact is reported."""
    lines = plan_text.split('\n')
    block = lines[FIX - 1:SHIP - 1]  # the task line plus its two body lines
    before = lines[:FIX - 1]
    rest = before + lines[SHIP - 1:]
    at = RENAME - 1 - len(block)  # right after 'Rename Lexer to Tokenizer'
    moved = rest[:at] + block + rest[at:]
    plan = compute_sync(parse_plan('\n'.join(moved)), init_rows(plan_text))
    only(plan)
    assert ordered(plan) == ['A2', 'A2.1', 'A2.2', 'A1', 'A3', 'B1']


def test_sync_reindent_updates_parent(plan_text):
    """§8 sync + D22: re-indenting under another checkbox refreshes
    parent_id in rows (and back to None at top level); ids untouched."""
    lines = plan_text.split('\n')
    nested = list(lines)
    rename_line = lines[RENAME - 1]
    nested[RENAME - 1] = f'  {rename_line}'  # Rename under Ship
    plan = compute_sync(parse_plan('\n'.join(nested)), init_rows(plan_text))
    only(plan)
    assert parents(plan) == {
        'A1': None, 'A2': None, 'A2.1': 'A2', 'A2.2': 'A2', 'A3': 'A2',
        'B1': None,
    }
    lifted = list(lines)
    lifted[EMPTY - 1] = lifted[EMPTY - 1].lstrip()  # A2.2 to top level
    plan = compute_sync(parse_plan('\n'.join(lifted)), init_rows(plan_text))
    only(plan)
    assert parents(plan) == {
        'A1': None, 'A2': None, 'A2.1': 'A2', 'A2.2': None, 'A3': None,
        'B1': None,
    }


def test_sync_regressed_checkbox_flagged(plan_text):
    """§8 sync: [ ] over doing/done lands in regressed; DB wins."""
    rows = list(init_rows(plan_text))
    rows[0] = doing(rows[0])
    rows[2] = done(rows[2], 'handled')
    plan = compute_sync(parse_plan(plan_text), tuple(rows))
    only(plan, regressed=('A1', 'A2.1'))


def test_sync_retitle_is_vanish_plus_new(plan_text):
    """§8 sync: an edited title orphans the old task and mints a new
    one, both flagged (accepted v1 limitation); the new row takes the
    old slot and the section's next ordinal, never the orphan's (I5)."""
    edited = plan_text.replace('Fix off-by-one', 'Fix off-by-two')
    plan = compute_sync(parse_plan(edited), init_rows(plan_text))
    only(plan, new=('A4',), vanished=('A1',))
    assert ordered(plan) == ['A4', 'A2', 'A2.1', 'A2.2', 'A3', 'B1']
    assert plan.rows[0].title == 'Fix off-by-two in the tokenizer'


def test_sync_duplicate_titles_match_in_order():
    """§8 sync: identical titles pair up by document order."""
    text = '- [ ] same\n- [ ] same\n- [ ] same\n'
    rows = init_rows(text)
    assert [row.task_id for row in rows] == ['A1', 'A2', 'A3']
    ticked = parse_plan('- [ ] same\n- [x] same\n- [ ] same\n')
    only(compute_sync(ticked, rows), checked=('A2',))
    shorter = compute_sync(parse_plan('- [ ] same\n- [ ] same\n'), rows)
    only(shorter, vanished=('A3',))


def test_mint_id_letters_ordinals_and_children():
    """§8/I5 (§13 step 5): letters by first appearance, the next unused
    one for a new section; ordinal = max under the prefix + 1 over ALL
    rows, orphaned included; children dot under their parent and count
    over that prefix only."""
    rows = init_rows('## Parser\n- [ ] one\n- [ ] two\n## Docs\n- [ ] three\n')
    assert [row.task_id for row in rows] == ['A1', 'A2', 'B1']
    head = PlanItem(
        line_no=9, parent_line=None, checkbox='', title='x', body='',
        section='Parser',
    )
    docs = dataclasses.replace(head, section='Docs')
    tests = dataclasses.replace(head, section='Tests')
    minted = [mint_id(top, None, rows) for top in (head, docs, tests)]
    assert minted == ['A3', 'B2', 'C1']
    # An orphaned A2 keeps its ordinal: the next Parser task is A3, not A2.
    orphaned = (
        rows[0],
        dataclasses.replace(rows[1], status=Status.ORPHANED),
        rows[2],
    )
    assert mint_id(head, None, orphaned) == 'A3'
    # Children dot under the parent and count over that prefix only.
    kid = dataclasses.replace(rows[1], task_id='A2.1', parent_id='A2')
    assert (
        mint_id(head, 'A2', rows),
        mint_id(head, 'A2', (*rows, kid)),
        mint_id(head, 'A2.1', (*rows, kid)),
    ) == ('A2.1', 'A2.2', 'A2.1.1')
    assert mint_id(head, None, (*rows, kid)) == 'A3'  # A2.1 is no A ordinal


def test_mint_id_same_pass_and_past_z():
    """§8/§13 (§13 step 5): a child under a parent minted in the same pass
    gets its dotted id immediately (D24: no deferral); the 27th section
    letters AA like a spreadsheet column."""
    rows = init_rows('## Parser\n- [ ] one\n## Docs\n- [ ] two\n')
    grown = compute_sync(parse_plan(
        '## Parser\n- [ ] one\n- [ ] four\n  - [ ] kid\n## Docs\n- [ ] two\n',
    ), rows)
    assert grown.new == ('A2', 'A2.1')
    assert parents(grown)['A2.1'] == 'A2'
    many = ''.join(
        f'## S{number}\n- [ ] t{number}\n' for number in range(27)
    )
    letters = [row.task_id for row in init_rows(many)]
    assert letters[25:] == ['Z1', 'AA1']


def test_sync_rows_refresh_text_keep_state(plan_text):
    """Rev 9 SyncPlan.rows: for every line, in document order - matched
    rows carry refreshed seq/section/parent_id/title/body and untouched
    status/owner/claimed_at/done_*; new rows are todo with minted ids, or
    done by human when hand-checked; `new` lists their ids; a new [x]
    line appears in `checked`."""
    rows = list(init_rows(plan_text))
    rows[0] = doing(rows[0])  # A1 is held; its line still says [ ]
    edited = (
        plan_text
        .replace('## Parser', '## Lexer')  # heading renamed
        .replace('token count is 12', 'token count is 13')  # body reworded
        .replace('- [ ] Fix off-by-one', '- [ ] Fix  off-by-one')  # same hash
        .replace('- [x] Rename Lexer', '  - [x] Rename Lexer')  # under Ship
    )
    edited = f'{edited}- [x] Write the changelog\n'  # new, hand-checked
    plan = compute_sync(parse_plan(edited), tuple(rows))
    assert ordered(plan) == ['A1', 'A2', 'A2.1', 'A2.2', 'A3', 'B1', 'B2']
    assert [row.section for row in plan.rows] == [
        'Lexer', 'Lexer', 'Lexer', 'Lexer', 'Lexer', 'Docs', 'Docs',
    ]
    held = plan.rows[0]
    assert (
        held.title,
        held.body.split('\n')[0],
        held.status,
        held.owner,
        held.claimed_at,
    ) == (
        'Fix  off-by-one in the tokenizer',
        'Repro: token count is 13 for fixtures/one.txt, expected 11.',
        Status.DOING,
        OTTER.agent_id,
        1,
    )
    renamed = plan.rows[4]
    assert (
        renamed.parent_id, renamed.status, renamed.owner, renamed.done_at,
    ) == ('A2', Status.DONE, 'human', NOW)
    fresh = plan.rows[-1]
    assert (fresh.task_id, fresh.status, fresh.owner, fresh.done_at) == (
        'B2', Status.DONE, 'human', None,
    )
    only(plan, new=('B2',), checked=('B2',), regressed=('A1',))
