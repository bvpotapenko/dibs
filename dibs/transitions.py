"""Write transitions: each public function is exactly one transaction.

Success is judged by rowcount alone (I1, C3) and appends exactly one
event in the same transaction (I6). Branching lives in the WHERE
clause; Python stays linear (C9). Level L2 (imports L0-L1).

Member budget 7 - AT THE CAP by design (ARCHITECTURE §3): the first
new write transition splits this module in two (e.g. transitions_work /
transitions_plan); never raise the limit.
"""

from sqlite3 import Connection

from dibs.records import Agent, Event, Task

REAP_TTL_SECONDS = 2700  # 45 minutes (SSoT §13); D9 passive reaping


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
    raise NotImplementedError('ARCHITECTURE §13 step 4: transitions.claim')


def finish(
    conn: Connection,
    actor: str,
    now: int,
    task_id: str,
    note: str,
) -> Task:
    """Complete an owned task: WHERE owner=:actor, note mandatory (I2, D11)."""
    raise NotImplementedError('ARCHITECTURE §13 step 4: transitions.finish')


def release(
    conn: Connection,
    actor: str,
    now: int,
    task_id: str,
    note: str | None,
) -> Task:
    """Drop an owned task back to todo, logging why (SSoT §6, D9, I2)."""
    raise NotImplementedError('ARCHITECTURE §13 step 4: transitions.release')


def housekeeping(
    conn: Connection,
    actor: str | None,
    now: int,
) -> tuple[Event, ...]:
    """Reap claims older than REAP_TTL_SECONDS; refresh caller lease (D9).

    Runs before every verb (C10) so claim sees freshly reaped tasks;
    returns the reap events it appended (I6, I8).
    """
    raise NotImplementedError(
        'ARCHITECTURE §13 step 4: transitions.housekeeping',
    )


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
    raise NotImplementedError(
        'ARCHITECTURE §13 step 4: transitions.record_note',
    )


def import_author_done(conn: Connection, now: int, task_id: str) -> Task:
    """Import a hand-checked [x] as done by 'human' during sync (SSoT §8)."""
    raise NotImplementedError(
        'ARCHITECTURE §13 step 4: transitions.import_author_done',
    )


def register_agent(conn: Connection, agent: Agent) -> bool:
    """INSERT the identity; False on UNIQUE collision, never pre-check (I1)."""
    raise NotImplementedError(
        'ARCHITECTURE §13 step 4: transitions.register_agent',
    )
