"""Author-side writes: the md->db direction of D4, one door (D24).

Level L3 (imports L0-L2: planfile for the diff, queries.board_snapshot
for the read taken under the write lock - C11 - and views for the SYNC
body). Member budget 2 (ARCHITECTURE §3). Same contract as transitions:
one BEGIN IMMEDIATE transaction per public function, rowcount truth
(I1), one event per mutation (I6, C3). SQL text with numbered
placeholders only (C2).
"""

import json
from dataclasses import astuple
from sqlite3 import Connection

from dibs import planfile, queries, views
from dibs.records import HUMAN, EventKind

# Take the write lock up front so contention waits on busy_timeout (D2).
BEGIN = 'BEGIN IMMEDIATE'

# ?1 key - founds the board once: rowcount 0 = already founded (D20, I1)
FOUND_SQL = "UPDATE meta SET value = ?1 WHERE key = 'board_key' AND value = ''"
# ?1 max_hand as TEXT (D6)
MAX_HAND_SQL = "UPDATE meta SET value = ?1 WHERE key = 'max_hand'"
# ?1 st_mtime_ns as TEXT - the plan as last synced (I9)
MTIME_SQL = "UPDATE meta SET value = ?1 WHERE key = 'plan_mtime'"
# (ts, agent, kind, task_id, to_agent, text) in that order
EVENT_SQL = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
VALUES (?, ?, ?, ?, ?, ?)
"""
# Every records.Task field in DDL order; a known id refreshes ONLY the
# text-cached columns, never a state column (C11, D4)
UPSERT_SQL = """
INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (id) DO UPDATE SET
    parent_id = excluded.parent_id,
    seq = excluded.seq,
    section = excluded.section,
    title = excluded.title,
    body = excluded.body
"""
# ?1 ids as a JSON array - lines that left the plan; rows stay (§8, I5)
ORPHAN_SQL = """
UPDATE tasks SET status = 'orphaned'
WHERE id IN (SELECT value FROM json_each(?1))
"""
# ?1 now  ?2 ids as a JSON array - hand-checked lines (§8): their rows
# already say done by human (compute_sync); this stamps the clock. The
# list is exact under the lock (C11), so no WHERE guard is needed.
IMPORT_SQL = """
UPDATE tasks SET status = 'done', owner = 'human', done_at = ?1
WHERE id IN (SELECT value FROM json_each(?2))
"""
# ?1 now  ?2 the same ids - one DONE event per import (I6, C3)
IMPORT_EVENTS_SQL = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
SELECT ?1, 'human', 'done', value, NULL, '' FROM json_each(?2)
"""


def found_board(conn: Connection, now: int, key: str, max_hand: int) -> bool:
    """Stamp board_key + max_hand once; False if already founded (D20, D6).

    UPDATE meta ... WHERE key = 'board_key' AND value = '' decides by
    rowcount (I1); the INIT event rides the same transaction (I6).
    """
    with conn:
        conn.execute(BEGIN)
        founded = conn.execute(FOUND_SQL, (key,)).rowcount
        if not founded:
            return False
        conn.execute(MAX_HAND_SQL, (str(max_hand),))
        conn.execute(
            EVENT_SQL, (now, HUMAN, EventKind.INIT.value, None, None, key),
        )
    return True


def apply_sync(
    conn: Connection,
    now: int,
    plan_items: tuple[planfile.PlanItem, ...],
    plan_mtime: int,
) -> planfile.SyncPlan:
    """Import plan text into the board in one transaction (SSoT §8, D24).

    Under the lock: board_snapshot -> compute_sync -> UPSERT every row
    (fresh rows inserted whole, matched rows' text-cached columns
    refreshed) -> orphan vanished -> stamp done_at on checked, one DONE
    event each -> one SYNC event carrying views.format_sync -> stamp
    plan_mtime. Returns the SyncPlan it applied (C11).
    """
    with conn:
        conn.execute(BEGIN)
        plan = planfile.compute_sync(
            plan_items, queries.board_snapshot(conn).tasks,
        )
        conn.executemany(UPSERT_SQL, [astuple(row) for row in plan.rows])
        conn.execute(ORPHAN_SQL, (json.dumps(plan.vanished),))
        conn.execute(IMPORT_SQL, (now, json.dumps(plan.checked)))
        conn.execute(IMPORT_EVENTS_SQL, (now, json.dumps(plan.checked)))
        conn.execute(EVENT_SQL, (
            now, HUMAN, EventKind.SYNC.value, None, None,
            '\n'.join(views.format_sync(plan)),
        ))
        conn.execute(MTIME_SQL, (str(plan_mtime),))
    return plan
