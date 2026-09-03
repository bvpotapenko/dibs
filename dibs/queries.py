"""Read-side queries; deliver_events also advances the cursor (D10).

Level L2 (imports L0-L1). Member budget 7 - at the cap, split seam in
ARCHITECTURE §3. SQL text with placeholders only (C2); misses steer via
output.steer (C5, C7, I10).
"""

from sqlite3 import Connection

from dibs.output import Refusal
from dibs.records import Board, Event, Task


def board_snapshot(conn: Connection) -> Board:
    """Read meta facts, every task in seq order, the last EVENT_CAP events."""
    raise NotImplementedError('ARCHITECTURE §13 step 6: board_snapshot')


def deliver_events(conn: Connection, actor: str | None) -> tuple[Event, ...]:
    """Return actor's unseen events, advancing the cursor - one txn (D10).

    Unseen means id > agents.last_event_seen, addressed to all or to
    the actor; the cursor advance rides the same transaction. No actor
    (None) means nothing to deliver.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 6: deliver_events')


def prior_claim(conn: Connection, task_id: str) -> Event | None:
    """Find the last reap on task_id so a re-claimer is warned (SSoT §6)."""
    raise NotImplementedError('ARCHITECTURE §13 step 6: prior_claim')


def resolve_task(conn: Connection, raw: str, verb: str) -> Task:
    """Match an id exactly, then fuzzily; a miss raises a steered error.

    The steer is the caller's own verb with the nearest id substituted
    (D14, I10): output.steer(Refusal.UNKNOWN_TASK, (raw, nearest, verb)).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 6: resolve_task')


def verify_actor(conn: Connection, actor: str) -> bool:
    """Answer whether a supplied identity exists on THIS board (D8, D18)."""
    raise NotImplementedError('ARCHITECTURE §13 step 6: verify_actor')


def newly_unlocked(conn: Connection, task_id: str) -> Task | None:
    """Return the parent this done just made claimable, if any (D22, D7).

    Fires exactly when task_id's finish closed the last open child;
    the verb turns it into a ready `claim --task` hint (SSoT §6).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 6: newly_unlocked')


def claim_refusal(
    conn: Connection,
    actor: str,
    task_ids: tuple[str, ...] | None,
) -> tuple[Refusal, tuple[str, ...]]:
    """Explain a zero-row claim: one CASE picks the kind, one read names it.

    Kinds: TAKEN (bundle member held/done - holders), GATED (member waits
    on children - children), HAND_FULL (held ids), WAITING (holders of
    what remaining todo rows wait on), EMPTY (D6, D22, C9).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 6: claim_refusal')
