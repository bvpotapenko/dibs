"""The only process-edge module: argv, env, print, exit codes (C1).

Level L5 (imports L0-L4). Member budget 6 + VERB_TABLE constant
(ARCHITECTURE §3). Every invocation runs the same §6 pipeline; `run`
is the one place that knows the three routes (verify / init / worker
verbs); no lower module branches on a verb name (C10). Steps 4-5 of
the pipeline (auto-sync, housekeeping) sit inside `open_context`: they
are what makes a Context usable by a verb, and keeping them there
leaves `run` at the settle tail the budgets allow.
"""

import os
import sqlite3
import sys
import time
from argparse import SUPPRESS, ArgumentParser, Namespace
from collections.abc import Sequence
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn

from dibs import output, planfile, plansync, queries, store, trace, transitions
from dibs.runtime import Context, DibsError, Reply
from dibs.verbs import board, work

ENV_ACTOR = 'DIBS_AS'  # identity minted by the launcher (D8)
ENV_BOARD = 'DIBS_BOARD'  # board key or plan path (D18, D19)
ENV_TRACE = 'DIBS_TRACE'  # non-empty enables the invocation trace (D23)

EXIT_OK = 0  # §6: success
EXIT_USER = 1  # §6: steered user error (DibsError, I10)
EXIT_ENV = 2  # §6: environment error (sqlite3.Error), steer 'retry'
SQLITE_FLOOR = (3, 35)  # ARCHITECTURE §1: RETURNING, UPSERT, json_each

PROG = 'dibs'
TASK = 'task'  # the id slot every task-taking verb fills (D14)
INIT = 'init'  # the one verb that founds a board (D20, D24)
VERIFY = 'verify'  # the one pure verb: no board, no DB, no identity (D21)
SYNC = 'sync'
JOIN = 'join'
CLAIM = 'claim'
DONE = 'done'
DROP = 'drop'
NOTE = 'note'
ANONYMOUS = (INIT, JOIN)  # no caller identity: the author founds, join mints
IMPORTERS = (INIT, SYNC)  # the verb IS the import, so no auto-sync ahead of it
MAX_HAND_DEFAULT = 1  # SSoT §13; init --max-hand overrides per board (D6)
TEMP_SUFFIX = '.dibs-tmp'  # the annotation's neighbour, replaced in (I4)
LINE = '{0}\n'  # stdout and stderr both end with one newline (C1)

# verify is absent on purpose: it is the pure route in `run` (D21, §6).
VERB_TABLE = MappingProxyType({
    INIT: board.init_board,
    SYNC: board.sync_board,
    JOIN: work.join_session,
    CLAIM: work.claim_task,
    DONE: work.done_task,
    DROP: work.drop_task,
    NOTE: board.note_verb,
    'list': board.list_board,
})
VERBS = (*VERB_TABLE, VERIFY)

# The namespace every invocation starts from: one default per
# verb-specific slot, so each verb reads the same attributes whatever
# was typed, plus `verb` and `plan_path` for the D23 trace of an
# invocation that never parsed. `main` hands it to parse_args, which
# fills it in place - so an unsupplied argument keeps the value below,
# including one given before the verb (`dibs --plan x claim`), and the
# flags argparse defaults from the environment (--plan, --as) are
# absent here on purpose: a slot listed below would shadow them.
DEFAULTS = MappingProxyType({
    'verb': None,
    TASK: '',
    NOTE: None,
    'to_name': None,
    'text': '',
    'max_hand': MAX_HAND_DEFAULT,
    'plan_path': None,
})
# add_argument keyword sets, immutable per WPS407; NARGS and METAVAR
# are argparse's own keyword names, spelled once each.
NARGS = 'nargs'
METAVAR = 'metavar'
BUNDLE = MappingProxyType({NARGS: '*', METAVAR: 'ID'})
ONE_ID = MappingProxyType({NARGS: '?', METAVAR: 'ID'})
OPTIONAL = MappingProxyType({NARGS: '?', METAVAR: 'plan.md'})
HAND = MappingProxyType({'type': int, METAVAR: 'N'})
NEEDED = MappingProxyType({'required': True})
AUDIENCE = MappingProxyType({'dest': 'to_name'})
ACTOR = MappingProxyType({'dest': 'actor'})
BARE = MappingProxyType({})

# The board and identity flags every verb accepts (D8, D18, D20).
SHARED = ((('--plan',), BARE), (('--as',), ACTOR))
# verb -> its own (flags, keywords) rows. Together with SHARED they give
# every tolerant form D14 asks for: `--task A3`, `--task=A3` and
# positional `dibs claim A3` all land in args.task.
PER_VERB = MappingProxyType({
    INIT: ((('plan',), OPTIONAL), (('--max-hand',), HAND)),
    VERIFY: ((('plan',), OPTIONAL),),
    CLAIM: (((TASK,), BUNDLE), (('--task',), BUNDLE)),
    DONE: (((TASK,), ONE_ID), (('--task',), BARE), (('--note',), NEEDED)),
    DROP: (((TASK,), ONE_ID), (('--task',), BARE), (('--note',), BARE)),
    NOTE: ((('text',), BARE), (('--for',), AUDIENCE)),
})
ARGUMENTS = MappingProxyType({
    verb: (*SHARED, *PER_VERB.get(verb, ())) for verb in VERBS
})


class Parser(ArgumentParser):
    """The one subclass (ARCHITECTURE §1): a usage error steers, never exits 2.

    argparse funnels every usage failure - missing verb, unknown verb,
    missing --note, unrecognized flag - through `error`, on every
    Python dibs supports; overriding it is the only hook that covers
    them all (§1 receipt). Both the top parser and every subparser are
    this class (build_parser passes parser_class=Parser).
    """

    def error(self, message: str) -> NoReturn:
        """Raise output.steer(BAD_USAGE, (message, verb)) - exit 1 (SSoT §6).

        verb is self.prog.removeprefix(PROG).strip(): 'done' for the
        `dibs done` subparser, '' for the top parser, so the steer is the
        verb's canonical form from output.USAGE (D14, I10).
        """
        raise output.steer(
            output.Refusal.BAD_USAGE,
            (message, self.prog.removeprefix(PROG).strip()),
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ARCHITECTURE §6 pipeline and return the exit code.

    Parse, `run`, write the rendered reply to stdout. DibsError ->
    stderr + EXIT_USER; sqlite3.Error -> stderr + EXIT_ENV (C7); a
    malformed invocation is a DibsError too, raised by Parser.error, so
    parsing happens inside the try - argparse fills the DEFAULTS
    namespace in place, which is why an invocation that never parsed
    still has a request to trace (verb and plan None). Finally: with
    $DIBS_TRACE set, append one TraceRecord line - success and both
    error paths alike, best-effort, never altering output or exit (D23).
    """
    now = int(time.time())
    args = Namespace(**DEFAULTS)
    stream, text, code = sys.stdout, '', EXIT_OK
    try:
        text = output.render_reply(run(build_parser().parse_args(argv, args)))
    except DibsError as refusal:
        stream, text, code = (
            sys.stderr, output.render_error(refusal), EXIT_USER,
        )
    except sqlite3.Error:
        stream, text, code = (
            sys.stderr,
            output.render_error(output.steer(output.Refusal.DB_ERROR)),
            EXIT_ENV,
        )
    finally:
        if os.environ.get(ENV_TRACE):
            trace.write_trace(
                trace.trace_path(args.plan_path, now),
                trace.TraceRecord(
                    ts=now,
                    argv=tuple(argv or sys.argv[1:]),
                    actor=args.actor,
                    plan=args.plan_path and args.plan_path.as_posix(),
                    verb=args.verb,
                    exit_code=code,
                    outcome=text,
                ),
            )
    stream.write(LINE.format(text))
    return code


def run(args: Namespace) -> Reply:
    """Route one parsed invocation (§6): verify pure, init founds, rest settle.

    verify is answered from the file alone (D21); every other verb gets
    a settled Context, runs, and then shares the settle tail: the plan
    is re-annotated through a neighbour file and os.replace when the
    text changed (I4), and the caller's unseen events ride the reply
    (D10). The ANONYMOUS verbs carry no caller identity - init is the
    author's command and join only mints (D8) - so their tail delivers
    nothing. The SQLite floor is checked here, once, before any board
    is touched (ARCHITECTURE §1).
    """
    if sqlite3.sqlite_version_info < SQLITE_FLOOR:
        raise output.steer(output.Refusal.OLD_SQLITE, (sqlite3.sqlite_version,))
    if args.verb == VERIFY:
        args.plan_path = Path(args.plan or '')
        return board.verify_board(args)
    ctx = open_context(
        args, None if args.verb in ANONYMOUS else args.actor,
    )
    reply = VERB_TABLE[args.verb](ctx, args)
    text = ctx.plan_path.read_text()
    annotated = planfile.annotate_lines(
        text, queries.board_snapshot(ctx.conn).tasks,
    )
    if annotated != text:
        neighbour = ctx.plan_path.with_name(ctx.plan_path.name + TEMP_SUFFIX)
        neighbour.write_text(annotated)
        neighbour.replace(ctx.plan_path)
    return Reply(
        reply.lines, queries.deliver_events(ctx.conn, ctx.actor), reply.hint,
    )


def open_context(args: Namespace, actor: str | None) -> Context:
    """Connect + ensure_schema; verify a supplied actor (D8); stamp now.

    Then settle the board so the verb meets it ready (§6 steps 3-5): the
    board key's registry entry self-heals when the plan moved (D20), a
    plan edited since the last sync is imported, silently - its SYNC
    event is the record (I9) - and stale claims are reaped before the
    verb runs, so claim sees them (D9, C10). An IMPORTERS verb skips the
    auto-sync because the verb itself is that import; housekeeping runs
    for every board verb, a no-op on init's brand-new board.
    """
    plan_path, db_path = resolve_board(args)
    ctx = Context(
        store.connect(db_path), plan_path, db_path, actor, int(time.time()),
    )
    store.ensure_schema(ctx.conn)
    if actor is not None and not queries.verify_actor(ctx.conn, actor):
        raise output.steer(output.Refusal.UNKNOWN_ACTOR, (actor,))
    snapshot = queries.board_snapshot(ctx.conn)
    store.registry_record(snapshot.key, plan_path)
    edited = plan_path.stat().st_mtime_ns
    if args.verb not in IMPORTERS and edited != snapshot.plan_mtime:
        plansync.apply_sync(
            ctx.conn, ctx.now, planfile.parse_plan(plan_path.read_text()),
            edited,
        )
    transitions.housekeeping(ctx.conn, actor, ctx.now)
    return ctx


def build_parser() -> Parser:
    """Build the tolerant parser: --task A3 / --task=A3 / positional (D14).

    Global flags: --plan (key or path, D18/D20) and --as (D8) sit on
    the top parser and, through SHARED, on every verb, so both `dibs
    --plan x claim` and `dibs claim --plan x` parse. Their defaults are
    the environment, read once and here alone (C1), so nothing below
    argv ever falls back to it. Every subparser suppresses its own
    defaults (see DEFAULTS), so an unsupplied flag never overwrites one
    given before the verb, and every parser is a Parser, whose usage
    errors steer instead of exiting (§1). The verb-slot defaults are
    not set here: they ride the namespace `main` passes in, so one
    mechanism carries them and none can shadow the two above.
    """
    parser = Parser(prog=PROG)
    parser.add_argument('--plan', default=os.environ.get(ENV_BOARD))
    parser.add_argument('--as', dest='actor', default=os.environ.get(ENV_ACTOR))
    verbs = parser.add_subparsers(
        dest='verb', required=True, parser_class=Parser,
    )
    made = {
        verb: verbs.add_parser(verb, argument_default=SUPPRESS)
        for verb in VERBS
    }
    tuple(  # each row is (flags, keywords); see ARGUMENTS
        made[verb].add_argument(*row[0], **row[1])
        for verb in ARGUMENTS
        for row in ARGUMENTS[verb]
    )
    return parser


def resolve_board(args: Namespace) -> tuple[Path, Path]:
    """Resolve (plan path, board path): --plan | $DIBS_BOARD | upward walk.

    The value is args.plan, whose default is already $DIBS_BOARD
    (build_parser). It is tried as a board key via store.registry_lookup
    first, then as a path (D20); the board file is .<plan-name>.dibs
    beside the plan (D2). Many boards -> MANY_BOARDS; none -> NO_BOARD (D18);
    a path with no board file -> NO_BOARD naming init (authors use
    paths, D20) - except for init itself, which needs only the plan,
    which every verb needs: a plan that is not there steers like a
    board that is not there, never a traceback (I10). The resolved plan
    is recorded on args so the D23 trace names it.
    """
    given = args.plan or ''
    plans = [store.registry_lookup(given) or Path(given)] if given else [
        found.with_name(
            found.name.removeprefix(store.BOARD_HEAD).removesuffix(
                store.BOARD_TAIL,
            ),
        )
        for found in next(filter(None, (
            sorted(folder.glob(store.BOARD_GLOB))
            for folder in (Path.cwd(), *Path.cwd().parents)
        )), ())
    ]
    if len(plans) > 1:
        raise output.steer(
            output.Refusal.MANY_BOARDS,
            (args.verb, *(plan.name for plan in plans)),
        )
    if not plans:
        raise output.steer(output.Refusal.NO_BOARD, (args.verb,))
    args.plan_path = plans[0]
    board_path = args.plan_path.with_name(
        store.BOARD_FILE.format(args.plan_path.name),
    )
    ready = args.plan_path.is_file() and (
        args.verb == INIT or board_path.is_file()
    )
    if not ready:  # a plan or a board that is not there steers, never traces
        raise output.steer(output.Refusal.NO_BOARD, (args.verb,))
    return args.plan_path, board_path
