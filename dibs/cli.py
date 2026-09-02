"""The only process-edge module: argv, env, print, exit codes (C1).

Level L5 (imports L0-L4). Member budget 4 + VERB_TABLE constant
(ARCHITECTURE §3). Every invocation runs the same §6 pipeline; verbs
never skip steps (C10).
"""

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from pathlib import Path
from types import MappingProxyType

from dibs.verbs import board, work

ENV_ACTOR = 'DIBS_AS'  # identity minted by the launcher (D8)
ENV_BOARD = 'DIBS_BOARD'  # board key or plan path (D18, D19)
ENV_TRACE = 'DIBS_TRACE'  # non-empty enables the invocation trace (D23)

EXIT_OK = 0  # §6: success
EXIT_USER = 1  # §6: steered user error (DibsError, I10)
EXIT_ENV = 2  # §6: environment error (sqlite3.Error), steer 'retry'

VERB_TABLE = MappingProxyType({
    'init': board.init_board,
    'verify': board.verify_board,
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

    Steps: parse args; resolve_board (D18/D20); store.connect +
    ensure_schema; resolve_actor + queries.verify_actor (D8); auto-sync
    when meta.plan_mtime moved (I9); transitions.housekeeping (D9);
    VERB_TABLE dispatch; queries.deliver_events (D10); annotate plan on
    state change via tempfile + os.replace (I4); print rendered reply.
    DibsError -> stderr + EXIT_USER; sqlite3.Error -> stderr + EXIT_ENV
    (C7). Finally: with $DIBS_TRACE set (non-empty), append one
    TraceRecord line via trace.write_trace - success and both error
    paths alike, best-effort, never altering output or exit (D23).
    init skips sync/housekeeping and annotates unconditionally;
    verify runs pure - no board, no DB, no identity (D21).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 9: cli.main')


def build_parser() -> ArgumentParser:
    """Build the tolerant parser: --task A3 / --task=A3 / positional (D14).

    Global flags: --plan (key or path, D18/D20) and --as (D8); every
    error message ends with the literal next command (I10).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 9: build_parser')


def resolve_actor(args: Namespace) -> str | None:
    """Pick identity: --as, else $DIBS_AS, else None (D8)."""
    raise NotImplementedError('ARCHITECTURE §13 step 9: resolve_actor')


def resolve_board(args: Namespace) -> tuple[Path, Path]:
    """Resolve (plan path, board path): --plan | $DIBS_BOARD | upward walk.

    A value is tried as a board key via store.registry_lookup first,
    then as a path (D20); the board file is .<plan-name>.dibs beside
    the plan (D2). Many boards -> enumerating DibsError with runnable
    steers; none -> the cd/--plan steer. Workers are never steered to
    init (D18).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 9: resolve_board')
