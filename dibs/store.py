"""SQLite bootstrap plus the board-key registry (D2, D20).

Level L1 (imports L0 + stdlib). Member budget 4 (ARCHITECTURE §3).
SQL text lives only in store/transitions/queries, placeholders only
(C2). DDL below is the SSoT §5 model made concrete; §5 is indicative,
so column changes go through SSoT first.
"""

from pathlib import Path
from sqlite3 import Connection

PRAGMAS = (
    'PRAGMA journal_mode=WAL',
    'PRAGMA busy_timeout=5000',
    'PRAGMA foreign_keys=ON',
)

TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id         TEXT PRIMARY KEY,
    parent_id  TEXT,
    seq        INTEGER,
    section    TEXT,
    title      TEXT,
    body       TEXT,
    text_hash  TEXT,
    status     TEXT,
    owner      TEXT,
    claimed_at INTEGER,
    done_at    INTEGER,
    done_note  TEXT
)
"""

AGENTS_DDL = """
CREATE TABLE IF NOT EXISTS agents (
    id              TEXT PRIMARY KEY,
    name            TEXT UNIQUE,
    created_at      INTEGER,
    last_seen       INTEGER,
    last_event_seen INTEGER,
    last_section    TEXT
)
"""

EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       INTEGER,
    agent    TEXT,
    kind     TEXT,
    task_id  TEXT,
    to_agent TEXT,
    text     TEXT
)
"""

META_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
)
"""

SCHEMA = (TASKS_DDL, AGENTS_DDL, EVENTS_DDL, META_DDL)

REGISTRY_DIR = Path('~/.local/state/dibs')  # D20; expanduser at use time


def connect(db_path: Path) -> Connection:
    """Open the board DB with every PRAGMAS entry applied (D2)."""
    raise NotImplementedError('ARCHITECTURE §13 step 2: store.connect')


def ensure_schema(conn: Connection) -> None:
    """Create the SSoT §5 tables; idempotent.

    Meta rows carried: board_key (D20), max_hand (D6), plan_mtime (I9),
    schema_version.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 2: store.ensure_schema')


def registry_record(key: str, plan_path: Path) -> None:
    """Write key -> absolute plan path once under REGISTRY_DIR (D20).

    The registry is a cache of the board's own meta truth; it self-heals
    on drift whenever a path-addressed command runs (D20).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 2: store.registry_record')


def registry_lookup(key: str) -> Path | None:
    """Resolve a board key to its plan path, None if unknown/stale (D20)."""
    raise NotImplementedError('ARCHITECTURE §13 step 2: store.registry_lookup')
