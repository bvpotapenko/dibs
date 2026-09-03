"""The only process-edge module: argv, env, print, exit codes (C1).

Level L5 (imports L0-L4). Member budget 6 + VERB_TABLE constant
(ARCHITECTURE §3). Every invocation runs the same §6 pipeline; `run`
is the one place that knows the three routes (verify / init / worker
verbs); no lower module branches on a verb name (C10).
"""

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from pathlib import Path
from types import MappingProxyType

from dibs.runtime import Context, Reply
from dibs.verbs import board, work

ENV_ACTOR = 'DIBS_AS'  # identity minted by the launcher (D8)
ENV_BOARD = 'DIBS_BOARD'  # board key or plan path (D18, D19)
ENV_TRACE = 'DIBS_TRACE'  # non-empty enables the invocation trace (D23)

EXIT_OK = 0  # §6: success
EXIT_USER = 1  # §6: steered user error (DibsError, I10)
EXIT_ENV = 2  # §6: environment error (sqlite3.Error), steer 'retry'
SQLITE_FLOOR = (3, 35)  # ARCHITECTURE §1: RETURNING, UPSERT, json_each

# verify is absent on purpose: it is the pure route in `run` (D21, §6).
VERB_TABLE = MappingProxyType({
    'init': board.init_board,
    'sync': board.sync_board,
    'join': work.join_session,
    'claim': work.claim_task,
    'done': work.done_task,
    'drop': work.drop_task,
    'note': board.note_verb,
    'list': board.list_board,
})


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ARCHITECTURE §6 pipeline and return the exit code.

    SQLite floor check (OLD_SQLITE steer); parse; `run`; print the
    rendered reply. DibsError -> stderr + EXIT_USER; sqlite3.Error ->
    stderr + EXIT_ENV (C7). Finally: with $DIBS_TRACE set, append one
    TraceRecord line - success and both error paths alike, best-effort,
    never altering output or exit (D23).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 11: cli.main')


def run(args: Namespace) -> Reply:
    """Route one parsed invocation (§6): verify pure, init founds, rest settle.

    verify: read, parse, compute_sync against no rows, format_board.
    init: resolve plan, open_context(actor=None), verb, settle tail.
    others: resolve_board, open_context, auto-sync (I9), housekeeping
    (D9), VERB_TABLE dispatch, then the settle tail: deliver_events
    (D10) and annotate plan.md via tempfile + os.replace when the
    annotated text differs (I4).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 11: cli.run')


def open_context(args: Namespace, actor: str | None) -> Context:
    """Connect + ensure_schema; verify a supplied actor (D8); stamp now."""
    raise NotImplementedError('ARCHITECTURE §13 step 11: cli.open_context')


def build_parser() -> ArgumentParser:
    """Build the tolerant parser: --task A3 / --task=A3 / positional (D14).

    Global flags: --plan (key or path, D18/D20) and --as (D8); every
    error message ends with the literal next command (I10).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 11: build_parser')


def resolve_actor(args: Namespace) -> str | None:
    """Pick identity: --as, else $DIBS_AS, else None (D8)."""
    raise NotImplementedError('ARCHITECTURE §13 step 11: resolve_actor')


def resolve_board(args: Namespace) -> tuple[Path, Path]:
    """Resolve (plan path, board path): --plan | $DIBS_BOARD | upward walk.

    A value is tried as a board key via store.registry_lookup first,
    then as a path (D20); the board file is .<plan-name>.dibs beside
    the plan (D2). Many boards -> MANY_BOARDS; none -> NO_BOARD (D18);
    a path with no board file -> NO_BOARD naming init (authors use
    paths, D20) - except for init itself, which needs only the plan.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 11: resolve_board')
