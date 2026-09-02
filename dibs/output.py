"""Every user-facing string and terseness cap lives here (C5, D14).

Output is prompt surface: terse, steering, self-sufficient (I10); in an
8k window every dibs token competes with code. Level L1 (imports L0).
Member budget 4 (ARCHITECTURE §3): the verify preview and the rest of
the per-verb composition moved to views.py at step 8, leaving this
module the rendering contract plus the templates its callers fill.
"""

from types import MappingProxyType

from dibs.records import Event, EventKind
from dibs.runtime import DibsError, Reply

EVENT_CAP = 15  # SSoT §13: unseen events shown before '... and N more'

# Refusal wording for the transitions, the sync applier and the
# read-side resolver. C5 keeps every user-facing string in this module
# and in views; callers below views only fill in an id or a key. Every
# steer is a runnable command (D14, I10) - see the §11 failure playbook
# for the story each one tells.
NOT_OWNER = '{0} is not yours - you were probably reaped.'
UNKNOWN_TASK = 'Unknown task {0} - did you mean {1}?'
NO_SUCH_TASK = 'Unknown task {0} - nothing on this board is close.'
BOARD_EXISTS = 'This plan already has a board - init runs once.'
RECLAIM = 'dibs claim --task {0}'
LIST_BOARD = 'dibs list'
SYNC_BOARD = 'dibs sync --plan {0}'

ERROR_LINE = '{0}\nRun: {1}'  # I10: the steer is always the last line
EVENTS_HEADER = '-- while you were away --'  # GUIDE's feed separator
OVERFLOW = '... and {0} more - run `dibs list`'  # SSoT §13 cap wording

# One line per event kind (D14, no banners). Slots: {0} recipient
# clause, {1} actor NAME - never the id (I7), {2} task id, {3} text.
# SYNC and ORPHAN are the two halves of the plan's own edits: a line
# arrived, a line left (SSoT §5, D4).
EVENT_LINES = MappingProxyType({
    EventKind.INIT: 'board opened by {1}: "{3}"',
    EventKind.SYNC: 'new {2} from {1}: "{3}"',
    EventKind.ORPHAN: 'orphaned {2} from {1}: "{3}"',
    EventKind.JOIN: '{1} joined',
    EventKind.CLAIM: 'claim {2} by {1}: "{3}"',
    EventKind.DONE: 'done {2} by {1}: "{3}"',
    EventKind.DROP: 'drop {2} by {1}: "{3}"',
    EventKind.NOTE: 'note by {1}{0}: "{3}"',
    EventKind.REAP: 'reap {2} from {1}: "{3}"',
})
DIRECTED = ' to {0}'  # D10: --for narrows a note, it does not hide it

# The next expected verb, exact syntax included (D14, I10). Named slots
# so a verb passes only what it knows; anything it omits degrades to a
# still-runnable placeholder rather than raising. No 'join' entry: its
# stdout is the bare id, so `export DIBS_AS=$(dibs join)` works (D8).
CLAIM_NEXT = 'Next: dibs claim'  # the worker loop's resting state (§10a)
UNLOCKED = 'unlocked'  # done's hint key when a parent became claimable
HINTS = MappingProxyType({
    'init': 'Hand each session: /dibs {key}',
    'verify': 'Next: dibs init {plan}',
    'sync': 'Next: dibs list',
    'claim': 'Next: dibs done {task} --note "what changed"',
    'done': CLAIM_NEXT,
    UNLOCKED: 'Next: dibs claim --task {task}',
    'drop': CLAIM_NEXT,
    'note': CLAIM_NEXT,
    'list': CLAIM_NEXT,
})
HINT_BLANKS = MappingProxyType({
    'task': '<ID>',
    'key': '<board key>',
    'plan': 'plan.md',
    'actor': '<your id>',
})


def render_reply(reply: Reply) -> str:
    """Join result lines, capped one-line events, then the hint (D14).

    Overflow past EVENT_CAP collapses to '... and N more - run
    `dibs list`' (SSoT §13). Empty pieces vanish, so a hint-less Reply
    renders as its bare lines - which is how `join` prints just an id
    (SSoT §6). No banners, ever.
    """
    shown = reply.events[:EVENT_CAP]
    feed = (
        EVENTS_HEADER, *(format_event(event) for event in shown),
    ) if shown else ()
    hidden = len(reply.events) - len(shown)
    return '\n'.join(
        reply.lines
        + feed
        # Empty string times 0: the overflow line exists only when
        # something overflowed (and likewise for the hint below).
        + (OVERFLOW.format(hidden),) * bool(hidden)
        + (reply.hint,) * bool(reply.hint),
    )


def render_error(err: DibsError) -> str:
    """Format '<message>' with 'Run: <steer>' as the last line (I10)."""
    return ERROR_LINE.format(err.message, err.steer)


def format_event(event: Event) -> str:
    """Compress one event to one line, worker-readable alone (D10, D14)."""
    return EVENT_LINES[event.kind].format(
        DIRECTED.format(event.to_agent.rsplit('-', 1)[0])
        if event.to_agent else '',
        event.agent.rsplit('-', 1)[0],
        event.task_id,
        ' '.join((event.text or '').split()),
    )


def next_hint(verb: str, context_bits: dict[str, str]) -> str:
    """Look up the next-expected-verb line, exact syntax included (D14)."""
    return HINTS[verb].format_map({**HINT_BLANKS, **context_bits})
