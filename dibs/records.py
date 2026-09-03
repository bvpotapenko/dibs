"""Domain rows: frozen dataclasses and str-enums (SSoT §5).

Data here, behavior in module functions; no methods, no inheritance
beyond Enum (ARCHITECTURE §1). Level L0: stdlib only. Member budget 7 -
the one function, agent_name, is the id-to-name idiom that three render
sites share (ARCHITECTURE §3).
"""

from dataclasses import dataclass
from enum import Enum

HUMAN = 'human'  # the plan author as an actor (SSoT §5, §8)


class Status(str, Enum):
    """Task lifecycle states as stored in tasks.status (SSoT §5)."""

    TODO = 'todo'
    DOING = 'doing'
    DONE = 'done'
    ORPHANED = 'orphaned'


class EventKind(str, Enum):
    """Journal kinds as stored in events.kind (SSoT §5, I6)."""

    INIT = 'init'
    SYNC = 'sync'
    JOIN = 'join'
    CLAIM = 'claim'
    DONE = 'done'
    DROP = 'drop'
    NOTE = 'note'
    REAP = 'reap'


@dataclass(frozen=True)
class Task:
    """One checkbox line's state row (SSoT §5 tasks; D4, D22, I5)."""

    task_id: str
    parent_id: str | None
    seq: int
    section: str
    title: str
    body: str
    text_hash: str
    status: Status
    owner: str | None
    claimed_at: int | None
    done_at: int | None
    done_note: str | None


@dataclass(frozen=True)
class Event:
    """One append-only journal row (SSoT §5 events; D10, I6)."""

    event_id: int
    ts: int
    agent: str
    kind: EventKind
    task_id: str | None
    to_agent: str | None
    text: str


@dataclass(frozen=True)
class Agent:
    """One minted per-board identity (SSoT §5 agents, §7, D8)."""

    agent_id: str
    name: str


@dataclass(frozen=True)
class Board:
    """One read of the board: meta facts, rows in seq order, recent events.

    Born whole in queries.board_snapshot (ARCHITECTURE §5); key is ''
    until init founds the board (D20, D24).
    """

    key: str
    max_hand: int
    plan_mtime: int
    tasks: tuple[Task, ...]
    events: tuple[Event, ...]


def agent_name(agent_id: str | None) -> str:
    """Display name of an id: 'happy-elephant-4821' -> 'happy-elephant' (I7).

    'human' and 'system' pass through; None renders as '' (SSoT §5, §7).
    """
    return (agent_id or '').rsplit('-', 1)[0]
