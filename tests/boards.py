"""Test-side board building and raw peeks (ARCHITECTURE §11 fixtures).

Boards are seeded through production code: the rows are
planfile.compute_sync(parse_plan(text), ()).rows - exactly what init
inserts (D24) - and hand-checked lines are imported through
transitions.import_author_done. The raw INSERT below is the one
sanctioned stand-in until plansync.apply_sync lands and takes both over
(§13 step 7). The reads are assertion peeks only; production reads live
in queries.py.
"""

import dataclasses
import sqlite3
from pathlib import Path

from dibs import planfile, store, transitions
from dibs.records import Agent, Status, Task
from dibs.runtime import Context

NOW = 1_700_000_000  # fixed clock for deterministic tests
OTTER = Agent(agent_id='brave-otter-1111', name='brave-otter')
ELEPHANT = Agent(agent_id='happy-elephant-2222', name='happy-elephant')

INSERT_TASK = 'INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
OPEN = (Status.TODO.value, Status.DOING.value)


def settle(
    plan: planfile.SyncPlan,
    tasks: tuple[Task, ...],
) -> tuple[Task, ...]:
    """Rows as apply_sync leaves them, minus the DB (the pure tier's oracle).

    plan.rows replace or add their ids, vanished rows turn orphaned, and
    checked ones import as done by 'human' at NOW (SSoT §8, D24).
    """
    by_id = {row.task_id: row for row in tasks}
    by_id.update((row.task_id, row) for row in plan.rows)
    for gone in plan.vanished:
        by_id[gone] = dataclasses.replace(by_id[gone], status=Status.ORPHANED)
    for ticked in plan.checked:
        by_id[ticked] = dataclasses.replace(
            by_id[ticked],
            status=Status.DONE,
            owner=transitions.HUMAN,
            done_at=NOW,
        )
    return tuple(by_id.values())


def init_rows(text: str) -> tuple[Task, ...]:
    """Task rows as init creates them: sync applied to an empty board (D24)."""
    return settle(planfile.compute_sync(planfile.parse_plan(text), ()), ())


def build_board(root: Path, text: str) -> Context:
    """Write plan.md and a seeded board DB under root; actor is None."""
    root.mkdir(parents=True, exist_ok=True)
    plan_path = root / 'plan.md'
    plan_path.write_text(text)
    db_path = root / '.plan.md.dibs'
    conn = store.connect(db_path)
    store.ensure_schema(conn)
    plan = planfile.compute_sync(planfile.parse_plan(text), ())
    with conn:
        conn.executemany(
            INSERT_TASK, [dataclasses.astuple(task) for task in plan.rows],
        )
    for task_id in plan.checked:
        transitions.import_author_done(conn, NOW, task_id)
    return Context(conn, plan_path, db_path, None, NOW)


def set_max_hand(ctx: Context, size: int) -> None:
    """Widen the per-board hand limit (init --max-hand stand-in, D6)."""
    with ctx.conn:
        ctx.conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'max_hand'", (str(size),),
        )


def orphan(ctx: Context, *task_ids: str) -> None:
    """Mark tasks orphaned as sync would after their lines vanished."""
    with ctx.conn:
        ctx.conn.executemany(
            "UPDATE tasks SET status = 'orphaned' WHERE id = ?",
            [(task_id,) for task_id in task_ids],
        )


def peek_task(ctx: Context, task_id: str) -> sqlite3.Row:
    """Read one task row for assertions."""
    return ctx.conn.execute(
        'SELECT * FROM tasks WHERE id = ?', (task_id,),
    ).fetchone()


def peek_events(ctx: Context, kind: str | None = None) -> list[sqlite3.Row]:
    """Read events in id order, optionally one kind only."""
    return ctx.conn.execute(
        'SELECT * FROM events WHERE ? IS NULL OR kind = ? ORDER BY id',
        (kind, kind),
    ).fetchall()


def held_ids(ctx: Context, actor: str) -> tuple[str, ...]:
    """Ids the actor currently holds (the hand-full steer's data, D6)."""
    rows = ctx.conn.execute(
        "SELECT id FROM tasks WHERE owner = ? AND status = 'doing'"
        ' ORDER BY seq',
        (actor,),
    ).fetchall()
    return tuple(row['id'] for row in rows)


def todo_ids(ctx: Context) -> tuple[str, ...]:
    """Ids still todo, gated or not (waiting-vs-empty steer data, D22)."""
    rows = ctx.conn.execute(
        "SELECT id FROM tasks WHERE status = 'todo' ORDER BY seq",
    ).fetchall()
    return tuple(row['id'] for row in rows)


def open_children(ctx: Context, task_id: str) -> tuple[str, ...]:
    """Children of task_id that are todo or doing (the gate, D22)."""
    rows = ctx.conn.execute(
        'SELECT id FROM tasks WHERE parent_id = ? AND status IN (?, ?)'
        ' ORDER BY seq',
        (task_id, *OPEN),
    ).fetchall()
    return tuple(row['id'] for row in rows)


def peek_cursor(ctx: Context, actor: str) -> int:
    """The actor's piggyback cursor, agents.last_event_seen (D10)."""
    return ctx.conn.execute(
        'SELECT last_event_seen FROM agents WHERE id = ?', (actor,),
    ).fetchone()[0]


def peek_tree(ctx: Context) -> list[sqlite3.Row]:
    """Every task row in seq order (the property tier's world model)."""
    return ctx.conn.execute('SELECT * FROM tasks ORDER BY seq').fetchall()
