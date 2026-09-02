"""Property/metamorphic tier for the pure plan functions (§11).

Use seeded stdlib random document generation (a local generator
helper, seeds 0..N) - dev deps stay at flake8/WPS/ruff/pytest. If
hypothesis is ever adopted, these become @given strategies; amend
pyproject dev extras first.

The seeded generator draws from hashlib rather than the random module:
ruff's bandit bundle flags random for non-crypto use (S311) and the
tests per-file-ignores cover only S101/D. Determinism is what these
tests need, and sha256(seed:index) gives it.
"""

import hashlib

from dibs import planfile
from dibs.records import Status, Task

SEEDS = 100
DOC_LINES = 40
HASH_BYTES = 4

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
    '',
    '   ',
    '> quoted text {0}',
    '- [ ] Task {0}',
    '  - [ ] Child {0}',
    '    Body prose for {0}',
    '- [x] Done task {0}',
    '- [~ brave-otter] Doing task {0}',
)

TASK_ID = 'T{0}'  # test-local ids; planfile never mints them

STATUSES = (Status.TODO, Status.DOING, Status.DONE)
EMPTY_SYNC = planfile.SyncPlan((), (), (), (), (), ())


def pick(seed, index, size):
    """Deterministic index from (seed, index) - no PRNG module needed."""
    digest = hashlib.sha256(bytes((seed, index))).digest()
    return int.from_bytes(digest[:HASH_BYTES], 'big') % size


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


def test_compute_sync_is_idempotent():
    """§8: applying a computed SyncPlan to the rows, then recomputing
    against the same text, yields an empty SyncPlan."""
    for seed in range(SEEDS):
        text = generate_document(seed)
        parsed = planfile.parse_plan(text)

        assert planfile.compute_sync(parsed, ()).new == parsed
        assert planfile.compute_sync(parsed, tasks_for(text)) == EMPTY_SYNC
