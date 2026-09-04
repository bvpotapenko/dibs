"""Write transitions: each public function is exactly one transaction.

Success is judged by rowcount alone (I1, C3) and appends exactly one
event per changed row in the same transaction (I6). Branching lives in
the WHERE clause; Python stays linear (C9). Level L2 (imports L0-L1).

Member budget 6 (ARCHITECTURE §3); never raise the limit.

Rows come back as sqlite3.Row (store.connect); `RETURNING *` and
`SELECT *` follow the DDL column order, which mirrors records.Task and
records.Event, so a record is built positionally and its str-enum
column coerced. Placeholders are numbered (?1 ...) so one value can be
named in a legend and reused inside a statement (C2).
"""

import json
import sqlite3
from dataclasses import replace
from itertools import starmap
from operator import itemgetter

from dibs.records import Agent, Event, EventKind, Status, Task

REAP_TTL_SECONDS = 2700  # 45 minutes (SSoT §13); D9 passive reaping
# Take the write lock up front so contention waits on busy_timeout
# instead of failing mid-transaction (D2).
BEGIN = 'BEGIN IMMEDIATE'
BY_SEQ = itemgetter('seq')

# ?1 actor  ?2 now  ?3 bundle as a JSON array of canonical (upper-cased)
# ids, NULL = take the next available  ?4 bundle size (1 when ?3 is
# NULL). Everything is decided here (I1): CAS on status, gating (no open
# child, D22), all-or-none for a bundle, and the hand limit (D6);
# ordering is section affinity, then seq (D7). Zero rows is a refusal
# the verb diagnoses with a read.
CLAIM_SQL = """
WITH available AS (
    SELECT id, seq, section FROM tasks AS candidate
    WHERE candidate.status = 'todo'
      AND NOT EXISTS (
          SELECT 1 FROM tasks AS child
          WHERE child.parent_id = candidate.id
            AND child.status IN ('todo', 'doing')
      )
),
wanted AS (
    SELECT id, seq, section FROM available
    WHERE ?3 IS NULL OR id IN (SELECT value FROM json_each(?3))
)
UPDATE tasks
SET status = 'doing', owner = ?1, claimed_at = ?2
WHERE id IN (
        SELECT id FROM wanted
        ORDER BY (
            section = (SELECT last_section FROM agents WHERE id = ?1)
        ) DESC, seq
        LIMIT ?4
    )
  AND (SELECT COUNT(*) FROM wanted) >= ?4
  AND (
        SELECT COUNT(*) FROM tasks AS held
        WHERE held.owner = ?1 AND held.status = 'doing'
      ) + ?4 <= (SELECT CAST(value AS INTEGER) FROM meta WHERE key = 'max_hand')
RETURNING *
"""

# ?1 now  ?2 note  ?3 task_id  ?4 actor  (I2: ownership in the WHERE)
FINISH_SQL = """
UPDATE tasks SET status = 'done', done_at = ?1, done_note = ?2
WHERE id = ?3 AND owner = ?4 AND status = 'doing'
RETURNING *
"""

# ?1 task_id  ?2 actor
RELEASE_SQL = """
UPDATE tasks SET status = 'todo', owner = NULL, claimed_at = NULL
WHERE id = ?1 AND owner = ?2 AND status = 'doing'
RETURNING *
"""

# ?1 now  ?2 actor - activity extends the lease (D9)
LEASE_SQL = """
UPDATE tasks SET claimed_at = ?1 WHERE owner = ?2 AND status = 'doing'
"""

# ?1 now  ?2 actor - last_seen, and last_section follows the freshest
# claim while one is held (D7)
TOUCH_AGENT_SQL = """
UPDATE agents
SET last_seen = ?1,
    last_section = COALESCE(
        (
            SELECT section FROM tasks
            WHERE owner = ?2 AND status = 'doing'
            ORDER BY claimed_at DESC, seq DESC LIMIT 1
        ),
        last_section
    )
WHERE id = ?2
"""

LAST_EVENT_SQL = 'SELECT COALESCE(MAX(id), 0) FROM events'

# ?1 now  ?2 cutoff - one reap event per stale claim by the 'system'
# actor (SSoT §5, D9), before the revert;
# its text is the former holder's NAME, display-safe like every event
# text (I7): titles, notes, names, the board key, the sync summary
REAP_EVENTS_SQL = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
SELECT ?1, 'system', 'reap', tasks.id, NULL,
       COALESCE((SELECT name FROM agents WHERE agents.id = tasks.owner), owner)
FROM tasks
WHERE status = 'doing' AND claimed_at < ?2
ORDER BY seq
"""

# ?1 cutoff
REAP_SQL = """
UPDATE tasks SET status = 'todo', owner = NULL, claimed_at = NULL
WHERE status = 'doing' AND claimed_at < ?1
"""

EVENTS_AFTER_SQL = 'SELECT * FROM events WHERE id > ?1 ORDER BY id'
EVENT_BY_ID_SQL = 'SELECT * FROM events WHERE id = ?1'

# (ts, agent, kind, task_id, to_agent, text) in that order
EVENT_SQL = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
VALUES (?, ?, ?, ?, ?, ?)
"""

# ?1 now  ?2 actor  ?3 to_name (NULL = broadcast)  ?4 text - a known name
# resolves to its id; an unknown one is kept verbatim for the verb's
# warning (SSoT §6 note row, D10)
NOTE_SQL = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
VALUES (
    ?1, ?2, 'note', NULL,
    COALESCE((SELECT id FROM agents WHERE name = ?3), ?3), ?4
)
"""

# ?1 agent_id  ?2 name  ?3 now - the one clock stamps the join and the
# agent row (I6, C3); the cursor starts after the join itself so a
# newcomer is not handed the whole history (D10, D16)
JOIN_EVENT_SQL = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
VALUES (?3, ?1, 'join', NULL, NULL, ?2)
"""
AGENT_SQL = """
INSERT INTO agents
    (id, name, created_at, last_seen, last_event_seen, last_section)
VALUES (
    ?1, ?2, ?3, ?3, (SELECT COALESCE(MAX(id), 0) FROM events), NULL
)
"""


def claim(
    conn: sqlite3.Connection,
    actor: str,
    now: int,
    task_ids: tuple[str, ...] | None = None,
) -> tuple[Task, ...]:
    """Claim the next available task, or an exact bundle (D6, D7, D22).

    One UPDATE decides everything: CAS on status='todo', hand limit via
    a holdings subquery against meta.max_hand, gating via NOT EXISTS an
    open (todo/doing) child. No-arg order: caller's last section first,
    then seq (D7). A bundle is all-or-none and must fit the hand; its
    members are upper-cased first, so `--task a3` is `--task A3` (D14
    tolerant forms), exactly as queries.resolve_task tolerates case.
    Zero rows is not an error here; refusal diagnostics (hand full /
    waiting / empty) come from a follow-up read in the verb (D6).
    """
    bundle = tuple(dict.fromkeys(
        task_id.upper() for task_id in task_ids or ()
    ))
    wanted = json.dumps(bundle) if bundle else None
    with conn:
        conn.execute(BEGIN)
        rows = conn.execute(
            CLAIM_SQL, (actor, now, wanted, len(bundle) or 1),
        ).fetchall()
        conn.executemany(EVENT_SQL, [
            (now, actor, EventKind.CLAIM.value, row['id'], None, row['title'])
            for row in rows
        ])
        conn.execute(TOUCH_AGENT_SQL, (now, actor))
    return tuple(
        replace(task, status=Status(task.status))
        for task in starmap(Task, sorted(rows, key=BY_SEQ))
    )


def finish(
    conn: sqlite3.Connection,
    actor: str,
    now: int,
    task_id: str,
    note: str,
) -> Task | None:
    """Complete an owned task: WHERE owner=:actor, note mandatory (I2, D11).

    None <=> zero rows (not the owner, or not doing); the verb raises
    output.steer(Refusal.NOT_OWNER, ...), never this function (C7).
    """
    with conn:
        conn.execute(BEGIN)
        row = conn.execute(FINISH_SQL, (now, note, task_id, actor)).fetchone()
        if row is None:
            return None
        conn.execute(
            EVENT_SQL, (now, actor, EventKind.DONE.value, task_id, None, note),
        )
    task = Task(*row)
    return replace(task, status=Status(task.status))


def release(
    conn: sqlite3.Connection,
    actor: str,
    now: int,
    task_id: str,
    note: str | None,
) -> Task | None:
    """Drop an owned task back to todo, logging why (SSoT §6, D9, I2).

    None <=> zero rows (not the owner, or not doing); the verb raises
    output.steer(Refusal.NOT_OWNER, ...), never this function (C7).
    """
    with conn:
        conn.execute(BEGIN)
        row = conn.execute(RELEASE_SQL, (task_id, actor)).fetchone()
        if row is None:
            return None
        conn.execute(
            EVENT_SQL,
            (now, actor, EventKind.DROP.value, task_id, None, note or ''),
        )
    task = Task(*row)
    return replace(task, status=Status(task.status))


def housekeeping(
    conn: sqlite3.Connection,
    actor: str | None,
    now: int,
) -> tuple[Event, ...]:
    """Refresh the caller's lease, then reap claims past the TTL (D9).

    Runs before every verb (C10) so claim sees freshly reaped tasks;
    returns the reap events it appended (I6, I8). The caller's own
    claims are renewed first: its command is proof of life, so they are
    never reaped by it.
    """
    with conn:
        conn.execute(BEGIN)
        conn.execute(LEASE_SQL, (now, actor))
        conn.execute(TOUCH_AGENT_SQL, (now, actor))
        before = conn.execute(LAST_EVENT_SQL).fetchone()[0]
        conn.execute(REAP_EVENTS_SQL, (now, now - REAP_TTL_SECONDS))
        conn.execute(REAP_SQL, (now - REAP_TTL_SECONDS,))
        rows = conn.execute(EVENTS_AFTER_SQL, (before,)).fetchall()
    return tuple(
        replace(event, kind=EventKind(event.kind))
        for event in starmap(Event, rows)
    )


def record_note(
    conn: sqlite3.Connection,
    actor: str,
    now: int,
    text: str,
    to_name: str | None = None,
) -> Event:
    """Append a broadcast or directed note event (D10).

    An unknown to_name still logs, with a warning left to the verb
    (SSoT §6 note row).
    """
    with conn:
        conn.execute(BEGIN)
        cursor = conn.execute(NOTE_SQL, (now, actor, to_name, text))
        row = conn.execute(EVENT_BY_ID_SQL, (cursor.lastrowid,)).fetchone()
    event = Event(*row)
    return replace(event, kind=EventKind(event.kind))


def register_agent(conn: sqlite3.Connection, agent: Agent, now: int) -> bool:
    """INSERT the identity; False on UNIQUE collision, never pre-check (I1).

    The join event, stamped `now` like every write (one clock per
    invocation), rides the same transaction and is rolled back with a
    refused INSERT (I6).
    """
    try:
        with conn:
            conn.execute(BEGIN)
            conn.execute(JOIN_EVENT_SQL, (agent.agent_id, agent.name, now))
            conn.execute(AGENT_SQL, (agent.agent_id, agent.name, now))
    except sqlite3.IntegrityError:
        return False
    return True
