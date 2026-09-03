"""Multi-line reply bodies: records in, tuple[str, ...] out (C5).

Level L1 (imports L0). Member budget 3 (ARCHITECTURE §3). The envelope
(events, hint, errors, caps) is output.py's job; bodies never import it.
"""

from collections import Counter
from datetime import datetime, timezone
from itertools import chain, compress
from types import MappingProxyType

from dibs.planfile import SyncPlan
from dibs.records import Event, Status, Task, agent_name

SEP = ', '  # list punctuation inside bodies (C5)
INDENT = '  '  # one nesting level, and a briefing's body (GUIDE)
BOARD = 'board {0} ({1} tasks)'  # D20 header, the lost-key recovery line
HANDOFF = 'hand to each session: /dibs {0}'  # GUIDE: paste-ready (D19)
SECTION = '## {0}'
ROW = '{0}{1} {2}: {3}{4}'  # indent, id, state, title, tags
PROGRESS = ' ({0}/{1})'  # done/all children on a parent (D22)
NO_BODY = ' !no body'  # D21 warning: a worker cannot act on this alone
DUPLICATE = ' !duplicate title'  # D21 warning: sync pairs these by order
STATES = MappingProxyType({  # slot 0: the owner's name (I7)
    Status.TODO: 'todo',
    Status.DOING: 'doing by {0}',
    Status.DONE: 'done by {0}',
    Status.ORPHANED: 'orphaned',
})
YOU_ARE = 'you are {0}'  # D8: the id reminder, by name
CLAIMED = 'claimed {0}: {1}'
PRIOR = '{0} was previously claimed by {1}, reaped {2} - verify before redoing'
STAMP = '%Y-%m-%d %H:%M UTC'
SYNCED = 'synced {0} tasks: {1}'
FACT = '{0} {1} ({2})'  # count, label, ids
UNCHANGED = 'nothing changed'
REGRESSED = (
    'warning: {0} stays {1} (board wins); its [ ] in the plan was '
    're-annotated'
)


def format_board(tasks: tuple[Task, ...], key: str) -> tuple[str, ...]:
    """Render list / verify / init roster: one view for all three (D24).

    Key header when key is non-empty (D20), sections, ids, state, owner
    name, child progress like 2/3 on gated parents (D22), and inline
    warnings for bodiless tasks and duplicate titles (D21). Orphaned rows
    stay listed, flagged by their state, and count for nothing (§8).
    """
    counts = Counter(chain(  # ('kids' | 'done', parent) and ('title', hash)
        (
            ('kids', task.parent_id)
            for task in tasks
            if task.status != Status.ORPHANED
        ),
        (
            ('done', task.parent_id)
            for task in tasks
            if task.status == Status.DONE
        ),
        (
            ('title', task.text_hash)
            for task in tasks
            if task.status != Status.ORPHANED
        ),
    ))
    heads = {  # section -> its first task (the row that carries the heading)
        task.section: task.task_id
        for task in reversed(tasks)
        if task.section
    }
    depths: dict[str | None, int] = {}
    rows = [
        BOARD.format(
            key, sum(task.status != Status.ORPHANED for task in tasks),
        ),
        HANDOFF.format(key),
    ] if key else []
    for task in tasks:
        depths[task.task_id] = depths.get(task.parent_id, -1) + 1
        if heads.get(task.section) == task.task_id:
            rows.append(SECTION.format(task.section))
        rows.append(ROW.format(
            INDENT * depths[task.task_id],
            task.task_id,
            STATES[task.status].format(agent_name(task.owner)),
            task.title,
            ''.join(compress(
                (
                    PROGRESS.format(
                        counts['done', task.task_id],
                        counts['kids', task.task_id],
                    ),
                    NO_BODY,
                    DUPLICATE,
                ),
                (
                    counts['kids', task.task_id],
                    not task.body,
                    counts['title', task.text_hash] > 1,
                ),
            )),
        ))
    return tuple(rows)


def format_briefing(
    tasks: tuple[Task, ...],
    actor_name: str,
    priors: tuple[Event, ...],
) -> tuple[str, ...]:
    """Render claim's briefing: identity, title, indented body, reap history.

    'you are <name>' (D8), then per task 'claimed A2: <title>' with the body
    indented (D17), then one 'previously claimed by ... reaped ...' line
    per prior reap event (SSoT §6), its time in UTC.
    """
    briefs = chain.from_iterable(
        (
            CLAIMED.format(task.task_id, task.title),
            *(f'{INDENT}{line}' for line in task.body.splitlines()),
        )
        for task in tasks
    )
    return (
        YOU_ARE.format(actor_name),
        *briefs,
        *(
            PRIOR.format(
                event.task_id,
                event.text,
                datetime.fromtimestamp(event.ts, tz=timezone.utc).strftime(
                    STAMP,
                ),
            )
            for event in priors
        ),
    )


def format_sync(plan: SyncPlan) -> tuple[str, ...]:
    """Render sync counts + ids, one warning per regressed id (SSoT §8, §6).

    The same text is the SYNC event's body (plansync.apply_sync).
    """
    facts = {
        'new': plan.new,
        'orphaned': plan.vanished,
        'imported as done': plan.checked,
    }
    listed = [
        FACT.format(len(ids), label, SEP.join(ids))
        for label, ids in facts.items()
        if ids
    ]
    statuses = {row.task_id: row.status.value for row in plan.rows}
    return (
        SYNCED.format(len(plan.rows), SEP.join(listed) or UNCHANGED),
        *(
            REGRESSED.format(task_id, statuses[task_id])
            for task_id in plan.regressed
        ),
    )
