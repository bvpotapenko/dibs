"""Read-side queries; deliver_events also advances the cursor (D10).

Level L2 (imports L0-L1). Member budget 7 - at the cap, split seam in
ARCHITECTURE §3. SQL text with placeholders only (C2); misses steer via
output.steer (C5, C7, I10). Rows are sqlite3.Row in records field order
(store DDL), so a record is built positionally and its str-enum column
coerced; a refusal is picked by one CASE and named by one query (C9).
"""

import json
from dataclasses import replace
from itertools import starmap
from sqlite3 import Connection
from string import ascii_uppercase, digits
from types import MappingProxyType

from dibs import output
from dibs.records import Board, Event, EventKind, Status, Task

# Take the write lock up front: the cursor advance rides the read (D2).
BEGIN = 'BEGIN IMMEDIATE'
# A deferred transaction: one snapshot for a two-statement read, no lock.
BEGIN_READ = 'BEGIN'
ID_TAIL = f'{digits}.'  # what follows the letters of an id (SSoT §13)

META_SQL = 'SELECT key, value FROM meta'
TASKS_SQL = 'SELECT * FROM tasks ORDER BY seq'
# ?1 cap - the newest ?1 events, oldest first (Board.events)
RECENT_EVENTS_SQL = """
SELECT * FROM (SELECT * FROM events ORDER BY id DESC LIMIT ?1) ORDER BY id
"""

# ?1 actor - unseen: past the cursor, broadcast or addressed to the
# actor, never the actor's own (D10); NULL or unknown actor gets nothing
UNSEEN_SQL = """
SELECT * FROM events
WHERE id > (SELECT last_event_seen FROM agents WHERE id = ?1)
  AND (to_agent IS NULL OR to_agent = ?1)
  AND agent != ?1
ORDER BY id
"""
# ?1 actor - the cursor jumps to the newest event, skipped ones included
CURSOR_SQL = """
UPDATE agents SET last_event_seen = (SELECT MAX(id) FROM events)
WHERE id = ?1
"""

# ?1 task_id - the last reap on it (SSoT §6 claim row)
PRIOR_SQL = """
SELECT * FROM events WHERE kind = 'reap' AND task_id = ?1
ORDER BY id DESC LIMIT 1
"""

# ?1 raw - exact, case tolerated (D14)
EXACT_SQL = 'SELECT * FROM tasks WHERE id = UPPER(?1)'
# ?1 raw  ?2 letters  ?3 ID_TAIL - the id to suggest: the same ordinal
# in another section (B7 -> A7), else the same letters by ordinal
# distance (A9 -> A3), else document order; the raw text on an empty board
NEAREST_SQL = """
SELECT COALESCE((
    SELECT id FROM tasks
    ORDER BY (LTRIM(id, ?2) = LTRIM(UPPER(?1), ?2)) DESC,
             (RTRIM(id, ?3) = RTRIM(UPPER(?1), ?3)) DESC,
             ABS(
                 CAST(LTRIM(id, ?2) AS INTEGER)
                 - CAST(LTRIM(UPPER(?1), ?2) AS INTEGER)
             ),
             seq
    LIMIT 1
), ?1)
"""

# ?1 actor
ACTOR_SQL = 'SELECT 1 FROM agents WHERE id = ?1'

# ?1 task_id - its parent, when todo and no longer gated (D22, D7)
UNLOCKED_SQL = """
SELECT parent.* FROM tasks AS parent
WHERE parent.id = (SELECT parent_id FROM tasks WHERE id = ?1)
  AND parent.status = 'todo'
  AND NOT EXISTS (
      SELECT 1 FROM tasks AS child
      WHERE child.parent_id = parent.id
        AND child.status IN ('todo', 'doing')
  )
"""

# :actor  :bundle (JSON array, NULL = next available)  :size (1 when
# NULL). Why claim returned zero rows, most specific first, mirroring
# CLAIM_SQL's WHERE (C9): a member no longer todo, a member with open
# children, a bundle no hand could take, the hand full, then whether any
# todo row is left at all.
REFUSAL_SQL = """
SELECT CASE
    WHEN EXISTS (
        SELECT 1 FROM tasks
        WHERE id IN (SELECT value FROM json_each(:bundle))
          AND status != 'todo'
    ) THEN 'taken'
    WHEN EXISTS (
        SELECT 1 FROM tasks AS gate
        WHERE gate.id IN (SELECT value FROM json_each(:bundle))
          AND EXISTS (
              SELECT 1 FROM tasks AS child
              WHERE child.parent_id = gate.id
                AND child.status IN ('todo', 'doing')
          )
    ) THEN 'gated'
    WHEN :size > (
        SELECT CAST(value AS INTEGER) FROM meta WHERE key = 'max_hand'
    ) THEN 'oversized'
    WHEN (
        SELECT COUNT(*) FROM tasks WHERE owner = :actor AND status = 'doing'
    ) + :size > (
        SELECT CAST(value AS INTEGER) FROM meta WHERE key = 'max_hand'
    ) THEN 'hand_full'
    WHEN EXISTS (SELECT 1 FROM tasks WHERE status = 'todo') THEN 'waiting'
    ELSE 'empty'
END
"""

# The names each refusal's steer needs, one row each, same bindings plus
# :sep (output.LIST_SEP) - slot order per output.CATALOG entry.
# TAKEN: (member, holder name - 'human' for imports, status if unowned)
TAKEN_SQL = """
SELECT tasks.id, COALESCE(agents.name, tasks.owner, tasks.status)
FROM tasks LEFT JOIN agents ON agents.id = tasks.owner
WHERE tasks.id IN (SELECT value FROM json_each(:bundle))
  AND tasks.status != 'todo'
ORDER BY tasks.seq
LIMIT 1
"""
# GATED: (parent, its open children, the first still-todo child)
GATED_SQL = """
WITH gate AS (
    SELECT id FROM tasks
    WHERE id IN (SELECT value FROM json_each(:bundle))
      AND EXISTS (
          SELECT 1 FROM tasks AS child
          WHERE child.parent_id = tasks.id
            AND child.status IN ('todo', 'doing')
      )
    ORDER BY seq
    LIMIT 1
),
open_children AS (
    SELECT id, status, seq FROM tasks
    WHERE parent_id = (SELECT id FROM gate)
      AND status IN ('todo', 'doing')
)
SELECT (SELECT id FROM gate),
       (
           SELECT group_concat(id, :sep)
           FROM (SELECT id FROM open_children ORDER BY seq)
       ),
       (
           SELECT id FROM open_children
           ORDER BY (status = 'todo') DESC, seq
           LIMIT 1
       )
"""
# OVERSIZED: (bundle size, max_hand, the first member as typed)
OVERSIZED_SQL = """
SELECT CAST(:size AS TEXT),
       (SELECT value FROM meta WHERE key = 'max_hand'),
       (SELECT value FROM json_each(:bundle) ORDER BY key LIMIT 1)
"""
# HAND_FULL: (held ids, first held id, max_hand) - the CASE guarantees a
# held row: the bundle fits an empty hand, so this one is not empty
HAND_FULL_SQL = """
WITH held AS (
    SELECT id, seq FROM tasks WHERE owner = :actor AND status = 'doing'
)
SELECT (SELECT group_concat(id, :sep) FROM (SELECT id FROM held ORDER BY seq)),
       (SELECT id FROM held ORDER BY seq LIMIT 1),
       (SELECT value FROM meta WHERE key = 'max_hand')
"""
# WAITING: (todo count, doing rows gating a todo parent, their holders) -
# nothing available while todo rows remain means such a gate exists
WAITING_SQL = """
WITH gates AS (
    SELECT tasks.id, tasks.seq, COALESCE(agents.name, tasks.owner) AS name
    FROM tasks LEFT JOIN agents ON agents.id = tasks.owner
    WHERE tasks.status = 'doing'
      AND tasks.parent_id IN (SELECT id FROM tasks WHERE status = 'todo')
)
SELECT CAST((SELECT COUNT(*) FROM tasks WHERE status = 'todo') AS TEXT),
       (SELECT group_concat(id, :sep) FROM (SELECT id FROM gates ORDER BY seq)),
       (
           SELECT group_concat(name, :sep)
           FROM (SELECT DISTINCT name FROM gates ORDER BY name)
       )
"""
# EMPTY: nothing to name
EMPTY_SQL = 'SELECT NULL LIMIT 0'

NAMES_SQL = MappingProxyType({
    output.Refusal.TAKEN: TAKEN_SQL,
    output.Refusal.GATED: GATED_SQL,
    output.Refusal.OVERSIZED: OVERSIZED_SQL,
    output.Refusal.HAND_FULL: HAND_FULL_SQL,
    output.Refusal.WAITING: WAITING_SQL,
    output.Refusal.EMPTY: EMPTY_SQL,
})


def board_snapshot(conn: Connection) -> Board:
    """Read meta facts, every task in seq order, the last EVENT_CAP events.

    Plain reads and no transaction of its own: apply_sync calls this
    inside the BEGIN IMMEDIATE it will write with (C11).
    """
    meta = dict(conn.execute(META_SQL).fetchall())
    tasks = conn.execute(TASKS_SQL).fetchall()
    events = conn.execute(RECENT_EVENTS_SQL, (output.EVENT_CAP,)).fetchall()
    return Board(
        key=meta['board_key'],
        max_hand=int(meta['max_hand']),
        plan_mtime=int(meta['plan_mtime']),
        tasks=tuple(
            replace(task, status=Status(task.status))
            for task in starmap(Task, tasks)
        ),
        events=tuple(
            replace(event, kind=EventKind(event.kind))
            for event in starmap(Event, events)
        ),
    )


def deliver_events(conn: Connection, actor: str | None) -> tuple[Event, ...]:
    """Return actor's unseen events, advancing the cursor - one txn (D10).

    Unseen means id > agents.last_event_seen, addressed to all or to
    the actor, and not the actor's own; the cursor advance rides the
    same transaction. No actor (None) means nothing to deliver.
    """
    with conn:
        conn.execute(BEGIN)
        rows = conn.execute(UNSEEN_SQL, (actor,)).fetchall()
        conn.execute(CURSOR_SQL, (actor,))
    return tuple(
        replace(event, kind=EventKind(event.kind))
        for event in starmap(Event, rows)
    )


def prior_claim(conn: Connection, task_id: str) -> Event | None:
    """Find the last reap on task_id so a re-claimer is warned (SSoT §6)."""
    row = conn.execute(PRIOR_SQL, (task_id,)).fetchone()
    if row is None:
        return None
    event = Event(*row)
    return replace(event, kind=EventKind(event.kind))


def resolve_task(conn: Connection, raw: str, verb: str) -> Task:
    """Match an id exactly (case tolerated), else raise a steered error.

    The steer is the caller's own verb with the nearest id substituted
    (D14, I10): output.steer(Refusal.UNKNOWN_TASK, (raw, nearest, verb)).
    """
    row = conn.execute(EXACT_SQL, (raw,)).fetchone()
    if row is None:
        nearest = conn.execute(
            NEAREST_SQL, (raw, ascii_uppercase, ID_TAIL),
        ).fetchone()[0]
        raise output.steer(
            output.Refusal.UNKNOWN_TASK, (raw, nearest, verb),
        )
    task = Task(*row)
    return replace(task, status=Status(task.status))


def verify_actor(conn: Connection, actor: str) -> bool:
    """Answer whether a supplied identity exists on THIS board (D8, D18)."""
    return conn.execute(ACTOR_SQL, (actor,)).fetchone() is not None


def newly_unlocked(conn: Connection, task_id: str) -> Task | None:
    """Return the parent this done just made claimable, if any (D22, D7).

    Fires exactly when task_id's finish closed the last open child;
    the verb turns it into a ready `claim --task` hint (SSoT §6).
    """
    row = conn.execute(UNLOCKED_SQL, (task_id,)).fetchone()
    if row is None:
        return None
    task = Task(*row)
    return replace(task, status=Status(task.status))


def claim_refusal(
    conn: Connection,
    actor: str,
    task_ids: tuple[str, ...] | None,
) -> tuple[output.Refusal, tuple[str, ...]]:
    """Explain a zero-row claim: one CASE picks the kind, one read names it.

    Kinds: TAKEN (bundle member held/done - holder), GATED (member waits
    on children - children), OVERSIZED (bundle larger than the hand -
    size, hand, first member), HAND_FULL (held ids), WAITING (holders of
    what remaining todo rows wait on), EMPTY (D6, D22, C9). Both reads
    share one snapshot, so the names always fit the kind; they feed
    output.steer(kind, names) verbatim.
    """
    bundle = tuple(dict.fromkeys(task_ids or ()))
    bindings = {
        'actor': actor,
        'bundle': json.dumps(bundle) if bundle else None,
        'size': len(bundle) or 1,
        'sep': output.LIST_SEP,
    }
    with conn:
        conn.execute(BEGIN_READ)
        kind = output.Refusal(
            conn.execute(REFUSAL_SQL, bindings).fetchone()[0],
        )
        names = conn.execute(NAMES_SQL[kind], bindings).fetchone()
    return kind, tuple(names or ())
