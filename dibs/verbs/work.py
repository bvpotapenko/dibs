"""Worker-loop verbs: join, claim, done, drop (SSoT §6).

Level L4 (imports L0-L3). Member budget 4 (ARCHITECTURE §3). Verbs
orchestrate only: <=10 statements, no SQL, no regex, no user-facing
string building (C6); collaborators per the ARCHITECTURE §9 trace. The
pipeline fills Reply.events afterwards (§6 step 8), so every verb hands
back an empty feed.

Argument contract, honored by cli.build_parser (§13 step 9): args.task
is a sequence of raw ids - the whole bundle for claim, the single id for
done and drop - and args.note is the note text.
"""

from argparse import Namespace

from dibs import names, output, queries, store, transitions, views
from dibs.records import EventKind
from dibs.runtime import Context, Reply

NO_FEED = ()  # §6 step 8 fills it; join keeps it empty by contract (D8)
REAP_HISTORY = 1  # one prior reap per claimed task is the whole warning


def join_session(ctx: Context, _args: Namespace) -> Reply:
    """Mint an identity; the reply is the bare id, for launchers (D8).

    No feed and no hint: stdout must be exactly the id so that
    `export DIBS_AS=$(dibs join)` captures it (SSoT §6).
    """
    return Reply((names.mint_identity(ctx.conn).agent_id,), NO_FEED, '')


def claim_task(ctx: Context, args: Namespace) -> Reply:
    """Claim the next available task or an exact bundle (D6, D7, D22).

    Identity is minted here when the launcher did not (D8); the claim
    statement decides, and a zero-row answer becomes the steered
    refusal views.claim_refusal computes from one snapshot.
    """
    actor = ctx.actor or names.mint_identity(ctx.conn).agent_id
    wanted = tuple(
        queries.resolve_task(ctx.conn, raw).task_id
        for raw in args.task or ()
    )
    claimed = transitions.claim(ctx.conn, actor, ctx.now, wanted)
    if not claimed:
        raise views.claim_refusal(
            queries.board_snapshot(ctx.conn),
            actor,
            wanted,
            int(store.read_meta(ctx.conn, store.MAX_HAND)),
        )
    return Reply(
        views.format_briefing(actor, ctx.now, claimed, tuple(
            reap
            for task in claimed
            for reap in queries.recent_events(
                ctx.conn, REAP_HISTORY, task.task_id, EventKind.REAP,
            )
        )),
        NO_FEED,
        output.next_hint('claim', {'task': claimed[0].task_id}),
    )


def done_task(ctx: Context, args: Namespace) -> Reply:
    """Finish an owned task with its mandatory note (D11, I2, I4).

    A completion that closed the last open child unlocks its parent, and
    the hint hands the finishing worker the ready claim for it - it has
    the freshest context (D7, D22).
    """
    task = queries.resolve_task(ctx.conn, args.task[0])
    finished = transitions.finish(
        ctx.conn, ctx.actor, ctx.now, task.task_id, args.note,
    )
    unlocked = queries.newly_unlocked(ctx.conn, task.task_id)
    return Reply(
        views.format_outcome('done', task=finished),
        NO_FEED,
        output.next_hint(*(
            (output.UNLOCKED, {'task': unlocked.task_id}) if unlocked
            else ('done', {})
        )),
    )


def drop_task(ctx: Context, args: Namespace) -> Reply:
    """Release a held task back to todo, logging why (SSoT §6, D9)."""
    task = queries.resolve_task(ctx.conn, args.task[0])
    return Reply(
        views.format_outcome('drop', task=transitions.release(
            ctx.conn, ctx.actor, ctx.now, task.task_id, args.note,
        )),
        NO_FEED,
        output.next_hint('drop', {}),
    )
