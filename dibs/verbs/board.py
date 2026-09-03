"""Author-side and shared verbs: init, verify, sync, note, list (SSoT §6).

Level L4 (imports L0-L3). Member budget 5 (ARCHITECTURE §3). C6 rules
as in work.py; plan file reads/writes happen here via pathlib - one
read, one atomic write (tempfile + os.replace) per §6 step 9 (C4, I4).
"""

from argparse import Namespace

from dibs.runtime import Context, Reply


def init_board(ctx: Context, args: Namespace) -> Reply:
    """Create the board from a parsed plan; print key + roster (SSoT §6).

    names.mint_board_key -> plansync.found_board (False -> steer
    BOARD_EXISTS pointing to sync) -> plansync.apply_sync (everything is
    new, D24) -> store.registry_record -> views.format_board + handoff.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 10: init_board')


def verify_board(args: Namespace) -> Reply:
    """Render the parse preview; create and touch nothing (D21, D24).

    The one pure verb, so no Context: read file, planfile.parse_plan,
    planfile.compute_sync(items, ()) for would-be ids, views.format_board
    on plan.rows with key ''. No board, no identity, no events; an
    existing board file is noted in one line pointing to list.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 10: verify_board')


def sync_board(ctx: Context, args: Namespace) -> Reply:
    """Reconcile plan text with the board per the SSoT §8 sync table.

    planfile.parse_plan -> plansync.apply_sync (one transaction,
    C11) -> views.format_sync; ambiguities are reported, never guessed
    (I5, I9, D22). Annotation is the pipeline's settle tail (§6).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 10: sync_board')


def note_verb(ctx: Context, args: Namespace) -> Reply:
    """Broadcast, or direct with --for, one note event (D10, SSoT §6)."""
    raise NotImplementedError('ARCHITECTURE §13 step 10: note_verb')


def list_board(ctx: Context, args: Namespace) -> Reply:
    """Show board key, tasks with child progress, recent events (SSoT §6).

    Headed by the board key (the lost-key recovery path, D20); gated
    parents show 2/3-style progress (D22); reaping already ran via the
    pipeline (C10).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 10: list_board')
