"""Shared fixtures for the dibs test suite (ARCHITECTURE §11).

Tiers map to files, not directories (the lint config globs a flat
tests/): unit = test_records / test_names / test_planfile /
test_output / test_views, property = test_property_*, integration =
test_store / test_transitions / test_plansync / test_queries,
end-to-end = test_cli.

Skeleton state: every test below the pure tier raises
NotImplementedError until its module lands (ARCHITECTURE §13); the
suite is red by design until then. Definition of done per module: its
tests green AND lint silent.

SQLite note: WAL mode needs a real file. Build DBs on tmp_path, never
sqlite3 ':memory:'.
"""

import hashlib
import os

import pytest

from dibs import planfile, plansync, store, transitions
from dibs.records import Agent
from dibs.runtime import Context

NOW = 1_700_000_000  # fixed clock for deterministic tests

AUTHOR = 'human'  # SSoT §8: owner of a hand-checked [x]
HASH_BYTES = 4  # entropy taken per pick() draw
BOARD = 'dibs-7f3a-9c2e'  # the fixture board's key (D20 shape)
ONE_HAND = 1  # store.MAX_HAND_DEFAULT; widen per test via set_hand
FIRST_STAMP = 1_000_000_000  # plan mtime in ns; resync bumps it
BOARD_FILE = '.{0}.dibs'  # the board beside its plan (D2)

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


def pick(seed, index, size):
    """Deterministic index from (seed, index) - no PRNG module needed.

    ruff's bandit bundle flags the random module for non-crypto use
    (S311) and tests ignore only S101/D, so the property tiers draw
    their seeded entropy from sha256 instead. Determinism is the only
    property they need.
    """
    digest = hashlib.sha256(bytes((seed, index))).digest()
    return int.from_bytes(digest[:HASH_BYTES], 'big') % size


def resync(ctx, text, stamp):
    """Rewrite the plan and apply it the way every command does (I9).

    The mtime is set explicitly: two writes inside one clock tick would
    share a stamp and the CAS would (correctly) skip the second.
    """
    ctx.plan_path.write_text(text, encoding='utf-8')
    os.utime(ctx.plan_path, ns=(stamp, stamp))
    return plansync.apply_sync(
        ctx.conn,
        NOW,
        planfile.parse_plan(text),
        str(ctx.plan_path.stat().st_mtime_ns),
    )


def open_plan(tmp_path, text, name='plan.md'):
    """A board built exactly the way init builds one (§11, §6).

    store.connect + ensure_schema, then the pipeline's own sync, then
    the board-key CAS - no test-only writer of task rows exists any
    more (ARCHITECTURE §13 step 8a).
    """
    plan_path = tmp_path / name
    db_path = tmp_path / BOARD_FILE.format(name)
    ctx = Context(store.connect(db_path), plan_path, db_path, None, NOW)
    store.ensure_schema(ctx.conn)
    resync(ctx, text, FIRST_STAMP)
    plansync.open_board(ctx.conn, NOW, BOARD, ONE_HAND)
    return ctx


@pytest.fixture
def board(tmp_path, plan_text):
    """Initialized board on tmp_path -> runtime.Context (actor None)."""
    return open_plan(tmp_path, plan_text)


@pytest.fixture
def two_agents(board):
    """Register two identities on the board and return them.

    brave-otter-1111 and happy-elephant-2222, via
    transitions.register_agent (never raw INSERT - I1 applies to test
    setup too). Registered after the board opened, so both cursors
    start above the roster a fresh init writes (§9 SSoT).
    """
    pair = (
        Agent('brave-otter-1111', 'brave-otter'),
        Agent('happy-elephant-2222', 'happy-elephant'),
    )
    for agent in pair:
        transitions.register_agent(board.conn, agent)
    return pair
