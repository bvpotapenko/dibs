"""Property/metamorphic tier for the pure plan functions (§11).

Use seeded stdlib random document generation (a local generator
helper, seeds 0..N) - dev deps stay at flake8/WPS/ruff/pytest. If
hypothesis is ever adopted, these become @given strategies; amend
pyproject dev extras first.
"""

import dataclasses
import random
import re
from operator import attrgetter
from string import ascii_uppercase
from types import MappingProxyType

from dibs.planfile import annotate_lines, compute_sync, parse_plan, title_hash
from dibs.records import Status, Task
from tests.boards import ELEPHANT, NOW, OTTER, task_rows

SEEDS = range(100)
GRAMMAR_LINE = re.compile(r'^[ \t]*- \[')
TITLES = (
    'Fix the parser', 'Ship it', 'Größe prüfen', 'Write docs',
    'Cover 日本語 input', 'Same title', 'Same title', 'Trailing spaces   ',
)
PROSE = (
    'Plain prose line.', 'Ünïcödé — prose ✓ with a check mark',
    '\tTabbed prose', 'Trailing spaces   ', '- plain bullet',
    '1. numbered', '```', '```python', '    code = "x"  # four spaces',
    '# Heading', '## Sub heading', '### Deep heading', '', '   ',
)
INDENTS = ('', '', '  ', '    ', ' ', '\t')
STATES = (' ', ' ', 'x', '~ brave-otter')
SUFFIXES = ('', '', '  ✓ happy-elephant: some note')
ENDINGS = ('\n', '\r\n')
LINE_KINDS = ('checkbox', 'body', 'prose')
LINE_WEIGHTS = (9, 5, 6)
ROW_KINDS = ('doing', 'done', 'orphaned', 'todo')
ROW_WEIGHTS = (5, 5, 2, 8)
ALL_EMPTY = MappingProxyType({
    'new': (), 'vanished': (), 'checked': (),
    'reordered': (), 'reparented': (), 'regressed': (),
})


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
                done_at=NOW, done_note='note ✓ with: punctuation',
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


def pair(plan_items, rows: tuple[Task, ...]) -> dict[int, Task]:
    """Test-side mirror of the §8 pairing (hash-matched, dupes by order)."""
    queues: dict[str, list[Task]] = {}
    for row in sorted(rows, key=attrgetter('seq')):
        if row.status != Status.ORPHANED:
            queues.setdefault(row.text_hash, []).append(row)
    matched = {}
    for head in plan_items:
        bucket = queues.get(title_hash(head.title))
        if bucket:
            matched[head.line_no] = bucket.pop(0)
    return matched


def mint_id(section: str, parent_id: str | None, rows) -> str:
    """Next free id in its section / under its parent (SSoT §8, I5).

    Max ordinal plus one, never a count: IDs are never reused, and a
    reparented task keeps its old id while leaving its old sibling set.
    """
    prefix = f'{parent_id}.'
    if parent_id is None:
        letters = {row.task_id[0] for row in rows}
        prefix = next(
            (row.task_id[0] for row in rows if row.section == section),
            ascii_uppercase[len(letters)],
        )
    taken = [
        int(row.task_id[len(prefix):])
        for row in rows
        if row.task_id.startswith(prefix)
        and row.task_id[len(prefix):].isdigit()
    ]
    ordinal = max(taken, default=0) + 1
    return f'{prefix}{ordinal}'


def apply_sync(plan, plan_items, rows: tuple[Task, ...]) -> tuple[Task, ...]:
    """What sync (§13 step 8) will do with a SyncPlan, minus the DB."""
    by_id = {row.task_id: row for row in rows}
    for gone in plan.vanished:
        by_id[gone] = dataclasses.replace(by_id[gone], status=Status.ORPHANED)
    for ticked in plan.checked:
        by_id[ticked] = dataclasses.replace(
            by_id[ticked], status=Status.DONE, owner='human', done_at=NOW,
        )
    for shifted, seq in plan.reordered:
        by_id[shifted] = dataclasses.replace(by_id[shifted], seq=seq)
    for child, parent in plan.reparented:
        by_id[child] = dataclasses.replace(by_id[child], parent_id=parent)
    line_ids = {
        line_no: row.task_id
        for line_no, row in pair(plan_items, tuple(by_id.values())).items()
    }
    for head in plan.new:  # document order: a new parent precedes its kids
        parent_id = line_ids.get(head.parent_line)
        task_id = mint_id(head.section, parent_id, tuple(by_id.values()))
        checked = head.checkbox == 'x'
        by_id[task_id] = Task(
            task_id=task_id, parent_id=parent_id,
            seq=plan_items.index(head) + 1, section=head.section,
            title=head.title, body=head.body,
            text_hash=title_hash(head.title),
            status=Status.DONE if checked else Status.TODO,
            owner='human' if checked else None, claimed_at=None,
            done_at=NOW if checked else None, done_note=None,
        )
        line_ids[head.line_no] = task_id
    return tuple(by_id.values())


def test_annotate_preserves_nongrammar_bytes():
    """I4 crown jewel: across generated documents (prose, fences,
    weird indentation, unicode), annotate_lines changes no byte outside
    its own grammar lines. Generator + seeds 0-99."""
    for seed in SEEDS:
        text = generate_document(seed)
        rows = mutate_rows(task_rows(parse_plan(text)), seed)
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
        rows = mutate_rows(task_rows(found), seed)
        again = parse_plan(annotate_lines(text, rows))
        assert len(again) == len(found), seed
        for old, new in zip(found, again, strict=True):
            assert dataclasses.replace(new, checkbox=old.checkbox) == old, seed


def test_compute_sync_is_idempotent():
    """§8: applying a computed SyncPlan to the rows, then recomputing
    against the same text, yields an empty SyncPlan.

    One case is deferred by design (compute_sync docstring): an existing
    task re-indented under a brand-new parent is reparented on the
    recompute after insertion. So: apply, annotate (sync's step 9),
    recompute -> only `reparented` may remain; apply that -> empty.
    """
    for seed in SEEDS:
        base = generate_document(seed)
        rows = task_rows(parse_plan(base))
        edited = mutate_document(base, seed)
        first = compute_sync(parse_plan(edited), rows)
        rows = apply_sync(first, parse_plan(edited), rows)
        settled = annotate_lines(edited, rows)
        second = compute_sync(parse_plan(settled), rows)
        assert dataclasses.asdict(second) == {
            **ALL_EMPTY, 'reparented': second.reparented,
        }, seed
        rows = apply_sync(second, parse_plan(settled), rows)
        third = compute_sync(parse_plan(settled), rows)
        assert dataclasses.asdict(third) == dict(ALL_EMPTY), seed
