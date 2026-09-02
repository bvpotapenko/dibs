"""Author-side and shared verbs: init, verify, sync, note, list (SSoT §6).

Level L4 (imports L0-L3). Member budget 5 (ARCHITECTURE §3). C6 rules
as in work.py; plan file reads/writes happen here via pathlib - one
read, one atomic write (tempfile + os.replace) per §6 step 9 (C4, I4).
"""

from argparse import Namespace

from dibs.runtime import Context, Reply


def init_board(ctx: Context, args: Namespace) -> Reply:
    """Create the board from a parsed plan; print key + roster (SSoT §6).

    Parse once, ensure schema, mint + register the board key (D20),
    honor --max-hand (D6), annotate unconditionally (§6 note). Refuses
    an existing board, steering to sync.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 8: init_board')


def verify_board(ctx: Context, args: Namespace) -> Reply:
    """Render the parse preview; create and touch nothing (D21, D22).

    Pure pipeline: read file, planfile.parse_plan, output.format_preview.
    No board, no identity, no events; an existing board is noted in one
    line pointing to list.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 8: verify_board')


def sync_board(ctx: Context, args: Namespace) -> Reply:
    """Reconcile plan text with the board per the SSoT §8 sync table.

    Orchestrates planfile.parse_plan + compute_sync, transitions
    (import_author_done and friends), then annotation; ambiguities are
    reported, never guessed (I5, I9, D22).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 8: sync_board')


def note_verb(ctx: Context, args: Namespace) -> Reply:
    """Broadcast, or direct with --for, one note event (D10, SSoT §6)."""
    raise NotImplementedError('ARCHITECTURE §13 step 8: note_verb')


def list_board(ctx: Context, args: Namespace) -> Reply:
    """Show board key, tasks with child progress, recent events (SSoT §6).

    Headed by the board key (the lost-key recovery path, D20); gated
    parents show 2/3-style progress (D22); reaping already ran via the
    pipeline (C10).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 8: list_board')
