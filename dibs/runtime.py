"""Execution plumbing shared by every layer (ARCHITECTURE §5).

Level L0: stdlib only at runtime; the guarded import below is a
type-only edge within L0, not a runtime dependency (ARCHITECTURE §4).
Member budget 3 (ARCHITECTURE §3).
"""

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dibs.records import Event


@dataclass(frozen=True)
class Context:
    """Per-invocation state; a verb receives (ctx, args), nothing more (C8)."""

    conn: Connection
    plan_path: Path
    db_path: Path
    actor: str | None
    now: int


@dataclass(frozen=True)
class Reply:
    """What a verb hands back for rendering by output/cli (C5, D14)."""

    lines: tuple[str, ...]
    events: 'tuple[Event, ...]'
    hint: str


class DibsError(Exception):
    """The one error type: message plus a runnable steer (C7, D14, I10)."""

    def __init__(self, message: str, steer: str) -> None:
        """Keep both channels; steer must be a literal next command (I10)."""
        super().__init__(message)
        self.message = message
        self.steer = steer
