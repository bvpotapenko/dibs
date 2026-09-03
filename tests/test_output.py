"""Unit: rendering, caps, hints, steers (C5, D14, I10; §13 steps 6, 9).

Feed hand-built records/Reply values; no DB, no board fixture needed.
"""

from types import MappingProxyType

from dibs.output import (
    EVENT_CAP,
    HINTS,
    Refusal,
    format_event,
    next_hint,
    render_error,
    render_reply,
    steer,
)
from dibs.records import Event, EventKind
from dibs.runtime import DibsError, Reply
from tests.boards import ELEPHANT, NOW, OTTER

MOMENTS = (
    'claim', 'done', 'unlocked', 'drop', 'note', 'sync', 'init', 'list',
    'empty',
)
OVERFLOW = 3

# One plausible names tuple per Refusal, in the slot order the catalog
# documents (ARCHITECTURE §5 steer).
SAMPLE_NAMES = MappingProxyType({
    Refusal.UNKNOWN_TASK: ('B7', 'A7', 'claim'),
    Refusal.NOT_OWNER: ('A2', 'brave-otter'),
    Refusal.TAKEN: ('A1', 'brave-otter'),
    Refusal.GATED: ('A2', 'A2.1, A2.2', 'A2.1'),
    Refusal.OVERSIZED: ('3', '1', 'A1'),
    Refusal.HAND_FULL: ('A2', 'A2', '1'),
    Refusal.WAITING: ('4', 'A3', 'brave-otter'),
    Refusal.EMPTY: (),
    Refusal.BOARD_EXISTS: ('dibs-7f3a-9c2e',),
    Refusal.NO_BOARD: ('claim',),
    Refusal.MANY_BOARDS: ('claim', 'errands.md, refactor.md'),
    Refusal.UNKNOWN_ACTOR: ('brave-otter-1111',),
    Refusal.OLD_SQLITE: ('3.31.1',),
})
# Steers that are shell rather than dibs commands: the binding to fix
# (D8/D18) and the interpreter to check (ARCHITECTURE §1 floor).
SHELL_STEERS = ('export ', 'python3 ')


def make_event(number, kind=EventKind.NOTE, **fields):
    """A journal row with sensible defaults; fields override columns."""
    columns = {
        'event_id': number, 'ts': NOW + number, 'agent': OTTER.agent_id,
        'kind': kind, 'task_id': None, 'to_agent': None, 'text': 'hi',
    }
    return Event(**{**columns, **fields})


def test_render_reply_lines_events_hint_order():
    """D14: result lines, then events one per line, hint last; empty parts
    vanish, so join prints the bare id."""
    reply = Reply(
        lines=('claimed A2: Fix it', '  body'),
        events=(make_event(1, EventKind.DONE, task_id='A1', text='fixed'),),
        hint='dibs done A2 --note "..."',
    )
    assert render_reply(reply).split('\n') == [
        'claimed A2: Fix it',
        '  body',
        '-- while you were away --',
        'done A1 by brave-otter: "fixed"',
        'next: dibs done A2 --note "..."',
    ]
    assert render_reply(Reply((OTTER.agent_id,), (), '')) == OTTER.agent_id


def test_events_capped_with_overflow_hint():
    """SSoT §13: more than EVENT_CAP unseen events collapse into
    '... and N more' pointing at `dibs list`."""
    events = tuple(make_event(number) for number in range(EVENT_CAP + OVERFLOW))
    lines = render_reply(Reply((), events, '')).split('\n')
    assert lines[0] == '-- while you were away --'
    assert len(lines) == EVENT_CAP + 2  # separator, the cap, the overflow
    assert lines[-1] == f'... and {OVERFLOW} more - run: dibs list'
    exact = render_reply(Reply((), events[:EVENT_CAP], ''))
    assert exact.count('\n') == EVENT_CAP  # separator + cap, no overflow


def test_render_error_ends_with_run_steer():
    """I10: render_error output ends with 'Run: <steer>' verbatim."""
    err = DibsError('Unknown task B7 - did you mean A7?', 'dibs claim A7')
    assert render_error(err) == (
        'Unknown task B7 - did you mean A7?\nRun: dibs claim A7'
    )
    assert render_error(steer(Refusal.EMPTY)).endswith('\nRun: dibs list')


def test_format_event_is_one_line():
    """D14: every EventKind formats to exactly one line, no banners; agents
    show by name and a multi-line text collapses (I7)."""
    samples = (
        make_event(1, EventKind.INIT, agent='human', text='dibs-7f3a-9c2e'),
        make_event(2, EventKind.SYNC, agent='human', text='synced 6\nwarn'),
        make_event(3, EventKind.JOIN, text=OTTER.name),
        make_event(4, EventKind.CLAIM, task_id='A1', text='Fix it'),
        make_event(5, EventKind.DONE, task_id='A1', text='fixed\nline two'),
        make_event(6, EventKind.DROP, task_id='A1', text='blocked'),
        make_event(7, to_agent=ELEPHANT.agent_id, text='psst'),
        make_event(
            8, EventKind.REAP, agent='system', task_id='A1', text=OTTER.name,
        ),
    )
    lines = [format_event(event) for event in samples]
    assert {event.kind for event in samples} == set(EventKind)
    assert all(line and '\n' not in line for line in lines)
    assert lines[4:7] == [
        'done A1 by brave-otter: "fixed line two"',
        'drop A1 by brave-otter: "blocked"',
        'note to happy-elephant by brave-otter: "psst"',
    ]
    assert (lines[0], lines[7]) == (
        'init: board dibs-7f3a-9c2e', 'reap A1: brave-otter timed out',
    )
    assert '1111' not in '\n'.join(lines) and '2222' not in '\n'.join(lines)


def test_next_hint_has_exact_syntax():
    """D14: hints carry runnable syntax (e.g. `dibs done A2 --note
    "..."`), not descriptions of it; one per moment, every slot filled."""
    assert next_hint('claim', ('A2',)) == 'dibs done A2 --note "..."'
    assert next_hint('unlocked', ('A2',)) == 'dibs claim --task A2'
    assert next_hint('init', ('dibs-7f3a-9c2e',)) == (
        'dibs list --plan dibs-7f3a-9c2e'
    )
    assert tuple(HINTS) == MOMENTS
    hints = [next_hint(moment, ('X',)) for moment in MOMENTS]
    assert all(hint.startswith('dibs ') and '{' not in hint for hint in hints)


def test_steer_every_refusal_is_runnable():
    """C7/I10: output.steer(kind, names) for EVERY Refusal member yields a
    DibsError whose steer is a runnable command (`dibs ...`, or a shell
    command for UNKNOWN_ACTOR / OLD_SQLITE), every slot filled, and whose
    rendered text (message + steer) names each slot."""
    for kind in Refusal:
        err = steer(kind, SAMPLE_NAMES[kind])
        assert isinstance(err, DibsError), kind
        assert str(err) == err.message, kind
        assert err.steer.startswith(('dibs ', *SHELL_STEERS)), kind
        rendered = f'{err.message} {err.steer}'
        assert '{' not in rendered, kind
        assert all(name in rendered for name in SAMPLE_NAMES[kind]), kind


def test_steer_unknown_task_is_the_callers_verb():
    """D14: 'Unknown task B7 - did you mean A7?' steers to the caller's own
    verb with the id corrected."""
    err = steer(Refusal.UNKNOWN_TASK, ('B7', 'A7', 'claim'))
    assert err.message == 'Unknown task B7 - did you mean A7?'
    assert err.steer == 'dibs claim A7'
