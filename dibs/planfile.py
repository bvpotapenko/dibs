"""Pure plan-text functions: text in, records out (C4).

No I/O, no DB, no clock; file reads/writes happen in verbs (C4).
Level L1 (imports L0). Member budget 6 (ARCHITECTURE §3).
Recognition and annotation grammar: SSoT §8; nesting: D22.
"""

import hashlib
import re
from dataclasses import dataclass, replace
from itertools import chain, groupby
from operator import attrgetter
from textwrap import dedent
from types import MappingProxyType, SimpleNamespace

from dibs.records import Status, Task

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
# The top level, shaped like a pairs entry whose task has no id.
TOP = SimpleNamespace(task=SimpleNamespace(task_id=None))

SeqUpdate = tuple[str, int]  # (task_id, new_seq) - §8 'lines reordered'
# (task_id, new parent_id or None back at top level) - §8 're-indented'
ParentUpdate = tuple[str, str | None]

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
    """Facts compute_sync found; wording them is output's job (C5, §8)."""

    new: tuple[PlanItem, ...]
    vanished: tuple[str, ...]  # task_ids whose line disappeared
    checked: tuple[str, ...]  # task_ids hand-marked [x] while todo
    reordered: tuple[SeqUpdate, ...]
    reparented: tuple[ParentUpdate, ...]
    regressed: tuple[str, ...]  # [ ] in file but doing/done in DB


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
    """Diff plan text against task rows, matched on title_hash (§8).

    Duplicate titles match by document order; a retitled line becomes a
    vanish + new pair (accepted v1 limitation). Orphaned rows never
    match (they left the plan). Pure and idempotent: applying the result
    and recomputing must find nothing - with one deferral: an existing
    task re-indented under a *new* parent has no parent id to report
    yet, so it shows up in `reparented` on the recompute after the new
    rows exist (sync applies, then recomputes once).
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
    pairs: dict[int, SimpleNamespace] = {}  # line_no -> (head, task, seq)
    for seq, plan_item in enumerate(plan_items, start=1):
        task = next(
            queues.get(title_hash(plan_item.title), iter(())),
            None,
        )
        if task is not None:
            pairs[plan_item.line_no] = SimpleNamespace(
                head=plan_item, task=task, seq=seq,
            )
    return SyncPlan(
        new=tuple(head for head in plan_items if head.line_no not in pairs),
        vanished=tuple(
            row.task_id
            for row in sorted(chain.from_iterable(queues.values()), key=BY_SEQ)
        ),
        checked=tuple(
            pair.task.task_id
            for pair in pairs.values()
            if pair.head.checkbox == CHECKED and pair.task.status == Status.TODO
        ),
        reordered=tuple(
            (pair.task.task_id, pair.seq)
            for pair in pairs.values()
            if pair.task.seq != pair.seq
        ),
        reparented=tuple(
            (
                pair.task.task_id,
                pairs.get(pair.head.parent_line, TOP).task.task_id,
            )
            for pair in pairs.values()
            if (pair.head.parent_line is None or pair.head.parent_line in pairs)
            and pairs.get(pair.head.parent_line, TOP).task.task_id
            != pair.task.parent_id
        ),
        regressed=tuple(
            pair.task.task_id
            for pair in pairs.values()
            if not pair.head.checkbox and pair.task.status in DB_WINS
        ),
    )


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
                name=(task.owner or '').rsplit('-', 1)[0],
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
