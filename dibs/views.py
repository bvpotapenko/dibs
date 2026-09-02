"""Per-verb views: records in, lines - or a steered refusal - out.

Pure functions, no DB, no clock, no I/O. Level L2: reads output's
templates and format_event, and planfile for the parse types and the §8
title normalization (ARCHITECTURE §4). Member budget 6 (ARCHITECTURE
§3). Together with output this module holds all user-facing text; a verb
fills no template of its own (C5, C6).
"""

from collections import Counter
from string import ascii_uppercase
from types import MappingProxyType

from dibs import planfile
from dibs.output import DIRECTED, LIST_BOARD, RECLAIM, format_event
from dibs.records import Event, Status, Task
from dibs.runtime import DibsError

OPEN = frozenset((Status.TODO, Status.DOING))  # what gates a parent (D22)
MINUTE = 60  # reap ages are reported in whole minutes (SSoT §6)
NAMED = ' {0}'  # ' brave-otter' - the display name, never the id (I7)
SUFFIX = '-'  # id is '<name>-NNNN'; everything before it displays (I7)
LIST_SEP = ', '  # how every enumeration in this module reads

# The verify view (D21): one header line naming the lettered sections,
# then one line per checkbox, indented by nesting depth (D22).
LETTERS = ascii_uppercase  # section lettering, A onwards (SSoT §8)
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

# The board view (init + list): the key first, because `list --plan
# <path>` is how a lost key comes back (D20).
BOARD_HEADER = 'board {0} - {1} tasks'
BOARD_ROW = '{0}  {1}{2}  {3}{4}'
PROGRESS = '  {0}/{1}'  # child progress on a gated parent (D22)
RECENT_HEADER = '-- recent --'

# The claim briefing: the only rich response dibs gives, because the
# task body IS the worker's whole context (D14, D16, D17).
IDENTITY = 'you are {0}'
CLAIMED = 'claimed {0}: {1}'
REAPED = 'previously claimed by {0}, reaped {1} min ago - verify before redoing'

# The three no-arg refusals and the per-id ones, each with a runnable
# steer (D6, D22, I10); the failure playbook (SSoT §11) tells the story
# each of them belongs to.
OVER_HAND = 'That bundle is {0} tasks and your hand holds {1}.'
HAND_FULL = 'Your hand is full: you hold {0} - finish or drop first.'
FINISH_FIRST = 'dibs done {0} --note "what changed"'
WAITING = (
    'Nothing available yet: {0} remaining, waiting on {1} - retry after '
    + 'finishing something else, or stop if your launcher respawns workers.'
)
CLAIM_AGAIN = 'dibs claim'
BOARD_EMPTY = 'No tasks remain; stop.'
HOLDER = '{0} ({1})'
# Slots of one refusal candidate: whether it applies, what it says,
# and the command to run next (planfile's PARSED/INDENT/BODY idiom).
WHEN = 0
SAYS = 1
STEER = 2
EXPLICIT = MappingProxyType({
    Status.DOING: '{0} is held by {1}.',
    Status.DONE: '{0} is already done.',
    Status.ORPHANED: '{0} left the plan.',
    Status.TODO: '{0} waits for {1}.',
})

# Stand-in for 'no named task is the problem', so the diagnosis table
# needs no None guards; its empty id is what switches its row off.
NO_TASK = Task(
    '', None, 0, '', '', '', '', Status.TODO, None, None, None, None,
)

# The sync report (manual sync only; the pipeline's own sync discards
# it). Labels double as the count words, so one table serves both lines.
SYNC_HEADER = 'sync: {0}'
SYNC_COUNT = '{0} {1}'
SYNC_ROW = '{0}: {1}'
NOTHING = 'nothing changed'
ARRIVED = 'new'
LEFT = 'orphaned'
IMPORTED = 'imported [x]'
RESEQUENCED = 'reordered'
REHOMED = 'reparented'
REWORDED = 'refreshed'
OVERRIDDEN = 'board wins, line re-annotated'

# One-line confirmations (D14, no banners).
OUTCOMES = MappingProxyType({
    'done': 'done {0}: {1}',
    'drop': 'dropped {0}: {1}',
    'note': 'noted{0}: "{1}"',
})
UNKNOWN_NAME = 'no agent named {0} on this board - sent to everyone.'


def format_preview(
    plan_items: tuple[planfile.PlanItem, ...],
) -> tuple[str, ...]:
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
        entry.line_no: LIST_SEP.join(
            ids[kid.line_no] for kid in plan_items
            if kid.parent_line == entry.line_no
            and kid.checkbox != planfile.DONE_STATE
        )
        for entry in plan_items
    }
    twins = Counter(
        planfile.title_hash(entry.title) for entry in plan_items
    )
    return (
        SECTIONS_ROW.format(LIST_SEP.join(
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
            DUPLICATE * (twins[planfile.title_hash(entry.title)] > 1),
        ) for entry in plan_items),
    )


def format_board(
    tasks: tuple[Task, ...],
    key: str,
    recent: tuple[Event, ...],
) -> tuple[str, ...]:
    """Render the board for init and list: key, rows, events (D20, D22).

    A parent carries its child progress (2/3), an orphaned row says so
    in its state column, and the events run oldest to newest so the
    tail reads like the feed every other verb ends with (D14).
    """
    kin = {
        task.task_id: tuple(
            kid for kid in tasks if kid.parent_id == task.task_id
        )
        for task in tasks
    }
    return (
        BOARD_HEADER.format(key, len(tasks)),
        *(BOARD_ROW.format(
            task.task_id,
            # SQLite hands the status back as the plain string it
            # stores; Status normalizes either form to the word (§5).
            Status(task.status).value,
            NAMED.format(task.owner.rsplit(SUFFIX, 1)[0])
            if task.owner else '',
            task.title,
            PROGRESS.format(
                sum(kid.status == Status.DONE for kid in kin[task.task_id]),
                len(kin[task.task_id]),
            ) * bool(kin[task.task_id]),
        ) for task in tasks),
        *(RECENT_HEADER,) * bool(recent),
        *(format_event(event) for event in reversed(recent)),
    )


def format_briefing(
    actor: str,
    now: int,
    claimed: tuple[Task, ...],
    prior: tuple[Event, ...],
) -> tuple[str, ...]:
    """Render the claim briefing: who you are, what you took, its body.

    The identity line is how a first-use claim announces the id it just
    minted (D8); a reap in prior warns that somebody already worked
    this task (SSoT §6 claim row).
    """
    return (
        IDENTITY.format(actor.rsplit(SUFFIX, 1)[0]),
        *(
            line
            for task in claimed
            for line in (
                CLAIMED.format(task.task_id, task.title),
                *(
                    TREE_STEP + body_line
                    for body_line in task.body.split('\n')
                    if task.body
                ),
            )
        ),
        *(
            REAPED.format(
                event.agent.rsplit(SUFFIX, 1)[0],
                (now - event.ts) // MINUTE,
            )
            for event in prior
        ),
    )


def claim_refusal(
    tasks: tuple[Task, ...],
    actor: str,
    wanted: tuple[str, ...],
    max_hand: int,
) -> DibsError:
    """Diagnose a zero-row claim from the snapshot alone (D6, D22, I10).

    The claim statement already decided; this only tells the worker
    which of the refusals it was - bundle over the hand, hand full, the
    named task's own state, nothing available yet, or board empty - and
    hands back the error the verb raises. Every steer runs as written.
    """
    gates = {
        row.task_id: LIST_SEP.join(
            kid.task_id for kid in tasks
            if kid.parent_id == row.task_id and kid.status in OPEN
        )
        for row in tasks
    }
    held = tuple(
        row.task_id for row in tasks
        if row.status == Status.DOING and row.owner == actor
    )
    stuck = next(
        (
            row for row in tasks
            if row.task_id in wanted
            and (row.status != Status.TODO or gates[row.task_id])
        ),
        NO_TASK,
    )
    waiting = LIST_SEP.join(
        HOLDER.format(
            row.task_id, (row.owner or '').rsplit(SUFFIX, 1)[0],
        )
        for row in tasks if row.status == Status.DOING
    )
    return next(
        DibsError(refusal[SAYS], refusal[STEER])
        for refusal in (
            (
                len(wanted) > max_hand,
                OVER_HAND.format(len(wanted), max_hand),
                RECLAIM.format(' '.join(wanted[:max_hand])),
            ),
            (
                bool(held),
                HAND_FULL.format(LIST_SEP.join(held)),
                FINISH_FIRST.format(''.join(held[:1])),
            ),
            (
                bool(stuck.task_id),
                EXPLICIT[stuck.status].format(
                    stuck.task_id,
                    gates.get(stuck.task_id)
                    or (stuck.owner or '').rsplit(SUFFIX, 1)[0],
                ),
                RECLAIM.format(
                    gates.get(stuck.task_id, '').split(LIST_SEP)[0]
                    or stuck.task_id,
                ),
            ),
            (
                bool(waiting),
                WAITING.format(
                    sum(row.status == Status.TODO for row in tasks),
                    waiting,
                ),
                CLAIM_AGAIN,
            ),
            (True, BOARD_EMPTY, LIST_BOARD),
        )
        if refusal[WHEN]
    )


def format_sync(sync_plan: planfile.SyncPlan) -> tuple[str, ...]:
    """Report what a manual sync applied, counts first (SSoT §6, §8).

    Regressed rows are the one warning: the file said [ ] where the
    board says otherwise, so the board won and the line was
    re-annotated. The pipeline's automatic sync discards all of this.
    """
    found = {
        ARRIVED: tuple(entry.title for entry in sync_plan.new),
        LEFT: sync_plan.vanished,
        IMPORTED: sync_plan.checked,
        RESEQUENCED: tuple(row[0] for row in sync_plan.reordered),
        REHOMED: tuple(row[0] for row in sync_plan.reparented),
        REWORDED: tuple(row[0] for row in sync_plan.refreshed),
        OVERRIDDEN: sync_plan.regressed,
    }
    return (
        SYNC_HEADER.format(LIST_SEP.join(
            SYNC_COUNT.format(len(named), label)
            for label, named in found.items() if named
        ) or NOTHING),
        *(
            SYNC_ROW.format(label, LIST_SEP.join(named))
            for label, named in found.items() if named
        ),
    )


def format_outcome(
    verb: str,
    task: Task | None = None,
    event: Event | None = None,
    to_name: str | None = None,
) -> tuple[str, ...]:
    """Confirm done, drop or note in one line (D14, SSoT §6).

    A note asked for a name this board does not know still goes out, as
    a broadcast, and says so - the event was logged either way (D10).
    """
    landed = event.to_agent if event else None
    return (
        OUTCOMES[verb].format(
            task.task_id if task else DIRECTED.format(
                (landed or '').rsplit(SUFFIX, 1)[0],
            ) * bool(landed),
            task.title if task else ' '.join((event.text or '').split()),
        ),
        *(UNKNOWN_NAME.format(to_name),) * bool(to_name and not landed),
    )
