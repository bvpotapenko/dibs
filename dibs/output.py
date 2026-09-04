"""The reply envelope, the hint catalog, and the ONLY error factory (C5, C7).

Output is prompt surface: terse, steering, self-sufficient (I10); in an
8k window every dibs token competes with code. Level L1 (imports L0).
Member budget 6 (ARCHITECTURE §3). Bodies live in views.py.
"""

from enum import Enum
from types import MappingProxyType

from dibs.records import Event, EventKind, Status, agent_name
from dibs.runtime import DibsError, Reply

EVENT_CAP = 15  # SSoT §13: unseen events shown before '... and N more'
LIST_SEP = ', '  # how queries join the ids and names a steer lists (C5)
SEPARATOR = '-- while you were away --'  # GUIDE: heads the event feed
OVERFLOW = '... and {0} more - run: dibs list'  # SSoT §13 piggyback cap
HINT = 'next: {0}'
RESUME = 'dibs claim'  # the worker loop's default next step (SSoT §10a)
REVIEW = 'dibs list'  # the human's board view and the lost-key path (D20)
# NOT_OWNER's slot 1 is the row's state now: a holder's name, or - the
# common case, a reap that already freed the row (§11) - its status,
# which a caller reading an unowned row hands over empty.
UNOWNED = Status.TODO.value
ERROR = '{0}\nRun: {1}'  # I10: the last line is the command to run
AUDIENCE = ' to {0}'  # a directed note (D10)
# D18: several boards are enumerated, one runnable line per board, and
# the Run: line stays the choice form so none is silently preferred.
OPTION = 'dibs {0} --plan {1}'

# One line per event kind; slots task, agent, audience, text - every
# stored text is display-safe (titles, notes, names, key, summary; I7)
EVENT_LINES = MappingProxyType({
    EventKind.INIT: 'init: board {text}',
    EventKind.SYNC: 'sync: {text}',
    EventKind.JOIN: 'join: {agent}',
    EventKind.CLAIM: 'claim {task} by {agent}: {text}',
    EventKind.DONE: 'done {task} by {agent}: "{text}"',
    EventKind.DROP: 'drop {task} by {agent}: "{text}"',
    EventKind.NOTE: 'note{audience} by {agent}: "{text}"',
    EventKind.REAP: 'reap {task}: {text} timed out',
})

# UNKNOWN_TASK steers with the caller's own verb, and the verbs differ
# in what they require (SSoT §6: done takes a mandatory --note), so the
# corrected command comes from here, keyed by the verb slot; slot 1 is
# the nearest id. An unlisted verb falls back to the catalog line (I10).
VERB_FORMS = MappingProxyType({
    'claim': 'dibs claim --task {1}',
    'done': 'dibs done {1} --note "..."',
    'drop': 'dibs drop {1}',
})

# BAD_USAGE steers with the canonical form of the verb the caller was
# reaching for, so a malformed invocation is answered by the shape that
# works (SSoT §6); an invocation with no verb at all falls back to the
# catalog line, the worker loop's own next step.
USAGE = MappingProxyType({
    'init': 'dibs init <plan.md>',
    'verify': 'dibs verify <plan.md>',
    'sync': 'dibs sync',
    'join': 'dibs join',
    'claim': RESUME,
    'done': 'dibs done <ID> --note "..."',
    'drop': 'dibs drop <ID>',
    'note': 'dibs note "..."',
    'list': REVIEW,
})

# The next expected command after each moment, exact syntax (D14, I10)
HINTS = MappingProxyType({
    'claim': 'dibs done {0} --note "..."',
    'done': RESUME,
    'unlocked': 'dibs claim --task {0}',
    'drop': RESUME,
    'note': RESUME,
    'sync': REVIEW,
    'verify': 'dibs init {0}',
    'init': 'dibs list --plan {0}',
    'list': RESUME,
})


class Refusal(str, Enum):
    """Every way the board says no; the keys of the steer catalog (D14)."""

    UNKNOWN_TASK = 'unknown_task'
    NOT_OWNER = 'not_owner'
    TAKEN = 'taken'
    GATED = 'gated'
    OVERSIZED = 'oversized'
    HAND_FULL = 'hand_full'
    WAITING = 'waiting'
    EMPTY = 'empty'
    UNKNOWN_AUDIENCE = 'unknown_audience'
    BOARD_EXISTS = 'board_exists'
    NO_BOARD = 'no_board'
    MANY_BOARDS = 'many_boards'
    UNKNOWN_ACTOR = 'unknown_actor'
    BAD_USAGE = 'bad_usage'
    OLD_SQLITE = 'old_sqlite'
    DB_ERROR = 'db_error'


# Refusal -> (message, command) templates; slots are positional and
# listed per entry. Every command runs as printed (I10); '...' and
# <angle brackets> mark the one value only the reader can supply.
CATALOG = MappingProxyType({
    # (raw, nearest, verb): the caller's own verb, id corrected - the
    # command itself comes from VERB_FORMS[verb], since each verb takes
    # different mandatory arguments (D14, SSoT §6)
    Refusal.UNKNOWN_TASK: (
        'Unknown task {0} - did you mean {1}?',
        RESUME,
    ),
    # (task_id, holder name or UNOWNED): claim it back, else note and
    # move on (§11) - an empty holder means reaping already freed it
    Refusal.NOT_OWNER: (
        '{0} is not yours (now {1}) - you were probably reaped.',
        'dibs claim --task {0}',
    ),
    # (member, holder name or status): a bundle is all-or-none (D6)
    Refusal.TAKEN: (
        '{0} is already taken ({1}); the bundle was refused whole.',
        RESUME,
    ),
    # (parent, open children, first open child): leaves first (D22)
    Refusal.GATED: (
        '{0} waits on its open children: {1}.',
        'dibs claim --task {2}',
    ),
    # (bundle size, max_hand, first member): the bundle can never fit (D6)
    Refusal.OVERSIZED: (
        'A bundle of {0} exceeds the hand of {1} - claim at most {1} at '
        'a time.',
        'dibs claim --task {2}',
    ),
    # (held ids, first held id, max_hand): finish or drop first (D6)
    Refusal.HAND_FULL: (
        'Hand full ({2} at most): you hold {0} - finish or drop it first.',
        'dibs done {1} --note "..."',
    ),
    # (todo count, held gates, their holders): waiting, not done (D6, D22)
    Refusal.WAITING: (
        'Nothing available yet: {0} task(s) wait on {1} (held by {2}) - '
        'retry after finishing something else, or stop if your launcher '
        'respawns workers.',
        RESUME,
    ),
    # (): the end state - review is the human's (§11)
    Refusal.EMPTY: (
        'No tasks remain; stop.',
        REVIEW,
    ),
    # (name, text): note --for a name no agent here carries; the
    # command is the same note as a broadcast, which always lands (§11)
    Refusal.UNKNOWN_AUDIENCE: (
        'No agent named {0} on this board - names are the ones events '
        'show.',
        'dibs note "{1}"',
    ),
    # (existing key,): init on a founded board points to sync (SSoT §6)
    Refusal.BOARD_EXISTS: (
        'Board {0} already exists - sync it instead.',
        'dibs sync --plan {0}',
    ),
    # (verb,): workers cd or --plan; init is an author aside only (D18)
    Refusal.NO_BOARD: (
        'No board found - cd to the directory holding the plan or pass '
        '--plan <key or plan.md>; plan authors found one with '
        'dibs init <plan.md>.',
        'dibs {0} --plan <key or plan.md>',
    ),
    # (verb, one board per slot): enumerate, never guess (D18); steer
    # fills {1} with the joined list and {2} with an OPTION line each
    Refusal.MANY_BOARDS: (
        'Several boards in scope - pick the one matching the plan path '
        'you were given, never guess:\n{2}',
        'dibs {0} --plan <one of: {1}>',
    ),
    # (actor,): almost always the wrong board - fix the binding (D8, D18)
    Refusal.UNKNOWN_ACTOR: (
        'Identity {0} is unknown on this board - probably the wrong '
        'board; check $DIBS_BOARD against the plan path you were given.',
        'export DIBS_BOARD=<key or plan.md you were given>',
    ),
    # (message, verb): argparse's own one-liner, then the verb's
    # canonical form from USAGE - a usage error is a refusal like any
    # other, never a usage dump (SSoT §6, C7)
    Refusal.BAD_USAGE: (
        '{0}',
        RESUME,
    ),
    # (): the board file itself failed - environment, not the caller;
    # cli exits 2 on this one and the command is worth retrying (§6)
    Refusal.DB_ERROR: (
        'The board could not be read or written - another process may '
        'hold it; run your last command again in a moment.',
        REVIEW,
    ),
    # (version,): the ARCHITECTURE §1 floor, refused up front
    Refusal.OLD_SQLITE: (
        'SQLite {0} is too old - dibs needs 3.35 or newer with JSON; run '
        'it with a newer Python.',
        "python3 -c 'import sqlite3, sys; "
        "print(sqlite3.sqlite_version, sys.executable)'",
    ),
})


def render_reply(reply: Reply) -> str:
    """Join result lines, capped one-line events, then the hint (D14).

    Empty parts vanish (join prints the bare id). Overflow past EVENT_CAP
    collapses to '... and N more - run: dibs list' (SSoT §13).
    """
    shown = reply.events[:EVENT_CAP]
    hidden = len(reply.events) - len(shown)
    feed = [format_event(event) for event in shown]
    return '\n'.join((
        *reply.lines,
        *([SEPARATOR, *feed] if feed else []),
        *([OVERFLOW.format(hidden)] if hidden else []),
        *([HINT.format(reply.hint)] if reply.hint else []),
    ))


def render_error(err: DibsError) -> str:
    """Format '<message>' with 'Run: <steer>' as the last line (I10)."""
    return ERROR.format(err.message, err.steer)


def format_event(event: Event) -> str:
    """Compress one event to one line; agent shown by name (D10, D14, I7)."""
    fields = {
        'task': event.task_id,
        'agent': agent_name(event.agent),
        'audience': AUDIENCE.format(agent_name(event.to_agent)) * bool(
            event.to_agent,
        ),
        'text': ' '.join(event.text.split()),
    }
    return EVENT_LINES[event.kind].format(**fields)


def next_hint(moment: str, names: tuple[str, ...] = ()) -> str:
    """Look up the next-expected command for a moment, exact syntax (D14).

    Moments: claim, done, unlocked, drop, note, sync, verify, init, list;
    no 'empty' - EMPTY is a refusal, and a refusal carries its own steer.
    """
    return HINTS[moment].format(*names)


def steer(kind: Refusal, names: tuple[str, ...] = ()) -> DibsError:
    """Build the one DibsError: catalog (message, command) per kind (C7).

    Slots are positional and documented per catalog entry; every command
    is runnable as printed (I10). Four kinds have a slot that words the
    steer rather than only filling it: UNKNOWN_TASK's verb picks its own
    command form (`done` carries the --note SSoT §6 makes mandatory),
    BAD_USAGE's verb picks that verb's canonical form the same way,
    NOT_OWNER's holder is empty exactly when a reap already freed the row
    - the common case, so it reads as the status (§11) - and MANY_BOARDS
    takes one board per slot and enumerates each as its own command (D18).
    """
    message, command = CATALOG[kind]
    if kind is Refusal.UNKNOWN_TASK:
        command = VERB_FORMS.get(names[2], command)
    if kind is Refusal.BAD_USAGE:
        command = USAGE.get(names[1], command)
    if kind is Refusal.NOT_OWNER:
        names = (names[0], names[1] or UNOWNED)
    if kind is Refusal.MANY_BOARDS:
        boards = names[1:]
        names = (
            names[0],
            LIST_SEP.join(boards),
            '\n'.join(OPTION.format(names[0], board) for board in boards),
        )
    return DibsError(message.format(*names), command.format(*names))
