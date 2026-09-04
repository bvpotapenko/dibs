"""Test-side board building and raw peeks (ARCHITECTURE §11 fixtures).

Boards are seeded through production code: plansync.apply_sync on an
empty board, which is what init does minus founding the key (D24) - the
fixture stays unfounded so found_board can be exercised from its first
call. `settle`/`init_rows` are the pure tier's model of the same apply.
The reads are assertion peeks only; production reads live in queries.py.
`run_cli`/`key_of`/`joined` drive cli.main for the end-to-end tier.
"""

import dataclasses
import sqlite3
from pathlib import Path

from dibs import cli, planfile, plansync, store
from dibs.records import HUMAN, Agent, Status, Task
from dibs.runtime import Context

NOW = 1_700_000_000  # fixed clock for deterministic tests
KEY = 'dibs-7f3a-9c2e'  # the key set_max_hand founds the board with (D20)
OTTER = Agent(agent_id='brave-otter-1111', name='brave-otter')
ELEPHANT = Agent(agent_id='happy-elephant-2222', name='happy-elephant')

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
            owner=HUMAN,
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
    plansync.apply_sync(
        conn, NOW, planfile.parse_plan(text), plan_path.stat().st_mtime_ns,
    )
    return Context(conn, plan_path, db_path, None, NOW)


def resync(ctx: Context, text: str, now: int = NOW) -> planfile.SyncPlan:
    """Write text to the board's plan and apply it, as the pipeline does.

    The one import path (D24): an edited plan reaches the board through
    plansync.apply_sync, never through a raw UPDATE (ARCHITECTURE §11).
    """
    ctx.plan_path.write_text(text)
    return plansync.apply_sync(
        ctx.conn, now, planfile.parse_plan(text),
        ctx.plan_path.stat().st_mtime_ns,
    )


def set_max_hand(ctx: Context, size: int) -> None:
    """Found the board with a wider hand, as `init --max-hand N` does (D6)."""
    assert plansync.found_board(ctx.conn, NOW, KEY, size)


def run_cli(capsys, *argv: str) -> tuple[int, str, str]:
    """Drive one cli.main invocation; return (exit code, stdout, stderr)."""
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def key_of(printed: str) -> str:
    """The board key out of init's first line (D20)."""
    return printed.split('\n')[0].split()[1]


def joined(capsys) -> str:
    """Mint an identity through `join` and return the bare id (D8)."""
    code, identity, _ = run_cli(capsys, 'join')
    assert code == cli.EXIT_OK
    return identity.strip()


def peek_meta(ctx: Context, key: str) -> str:
    """One meta value as stored (TEXT)."""
    return ctx.conn.execute(
        'SELECT value FROM meta WHERE key = ?', (key,),
    ).fetchone()[0]


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
