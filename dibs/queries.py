"""Read-side queries; deliver_events also advances the cursor (D10).

Level L2 (imports L0-L1). Member budget 6 (ARCHITECTURE §3). SQL text
with placeholders only (C2); misses steer via DibsError (C7, I10).
"""

from sqlite3 import Connection

from dibs.records import Event, Task


def board_snapshot(conn: Connection) -> tuple[Task, ...]:
    """Return every task row in seq order, for list and sync (SSoT §6)."""
    raise NotImplementedError('ARCHITECTURE §13 step 5: board_snapshot')


def deliver_events(conn: Connection, actor: str) -> tuple[Event, ...]:
    """Return actor's unseen events, advancing the cursor - one txn (D10).

    Unseen means id > agents.last_event_seen, addressed to all or to
    the actor; the cursor advance rides the same transaction (an honest
    piggyback, ARCHITECTURE §5).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 5: deliver_events')


def prior_claim(conn: Connection, task_id: str) -> Event | None:
    """Find reap history so a re-claimer gets warned (SSoT §6 claim row)."""
    raise NotImplementedError('ARCHITECTURE §13 step 5: prior_claim')


def resolve_task(conn: Connection, raw: str) -> Task:
    """Match an id exactly, then fuzzily; a miss raises a steered error.

    The DibsError steer names the nearest id as a runnable command
    (D14, I10): "Unknown task B7 - did you mean A7? Run: ...".
    """
    raise NotImplementedError('ARCHITECTURE §13 step 5: resolve_task')


def verify_actor(conn: Connection, actor: str) -> bool:
    """Answer whether a supplied identity exists on THIS board (D8, D18)."""
    raise NotImplementedError('ARCHITECTURE §13 step 5: verify_actor')


def newly_unlocked(conn: Connection, task_id: str) -> Task | None:
    """Return the parent this done just made claimable, if any (D22, D7).

    Fires exactly when task_id's finish closed the last open child;
    the verb turns it into a ready `claim --task` hint (SSoT §6).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 5: newly_unlocked')
