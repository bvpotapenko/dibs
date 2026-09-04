"""Worker-loop verbs: join, claim, done, drop (SSoT §6).

Level L4 (imports L0-L3). Member budget 4 (ARCHITECTURE §3). Verbs
orchestrate only: <=10 statements, no SQL, no regex, no user-facing
string building (C6); collaborators per the ARCHITECTURE §9 trace.
An `_args` parameter is the verb's unused half of the (ctx, args)
dispatch signature - the table calls every verb the same way (C10).
"""

from argparse import Namespace

from dibs import names, output, queries, transitions, views
from dibs.records import agent_name
from dibs.runtime import Context, Reply


def join_session(ctx: Context, _args: Namespace) -> Reply:
    """Mint an identity; reply is the bare id, for launchers (D8, SSoT §6).

    Nothing else is printed here: `export DIBS_AS=$(dibs join)` must
    capture an id, so the reply carries no body lines and no hint (I10).
    """
    return Reply(
        lines=(names.mint_identity(ctx.conn, ctx.now).agent_id,),
        events=(),
        hint='',
    )


def claim_task(ctx: Context, args: Namespace) -> Reply:
    """Claim next available task or an exact bundle; reply is the briefing.

    names.mint_identity when no identity was supplied (D8), then
    transitions.claim; () -> raise output.steer(*queries.claim_refusal)
    (D6, D22); queries.prior_claim per task; views.format_briefing.
    """
    actor = ctx.actor or names.mint_identity(ctx.conn, ctx.now).agent_id
    claimed = transitions.claim(ctx.conn, actor, ctx.now, args.task)
    if not claimed:
        raise output.steer(*queries.claim_refusal(ctx.conn, actor, args.task))
    priors = tuple(filter(None, (
        queries.prior_claim(ctx.conn, task.task_id) for task in claimed
    )))
    return Reply(
        lines=views.format_briefing(claimed, actor, priors, ctx.actor is None),
        events=(),
        hint=output.next_hint('claim', (claimed[0].task_id,)),
    )


def done_task(ctx: Context, args: Namespace) -> Reply:
    """Finish an owned task with its mandatory note (D11, I2, I4).

    Orchestrates queries.resolve_task, transitions.finish and
    queries.newly_unlocked: a completion that made a parent claimable
    hints straight at it, since this worker has the freshest context
    for it (D7, D22). The plan annotation is the pipeline's own tail.
    """
    task = queries.resolve_task(ctx.conn, args.task, 'done')
    finished = transitions.finish(
        ctx.conn, ctx.actor, ctx.now, task.task_id, args.note,
    )
    if finished is None:
        raise output.steer(
            output.Refusal.NOT_OWNER, (task.task_id, agent_name(task.owner)),
        )
    unlocked = queries.newly_unlocked(ctx.conn, finished.task_id)
    return Reply(
        lines=(),
        events=(),
        hint=(
            output.next_hint('unlocked', (unlocked.task_id,)) if unlocked
            else output.next_hint('done')
        ),
    )


def drop_task(ctx: Context, args: Namespace) -> Reply:
    """Release a held task back to todo, logging why (SSoT §6, D9)."""
    task = queries.resolve_task(ctx.conn, args.task, 'drop')
    dropped = transitions.release(
        ctx.conn, ctx.actor, ctx.now, task.task_id, args.note,
    )
    if dropped is None:
        raise output.steer(
            output.Refusal.NOT_OWNER, (task.task_id, agent_name(task.owner)),
        )
    return Reply(lines=(), events=(), hint=output.next_hint('drop'))
