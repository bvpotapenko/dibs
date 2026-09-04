"""The DIBS_TRACE debugging lens: one JSON line per invocation (D23).

A lens, never a ledger: the events table stays the sole truth (D4,
I6); nothing ever reads a trace back, and a trace failure must never
change behavior, output, or exit codes - write_trace swallows its own
errors by contract. The env read itself stays in cli.py (C1); this
module only shapes paths and appends lines. Level L1, stdlib only.
Member budget 3 (ARCHITECTURE §3).
"""

import json
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

TRACE_DIR = '.logs'  # beside the plan; relative under CWD when unbound
UNBOUND_STEM = 'unbound'  # filename stem when no board resolved (D23)
OUTCOME_CAP = 200  # chars of reply/error text kept per trace line
DAY = '%Y-%m-%d'  # one file per UTC day, from the invocation's own clock
LINE = '{0}.{1}.jsonl'  # <plan-name>.<UTC date>.jsonl (D23)


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
    day = datetime.fromtimestamp(now, tz=timezone.utc).strftime(DAY)
    beside = plan_path.parent if plan_path else Path()
    stem = plan_path.stem if plan_path else UNBOUND_STEM
    return beside / TRACE_DIR / LINE.format(stem, day)


def write_trace(path: Path, record: TraceRecord) -> None:
    """Append one JSON line, creating .logs/ as needed; never raise (D23).

    Best-effort by contract: a lens that changed behavior would be a
    ledger. Every failure - unwritable directory, full disk, a path
    taken by a file - is swallowed here, never above (D23, I6).
    """
    line = json.dumps({
        **asdict(record), 'outcome': record.outcome[:OUTCOME_CAP],
    })
    with suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as journal:
            journal.write(f'{line}\n')
