"""The DIBS_TRACE debugging lens: one JSON line per invocation (D23).

A lens, never a ledger: the events table stays the sole truth (D4,
I6); nothing ever reads a trace back, and a trace failure must never
change behavior, output, or exit codes - write_trace swallows its own
errors by contract. The env read itself stays in cli.py (C1); this
module only shapes paths and appends lines. Level L1, stdlib only.
Member budget 3 (ARCHITECTURE §3).
"""

from dataclasses import dataclass
from pathlib import Path

TRACE_DIR = '.logs'  # beside the plan; relative under CWD when unbound
UNBOUND_STEM = 'unbound'  # filename stem when no board resolved (D23)
OUTCOME_CAP = 200  # chars of reply/error text kept per trace line


@dataclass(frozen=True)
class TraceRecord:
    """One invocation's trace line - the stable schema debuggers read (D23)."""

    ts: int
    argv: tuple[str, ...]
    actor: str | None
    plan: str | None  # resolved plan path as posix str; None when unbound
    verb: str | None  # None when parsing failed before dispatch
    exit_code: int
    outcome: str  # first reply line or error message, <= OUTCOME_CAP


def trace_path(plan_path: Path | None, now: int) -> Path:
    """Shape .logs/<plan-name>.<UTC date>.jsonl beside the plan (D23).

    Unbound invocations fall back to the relative
    .logs/unbound.<UTC date>.jsonl so addressing failures stay visible.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 9: trace.trace_path')


def write_trace(path: Path, record: TraceRecord) -> None:
    """Append one JSON line, creating .logs/ as needed; never raise (D23)."""
    raise NotImplementedError('ARCHITECTURE §13 step 9: trace.write_trace')
