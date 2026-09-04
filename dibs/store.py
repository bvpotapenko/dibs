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

# Column order is load-bearing: it mirrors records.Task field order so
# `SELECT *` / `RETURNING *` rows build a Task positionally (L2 modules).
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

# Column order mirrors records.Event field order (same reason as tasks).
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

# Seeded once; OR IGNORE keeps values a later command has set (D6, I9).
META_SEED_SQL = 'INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)'
META_DEFAULTS = (
    ('board_key', ''),
    ('max_hand', '1'),
    ('plan_mtime', '0'),
    ('schema_version', '1'),
)

REGISTRY_DIR = Path('~/.local/state/dibs')  # D20; expanduser at use time
# The board file derives from its plan: errands.md -> .errands.md.dibs,
# so N plans in one directory get N isolated boards (D2). The glob finds
# them for the upward walk; WAL siblings (-wal, -shm) do not match it.
BOARD_FILE = '.{0}.dibs'
BOARD_GLOB = BOARD_FILE.format('*')
BOARD_HEAD, BOARD_TAIL = BOARD_FILE.split('{0}')  # a board name's two ends


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the board DB with every PRAGMAS entry applied (D2).

    Rows come back as sqlite3.Row: positional for record building,
    by name for the odd column peek.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for pragma in PRAGMAS:
        conn.execute(pragma)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the SSoT §5 tables; idempotent.

    Meta rows carried: board_key (D20), max_hand (D6), plan_mtime (I9),
    schema_version.
    """
    with conn:
        for ddl in SCHEMA:
            conn.execute(ddl)
        conn.executemany(META_SEED_SQL, META_DEFAULTS)


def registry_record(key: str, plan_path: Path) -> None:
    """Write key -> absolute plan path once under REGISTRY_DIR (D20).

    The registry is a cache of the board's own meta truth; it self-heals
    on drift whenever a path-addressed command runs (D20).
    """
    registry = REGISTRY_DIR.expanduser()
    registry.mkdir(parents=True, exist_ok=True)
    (registry / key).write_text(str(plan_path.resolve()))


def registry_lookup(key: str) -> Path | None:
    """Resolve a board key to its plan path, None if unknown/stale (D20)."""
    try:
        recorded = Path((REGISTRY_DIR.expanduser() / key).read_text().strip())
    except OSError:
        return None
    return recorded if recorded.is_file() else None
