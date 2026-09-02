"""Every user-facing string and terseness cap lives here (C5, D14).

Output is prompt surface: terse, steering, self-sufficient (I10); in an
8k window every dibs token competes with code. Level L1 (imports L0;
the guarded planfile import is a type-only sibling edge, ARCHITECTURE
§4). Member budget 5 (ARCHITECTURE §3).
"""

from string import ascii_uppercase
from types import MappingProxyType
from typing import TYPE_CHECKING

from dibs.records import Event, EventKind
from dibs.runtime import DibsError, Reply

if TYPE_CHECKING:
    from dibs.planfile import PlanItem

EVENT_CAP = 15  # SSoT §13: unseen events shown before '... and N more'

# Refusal wording for the transitions and the read-side resolver. C5
# keeps every user-facing string in this module; callers only fill in
# the task id and pair message with steer. Every steer is a runnable
# command (D14, I10) - see the §11 failure playbook for the story each
# one tells.
NOT_OWNER = '{0} is not yours - you were probably reaped.'
NOT_IMPORTABLE = '{0} is not a todo task, so sync cannot import it.'
UNKNOWN_TASK = 'Unknown task {0} - did you mean {1}?'
NO_SUCH_TASK = 'Unknown task {0} - nothing on this board is close.'
RECLAIM = 'dibs claim --task {0}'
LIST_BOARD = 'dibs list'

ERROR_LINE = '{0}\nRun: {1}'  # I10: the steer is always the last line
EVENTS_HEADER = '-- while you were away --'  # GUIDE's feed separator
OVERFLOW = '... and {0} more - run `dibs list`'  # SSoT §13 cap wording

# One line per event kind (D14, no banners). Slots: {0} recipient
# clause, {1} actor NAME - never the id (I7), {2} task id, {3} text.
EVENT_LINES = MappingProxyType({
    EventKind.INIT: 'board opened by {1}: "{3}"',
    EventKind.SYNC: 'sync {2} by {1}: "{3}"',
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
# still-runnable placeholder rather than raising.
CLAIM_NEXT = 'Next: dibs claim'  # the worker loop's resting state (§10a)
HINTS = MappingProxyType({
    'init': 'Hand each session: /dibs {key}',
    'verify': 'Next: dibs init {plan}',
    'sync': 'Next: dibs list',
    'join': 'Next: export DIBS_AS={actor} && dibs claim',
    'claim': 'Next: dibs done {task} --note "what changed"',
    'done': CLAIM_NEXT,
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

# The verify view (D21): one header line naming the lettered sections,
# then one line per checkbox, indented by nesting depth (D22).
LETTERS = ascii_uppercase  # section lettering, A onwards (SSoT §8)
HAND_DONE = 'x'  # SSoT §8 done token; a done child gates nothing (D22)
DOT = '.'
DOTTED = '{0}.'  # a child id is built on its parent's: 'A2' -> 'A2.1'
NUMBERED = '{0}{1}'  # section letter or dotted parent, plus the ordinal
TREE_STEP = '  '  # one nesting level of preview indent
SECTIONS_ROW = 'sections: {0}'
SECTION_ITEM = '{0} {1}'
PREVIEW_ROW = '{0}{1}  {2}{3}{4}{5}{6}'
HAND_STATE = '[{0}] '  # the token exactly as the author wrote it
NO_BODY = '  (no body)'  # D17 briefing warning, inline (D21)
WAITS_FOR = '  waits for {0}'  # D22 gating, derived and never written
DUPLICATE = '  (duplicate title)'  # §8 matches duplicates by order


def render_reply(reply: Reply) -> str:
    """Join result lines, capped one-line events, then the hint (D14).

    Overflow past EVENT_CAP collapses to '... and N more - run
    `dibs list`' (SSoT §13). No banners, ever.
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
        # something overflowed (and likewise for the tags below).
        + (OVERFLOW.format(hidden),) * bool(hidden)
        + (reply.hint,),
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


def format_preview(plan_items: 'tuple[PlanItem, ...]') -> tuple[str, ...]:
    """Render the verify view: tree with waits-for, would-be IDs (D21).

    Sections, titles, body presence, hand-written [x], plus inline
    warnings (bodiless tasks, duplicate titles) are computed here, not
    in verbs (C5, C6, D22).
    """
    sections = tuple(dict.fromkeys(entry.section for entry in plan_items))
    ids = {}
    for row in plan_items:
        # One rule for both levels: rank among earlier lines sharing
        # this line's section and parent (SSoT §8 creation order).
        ids[row.line_no] = NUMBERED.format(
            DOTTED.format(ids[row.parent_line])
            if row.parent_line in ids
            else LETTERS[sections.index(row.section)],
            1 + sum(
                (older.section, older.parent_line)
                == (row.section, row.parent_line)
                and older.line_no < row.line_no
                for older in plan_items
            ),
        )
    waits = {
        entry.line_no: ', '.join(
            ids[kid.line_no] for kid in plan_items
            if kid.parent_line == entry.line_no
            and kid.checkbox != HAND_DONE
        )
        for entry in plan_items
    }
    # Normalized exactly as planfile.title_hash normalizes, but
    # spelled out: output may not import a sibling level (§4).
    twins = {
        entry.line_no: sum(
            ' '.join(other.title.lower().split())
            == ' '.join(entry.title.lower().split())
            for other in plan_items
        )
        for entry in plan_items
    }
    return (
        SECTIONS_ROW.format(', '.join(
            # A plan with no headings is one nameless section (§8), so
            # the letter stands alone rather than trailing a blank.
            SECTION_ITEM.format(LETTERS[rank], sections[rank]).rstrip()
            for rank in range(len(sections))
        )),
        *(PREVIEW_ROW.format(
            TREE_STEP * ids[entry.line_no].count(DOT),
            ids[entry.line_no],
            HAND_STATE.format(entry.checkbox) * bool(entry.checkbox),
            entry.title,
            NO_BODY * (not entry.body),
            WAITS_FOR.format(waits[entry.line_no]) * bool(
                waits[entry.line_no],
            ),
            DUPLICATE * (twins[entry.line_no] > 1),
        ) for entry in plan_items),
    )
