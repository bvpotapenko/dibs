"""Integration: store bootstrap + key registry on tmp DBs (§11, §13.2)."""

from dibs import store

BUSY_TIMEOUT_MS = 5000  # D2
TABLE_NAMES_SQL = "SELECT name FROM sqlite_master WHERE type = 'table'"
META_KEYS = frozenset(
    ('board_key', 'max_hand', 'plan_mtime', 'schema_version'),
)


def read_scalar(conn, sql):
    """First column of the first row of sql."""
    return conn.execute(sql).fetchone()[0]


def read_column(conn, sql):
    """First column of every row of sql, as a set."""
    return {row[0] for row in conn.execute(sql)}


def test_connect_applies_pragmas(tmp_path):
    """D2: journal_mode is WAL, busy_timeout 5000, foreign_keys on.

    Assert via PRAGMA reads on the returned connection, not by trusting
    store.PRAGMAS.
    """
    conn = store.connect(tmp_path / 'board.dibs')

    assert read_scalar(conn, 'PRAGMA journal_mode') == 'wal'
    assert read_scalar(conn, 'PRAGMA busy_timeout') == BUSY_TIMEOUT_MS
    assert read_scalar(conn, 'PRAGMA foreign_keys') == 1


def test_ensure_schema_is_idempotent(tmp_path):
    """SSoT §5: run twice; tables + meta keys present, no error.

    Meta keys: board_key, max_hand, plan_mtime, schema_version.
    """
    conn = store.connect(tmp_path / 'board.dibs')

    store.ensure_schema(conn)
    store.ensure_schema(conn)

    assert read_column(conn, TABLE_NAMES_SQL) >= {
        'tasks', 'agents', 'events', 'meta',
    }
    assert read_column(conn, 'SELECT key FROM meta') == META_KEYS
    assert read_scalar(conn, 'SELECT count(*) FROM meta') == len(META_KEYS)


def test_ensure_schema_keeps_existing_meta(tmp_path):
    """SSoT §5: a second call never overwrites board facts already set."""
    conn = store.connect(tmp_path / 'board.dibs')
    store.ensure_schema(conn)
    conn.execute(
        "UPDATE meta SET value = 'dibs-7f3a-9c2e' WHERE key = 'board_key'",
    )
    conn.commit()

    store.ensure_schema(conn)

    assert read_scalar(
        conn, "SELECT value FROM meta WHERE key = 'board_key'",
    ) == 'dibs-7f3a-9c2e'


def test_registry_record_and_lookup(tmp_path, monkeypatch):
    """D20: a recorded key resolves to the absolute plan path.

    Point REGISTRY_DIR at tmp_path via monkeypatch; never touch the
    real ~/.local/state/dibs.
    """
    monkeypatch.setattr(store, 'REGISTRY_DIR', tmp_path / 'state')
    plan = tmp_path / 'plan.md'
    plan.write_text('- [ ] a task\n', encoding='utf-8')

    store.registry_record('dibs-7f3a-9c2e', plan)

    assert store.registry_lookup('dibs-7f3a-9c2e') == plan.resolve()


def test_registry_lookup_unknown_is_none(tmp_path, monkeypatch):
    """D20: an unknown or stale key returns None, never raises."""
    monkeypatch.setattr(store, 'REGISTRY_DIR', tmp_path / 'state')
    plan = tmp_path / 'plan.md'
    plan.write_text('- [ ] a task\n', encoding='utf-8')
    store.registry_record('dibs-1111-2222', plan)
    plan.unlink()

    assert store.registry_lookup('dibs-0000-0000') is None
    assert store.registry_lookup('dibs-1111-2222') is None


def test_registry_self_heals_on_drift(tmp_path, monkeypatch):
    """D20: a stale entry is rewritten by a path-addressed command."""
    monkeypatch.setattr(store, 'REGISTRY_DIR', tmp_path / 'state')
    key = 'dibs-7f3a-9c2e'
    moved = []
    for name in ('old', 'new'):
        plan = tmp_path / name / 'plan.md'
        plan.parent.mkdir()
        plan.write_text('- [ ] a task\n', encoding='utf-8')
        moved.append(plan)
        store.registry_record(key, plan)

    assert store.registry_lookup(key) == moved[-1].resolve()
