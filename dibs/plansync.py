"""Author-side writes: the plan -> board direction of D4.

One transaction each, first statement a compare-and-swap, outcome from
rowcounts alone (I1, C3). Level L2 (imports L0-L1; calls
planfile.compute_sync inside the write lock). Member budget 2
(ARCHITECTURE §3). SQL text with placeholders only (C2).

This is the half of the old transitions module that speaks for the plan
author rather than a worker, so the author's identity and the note a
hand-checked [x] carries live here (SSoT §5, §8).
"""

from sqlite3 import Connection

from dibs import planfile
from dibs.output import BOARD_EXISTS, SYNC_BOARD
from dibs.records import Event, EventKind, Task
from dibs.runtime import DibsError
from dibs.store import BOARD_KEY, read_meta

AUTHOR = 'human'  # SSoT §5: the actor behind every plan-file change
AUTHOR_DONE_NOTE = 'checked by the plan author'  # planfile renders it

# Nothing found, nothing changed: what the mtime CAS returns when this
# file version is already applied (SSoT §6 sync row).
EMPTY_SYNC = planfile.SyncPlan((), (), (), (), (), (), ())

# init is a compare-and-swap on the stored key: the seed is '', so the
# first init wins and a second one finds a key and is refused (I1, §6).
OPEN_CAS = """
UPDATE meta SET value = ?
WHERE key = 'board_key' AND value = ''
"""

SET_HAND = "UPDATE meta SET value = ? WHERE key = 'max_hand'"

INIT_EVENT = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
VALUES (?, ?, ?, NULL, NULL, ?)
RETURNING *
"""

# The whole of sync's concurrency control: has the plan changed, and am
# I the one applying it? Zero rows means this version is already applied
# or a concurrent sync won. The UPDATE also takes SQLite's write lock,
# so the compute-then-apply below is serialized against every other
# writer - not check-then-act (C9, I1, I9).
STAMP_CAS = """
UPDATE meta SET value = ?
WHERE key = 'plan_mtime' AND value <> ?
"""

SNAPSHOT = 'SELECT * FROM tasks ORDER BY seq'

# Orphaned, not deleted, and the owner stays on the row for the record
# (I5, SSoT §8 'line vanished').
ORPHAN_ROW = "UPDATE tasks SET status = 'orphaned' WHERE id = ?"

# The DB wins over a hand-written [x]: the WHERE is the guard, and the
# write lock this transaction holds means the snapshot's todo rows are
# still todo here - every listed row imports (SSoT §8, I1).
IMPORT_DONE = """
UPDATE tasks SET
    status = 'done', owner = ?, done_at = ?, done_note = ?
WHERE id = ? AND status = 'todo'
"""

RESEQUENCE = 'UPDATE tasks SET seq = ? WHERE id = ?'

# ID minting, SSoT §8, computed inside the lock. Top level: the letter
# this section's rows already carry, else the next one after the highest
# in use ('A' on a fresh board); the ordinal counts rows EVER created
# under that letter, orphans included, so an id is never reused (I5). A
# child is '<parent id>.<n>', counted the same way. 'The live row at
# seq' is one row by the seq invariant (records.Task) - reordering has
# already put every matched row on its own line, and orphaned rows keep
# a stale seq and are excluded. New rows arrive in document order, so a
# parent line created in this same pass is already on the board when its
# child looks that line up.
CREATE_TASK = """
INSERT INTO tasks (
    id, parent_id, seq, section, title, body, text_hash,
    status, owner, claimed_at, done_at, done_note
)
SELECT
    CASE WHEN parent.id IS NULL
        THEN mint.letter || (
            SELECT count(*) + 1 FROM tasks top
            WHERE substr(top.id, 1, 1) = mint.letter
              AND instr(top.id, '.') = 0
        )
        ELSE parent.id || '.' || (
            SELECT count(*) + 1 FROM tasks kin
            WHERE substr(kin.id, 1, length(parent.id) + 1)
                  = parent.id || '.'
              AND instr(substr(kin.id, length(parent.id) + 2), '.') = 0
        )
    END,
    parent.id, :line, :section, :title, :body, :hash,
    CASE WHEN :checkbox = 'x' THEN 'done' ELSE 'todo' END,
    CASE WHEN :checkbox = 'x' THEN :author END,
    NULL,
    CASE WHEN :checkbox = 'x' THEN :now END,
    CASE WHEN :checkbox = 'x' THEN :note END
FROM
    (SELECT (
        SELECT live.id FROM tasks live
        WHERE live.seq = :parent_line AND live.status <> 'orphaned'
    ) AS id) AS parent,
    (SELECT COALESCE(
        (SELECT substr(id, 1, 1) FROM tasks
         WHERE section = :section AND instr(id, '.') = 0 LIMIT 1),
        char(COALESCE(
            (SELECT unicode(max(substr(id, 1, 1))) FROM tasks
             WHERE instr(id, '.') = 0),
            unicode('A') - 1
        ) + 1)
    ) AS letter) AS mint
"""

# A line, not an id: the new parent may be a row this same pass created
# (planfile.ParentUpdate). A NULL line lands the row back at top level.
REPARENT = """
UPDATE tasks SET parent_id = (
    SELECT live.id FROM tasks live
    WHERE live.seq = ? AND live.status <> 'orphaned'
)
WHERE id = ?
"""

# Text truth flowing md -> db, so no event: the plan file is this
# change's own journal (D4, I6).
REFRESH_TEXT = 'UPDATE tasks SET body = ?, section = ? WHERE id = ?'

# One event per row whose STATE changed (I6). The row carries its own
# title, so a caller names either the id it already knows or - for a row
# this pass created, whose id was minted in SQL - the line it sits on.
SYNC_EVENT = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
SELECT ?, ?, ?, changed.id, NULL, COALESCE(?, changed.title)
FROM tasks changed
WHERE changed.id = COALESCE(?, (
    SELECT live.id FROM tasks live
    WHERE live.seq = ? AND live.status <> 'orphaned'
))
"""


def open_board(
    conn: Connection,
    now: int,
    key: str,
    max_hand: int,
) -> Event:
    """Claim this plan's board for a minted key, once (D20, I1, SSoT §6).

    Zero rows from the CAS means the board is already open, so init is
    refused with the existing key in its steer. Task rows are none of
    this function's business: they arrive through apply_sync, which the
    pipeline runs for init exactly as for every other verb.
    """
    if not conn.execute(OPEN_CAS, (key,)).rowcount:
        raise DibsError(
            BOARD_EXISTS, SYNC_BOARD.format(read_meta(conn, BOARD_KEY)),
        )
    conn.execute(SET_HAND, (max_hand,))
    opened = conn.execute(
        INIT_EVENT, (now, AUTHOR, EventKind.INIT.value, key),
    ).fetchone()
    conn.commit()
    return Event(*opened)


def apply_sync(
    conn: Connection,
    now: int,
    plan_items: tuple[planfile.PlanItem, ...],
    stamp: str,
) -> planfile.SyncPlan:
    """Reconcile plan text with the board, one stamped transaction (§6).

    The mtime CAS goes first: zero rows means this file version is
    already applied (or a concurrent sync won) and nothing else happens,
    so the unchanged-file case every command pays for costs one UPDATE
    (I9). Everything below runs under the write lock it took (I1).
    """
    if not conn.execute(STAMP_CAS, (stamp, stamp)).rowcount:
        conn.commit()
        return EMPTY_SYNC
    rows = tuple(Task(*row) for row in conn.execute(SNAPSHOT))
    plan = planfile.compute_sync(plan_items, rows)
    # ARCHITECTURE §5 fixes this order, and the order is the contract:
    # orphan and import first, then seq - so every live row sits on its
    # own line - then the new rows, whose parent is resolved through
    # that seq, then the moves, the text refreshes and the journal.
    for statement, binds in (
        (ORPHAN_ROW, [(gone,) for gone in plan.vanished]),
        (IMPORT_DONE, [
            (AUTHOR, now, AUTHOR_DONE_NOTE, hand)
            for hand in plan.checked
        ]),
        # Both statements bind (line, task); the SyncPlan pairs read
        # (task, line), so each pair goes in reversed.
        (RESEQUENCE, [tuple(reversed(move)) for move in plan.reordered]),
        (CREATE_TASK, [
            {
                'line': entry.line_no,
                'parent_line': entry.parent_line,
                'section': entry.section,
                'title': entry.title,
                'body': entry.body,
                'hash': planfile.title_hash(entry.title),
                'checkbox': entry.checkbox,
                'author': AUTHOR,
                'now': now,
                'note': AUTHOR_DONE_NOTE,
            }
            for entry in plan.new
        ]),
        (REPARENT, [tuple(reversed(move)) for move in plan.reparented]),
        # (task, body, section) rebound as (body, section, task).
        (REFRESH_TEXT, [
            (*reword[1:], reword[0]) for reword in plan.refreshed
        ]),
        (SYNC_EVENT, [
            (now, AUTHOR, EventKind.ORPHAN.value, None, gone, None)
            for gone in plan.vanished
        ] + [
            (now, AUTHOR, EventKind.DONE.value, AUTHOR_DONE_NOTE, hand, None)
            for hand in plan.checked
        ] + [
            (now, AUTHOR, EventKind.SYNC.value, None, None, entry.line_no)
            for entry in plan.new
        ]),
    ):
        conn.executemany(statement, binds)
    conn.commit()
    return plan
