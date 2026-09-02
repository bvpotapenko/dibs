"""Read-side queries; deliver_events also advances the cursor (D10).

Level L2 (imports L0-L1). Member budget 6 (ARCHITECTURE §3). SQL text
with placeholders only (C2); misses steer via DibsError (C7, I10).
"""

from difflib import get_close_matches
from sqlite3 import Connection

from dibs.output import LIST_BOARD, NO_SUCH_TASK, RECLAIM, UNKNOWN_TASK
from dibs.records import Event, EventKind, Task
from dibs.runtime import DibsError

NEAREST = 1  # one 'did you mean' candidate; a list is noise (D14)
NEAR_ENOUGH = 0.5  # two-char ids sharing a section letter score 0.5

SNAPSHOT = 'SELECT * FROM tasks ORDER BY seq'

# What is addressed to you always arrives; your own broadcasts never
# do - the command that made them already said so (D14, §9 SSoT). An
# actor of None matches nothing: every comparison against NULL is NULL,
# so the guard is the WHERE clause, not a Python branch (C9).
UNSEEN = """
SELECT * FROM events
WHERE id > (SELECT last_event_seen FROM agents WHERE id = :actor)
  AND (
      to_agent = :actor
      OR (to_agent IS NULL AND agent <> :actor)
  )
ORDER BY id
"""

# Directed events for other agents sit below the new cursor and are
# already filtered out above, so the board's high-water mark is the
# honest resting place (D10).
ADVANCE_CURSOR = """
UPDATE agents
SET last_event_seen = (SELECT COALESCE(max(id), 0) FROM events)
WHERE id = ?
"""

# Both filters live in the WHERE, so one statement serves list (cap
# only) and claim's reap-history warning (cap 1, task, REAP) - C9.
RECENT = """
SELECT * FROM events
WHERE (:task IS NULL OR task_id = :task)
  AND (:kind IS NULL OR kind = :kind)
ORDER BY id DESC
LIMIT :cap
"""

# Tolerance is normalization, never substitution: upper() and the
# caller's strip() forgive shape, but a different id is only ever
# suggested in the steer - resolving A2 to A2.1 would claim the wrong
# work (D14, D18).
MATCH_TASK = 'SELECT * FROM tasks WHERE upper(id) = ?'
KNOWN_IDS = 'SELECT id FROM tasks ORDER BY seq'
KNOWN_AGENT = 'SELECT 1 FROM agents WHERE id = ?'

UNLOCKED_PARENT = """
SELECT parent.* FROM tasks parent
WHERE parent.id = (SELECT parent_id FROM tasks WHERE id = :task)
  AND parent.status = 'todo'
  AND NOT EXISTS (
      SELECT 1 FROM tasks child
      WHERE child.parent_id = parent.id
        AND child.status IN ('todo', 'doing')
  )
"""


def board_snapshot(conn: Connection) -> tuple[Task, ...]:
    """Return every task row in seq order, for list and sync (SSoT §6)."""
    return tuple(Task(*row) for row in conn.execute(SNAPSHOT))


def deliver_events(
    conn: Connection,
    actor: str | None,
) -> tuple[Event, ...]:
    """Return actor's unseen events, advancing the cursor - one txn (D10).

    Unseen means id > agents.last_event_seen and either directed at the
    actor or broadcast by somebody else; the cursor advance rides the
    same transaction (an honest piggyback, ARCHITECTURE §5). An actor of
    None - join, and a claim that minted its own identity - delivers
    nothing and moves no cursor (ARCHITECTURE §6 step 8).
    """
    unseen = conn.execute(UNSEEN, {'actor': actor}).fetchall()
    conn.execute(ADVANCE_CURSOR, (actor,))
    conn.commit()
    return tuple(Event(*row) for row in unseen)


def recent_events(
    conn: Connection,
    cap: int,
    task_id: str | None = None,
    kind: EventKind | None = None,
) -> tuple[Event, ...]:
    """Return the newest events first, capped, filters optional (D14).

    Serves the human's list view (cap alone) and claim's reap-history
    warning (cap 1, one task, REAP), so a re-claimer learns who held the
    task before them (SSoT §6 claim row).
    """
    found = conn.execute(RECENT, {
        'task': task_id,
        'kind': kind.value if kind else None,
        'cap': cap,
    })
    return tuple(Event(*row) for row in found)


def resolve_task(conn: Connection, raw: str) -> Task:
    """Match an id exactly, then fuzzily; a miss raises a steered error.

    The DibsError steer names the nearest id as a runnable command
    (D14, I10): "Unknown task B7 - did you mean A7? Run: ...".
    """
    wanted = raw.strip().upper()
    found = conn.execute(MATCH_TASK, (wanted,)).fetchone()
    if found:
        return Task(*found)
    known = [row[0] for row in conn.execute(KNOWN_IDS)]
    near = get_close_matches(wanted, known, NEAREST, NEAR_ENOUGH)
    if not near:
        raise DibsError(NO_SUCH_TASK.format(raw), LIST_BOARD)
    raise DibsError(
        UNKNOWN_TASK.format(raw, near[0]), RECLAIM.format(near[0]),
    )


def verify_actor(conn: Connection, actor: str) -> bool:
    """Answer whether a supplied identity exists on THIS board (D8, D18)."""
    return bool(conn.execute(KNOWN_AGENT, (actor,)).fetchone())


def newly_unlocked(conn: Connection, task_id: str) -> Task | None:
    """Return the parent this done just made claimable, if any (D22, D7).

    Fires exactly when task_id's finish closed the last open child;
    the verb turns it into a ready `claim --task` hint (SSoT §6).
    """
    parent = conn.execute(UNLOCKED_PARENT, {'task': task_id}).fetchone()
    return Task(*parent) if parent else None
