"""Worker-loop verbs: join, claim, done, drop (SSoT §6).

Level L4 (imports L0-L3). Member budget 4 (ARCHITECTURE §3). Verbs
orchestrate only: <=10 statements, no SQL, no regex, no user-facing
string building (C6); collaborators per the ARCHITECTURE §9 trace.
"""

from argparse import Namespace

from dibs.runtime import Context, Reply


def join_session(ctx: Context, args: Namespace) -> Reply:
    """Mint an identity; reply is the bare id, for launchers (D8, SSoT §6).

    Orchestrates names.mint_identity + output.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 10: join_session')


def claim_task(ctx: Context, args: Namespace) -> Reply:
    """Claim next available task or an exact bundle; reply is the briefing.

    names.mint_identity when no identity was supplied (D8), then
    transitions.claim; () -> raise output.steer(*queries.claim_refusal)
    (D6, D22); queries.prior_claim per task; views.format_briefing.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 10: claim_task')


def done_task(ctx: Context, args: Namespace) -> Reply:
    """Finish an owned task with its mandatory note (D11, I2, I4).

    Orchestrates queries.resolve_task, transitions.finish,
    queries.newly_unlocked (ready claim hint on unlock, D7/D22), and
    the plan annotation step (§6 pipeline step 9).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 10: done_task')


def drop_task(ctx: Context, args: Namespace) -> Reply:
    """Release a held task back to todo, logging why (SSoT §6, D9)."""
    raise NotImplementedError('ARCHITECTURE §13 step 10: drop_task')
