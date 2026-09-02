"""Pure plan-text functions: text in, records out (C4).

No I/O, no DB, no clock; file reads/writes happen in verbs (C4).
Level L1 (imports L0). Member budget 6 (ARCHITECTURE §3).
Recognition and annotation grammar: SSoT §8; nesting: D22.
"""

import hashlib
import re
from dataclasses import dataclass, replace
from operator import attrgetter
from textwrap import dedent
from types import MappingProxyType

from dibs.records import Status, Task

# Draft recognition pattern (SSoT §8). Pin the exact behavior through
# the tests/test_planfile.py recognition table before relying on it;
# note that done lines carry an annotation suffix to strip (see below).
CHECKBOX_RE = re.compile(
    r'^(?P<indent>[ \t]*)- \[(?P<state>[^\]]*)\] ?(?P<rest>.*)$',
)

# Annotation grammar (SSoT §8) - the ONLY lines the tool may rewrite:
#   - [ ] <title>
#   - [~ <name>] <title>
#   - [x] <title>  ✓ <name>: <done-note>
DONE_MARK = '✓'
DONE_STATE = 'x'  # §8 recognition: the only checkbox token dibs imports

# Rendered from (title, DONE_MARK, owner name, done note); extra
# arguments are ignored by str.format, so one call serves all three.
# A done row is assumed to carry a note: D11 makes --note mandatory and
# transitions.import_author_done must supply one for a hand [x].
ANNOTATIONS = MappingProxyType({
    Status.TODO: '- [ ] {0}',
    Status.DOING: '- [~ {2}] {0}',
    Status.DONE: '- [x] {0}  {1} {2}: {3}',
})

HEADING = '#'  # nearest one above a task becomes its section (§8)

# Slots of the staging row parse_plan carries per recognized checkbox:
# the parsed item, the indent width that decides parenthood and body
# membership (D22), and the raw lines beneath it.
PARSED = 0
INDENT = 1
BODY = 2

SeqUpdate = tuple[str, int]  # (task_id, new_seq) - §8 'lines reordered'
# (task_id, new parent_id or None back at top level) - §8 're-indented'
ParentUpdate = tuple[str, str | None]


@dataclass(frozen=True)
class PlanItem:
    """One recognized checkbox line, before any DB exists (SSoT §8)."""

    line_no: int
    parent_line: int | None  # nearest less-indented checkbox above (D22)
    checkbox: str  # raw state token: '', 'x', or '~ <name>'
    title: str
    body: str
    section: str


@dataclass(frozen=True)
class SyncPlan:
    """Facts compute_sync found; wording them is output's job (C5, §8)."""

    new: tuple[PlanItem, ...]
    vanished: tuple[str, ...]  # task_ids whose line disappeared
    checked: tuple[str, ...]  # task_ids hand-marked [x] while todo
    reordered: tuple[SeqUpdate, ...]
    reparented: tuple[ParentUpdate, ...]
    regressed: tuple[str, ...]  # [ ] in file but doing/done in DB


def parse_plan(text: str) -> tuple[PlanItem, ...]:
    """Read tasks per the SSoT §8 recognition table; invent nothing.

    Indented non-checkbox lines travel as body; an indented checkbox is
    a child of the nearest less-indented checkbox (D22). The nearest
    heading is the section; no headings means one implicit section.
    """
    rows = []
    section = ''
    for line_no, line in enumerate(text.split('\n'), start=1):
        match = CHECKBOX_RE.match(line)
        if match:
            rows.append([
                PlanItem(
                    line_no,
                    next(
                        (
                            row[PARSED].line_no for row in reversed(rows)
                            if row[INDENT] < len(match.group('indent'))
                        ),
                        None,
                    ),
                    match.group('state').strip(),
                    match.group('rest').split(DONE_MARK)[0].strip(),
                    '',
                    section,
                ),
                len(match.group('indent')),
                [],
            ])
        elif line.startswith(HEADING):
            section = line.lstrip(HEADING).strip()
        elif rows:
            rows[-1][BODY].append(line)
    return tuple(
        replace(row[PARSED], body=dedent('\n'.join(
            # Blank, or indented past its checkbox: the §8 body test.
            body_line for body_line in row[BODY]
            if not body_line[:row[INDENT] + 1].strip()
        )).strip('\n'))
        for row in rows
    )


def compute_sync(
    plan_items: tuple[PlanItem, ...],
    tasks: tuple[Task, ...],
) -> SyncPlan:
    """Diff plan text against task rows, matched on title_hash (§8).

    Duplicate titles match by document order; a retitled line becomes a
    vanish + new pair (accepted v1 limitation). Pure and idempotent:
    applying the result and recomputing must find nothing.
    """
    pool = {
        task.text_hash: [
            sibling
            for sibling in sorted(tasks, key=attrgetter('seq'))
            if sibling.text_hash == task.text_hash
            and sibling.status != Status.ORPHANED
        ]
        for task in tasks
    }
    pairs = {
        entry: pool[title_hash(entry.title)].pop(0)
        if pool.get(title_hash(entry.title)) else None
        for entry in plan_items
    }
    by_line = {
        entry.line_no: pairs[entry].task_id
        for entry in pairs if pairs[entry]
    }
    return SyncPlan(
        new=tuple(entry for entry in pairs if pairs[entry] is None),
        vanished=tuple(
            row.task_id for bucket in pool.values() for row in bucket
        ),
        checked=tuple(
            row.task_id for entry, row in pairs.items()
            if row and entry.checkbox == DONE_STATE
            and row.status == Status.TODO
        ),
        reordered=tuple(
            (row.task_id, entry.line_no) for entry, row in pairs.items()
            if row and row.seq != entry.line_no
        ),
        reparented=tuple(
            (row.task_id, by_line.get(entry.parent_line))
            for entry, row in pairs.items()
            if row and row.parent_id != by_line.get(entry.parent_line)
        ),
        regressed=tuple(
            row.task_id for entry, row in pairs.items()
            if row and not entry.checkbox
            and row.status in {Status.DOING, Status.DONE}
        ),
    )


def annotate_lines(text: str, tasks: tuple[Task, ...]) -> str:
    """Rewrite ONLY annotation-grammar lines; keep every other byte (I4).

    Lines are matched to rows by title hash, so two lines sharing a
    title share an annotation - the same duplicate-title limitation §8
    accepts for sync, and what verify's duplicate warning exists for.
    """
    forms = {
        task.text_hash: ANNOTATIONS[task.status].format(
            task.title,
            DONE_MARK,
            (task.owner or '').rsplit('-', 1)[0],
            task.done_note or '',
        )
        for task in tasks
        if task.status in ANNOTATIONS
    }
    lines = []
    for line in text.split('\n'):
        match = CHECKBOX_RE.match(line)
        form = forms.get(
            title_hash(match.group('rest').split(DONE_MARK)[0]),
        ) if match else None
        lines.append(match.group('indent') + form if form else line)
    return '\n'.join(lines)


def title_hash(title: str) -> str:
    """Hash the lowercased, whitespace-collapsed title (SSoT §8 sync)."""
    normalized = ' '.join(title.lower().split())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
