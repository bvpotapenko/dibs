"""The reply envelope, the hint catalog, and the ONLY error factory (C5, C7).

Output is prompt surface: terse, steering, self-sufficient (I10); in an
8k window every dibs token competes with code. Level L1 (imports L0).
Member budget 6 (ARCHITECTURE §3). Bodies live in views.py.
"""

from enum import Enum
from types import MappingProxyType

from dibs.records import Event
from dibs.runtime import DibsError, Reply

EVENT_CAP = 15  # SSoT §13: unseen events shown before '... and N more'
LIST_SEP = ', '  # how queries join the ids and names a steer lists (C5)


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
    BOARD_EXISTS = 'board_exists'
    NO_BOARD = 'no_board'
    MANY_BOARDS = 'many_boards'
    UNKNOWN_ACTOR = 'unknown_actor'
    OLD_SQLITE = 'old_sqlite'


# Refusal -> (message, command) templates; slots are positional and
# listed per entry. Every command runs as printed (I10); '...' and
# <angle brackets> mark the one value only the reader can supply.
CATALOG = MappingProxyType({
    # (raw, nearest, verb): the caller's own verb, id corrected (D14)
    Refusal.UNKNOWN_TASK: (
        'Unknown task {0} - did you mean {1}?',
        'dibs {2} {1}',
    ),
    # (task_id, holder name): claim it back, else note and move on (§11)
    Refusal.NOT_OWNER: (
        '{0} is not yours - {1} holds it; you were probably reaped.',
        'dibs claim --task {0}',
    ),
    # (member, holder name or status): a bundle is all-or-none (D6)
    Refusal.TAKEN: (
        '{0} is already taken ({1}); the bundle was refused whole.',
        'dibs claim',
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
        'dibs claim',
    ),
    # (): the end state - review is the human's (§11)
    Refusal.EMPTY: (
        'No tasks remain; stop.',
        'dibs list',
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
    # (verb, boards): enumerate, never guess (D18)
    Refusal.MANY_BOARDS: (
        'Several boards in scope: {1}. Pick the one matching the plan '
        'path you were given - never guess.',
        'dibs {0} --plan <one of: {1}>',
    ),
    # (actor,): almost always the wrong board - fix the binding (D8, D18)
    Refusal.UNKNOWN_ACTOR: (
        'Identity {0} is unknown on this board - probably the wrong '
        'board; check $DIBS_BOARD against the plan path you were given.',
        'export DIBS_BOARD=<key or plan.md you were given>',
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
    collapses to '... and N more - run `dibs list`' (SSoT §13).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 9: render_reply')


def render_error(err: DibsError) -> str:
    """Format '<message>' with 'Run: <steer>' as the last line (I10)."""
    raise NotImplementedError('ARCHITECTURE §13 step 9: render_error')


def format_event(event: Event) -> str:
    """Compress one event to one line; agent shown by name (D10, D14, I7)."""
    raise NotImplementedError('ARCHITECTURE §13 step 9: format_event')


def next_hint(moment: str, names: tuple[str, ...] = ()) -> str:
    """Look up the next-expected command for a moment, exact syntax (D14).

    Moments: claim, done, unlocked, drop, note, sync, init, list, empty.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 9: next_hint')


def steer(kind: Refusal, names: tuple[str, ...] = ()) -> DibsError:
    """Build the one DibsError: catalog (message, command) per kind (C7).

    Slots are positional and documented per catalog entry; every command
    is runnable as printed (I10).
    """
    message, command = CATALOG[kind]
    return DibsError(message.format(*names), command.format(*names))
