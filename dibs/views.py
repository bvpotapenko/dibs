"""Multi-line reply bodies: records in, tuple[str, ...] out (C5).

Level L1 (imports L0). Member budget 3 (ARCHITECTURE §3). The envelope
(events, hint, errors, caps) is output.py's job; bodies never import it.
"""

from dibs.planfile import SyncPlan
from dibs.records import Event, Task

SEP = ', '  # list punctuation inside bodies (C5)
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
    warnings for bodiless tasks and duplicate titles (D21).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 9: views.format_board')


def format_briefing(
    tasks: tuple[Task, ...],
    actor_name: str,
    priors: tuple[Event, ...],
) -> tuple[str, ...]:
    """Render claim's briefing: identity, title, indented body, reap history."""
    raise NotImplementedError(
        'ARCHITECTURE §13 step 9: views.format_briefing',
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
