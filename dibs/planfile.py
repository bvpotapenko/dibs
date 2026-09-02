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

# Recognition pattern (SSoT §8): exactly the three checkbox tokens -
# a single space, 'x' (or 'X', lowercased at parse), or '~ <name>' -
# and the space after ']' that separates the token from the title. Any
# other bracket content is the human's prose, never a task and never
# rewritten (D5, I4). A bare '- [ ]' with no title still counts; done
# lines carry an annotation suffix to strip (see below). 'eol' holds the
# CR of a CRLF document so a rewritten line keeps the terminator the
# rest of the file uses (I4).
CHECKBOX_RE = re.compile(
    r'^(?P<indent>[ \t]*)- \[(?P<state> |x|X|~ [^\]]+)\]'
    r'(?P<rest>| .*?)(?P<eol>\r?)$',
)

# Annotation grammar (SSoT §8) - the ONLY lines the tool may rewrite:
#   - [ ] <title>
#   - [~ <name>] <title>
#   - [x] <title>  ✓ <name>: <done-note>
# One task is one line: the name and note are whitespace-collapsed on
# the way in, so a multi-line done-note can never inject a second line
# into the file (I4, and annotation stays idempotent).
DONE_MARK = '✓'
DONE_STATE = 'x'  # §8 recognition: the only checkbox token dibs imports

# The done suffix exactly as §8 spells it: two spaces, the mark, the
# owner name, a colon, the note. Matched as a whole - never by splitting
# on the first mark - so a title may contain one and survive (D4, I4).
DONE_SUFFIX_RE = re.compile(r'  ✓ \S+: .*$')

# Rendered from (title, DONE_MARK, owner name, done note); extra
# arguments are ignored by str.format, so one call serves all three.
# {0} is the line's own text INCLUDING the separator space, so a title's
# spacing survives a state change untouched (D4, I4).
# A done row is assumed to carry a note: D11 makes --note mandatory and
# plansync supplies AUTHOR_DONE_NOTE for a hand [x] (SSoT §8).
ANNOTATIONS = MappingProxyType({
    Status.TODO: '- [ ]{0}',
    Status.DOING: '- [~ {2}]{0}',
    Status.DONE: '- [x]{0}  {1} {2}: {3}',
})

HEADING = '#'  # nearest one above a task becomes its section (§8)

# Slots of the staging row parse_plan carries per recognized checkbox:
# the parsed item, the indent width that decides parenthood and body
# membership (D22), and the raw lines beneath it.
PARSED = 0
INDENT = 1
BODY = 2

SeqUpdate = tuple[str, int]  # (task_id, new_seq) - §8 'lines reordered'
# (task_id, body, section) - §8 'body or heading text edited'. Text
# truth flowing md -> db: the plan file is its own journal, so applying
# one writes no event (D4, I6).
TextUpdate = tuple[str, str, str]
# (task_id, parent's LINE, or None back at top level) - §8 're-indented'.
# A line, not an id: the new parent may itself be a line this same
# SyncPlan is asking the applier to create, which has no id yet. The
# applier resolves line -> id after creating SyncPlan.new (it must do
# that for nested new items anyway), which keeps sync a single pass.
ParentUpdate = tuple[str, int | None]

# Sentinel line for 'this row's parent left the plan': never equal to a
# real parent_line, so the row is reparented to whatever the text says.
GONE_PARENT = -1


@dataclass(frozen=True)
class PlanItem:
    """One recognized checkbox line, before any DB exists (SSoT §8)."""

    line_no: int
    parent_line: int | None  # nearest less-indented checkbox above (D22)
    checkbox: str  # state token, lowercased: '', 'x', '~ <name>'
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
    reparented: tuple[ParentUpdate, ...]  # parent named by LINE, not id
    regressed: tuple[str, ...]  # [ ] in file but doing/done in DB
    refreshed: tuple[TextUpdate, ...]  # reworded body / renamed heading


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
                    match.group('state').strip().lower(),
                    DONE_SUFFIX_RE.sub('', match.group('rest')).strip(),
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
    applying the result and recomputing must find nothing - which is
    why reparented names the parent's LINE (see ParentUpdate), so a
    move under a brand-new parent lands in the same single pass.
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
    # task_id -> the line it now sits on; None maps to None so a
    # top-level row compares equal to a top-level line.
    line_of = {None: None} | {
        pairs[entry].task_id: entry.line_no
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
            (row.task_id, entry.parent_line)
            for entry, row in pairs.items()
            if row and entry.parent_line != line_of.get(
                row.parent_id, GONE_PARENT,
            )
        ),
        regressed=tuple(
            row.task_id for entry, row in pairs.items()
            if row and not entry.checkbox
            and row.status in {Status.DOING, Status.DONE}
        ),
        # Keyed like 'new' above rather than unpacked like its
        # neighbours: the pair-unpacking form is spent (WPS204), and
        # this reads the same - the parsed line and the row it matched.
        refreshed=tuple(
            (pairs[fresh].task_id, fresh.body, fresh.section)
            for fresh in pairs
            if pairs[fresh]
            and (fresh.body, fresh.section)
            != (pairs[fresh].body, pairs[fresh].section)
        ),
    )


def annotate_lines(text: str, tasks: tuple[Task, ...]) -> str:
    """Rewrite ONLY annotation-grammar lines; keep every other byte (I4).

    The DB owns the state token and the done suffix; the file owns the
    title, so each line is re-rendered around the text already on it
    (D4). Lines are matched to rows by title hash and consumed in
    document order, exactly as compute_sync pairs them, so the n-th
    line with a title gets the n-th row carrying it (§8 duplicates).
    """
    forms = {
        task.text_hash: [
            sibling
            for sibling in sorted(tasks, key=attrgetter('seq'))
            if sibling.text_hash == task.text_hash
            and sibling.status in ANNOTATIONS
        ]
        for task in tasks
    }
    lines = []
    for line in text.split('\n'):
        mark = CHECKBOX_RE.match(line)
        row = (forms.get(
            title_hash(DONE_SUFFIX_RE.sub('', mark.group('rest'))),
        ) or [None]).pop(0) if mark else None
        lines.append(
            mark.group('indent')
            + ANNOTATIONS[row.status].format(
                DONE_SUFFIX_RE.sub('', mark.group('rest')),
                DONE_MARK,
                ' '.join(
                    (row.owner or '').rsplit('-', 1)[0].split(),
                ),
                ' '.join((row.done_note or '').split()),
            )
            + mark.group('eol')
            if row else line,
        )
    return '\n'.join(lines)


def title_hash(title: str) -> str:
    """Hash the lowercased, whitespace-collapsed title (SSoT §8 sync)."""
    normalized = ' '.join(title.lower().split())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
