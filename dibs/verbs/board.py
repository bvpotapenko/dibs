"""Author-side and shared verbs: init, verify, sync, note, list (SSoT §6).

Level L4 (imports L0-L3). Member budget 5 (ARCHITECTURE §3). C6 rules
as in work.py; plan file reads/writes happen here via pathlib - one
read, one atomic write (tempfile + os.replace) per §6 step 9 (C4, I4).
"""

from argparse import Namespace

from dibs import (
    names,
    output,
    planfile,
    plansync,
    queries,
    store,
    transitions,
    views,
)
from dibs.runtime import Context, Reply


def init_board(ctx: Context, args: Namespace) -> Reply:
    """Create the board from a parsed plan; print key + roster (SSoT §6).

    names.mint_board_key -> plansync.found_board (False -> steer
    BOARD_EXISTS pointing to sync) -> plansync.apply_sync (everything is
    new, D24) -> store.registry_record -> views.format_board + handoff.
    """
    key = names.mint_board_key()
    if not plansync.found_board(ctx.conn, ctx.now, key, args.max_hand):
        raise output.steer(
            output.Refusal.BOARD_EXISTS,
            (queries.board_snapshot(ctx.conn).key,),
        )
    plan = plansync.apply_sync(
        ctx.conn,
        ctx.now,
        planfile.parse_plan(ctx.plan_path.read_text()),
        ctx.plan_path.stat().st_mtime_ns,
    )
    store.registry_record(key, ctx.plan_path)
    return Reply(
        lines=views.format_board(plan.rows, key),
        events=(),
        hint=output.next_hint('init', (key,)),
    )


def verify_board(args: Namespace) -> Reply:
    """Render the parse preview; create and touch nothing (D21, D24).

    The one pure verb, so no Context: read file, planfile.parse_plan,
    planfile.compute_sync(items, ()) for would-be ids, views.format_board
    on plan.rows with key ''. No board, no identity, no events; an
    existing board file is noted in one line pointing to list. A plan
    that is not there is steered, never traced back (I10).
    """
    if not args.plan_path.is_file():
        raise output.steer(output.Refusal.NO_BOARD, (args.verb,))
    plan = planfile.compute_sync(
        planfile.parse_plan(args.plan_path.read_text()), (),
    )
    founded = args.plan_path.with_name(
        store.BOARD_FILE.format(args.plan_path.name),
    ).is_file()
    return Reply(
        lines=views.format_board(plan.rows, '') + (views.LIVE_BOARD,) * founded,
        events=(),
        hint=output.next_hint(
            'init' if founded else 'verify', (args.plan,),
        ),
    )


def sync_board(ctx: Context, _args: Namespace) -> Reply:
    """Reconcile plan text with the board per the SSoT §8 sync table.

    planfile.parse_plan -> plansync.apply_sync (one transaction,
    C11) -> views.format_sync; ambiguities are reported, never guessed
    (I5, I9, D22). Annotation is the pipeline's settle tail (§6).
    """
    plan = plansync.apply_sync(
        ctx.conn,
        ctx.now,
        planfile.parse_plan(ctx.plan_path.read_text()),
        ctx.plan_path.stat().st_mtime_ns,
    )
    return Reply(
        lines=views.format_sync(plan),
        events=(),
        hint=output.next_hint('sync'),
    )


def note_verb(ctx: Context, args: Namespace) -> Reply:
    """Broadcast, or direct with --for, one note event (D10, SSoT §6).

    An audience no agent on this board carries is refused before
    anything is logged: record_note's zero rows is this verb's one
    `if ... raise`, steering to the broadcast form, which always lands
    (C6, C7).
    """
    event = transitions.record_note(
        ctx.conn, ctx.actor, ctx.now, args.text, args.to_name,
    )
    if event is None:
        raise output.steer(
            output.Refusal.UNKNOWN_AUDIENCE, (args.to_name, args.text),
        )
    return Reply(lines=(), events=(), hint=output.next_hint('note'))


def list_board(ctx: Context, _args: Namespace) -> Reply:
    """Show board key, tasks with child progress, recent events (SSoT §6).

    Headed by the board key (the lost-key recovery path, D20); gated
    parents show 2/3-style progress (D22); reaping already ran via the
    pipeline (C10). The recent events are the body's own lines: the
    envelope's feed carries only what the caller has not seen (D10).
    """
    snapshot = queries.board_snapshot(ctx.conn)
    return Reply(
        lines=(
            *views.format_board(snapshot.tasks, snapshot.key),
            *map(output.format_event, snapshot.events),
        ),
        events=(),
        hint=output.next_hint('list'),
    )
