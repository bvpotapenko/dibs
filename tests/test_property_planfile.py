"""Property/metamorphic tier for the pure plan functions (§11).

Use seeded stdlib random document generation (a local generator
helper, seeds 0..N) - dev deps stay at flake8/WPS/ruff/pytest. If
hypothesis is ever adopted, these become @given strategies; amend
pyproject dev extras first.
"""

import dataclasses
import random
import re

from dibs.planfile import annotate_lines, compute_sync, parse_plan
from dibs.records import Status, Task
from tests.boards import ELEPHANT, NOW, OTTER, init_rows, settle

SEEDS = range(100)
# The §8 annotation grammar exactly as dibs/planfile.LINE_RE reads it:
# the only lines the tool is licensed to rewrite. Anything else the
# generator emits must survive byte-identical (I4).
GRAMMAR_LINE = re.compile(r'^[ \t]*- \[( |x|X|~ [^\]]+)\] ')
TITLES = (
    'Fix the parser', 'Ship it', 'Größe prüfen', 'Write docs',
    'Cover 日本語 input', 'Same title', 'Same title', 'Trailing spaces   ',
    'Render ✓ marks',  # an authored check mark, not an annotation (F4)
)
PROSE = (
    'Plain prose line.', 'Ünïcödé — prose ✓ with a check mark',
    '\tTabbed prose', 'Trailing spaces   ', '- plain bullet',
    '1. numbered', '```', '```python', '    code = "x"  # four spaces',
    '# Heading', '## Sub heading', '### Deep heading', '', '   ',
    # Checkbox lookalikes outside the §8 state grammar (I4, D5).
    '- [-] cancel', '- [] blank', '- [ ]nospace',
)
INDENTS = ('', '', '  ', '    ', ' ', '\t')
STATES = (' ', ' ', 'x', '~ brave-otter')
SUFFIXES = ('', '', '  ✓ happy-elephant: some note')
ENDINGS = ('\n', '\r\n')
LINE_KINDS = ('checkbox', 'body', 'prose')
LINE_WEIGHTS = (9, 5, 6)
# A multi-line note: §8's done form is one line, so annotate must
# collapse it - the line count assertion in the I4 fuzz is the guard.
DONE_NOTE = 'note ✓ with: punctuation\nand a second line\r\n\tthird'
ROW_KINDS = ('doing', 'done', 'orphaned', 'todo')
ROW_WEIGHTS = (5, 5, 2, 8)
NO_FACTS = ((), (), (), ())  # new, vanished, checked, regressed: nothing


def generate_document(seed: int) -> str:
    """Random plan text: prose, fences, odd indentation, unicode, CRLF."""
    rng = random.Random(seed)
    lines = []
    for _ in range(rng.randint(3, 25)):
        kind = rng.choices(LINE_KINDS, LINE_WEIGHTS)[0]
        if kind == 'checkbox':
            lines.append(
                f'{rng.choice(INDENTS)}- [{rng.choice(STATES)}] '
                f'{rng.choice(TITLES)}{rng.choice(SUFFIXES)}',
            )
        elif kind == 'body':
            indent = rng.choice(INDENTS[2:])
            prose = rng.choice(PROSE)
            lines.append(f'{indent}{prose}')
        else:
            lines.append(rng.choice(PROSE))
    ending = rng.choice(ENDINGS)
    return ending.join(lines) + rng.choice(('', ending))


def mutate_rows(rows: tuple[Task, ...], seed: int) -> tuple[Task, ...]:
    """Random DB state over the rows: claims, dones, orphans."""
    rng = random.Random(seed)
    out = []
    for row in rows:
        kind = rng.choices(ROW_KINDS, ROW_WEIGHTS)[0]
        if kind == 'doing':
            out.append(dataclasses.replace(
                row, status=Status.DOING, owner=OTTER.agent_id, claimed_at=NOW,
            ))
        elif kind == 'done':
            out.append(dataclasses.replace(
                row, status=Status.DONE, owner=ELEPHANT.agent_id,
                done_at=NOW, done_note=DONE_NOTE,
            ))
        elif kind == 'orphaned':
            out.append(dataclasses.replace(row, status=Status.ORPHANED))
        else:
            out.append(row)
    return tuple(out)


def grammar_lines(lines) -> list[int]:
    """Indexes of the checkbox lines a human edit may target."""
    return [
        line_no
        for line_no, line in enumerate(lines)
        if GRAMMAR_LINE.match(line)
    ]


def toggle(lines, rng):
    """Human edit: tick a checkbox line by hand."""
    line_no = rng.choice(grammar_lines(lines))
    lines[line_no] = lines[line_no].replace('- [ ]', '- [x]', 1)


def delete(lines, rng):
    """Human edit: remove a checkbox line."""
    lines.pop(rng.choice(grammar_lines(lines)))


def move(lines, rng):
    """Human edit: move a checkbox line elsewhere."""
    moved = lines.pop(rng.choice(grammar_lines(lines)))
    lines.insert(rng.randrange(len(lines) + 1), moved)


def reindent(lines, rng):
    """Human edit: nest a checkbox line, or lift it to the top level."""
    line_no = rng.choice(grammar_lines(lines))
    indent = rng.choice(('  ', ''))
    stripped = lines[line_no].lstrip(' \t')
    lines[line_no] = f'{indent}{stripped}'


def insert(lines, rng):
    """Human edit: add a fresh checkbox line (title unique per length)."""
    indent = rng.choice(INDENTS)
    lines.insert(
        rng.randrange(len(lines) + 1), f'{indent}- [ ] New task {len(lines)}',
    )


EDITS = (toggle, delete, move, reindent, insert)


def mutate_document(text: str, seed: int) -> str:
    """One to three human edits: toggle, delete, insert, move, re-indent."""
    rng = random.Random(seed)
    lines = text.split('\n')
    for _ in range(rng.randint(1, 3)):
        rng.choice(EDITS if grammar_lines(lines) else (insert,))(lines, rng)
    return '\n'.join(lines)


def facts(plan) -> tuple:
    """The four facts a SyncPlan reports, rows aside."""
    return (plan.new, plan.vanished, plan.checked, plan.regressed)


def test_annotate_preserves_nongrammar_bytes():
    """I4 crown jewel: across generated documents (prose, fences,
    weird indentation, unicode), annotate_lines changes no byte outside
    its own grammar lines. Generator + seeds 0-99."""
    for seed in SEEDS:
        text = generate_document(seed)
        rows = mutate_rows(init_rows(text), seed)
        before = text.split('\n')
        after = annotate_lines(text, rows).split('\n')
        assert len(after) == len(before), seed
        for old, new in zip(before, after, strict=True):
            if not GRAMMAR_LINE.match(old):
                assert new == old, seed
            assert new.endswith('\r') == old.endswith('\r'), seed


def test_annotate_then_parse_is_stable():
    """Metamorphic: parse(annotate(text, tasks)) finds the same items
    (titles, parents, sections) as parse(text) - only checkbox state
    tokens differ."""
    for seed in SEEDS:
        text = generate_document(seed)
        found = parse_plan(text)
        rows = mutate_rows(init_rows(text), seed)
        again = parse_plan(annotate_lines(text, rows))
        assert len(again) == len(found), seed
        for old, new in zip(found, again, strict=True):
            assert dataclasses.replace(new, checkbox=old.checkbox) == old, seed


def test_compute_sync_is_idempotent():
    """§8/D24: apply a computed SyncPlan to the rows, annotate (sync's
    last step), recompute against the settled text -> nothing is left in
    ONE pass: no new, vanished, checked or regressed ids, and rows equal
    to the live rows. A child under a brand-new parent got its dotted id
    in the first pass (mint_id), so the Rev 8 deferral is gone."""
    for seed in SEEDS:
        base = generate_document(seed)
        rows = mutate_rows(init_rows(base), seed)
        edited = mutate_document(base, seed)
        rows = settle(compute_sync(parse_plan(edited), rows), rows)
        settled = annotate_lines(edited, rows)
        second = compute_sync(parse_plan(settled), rows)
        assert facts(second) == NO_FACTS, seed
        assert settle(second, rows) == rows, seed


def test_minted_ids_unique_and_never_reused():
    """I5: through two rounds of edits ids stay unique across the whole
    board, and a minted id never repeats an existing one - the orphaned
    rows the first round left behind included."""
    for seed in SEEDS:
        base = generate_document(seed)
        edited = mutate_document(base, seed)
        rows = init_rows(base)
        rows = settle(compute_sync(parse_plan(edited), rows), rows)
        twice = mutate_document(edited, seed + 1)
        again = compute_sync(parse_plan(twice), rows)
        assert not set(again.new) & {row.task_id for row in rows}, seed
        ids = [row.task_id for row in settle(again, rows)]
        assert len(ids) == len(set(ids)), seed
