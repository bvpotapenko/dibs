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

UNSEEN = """
SELECT * FROM events
WHERE id > (SELECT last_event_seen FROM agents WHERE id = :actor)
  AND (to_agent IS NULL OR to_agent = :actor)
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

LAST_REAP = """
SELECT * FROM events
WHERE task_id = ? AND kind = ?
ORDER BY id DESC
LIMIT 1
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


def deliver_events(conn: Connection, actor: str) -> tuple[Event, ...]:
    """Return actor's unseen events, advancing the cursor - one txn (D10).

    Unseen means id > agents.last_event_seen, addressed to all or to
    the actor; the cursor advance rides the same transaction (an honest
    piggyback, ARCHITECTURE §5).
    """
    unseen = conn.execute(UNSEEN, {'actor': actor}).fetchall()
    conn.execute(ADVANCE_CURSOR, (actor,))
    conn.commit()
    return tuple(Event(*row) for row in unseen)


def prior_claim(conn: Connection, task_id: str) -> Event | None:
    """Find reap history so a re-claimer gets warned (SSoT §6 claim row)."""
    reaped = conn.execute(
        LAST_REAP, (task_id, EventKind.REAP.value),
    ).fetchone()
    return Event(*reaped) if reaped else None


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
