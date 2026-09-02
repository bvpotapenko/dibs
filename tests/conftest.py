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

import hashlib
from dataclasses import astuple

import pytest

from dibs import planfile, store, transitions
from dibs.records import Agent, Status, Task
from dibs.runtime import Context

NOW = 1_700_000_000  # fixed clock for deterministic tests

SECTION_LETTERS = 'ABCDEFGH'  # SSoT §8 lettering, enough for any fixture
TOP_ID = '{0}{1}'  # section letter + ordinal, e.g. A3
CHILD_ID = '{0}.{1}'  # parent id + ordinal, e.g. A3.1
AUTHOR = 'human'  # SSoT §8: owner of a hand-checked [x]
HASH_BYTES = 4  # entropy taken per pick() draw

INSERT_TASK = """
INSERT INTO tasks (
    id, parent_id, seq, section, title, body, text_hash,
    status, owner, claimed_at, done_at, done_note
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

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


def insert_task(conn, task):
    """Write one task row.

    Stands in for the sync applier: ARCHITECTURE §5 gives no member that
    creates task rows, so test setup writes them directly. Flagged in
    the step-4 report; revisit when step 8 needs the real thing.
    """
    conn.execute(INSERT_TASK, astuple(task))
    conn.commit()


def plan_tasks(text):
    """Task rows for a plan, with SSoT §8 ids (A1, A2, A2.1, B1 ...)."""
    parsed = planfile.parse_plan(text)
    sections = tuple(dict.fromkeys(entry.section for entry in parsed))
    by_line = {}
    rows = []
    for entry in parsed:
        parent = by_line.get(entry.parent_line)
        kin = [
            task for task in rows
            if task.parent_id == parent and task.section == entry.section
        ]
        by_line[entry.line_no] = (
            CHILD_ID.format(parent, len(kin) + 1) if parent
            else TOP_ID.format(
                SECTION_LETTERS[sections.index(entry.section)], len(kin) + 1,
            )
        )
        rows.append(as_task(entry, by_line[entry.line_no], parent))
    return tuple(rows)


def as_task(entry, task_id, parent):
    """One parsed item as the row a sync applier would insert (§8)."""
    done = entry.checkbox == planfile.DONE_STATE
    return Task(
        task_id=task_id,
        parent_id=parent,
        seq=entry.line_no,
        section=entry.section,
        title=entry.title,
        body=entry.body,
        text_hash=planfile.title_hash(entry.title),
        status=Status.DONE if done else Status.TODO,
        owner=AUTHOR if done else None,
        claimed_at=None,
        done_at=None,
        done_note='checked by the plan author' if done else None,
    )


@pytest.fixture
def board(tmp_path, plan_text):
    """Initialized board on tmp_path -> runtime.Context (actor None).

    Build: write plan.md from plan_text; store.connect on
    tmp_path/'.plan.md.dibs' + ensure_schema; seed tasks from
    planfile.parse_plan; return Context(conn, plan, db, None, NOW).
    """
    plan_path = tmp_path / 'plan.md'
    plan_path.write_text(plan_text, encoding='utf-8')
    db_path = tmp_path / '.plan.md.dibs'
    conn = store.connect(db_path)
    store.ensure_schema(conn)
    for task in plan_tasks(plan_text):
        insert_task(conn, task)
    return Context(conn, plan_path, db_path, None, NOW)


@pytest.fixture
def two_agents(board):
    """Register two identities on the board and return them.

    brave-otter-1111 and happy-elephant-2222, via
    transitions.register_agent (never raw INSERT - I1 applies to test
    setup too).
    """
    pair = (
        Agent('brave-otter-1111', 'brave-otter'),
        Agent('happy-elephant-2222', 'happy-elephant'),
    )
    for agent in pair:
        transitions.register_agent(board.conn, agent)
    return pair
