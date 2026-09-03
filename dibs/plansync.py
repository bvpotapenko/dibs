"""Author-side writes: the md->db direction of D4, one door (D24).

Level L3 (imports L0-L2: planfile for the diff, queries.board_snapshot
for the read taken under the write lock - C11). Member budget 2
(ARCHITECTURE §3). Same contract as transitions: one BEGIN IMMEDIATE
transaction per public function, rowcount truth (I1), one event per
mutation (I6, C3). SQL text with numbered placeholders only (C2).
"""

from sqlite3 import Connection

from dibs.planfile import PlanItem, SyncPlan


def found_board(conn: Connection, now: int, key: str, max_hand: int) -> bool:
    """Stamp board_key + max_hand once; False if already founded (D20, D6).

    UPDATE meta ... WHERE key = 'board_key' AND value = '' decides by
    rowcount (I1); the INIT event rides the same transaction (I6).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 7: plansync.found_board')


def apply_sync(
    conn: Connection,
    now: int,
    plan_items: tuple[PlanItem, ...],
    plan_mtime: int,
) -> SyncPlan:
    """Import plan text into the board in one transaction (SSoT §8, D24).

    Under the lock: board_snapshot -> compute_sync -> UPSERT every row
    (fresh rows inserted, matched rows' text-cached columns refreshed) ->
    orphan vanished -> import checked as done by 'human' -> one SYNC event
    -> stamp plan_mtime. Returns the SyncPlan it applied (C11).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 7: plansync.apply_sync')
