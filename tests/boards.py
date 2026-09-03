"""Test-side board building and raw peeks (ARCHITECTURE §11 fixtures).

The package has no member that inserts tasks, mints task IDs, or writes
meta rows (init/sync land at §13 step 8 and need a home first - see the
step 2-4 report). Until then tests seed boards here with raw SQL, and
the reads below are assertion peeks only; production reads live in
queries.py. Task IDs follow SSoT §8/§13: lettered section in order of
first appearance, ordinals per section, dotted children.
"""

import dataclasses
import sqlite3
from pathlib import Path
from string import ascii_uppercase

from dibs import planfile, store
from dibs.records import Agent, Status, Task
from dibs.runtime import Context

NOW = 1_700_000_000  # fixed clock for deterministic tests
OTTER = Agent(agent_id='brave-otter-1111', name='brave-otter')
ELEPHANT = Agent(agent_id='happy-elephant-2222', name='happy-elephant')

INSERT_TASK = 'INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
OPEN = (Status.TODO.value, Status.DOING.value)


def assign_ids(plan_items: tuple[planfile.PlanItem, ...]) -> dict[int, str]:
    """Map line_no -> would-be task id for a fresh board (SSoT §8, §13)."""
    letters: dict[str, str] = {}
    counters: dict[str, int] = {}
    ids: dict[int, str] = {}
    for plan_item in plan_items:
        letter = letters.setdefault(
            plan_item.section, ascii_uppercase[len(letters)],
        )
        prefix = letter
        if plan_item.parent_line is not None:
            parent = ids[plan_item.parent_line]
            prefix = f'{parent}.'
        counters[prefix] = counters.get(prefix, 0) + 1
        ordinal = counters[prefix]
        ids[plan_item.line_no] = f'{prefix}{ordinal}'
    return ids


def task_rows(plan_items: tuple[planfile.PlanItem, ...]) -> tuple[Task, ...]:
    """Pure Task rows as init would create them ([x] -> done by human)."""
    ids = assign_ids(plan_items)
    rows = []
    for seq, plan_item in enumerate(plan_items, start=1):
        checked = plan_item.checkbox == 'x'
        rows.append(Task(
            task_id=ids[plan_item.line_no],
            parent_id=ids.get(plan_item.parent_line),
            seq=seq,
            section=plan_item.section,
            title=plan_item.title,
            body=plan_item.body,
            text_hash=planfile.title_hash(plan_item.title),
            status=Status.DONE if checked else Status.TODO,
            owner='human' if checked else None,
            claimed_at=None,
            done_at=NOW if checked else None,
            done_note=None,
        ))
    return tuple(rows)


def build_board(root: Path, text: str) -> Context:
    """Write plan.md and a seeded board DB under root; actor is None."""
    root.mkdir(parents=True, exist_ok=True)
    plan = root / 'plan.md'
    plan.write_text(text)
    db_path = root / '.plan.md.dibs'
    conn = store.connect(db_path)
    store.ensure_schema(conn)
    with conn:
        conn.executemany(INSERT_TASK, [
            dataclasses.astuple(task)
            for task in task_rows(planfile.parse_plan(text))
        ])
    return Context(conn, plan, db_path, None, NOW)


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


def peek_tree(ctx: Context) -> list[sqlite3.Row]:
    """Every task row in seq order (the property tier's world model)."""
    return ctx.conn.execute('SELECT * FROM tasks ORDER BY seq').fetchall()
