"""Integration: store bootstrap + key registry on tmp DBs (§11, §13.2)."""


def test_connect_applies_pragmas(tmp_path):
    """D2: journal_mode is WAL, busy_timeout 5000, foreign_keys on.

    Assert via PRAGMA reads on the returned connection, not by trusting
    store.PRAGMAS.
    """
    raise NotImplementedError('needs store.connect (§13 step 2)')


def test_ensure_schema_is_idempotent(tmp_path):
    """SSoT §5: run twice; tables + meta keys present, no error.

    Meta keys: board_key, max_hand, plan_mtime, schema_version.
    """
    raise NotImplementedError('needs store.ensure_schema (§13 step 2)')


def test_registry_record_and_lookup(tmp_path, monkeypatch):
    """D20: a recorded key resolves to the absolute plan path.

    Point REGISTRY_DIR at tmp_path via monkeypatch; never touch the
    real ~/.local/state/dibs.
    """
    raise NotImplementedError('needs store.registry_* (§13 step 2)')


def test_registry_lookup_unknown_is_none(tmp_path, monkeypatch):
    """D20: an unknown or stale key returns None, never raises."""
    raise NotImplementedError('needs store.registry_lookup (§13 step 2)')


def test_registry_self_heals_on_drift(tmp_path, monkeypatch):
    """D20: a stale entry is rewritten by a path-addressed command."""
    raise NotImplementedError('needs store.registry_record (§13 step 2)')
