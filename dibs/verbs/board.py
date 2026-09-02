"""Author-side and shared verbs: init, verify, sync, note, list (SSoT §6).

Level L4 (imports L0-L3). Member budget 6 (ARCHITECTURE §3). C6 rules
as in work.py; plan file reads/writes happen here via pathlib - one
read, one atomic write (tempfile + replace) per §6 step 9 (C4, I4).
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

NO_FEED = ()  # the §6 pipeline fills Reply.events after the verb runs
UTF8 = 'utf-8'  # plan.md is text the human wrote; read and write it so
SCRATCH = '.{0}.dibs.tmp'  # sibling temp file, same filesystem (I4)

# The one line verify adds when the plan already has a board: D21 says
# say so and point at list, never at a second init.
BOARD_LIVE = ('this plan already has a board - run: dibs list',)


def init_board(ctx: Context, args: Namespace) -> Reply:
    """Open the board for this plan and print key + roster (SSoT §6).

    The task rows arrived through the pipeline's own sync, so all that
    is left is the compare-and-swap on the key (a second init is
    refused there), the registry cache, and the roster (D20).
    """
    key = names.mint_board_key()
    plansync.open_board(ctx.conn, ctx.now, key, args.max_hand)
    store.registry_record(key, ctx.plan_path)
    return Reply(
        views.format_board(queries.board_snapshot(ctx.conn), key, ()),
        NO_FEED,
        output.next_hint('init', {'key': key}),
    )


def verify_board(ctx: Context, _args: Namespace) -> Reply:
    """Render the parse preview; create and touch nothing (D21, D22).

    Pure pipeline: read the file, parse it, render it. No board, no
    identity, no events, no annotation - ctx.conn is None and stays
    untouched (ARCHITECTURE §6 step 1).
    """
    return Reply(
        views.format_preview(planfile.parse_plan(
            ctx.plan_path.read_text(encoding=UTF8),
        )) + BOARD_LIVE * ctx.db_path.exists(),
        NO_FEED,
        output.next_hint('verify', {'plan': str(ctx.plan_path)}),
    )


def sync_board(ctx: Context, _args: Namespace) -> Reply:
    """Reconcile plan text with the board per the SSoT §8 sync table.

    Text and mtime are read together so the stamp belongs to the bytes
    that were parsed (C4); everything else is one stamped transaction
    inside plansync (I1, I9). The pipeline runs this before every verb
    and discards the report (§6 step 5) - so for the `sync` verb itself
    it must KEEP that first Reply rather than call this twice: the mtime
    CAS is honest, and a second call would report 'nothing changed'.
    """
    return Reply(
        views.format_sync(plansync.apply_sync(
            ctx.conn,
            ctx.now,
            planfile.parse_plan(ctx.plan_path.read_text(encoding=UTF8)),
            str(ctx.plan_path.stat().st_mtime_ns),
        )),
        NO_FEED,
        output.next_hint('sync', {}),
    )


def note_verb(ctx: Context, args: Namespace) -> Reply:
    """Broadcast, or direct with --for, one note event (D10, SSoT §6)."""
    return Reply(
        views.format_outcome(
            'note',
            event=transitions.record_note(
                ctx.conn, ctx.actor, ctx.now, args.text, args.to_name,
            ),
            to_name=args.to_name,
        ),
        NO_FEED,
        output.next_hint('note', {}),
    )


def list_board(ctx: Context, _args: Namespace) -> Reply:
    """Show board key, tasks with child progress, recent events (SSoT §6).

    Headed by the board key (the lost-key recovery path, D20); gated
    parents show 2/3-style progress (D22); reaping already ran via the
    pipeline (C10).
    """
    return Reply(
        views.format_board(
            queries.board_snapshot(ctx.conn),
            store.read_meta(ctx.conn, store.BOARD_KEY),
            queries.recent_events(ctx.conn, output.EVENT_CAP),
        ),
        NO_FEED,
        output.next_hint('list', {}),
    )


def annotate_plan(ctx: Context) -> None:
    """Write board state back into the checkbox lines (D5, I3, I4).

    The one writer of plan.md, run by every command (§6 step 9).
    Re-render from the snapshot and write only if the bytes changed and
    the file is still the one that was read: an author's save landing in
    that window is left alone, and the next command retries.
    """
    stamp = ctx.plan_path.stat().st_mtime_ns
    text = ctx.plan_path.read_text(encoding=UTF8)
    rendered = planfile.annotate_lines(
        text, queries.board_snapshot(ctx.conn),
    )
    scratch = ctx.plan_path.with_name(SCRATCH.format(ctx.plan_path.name))
    if rendered != text and ctx.plan_path.stat().st_mtime_ns == stamp:
        scratch.write_text(rendered, encoding=UTF8)
        scratch.replace(ctx.plan_path)
