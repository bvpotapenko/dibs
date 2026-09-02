"""SQLite bootstrap plus the board-key registry (D2, D20).

Level L1 (imports L0 + stdlib). Member budget 4 (ARCHITECTURE §3).
SQL text lives only in store/transitions/queries, placeholders only
(C2). DDL below is the SSoT §5 model made concrete; §5 is indicative,
so column changes go through SSoT first.
"""

import sqlite3
from pathlib import Path

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

SCHEMA_VERSION = '1'
MAX_HAND_DEFAULT = '1'  # SSoT §13; init --max-hand overrides (D6)

# Board facts seeded once; init and sync own their values afterwards, so
# the seed must never overwrite (D6, D20, I9).
META_DEFAULTS = (
    ('board_key', ''),
    ('max_hand', MAX_HAND_DEFAULT),
    ('plan_mtime', '0'),
    ('schema_version', SCHEMA_VERSION),
)

META_SEED = 'INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)'

REGISTRY_DIR = Path('~/.local/state/dibs')  # D20; expanduser at use time


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the board DB with every PRAGMAS entry applied (D2)."""
    conn = sqlite3.connect(db_path)
    for pragma in PRAGMAS:
        conn.execute(pragma)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the SSoT §5 tables; idempotent.

    Meta rows carried: board_key (D20), max_hand (D6), plan_mtime (I9),
    schema_version.
    """
    for table_ddl in SCHEMA:
        conn.execute(table_ddl)
    for meta_row in META_DEFAULTS:
        conn.execute(META_SEED, meta_row)
    conn.commit()


def registry_record(key: str, plan_path: Path) -> None:
    """Write key -> absolute plan path once under REGISTRY_DIR (D20).

    The registry is a cache of the board's own meta truth; it self-heals
    on drift whenever a path-addressed command runs (D20).
    """
    registry_dir = REGISTRY_DIR.expanduser()
    registry_dir.mkdir(parents=True, exist_ok=True)
    entry = registry_dir / key
    entry.write_text(str(plan_path.resolve()), encoding='utf-8')


def registry_lookup(key: str) -> Path | None:
    """Resolve a board key to its plan path, None if unknown/stale (D20)."""
    entry = REGISTRY_DIR.expanduser() / key
    if not entry.is_file():
        return None
    plan_path = Path(entry.read_text(encoding='utf-8').strip())
    return plan_path if plan_path.is_file() else None
