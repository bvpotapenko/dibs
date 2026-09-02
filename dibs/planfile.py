"""Pure plan-text functions: text in, records out (C4).

No I/O, no DB, no clock; file reads/writes happen in verbs (C4).
Level L1 (imports L0). Member budget 6 (ARCHITECTURE §3).
Recognition and annotation grammar: SSoT §8; nesting: D22.
"""

import re
from dataclasses import dataclass

from dibs.records import Task

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
    raise NotImplementedError('ARCHITECTURE §13 step 3: parse_plan')


def compute_sync(
    plan_items: tuple[PlanItem, ...],
    tasks: tuple[Task, ...],
) -> SyncPlan:
    """Diff plan text against task rows, matched on title_hash (§8).

    Duplicate titles match by document order; a retitled line becomes a
    vanish + new pair (accepted v1 limitation). Pure and idempotent:
    applying the result and recomputing must find nothing.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 3: compute_sync')


def annotate_lines(text: str, tasks: tuple[Task, ...]) -> str:
    """Rewrite ONLY annotation-grammar lines; keep every other byte (I4)."""
    raise NotImplementedError('ARCHITECTURE §13 step 3: annotate_lines')


def title_hash(title: str) -> str:
    """Hash the lowercased, whitespace-collapsed title (SSoT §8 sync)."""
    raise NotImplementedError('ARCHITECTURE §13 step 3: title_hash')
