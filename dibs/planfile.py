"""Pure plan-text functions: text in, records out (C4).

No I/O, no DB, no clock; file reads/writes happen in verbs (C4).
Level L1 (imports L0). Member budget 7 - at the cap: an 8th member
splits along the D4 direction seam, annotate_lines taking LINE_RE and
LINE_FORMS into the db->md half (ARCHITECTURE §3).
Recognition and annotation grammar: SSoT §8; nesting: D22; ids: §13.
"""

import hashlib
import re
from dataclasses import dataclass, replace
from itertools import chain, count, groupby, islice, product
from operator import attrgetter
from string import ascii_uppercase
from textwrap import dedent
from types import MappingProxyType, SimpleNamespace

from dibs.records import HUMAN, Status, Task, agent_name

# One pattern for every line (SSoT §8 recognition): a column-0 ATX
# heading ('heading'), a checkbox at any indent ('indent', 'state',
# 'title' - a trailing '✓ name: note' annotation is excluded - and
# 'ending', the CR of a CRLF line), or anything else - so a match
# always exists. The line rule wins even inside code fences (pinned by
# test_parse_fence_lookalike_policy). Text splits on '\n'.
#
# 'state' admits ONLY the three §8 tokens - ' ', 'x' (or 'X'), and
# '~ <name>' - and the separating space after ']' is required. Any
# other bracket content ('- [-] cancelled', '- [] blank', '- [wip] x',
# '- [ ]nospace') is prose the tool must never rewrite (I4, D5).
#
# The excluded suffix is the tool's OWN done annotation and nothing
# else: two-plus spaces, '✓ ', a whitespace/colon-free name, ':', rest
# of line. A '✓' the author typed in a title stays in the title (D4:
# plan.md is text truth). Residual ambiguity: a title that itself ends
# in a full '  ✓ name: text' form reads as an annotation - accepted.
LINE_RE = re.compile(
    r'^(?:#{1,6}[ \t]+(?P<heading>.*)'
    r'|(?P<indent>[ \t]*)- \[(?P<state>[ xX]|~ [^\]]+)\] '
    r'(?P<title>.*?)[ \t]*(?:[ \t]{2,}✓ [^\s:]+:[^\r]*)?(?P<ending>\r?)'
    r'|.*)$',
)
CHECKED = 'x'
HASH_CHARS = 16  # sha256 prefix; a matching key, not a secret
BY_SEQ = attrgetter('seq')
BY_HASH = attrgetter('text_hash')
BY_HASH_SEQ = attrgetter('text_hash', 'seq')
DB_WINS = (Status.DOING, Status.DONE)  # §8 sync: '[ ]' over these regresses
LETTERS_RE = re.compile('[A-Z]+')  # the section letters an id opens with
# The top level, shaped like a row whose id a child would dot under.
TOP = SimpleNamespace(task_id=None)
# What a line without a pair starts from (§8 'new checkbox line'): todo,
# unowned; compute_sync fills in the id and every text-cached column.
FRESH = Task(
    task_id='', parent_id=None, seq=0, section='', title='', body='',
    text_hash='', status=Status.TODO, owner=None, claimed_at=None,
    done_at=None, done_note=None,
)

# Annotation grammar (SSoT §8) - the ONLY lines the tool may rewrite -
# keyed by (status, done_note is None). A done row with no note (a
# hand-checked [x] imported by sync) keeps the bare form: the tool has
# nothing to add. Orphaned rows are never rendered - they left the plan.
# Every form is exactly ONE line: the note is whitespace-collapsed on
# render so a multi-line --note cannot inject prose the human never
# wrote (I4). The DB keeps the note verbatim - state truth is there (D4).
LINE_FORMS = MappingProxyType({
    (Status.TODO, True): '{indent}- [ ] {title}',
    (Status.TODO, False): '{indent}- [ ] {title}',
    (Status.DOING, True): '{indent}- [~ {name}] {title}',
    (Status.DOING, False): '{indent}- [~ {name}] {title}',
    (Status.DONE, True): '{indent}- [x] {title}',
    (Status.DONE, False): '{indent}- [x] {title}  ✓ {name}: {note}',
})


@dataclass(frozen=True)
class PlanItem:
    """One recognized checkbox line, before any DB exists (SSoT §8)."""

    line_no: int  # 1-based, counting '\n'-separated lines
    parent_line: int | None  # nearest less-indented checkbox above (D22)
    checkbox: str  # state token, lowercased: '', 'x', or '~ <name>'
    title: str
    body: str
    section: str


@dataclass(frozen=True)
class SyncPlan:
    """Facts compute_sync found; wording them is views' job (C5, §8, D24)."""

    rows: tuple[Task, ...]  # every line as the row it should be, in doc order
    new: tuple[str, ...]  # ids minted this pass; their rows sit in `rows`
    vanished: tuple[str, ...]  # live rows whose line disappeared -> orphaned
    checked: tuple[str, ...]  # [x] over todo, new lines too: stamp done_at
    regressed: tuple[str, ...]  # [ ] over doing/done: DB wins, warning


# The outline root: never a real line; carries the current section.
ROOT = PlanItem(
    line_no=0, parent_line=None, checkbox='', title='', body='', section='',
)


def parse_plan(text: str) -> tuple[PlanItem, ...]:
    """Read tasks per the SSoT §8 recognition table; invent nothing.

    A stack of open checkboxes is the outline: any non-blank line closes
    every open checkbox at its indent or deeper; a checkbox's parent is
    the stack top; other lines belong to the stack top's body (blank
    lines included, trailing ones trimmed). A heading closes everything
    and names the section; no headings means one implicit section ''.
    """
    heads: list[PlanItem] = []
    bodies: dict[PlanItem, list[str]] = {}
    # Stack entries: (indent, open checkbox, the parent_line its children get).
    open_tasks: list[tuple[int, PlanItem, int | None]] = [(-1, ROOT, None)]
    for line_no, match in enumerate(
        map(LINE_RE.match, text.replace('\r\n', '\n').split('\n')),
        start=1,
    ):
        while (
            match.string.strip()
            and open_tasks[-1][0]
            >= len(match.string) - len(match.string.lstrip())
        ):
            open_tasks.pop()
        if match['heading'] is not None:
            open_tasks[0] = (
                -1, replace(ROOT, section=match['heading'].strip()), None,
            )
        elif match['state'] is not None:
            heads.append(PlanItem(
                line_no=line_no,
                parent_line=open_tasks[-1][2],
                checkbox=match['state'].strip().lower(),
                title=match['title'],
                body='',
                section=open_tasks[0][1].section,
            ))
            open_tasks.append(
                (len(match['indent']), heads[-1], line_no),
            )
            bodies[heads[-1]] = []
        else:
            bodies.setdefault(
                open_tasks[-1][1], [],
            ).append(match.string)
    return tuple(
        replace(
            head,
            body=dedent('\n'.join(bodies[head])).strip('\n'),
        )
        for head in heads
    )


def compute_sync(
    plan_items: tuple[PlanItem, ...],
    tasks: tuple[Task, ...],
) -> SyncPlan:
    """Diff plan text against task rows, matched on title_hash (§8, D24).

    Duplicate titles pair by document order; a retitled line is a vanish
    plus a new id (accepted v1 limitation); orphaned rows never pair.
    One pass in document order turns every line into the row it should
    be: a paired row with its text-cached columns refreshed, or a fresh
    row whose id mint_id draws from every row known so far - so a child
    under a brand-new parent gets its dotted id immediately. The one
    state the diff decides: a [x] line over a todo or fresh row is
    carried as done by human (`checked` lists it for the clock stamp), so
    verify previews what init creates (D21, D24). Pure and idempotent:
    apply the result and recompute, and every fact is empty.
    """
    queues = {  # text_hash -> live rows in seq order, consumed as paired
        group[0]: iter(tuple(group[1]))
        for group in groupby(
            sorted(
                (row for row in tasks if row.status != Status.ORPHANED),
                key=BY_HASH_SEQ,
            ),
            key=BY_HASH,
        )
    }
    bases = {  # line_no -> the row a line starts from: its pair, or FRESH
        head.line_no: replace(task, section=head.section)
        for head in plan_items
        for task in islice(queues.get(title_hash(head.title), iter(())), 1)
    }
    known = {  # every row that exists, pairs already in their new section
        row.task_id: row for row in chain(tasks, bases.values())
    }
    lines: dict[int, Task] = {}  # line_no -> the row it should be
    for plan_item in plan_items:
        if plan_item.line_no not in bases:
            bases[plan_item.line_no] = replace(
                FRESH,
                task_id=mint_id(
                    plan_item,
                    lines.get(plan_item.parent_line, TOP).task_id,
                    (*known.values(), *lines.values()),
                ),
            )
        lines[plan_item.line_no] = replace(
            bases[plan_item.line_no],
            parent_id=lines.get(plan_item.parent_line, TOP).task_id,
            seq=len(lines) + 1,
            section=plan_item.section,
            title=plan_item.title,
            body=plan_item.body,
            text_hash=title_hash(plan_item.title),
        )
        if (
            plan_item.checkbox == CHECKED
            and lines[plan_item.line_no].status == Status.TODO
        ):
            lines[plan_item.line_no] = replace(
                lines[plan_item.line_no], status=Status.DONE, owner=HUMAN,
            )
    return SyncPlan(
        rows=tuple(lines.values()),
        new=tuple(
            row.task_id for row in lines.values() if row.task_id not in known
        ),
        vanished=tuple(
            row.task_id
            for row in sorted(chain.from_iterable(queues.values()), key=BY_SEQ)
        ),
        checked=tuple(
            lines[head.line_no].task_id
            for head in plan_items
            if (
                head.checkbox == CHECKED
                and bases[head.line_no].status == Status.TODO
            )
        ),
        regressed=tuple(
            lines[head.line_no].task_id
            for head in plan_items
            if not head.checkbox and bases[head.line_no].status in DB_WINS
        ),
    )


def mint_id(
    head: PlanItem,
    parent_id: str | None,
    taken: tuple[Task, ...],
) -> str:
    """Mint the next free id for head over every row that exists (I5).

    Under a parent the id dots: parent_id.N. At the top level it is the
    section's letter - the one any top-level row of head's section
    carries, else the first unused (A..Z, AA..) - plus N. N is the max
    ordinal under that prefix + 1 over ALL rows, orphaned included, so
    an id is never reused (SSoT §8, §13).
    """
    prefix = f'{parent_id}.'
    if parent_id is None:
        used = {LETTERS_RE.match(row.task_id)[0] for row in taken}
        prefix = next(chain(
            (
                LETTERS_RE.match(row.task_id)[0]
                for row in taken
                if row.parent_id is None and row.section == head.section
            ),
            (
                letters
                for letters in map(''.join, chain.from_iterable(
                    product(ascii_uppercase, repeat=size) for size in count(1)
                ))
                if letters not in used
            ),
        ))
    ordinal = max(
        (
            int(row.task_id.removeprefix(prefix))
            for row in taken
            if row.task_id.removeprefix(prefix).isdigit()
        ),
        default=0,
    ) + 1
    return f'{prefix}{ordinal}'


def annotate_lines(text: str, tasks: tuple[Task, ...]) -> str:
    """Rewrite ONLY annotation-grammar lines; keep every other byte (I4).

    Grammar lines pair with rows exactly as compute_sync pairs them
    (hash, duplicates by order); an unpaired grammar line is left as
    written. LF and CRLF endings are preserved, and the line count
    never changes: a done-note carrying newlines renders collapsed to
    single spaces (§8's done form is one line; the verbatim note stays
    in the DB per D4).
    """
    queues = {  # text_hash -> live rows in seq order, consumed as paired
        group[0]: iter(tuple(group[1]))
        for group in groupby(
            sorted(
                (row for row in tasks if row.status != Status.ORPHANED),
                key=BY_HASH_SEQ,
            ),
            key=BY_HASH,
        )
    }
    lines = text.split('\n')
    replacements: dict[int, str] = {}
    for head in parse_plan(text):
        task = next(
            queues.get(title_hash(head.title), iter(())),
            None,
        )
        if task is not None:
            replacements[head.line_no] = LINE_FORMS[
                (task.status, task.done_note is None)
            ].format(
                indent=LINE_RE.match(lines[head.line_no - 1])['indent'],
                title=head.title,
                name=agent_name(task.owner),
                note=' '.join((task.done_note or '').split()),
            ) + LINE_RE.match(lines[head.line_no - 1])['ending']
    return '\n'.join(
        replacements.get(line_no, lines[line_no - 1])
        for line_no in range(1, len(lines) + 1)
    )


def title_hash(title: str) -> str:
    """Hash the lowercased, whitespace-collapsed title (SSoT §8 sync)."""
    normalized = ' '.join(title.split()).casefold()
    return hashlib.sha256(normalized.encode()).hexdigest()[:HASH_CHARS]
