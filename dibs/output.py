"""The reply envelope, the hint catalog, and the ONLY error factory (C5, C7).

Output is prompt surface: terse, steering, self-sufficient (I10); in an
8k window every dibs token competes with code. Level L1 (imports L0).
Member budget 6 (ARCHITECTURE §3). Bodies live in views.py.
"""

from enum import Enum

from dibs.records import Event
from dibs.runtime import DibsError, Reply

EVENT_CAP = 15  # SSoT §13: unseen events shown before '... and N more'


class Refusal(str, Enum):
    """Every way the board says no; the keys of the steer catalog (D14)."""

    UNKNOWN_TASK = 'unknown_task'
    NOT_OWNER = 'not_owner'
    TAKEN = 'taken'
    GATED = 'gated'
    HAND_FULL = 'hand_full'
    WAITING = 'waiting'
    EMPTY = 'empty'
    BOARD_EXISTS = 'board_exists'
    NO_BOARD = 'no_board'
    MANY_BOARDS = 'many_boards'
    UNKNOWN_ACTOR = 'unknown_actor'
    OLD_SQLITE = 'old_sqlite'


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
    is runnable as printed (I10). Landed at step 6 with queries.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 6: output.steer')
