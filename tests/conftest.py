"""Shared fixtures for the dibs test suite (ARCHITECTURE §11).

Tiers map to files, not directories (the lint config globs a flat
tests/): unit = test_records / test_runtime / test_names /
test_planfile / test_output, property = test_property_*,
integration = test_store / test_transitions / test_queries,
end-to-end = test_cli. Board building and raw peeks live in
tests/boards.py (importable under bare pytest via tests/__init__.py).

Every §13 step has landed, so no case raises NotImplementedError any
more: the suite is green by contract. Definition of done per module:
its tests green AND lint silent.

SQLite note: WAL mode needs a real file. Build DBs on tmp_path, never
sqlite3 ':memory:'.
"""

import pytest

from dibs import cli, store, transitions
from tests.boards import ELEPHANT, NOW, OTTER, build_board

# Exercises every SSoT §8 recognition rule: two sections, bodies,
# nested children (one bodiless - a verify-warning case), a hand [x],
# a doing line, and prose/bullets/numbers that must survive verbatim.
PLAN_TEXT = """# Demo corrections

Prose preamble that annotation must never touch.

## Parser

- [ ] Fix off-by-one in the tokenizer
  Repro: token count is 12 for fixtures/one.txt, expected 11.
  Done: count matches and the regression fixture passes.
- [ ] Ship the tokenizer regression suite
  Cover the cases below once both land.
  - [ ] Cover multi-byte input
    Body of a child task: paths, symptom, criterion.
  - [ ] Cover the empty file
- [x] Rename Lexer to Tokenizer

## Docs

The bullet below is prose, not a task:
- keep this line exactly as written

1. numbered lines are prose too

- [~ brave-otter] Update the README quickstart
  Body line for a doing task.
"""


@pytest.fixture
def plan_text() -> str:
    """Sample plan exercising the SSoT §8 recognition table."""
    return PLAN_TEXT


@pytest.fixture
def board(tmp_path, plan_text):
    """Initialized board on tmp_path -> runtime.Context (actor None).

    Build: write plan.md from plan_text; store.connect on
    tmp_path/'.plan.md.dibs' + ensure_schema; seed through
    plansync.apply_sync on the empty board, key left unfounded
    (tests/boards.build_board); return Context(conn, plan, db, None, NOW).
    """
    ctx = build_board(tmp_path, plan_text)
    yield ctx
    ctx.conn.close()


@pytest.fixture
def two_agents(board):
    """Register two identities on the board and return them.

    brave-otter-1111 and happy-elephant-2222, via
    transitions.register_agent (never raw INSERT - I1 applies to test
    setup too).
    """
    for agent in (OTTER, ELEPHANT):
        assert transitions.register_agent(board.conn, agent, NOW)
    return (OTTER, ELEPHANT)


@pytest.fixture
def make_board():
    """Board factory for purpose-built plans: make_board(root, text)."""
    return build_board


@pytest.fixture
def workspace(tmp_path, monkeypatch, plan_text):
    """A tmp CWD holding plan.md, with a private registry and clean env.

    The end-to-end fixture (§13 steps 10-11): the board-key registry
    (D20) is redirected into tmp_path so no test writes to the
    developer's ~/.local/state, and the three env bindings start unset
    so each case states its own (D8, D18, D23).
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, 'REGISTRY_DIR', tmp_path / 'registry')
    for binding in (cli.ENV_ACTOR, cli.ENV_BOARD, cli.ENV_TRACE):
        monkeypatch.delenv(binding, raising=False)
    (tmp_path / 'plan.md').write_text(plan_text)
    return tmp_path
