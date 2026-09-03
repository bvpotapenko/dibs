"""Integration: store bootstrap + key registry on tmp DBs (§11, §13.2)."""

from contextlib import closing
from pathlib import Path

from dibs import store

META_KEYS = ('board_key', 'max_hand', 'plan_mtime', 'schema_version')
KEY = 'dibs-7f3a-9c2e'
BUSY_TIMEOUT_MS = 5000  # D2


def test_connect_applies_pragmas(tmp_path):
    """D2: journal_mode is WAL, busy_timeout 5000, foreign_keys on.

    Assert via PRAGMA reads on the returned connection, not by trusting
    store.PRAGMAS.
    """
    with closing(store.connect(tmp_path / '.plan.md.dibs')) as conn:
        assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        timeout = conn.execute('PRAGMA busy_timeout').fetchone()[0]
        assert timeout == BUSY_TIMEOUT_MS
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert (tmp_path / '.plan.md.dibs').is_file()


def test_ensure_schema_is_idempotent(tmp_path):
    """SSoT §5: run twice; tables + meta keys present, no error.

    Meta keys: board_key, max_hand, plan_mtime, schema_version.
    """
    with closing(store.connect(tmp_path / '.plan.md.dibs')) as conn:
        store.ensure_schema(conn)
        conn.execute("UPDATE meta SET value = '3' WHERE key = 'max_hand'")
        conn.commit()
        store.ensure_schema(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            )
        }
        assert {'tasks', 'agents', 'events', 'meta'} <= tables
        keys = conn.execute('SELECT key FROM meta ORDER BY key').fetchall()
        found = tuple(row[0] for row in keys)
        assert found == tuple(sorted(META_KEYS))
        max_hand = conn.execute(
            "SELECT value FROM meta WHERE key = 'max_hand'",
        ).fetchone()
        assert max_hand[0] == '3'  # a second run never resets values


def test_registry_record_and_lookup(tmp_path, monkeypatch):
    """D20: a recorded key resolves to the absolute plan path.

    Point REGISTRY_DIR at tmp_path via monkeypatch; never touch the
    real ~/.local/state/dibs.
    """
    monkeypatch.setattr(store, 'REGISTRY_DIR', tmp_path / 'state' / 'dibs')
    monkeypatch.chdir(tmp_path)
    plan = tmp_path / 'errands.md'
    plan.write_text('- [ ] buy milk\n')
    store.registry_record(KEY, Path('errands.md'))  # relative on purpose
    found = store.registry_lookup(KEY)
    assert found == plan.resolve()
    assert found.is_absolute()


def test_registry_lookup_unknown_is_none(tmp_path, monkeypatch):
    """D20: an unknown or stale key returns None, never raises."""
    monkeypatch.setattr(store, 'REGISTRY_DIR', tmp_path / 'state' / 'dibs')
    assert store.registry_lookup('dibs-0000-0000') is None  # no dir yet
    plan = tmp_path / 'gone.md'
    plan.write_text('- [ ] vanish\n')
    store.registry_record(KEY, plan)
    plan.unlink()
    assert store.registry_lookup(KEY) is None  # recorded, but stale
    assert store.registry_lookup('dibs-ffff-ffff') is None  # dir exists


def test_registry_self_heals_on_drift(tmp_path, monkeypatch):
    """D20: a stale entry is rewritten by a path-addressed command."""
    monkeypatch.setattr(store, 'REGISTRY_DIR', tmp_path / 'state' / 'dibs')
    old_home = tmp_path / 'old'
    new_home = tmp_path / 'new'
    old_home.mkdir()
    new_home.mkdir()
    plan = old_home / 'plan.md'
    plan.write_text('- [ ] move me\n')
    store.registry_record(KEY, plan)
    moved = plan.rename(new_home / 'plan.md')
    assert store.registry_lookup(KEY) is None
    store.registry_record(KEY, moved)  # what a --plan <path> command does
    assert store.registry_lookup(KEY) == moved.resolve()
