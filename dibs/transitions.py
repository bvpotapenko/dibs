"""Worker-side write transitions: one transaction per public function.

Success is judged by rowcount alone (I1, C3) and appends exactly one
event per row whose state changed, in the same transaction (I6).
Branching lives in the WHERE clause; Python stays linear (C9). Level L2
(imports L0-L1).

Member budget 6 - AT THE CAP (ARCHITECTURE §3). The split this module
pre-announced happened at step 8: the plan -> board direction (board
opening, the sync applier) lives in plansync.py, which owns AUTHOR and
the hand-checked-[x] import. A seventh member here means stop and flag.
"""

from sqlite3 import Connection

from dibs.output import NOT_OWNER, RECLAIM
from dibs.records import Agent, Event, EventKind, Task
from dibs.runtime import DibsError

REAP_TTL_SECONDS = 2700  # 45 minutes (SSoT §13); D9 passive reaping

BUNDLE = ',{0},'  # ',A1,A2,' - one bound value instead of an id list

# Event kinds ride in as parameters so records.EventKind stays their one
# home; statuses stay inline because they are the WHERE logic (C9).
CLAIM = """
UPDATE tasks SET
    status = 'doing',
    owner = :actor,
    claimed_at = :now
WHERE status = 'todo'
  AND id IN (
      SELECT ready.id FROM tasks ready
      WHERE ready.status = 'todo'
        AND (:bundle IS NULL OR instr(:bundle, ',' || ready.id || ',') > 0)
        AND NOT EXISTS (
            SELECT 1 FROM tasks child
            WHERE child.parent_id = ready.id
              AND child.status IN ('todo', 'doing')
        )
      ORDER BY (
          ready.section = (SELECT last_section FROM agents WHERE id = :actor)
      ) DESC, ready.seq
      LIMIT :want
  )
  AND (
      :bundle IS NULL
      OR :want = (
          SELECT count(*) FROM tasks listed
          WHERE listed.status = 'todo'
            AND instr(:bundle, ',' || listed.id || ',') > 0
            AND NOT EXISTS (
                SELECT 1 FROM tasks child
                WHERE child.parent_id = listed.id
                  AND child.status IN ('todo', 'doing')
            )
      )
  )
  AND :want + (
      SELECT count(*) FROM tasks held
      WHERE held.owner = :actor AND held.status = 'doing'
  ) <= (SELECT CAST(value AS INTEGER) FROM meta WHERE key = 'max_hand')
RETURNING *
"""

REMEMBER_SECTION = """
UPDATE agents SET last_section = COALESCE(?, last_section)
WHERE id = ?
"""

FINISH = """
UPDATE tasks SET status = 'done', done_at = ?, done_note = ?
WHERE id = ? AND owner = ? AND status = 'doing'
RETURNING *
"""

RELEASE = """
UPDATE tasks SET status = 'todo', owner = NULL, claimed_at = NULL
WHERE id = ? AND owner = ? AND status = 'doing'
RETURNING *
"""

# A reap is directed at the agent who must know it happened - the
# former owner - so it reaches them even after their cursor moved past
# every broadcast (D9, D10, §9 SSoT).
REAP_EVENTS = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
SELECT ?, stale.owner, ?, stale.id, stale.owner, stale.title
FROM tasks stale
WHERE stale.status = 'doing' AND stale.claimed_at < ?
RETURNING *
"""

REAP_TASKS = """
UPDATE tasks SET status = 'todo', owner = NULL, claimed_at = NULL
WHERE status = 'doing' AND claimed_at < ?
"""

REFRESH_LEASE = """
UPDATE tasks SET claimed_at = ?
WHERE owner = ? AND status = 'doing'
"""

TOUCH_AGENT = 'UPDATE agents SET last_seen = ? WHERE id = ?'

EVENT = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
VALUES (?, ?, ?, ?, ?, ?)
"""

NOTE_EVENT = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
VALUES (
    ?, ?, ?, NULL, (SELECT id FROM agents WHERE name = ?), ?
)
RETURNING *
"""

# The cursor starts at the board's high-water mark: a joiner has no
# 'while you were away', and the roster a fresh init wrote never floods
# a first feed (§9 SSoT).
INSERT_AGENT = """
INSERT OR IGNORE INTO agents (
    id, name, created_at, last_seen, last_event_seen, last_section
) VALUES (
    ?, ?,
    CAST(strftime('%s', 'now') AS INTEGER),
    CAST(strftime('%s', 'now') AS INTEGER),
    (SELECT COALESCE(max(id), 0) FROM events), NULL
)
"""

JOIN_EVENT = """
INSERT INTO events (ts, agent, kind, task_id, to_agent, text)
VALUES (
    CAST(strftime('%s', 'now') AS INTEGER), ?, ?, NULL, NULL, ?
)
"""


def claim(
    conn: Connection,
    actor: str,
    now: int,
    task_ids: tuple[str, ...] | None = None,
) -> tuple[Task, ...]:
    """Claim the next available task, or an exact bundle (D6, D7, D22).

    One UPDATE decides everything: CAS on status='todo', hand limit via
    a holdings subquery against meta.max_hand, gating via NOT EXISTS an
    open (todo/doing) child. No-arg order: caller's last section first,
    then seq (D7). A bundle is all-or-none and must fit the hand.
    Zero rows is not an error here; refusal diagnostics (hand full /
    waiting / empty) come from a follow-up read in the verb (D6).
    """
    wanted = tuple(task_ids or ())
    bundle = BUNDLE.format(','.join(wanted)) if wanted else None
    winners = conn.execute(CLAIM, {
        'actor': actor,
        'now': now,
        'bundle': bundle,
        'want': len(wanted) or 1,
    })
    claimed = tuple(Task(*row) for row in winners)
    conn.executemany(EVENT, [
        (now, actor, EventKind.CLAIM.value, task.task_id, None, task.title)
        for task in claimed
    ])
    conn.execute(
        REMEMBER_SECTION,
        (claimed[-1].section if claimed else None, actor),
    )
    conn.commit()
    return claimed


def finish(
    conn: Connection,
    actor: str,
    now: int,
    task_id: str,
    note: str,
) -> Task:
    """Complete an owned task: WHERE owner=:actor, note mandatory (I2, D11)."""
    done = conn.execute(FINISH, (now, note, task_id, actor)).fetchall()
    if not done:
        raise DibsError(NOT_OWNER.format(task_id), RECLAIM.format(task_id))
    conn.execute(
        EVENT,
        (now, actor, EventKind.DONE.value, task_id, None, note),
    )
    conn.commit()
    return Task(*done[0])


def release(
    conn: Connection,
    actor: str,
    now: int,
    task_id: str,
    note: str | None,
) -> Task:
    """Drop an owned task back to todo, logging why (SSoT §6, D9, I2)."""
    dropped = conn.execute(RELEASE, (task_id, actor)).fetchall()
    if not dropped:
        raise DibsError(NOT_OWNER.format(task_id), RECLAIM.format(task_id))
    conn.execute(
        EVENT,
        (now, actor, EventKind.DROP.value, task_id, None, note or ''),
    )
    conn.commit()
    return Task(*dropped[0])


def housekeeping(
    conn: Connection,
    actor: str | None,
    now: int,
) -> tuple[Event, ...]:
    """Reap claims older than REAP_TTL_SECONDS; refresh caller lease (D9).

    Runs before every verb (C10) so claim sees freshly reaped tasks;
    returns the reap events it appended (I6, I8).
    """
    cutoff = now - REAP_TTL_SECONDS
    stale = conn.execute(REAP_EVENTS, (now, EventKind.REAP.value, cutoff))
    reaped = tuple(Event(*row) for row in stale)
    conn.execute(REAP_TASKS, (cutoff,))
    conn.execute(REFRESH_LEASE, (now, actor))
    conn.execute(TOUCH_AGENT, (now, actor))
    conn.commit()
    return reaped


def record_note(
    conn: Connection,
    actor: str,
    now: int,
    text: str,
    to_name: str | None = None,
) -> Event:
    """Append a broadcast or directed note event (D10).

    An unknown to_name still logs, with a warning left to the verb
    (SSoT §6 note row).
    """
    logged = conn.execute(
        NOTE_EVENT,
        (now, actor, EventKind.NOTE.value, to_name, text),
    ).fetchone()
    conn.commit()
    return Event(*logged)


def register_agent(conn: Connection, agent: Agent) -> bool:
    """INSERT the identity; False on UNIQUE collision, never pre-check (I1).

    The rowcount is the whole truth (I1): a mint writes exactly one
    join event, an ignored duplicate writes none (I6).
    """
    minted = conn.execute(
        INSERT_AGENT, (agent.agent_id, agent.name),
    ).rowcount == 1
    if minted:
        conn.execute(
            JOIN_EVENT,
            (agent.agent_id, EventKind.JOIN.value, agent.name),
        )
    conn.commit()
    return minted
