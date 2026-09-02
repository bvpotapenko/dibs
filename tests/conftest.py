"""Shared fixtures for the dibs test suite (ARCHITECTURE §11).

Tiers map to files, not directories (the lint config globs a flat
tests/): unit = test_records / test_names / test_planfile /
test_output, property = test_property_*, integration = test_store /
test_transitions / test_queries, end-to-end = test_cli.

Skeleton state: every test below the pure tier raises
NotImplementedError until its module lands (ARCHITECTURE §13); the
suite is red by design until then. Definition of done per module: its
tests green AND lint silent.

SQLite note: WAL mode needs a real file. Build DBs on tmp_path, never
sqlite3 ':memory:'.
"""

import pytest

NOW = 1_700_000_000  # fixed clock for deterministic tests

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
    tmp_path/'.plan.md.dibs' + ensure_schema; seed tasks from
    planfile.parse_plan; return Context(conn, plan, db, None, NOW).
    """
    raise NotImplementedError(
        'needs store + planfile (ARCHITECTURE §13 steps 2-3)',
    )


@pytest.fixture
def two_agents(board):
    """Register two identities on the board and return them.

    brave-otter-1111 and happy-elephant-2222, via
    transitions.register_agent (never raw INSERT - I1 applies to test
    setup too).
    """
    raise NotImplementedError(
        'needs transitions.register_agent (ARCHITECTURE §13 step 4)',
    )
