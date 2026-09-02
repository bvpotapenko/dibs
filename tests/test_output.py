"""Unit: rendering, caps, hints, steers (C5, D14, I10; §13 step 7).

Feed hand-built records/Reply values; no DB, no board fixture needed.
The verify-preview cases moved to test_views with format_preview
(ARCHITECTURE §13 step 8a).
"""

import pytest

from dibs import output
from dibs.records import Event, EventKind
from dibs.runtime import DibsError, Reply

NOW = 1_700_000_000  # fixed clock; nothing here reads a real one
OTTER = 'brave-otter-1111'
ELEPHANT = 'happy-elephant-2222'
OVERFLOWING = output.EVENT_CAP + 5  # enough events to trip the cap
HINT = 'Next: dibs done A2 --note "what changed"'


def event(kind, task_id=None, text='', to_agent=None, agent=OTTER):
    """One journal row, shaped as the DB hands it back."""
    return Event(1, NOW, agent, kind, task_id, to_agent, text)


def test_render_reply_lines_events_hint_order():
    """D14: result lines, then events one per line, hint last."""
    reply = Reply(
        lines=('you are happy-elephant', 'claimed A2: Ship it'),
        events=(event(EventKind.DONE, 'A1', 'anchored the regex'),),
        hint=HINT,
    )

    rendered = output.render_reply(reply).split('\n')

    assert rendered == [
        'you are happy-elephant',
        'claimed A2: Ship it',
        output.EVENTS_HEADER,
        'done A1 by brave-otter: "anchored the regex"',
        HINT,
    ]
    # No feed at all when nothing is unseen: no empty banner (D14).
    assert output.render_reply(
        Reply(lines=('ok',), events=(), hint=HINT),
    ).split('\n') == ['ok', HINT]


def test_render_reply_drops_an_empty_hint():
    """SSoT §6 join: a hint-less Reply renders as its bare lines, so
    `export DIBS_AS=$(dibs join)` captures exactly the id - no trailing
    blank line, no verb-specific branch anywhere (8a)."""
    bare = Reply(lines=(OTTER,), events=(), hint='')

    assert output.render_reply(bare) == OTTER
    # And no hint template invites one: join fills no slot (D8).
    assert 'join' not in output.HINTS
    with pytest.raises(KeyError):
        output.next_hint('join', {'actor': OTTER})


def test_events_capped_with_overflow_hint():
    """SSoT §13: more than EVENT_CAP unseen events collapse into
    '... and N more' pointing at `dibs list`."""
    reply = Reply(
        lines=(),
        events=tuple(
            event(EventKind.NOTE, text='chatter')
            for _each in range(OVERFLOWING)
        ),
        hint=HINT,
    )

    rendered = output.render_reply(reply).split('\n')

    # header + EVENT_CAP events + overflow + hint
    assert len(rendered) == output.EVENT_CAP + 3
    assert rendered.count('note by brave-otter: "chatter"') == (
        output.EVENT_CAP
    )
    assert rendered[-2] == output.OVERFLOW.format(
        OVERFLOWING - output.EVENT_CAP,
    )
    assert 'dibs list' in rendered[-2]


def test_render_error_ends_with_run_steer():
    """I10: render_error output ends with 'Run: <steer>' verbatim."""
    rendered = output.render_error(
        DibsError(output.NOT_OWNER.format('A2'), output.RECLAIM.format('A2')),
    )

    assert rendered.startswith('A2 is not yours')
    assert rendered.split('\n')[-1] == 'Run: dibs claim --task A2'


def test_format_event_is_one_line():
    """D14: every EventKind formats to exactly one line, no banners."""
    every = tuple(
        event(kind, 'A1', 'a note\nwith a newline in it')
        for kind in EventKind
    )

    assert all('\n' not in output.format_event(one) for one in every)
    # I7: shared surfaces show names, never session ids.
    assert all(OTTER not in output.format_event(one) for one in every)
    assert all('brave-otter' in output.format_event(one) for one in every)
    assert output.format_event(
        event(EventKind.NOTE, text='yours', to_agent=ELEPHANT),
    ) == 'note by brave-otter to happy-elephant: "yours"'
    assert output.format_event(
        event(EventKind.REAP, 'A1', 'Fix the tokenizer'),
    ) == 'reap A1 from brave-otter: "Fix the tokenizer"'


def test_format_event_covers_the_plan_edits():
    """SSoT §5 (Rev 9): the two halves of an author's edit each read as
    one line - a task arrived, a task's line left (8a)."""
    assert output.format_event(
        event(EventKind.SYNC, 'A4', 'Ship the docs', agent='human'),
    ) == 'new A4 from human: "Ship the docs"'
    assert output.format_event(
        event(EventKind.ORPHAN, 'A4', 'Ship the docs', agent='human'),
    ) == 'orphaned A4 from human: "Ship the docs"'


def test_next_hint_has_exact_syntax():
    """D14: hints carry runnable syntax (e.g. `dibs done A2 --note
    "..."`), not descriptions of it."""
    assert output.next_hint('claim', {'task': 'A2'}) == HINT
    assert output.next_hint('done', {}) == 'Next: dibs claim'
    assert output.next_hint('init', {'key': 'dibs-7f3a-9c2e'}) == (
        'Hand each session: /dibs dibs-7f3a-9c2e'
    )
    # A done that unlocked a parent hands over the ready claim (D7, D22).
    assert output.next_hint(output.UNLOCKED, {'task': 'A2'}) == (
        'Next: dibs claim --task A2'
    )
    # A verb that omits a slot still emits a runnable shape, never a
    # KeyError (I10).
    assert 'dibs done <ID>' in output.next_hint('claim', {})


def test_refusal_templates_steer_with_commands():
    """C5/I10: every steer this module offers is a literal command, and
    the two board-level ones landed with plansync (8a)."""
    steers = (
        output.RECLAIM.format('A2'),
        output.LIST_BOARD,
        output.SYNC_BOARD.format('dibs-7f3a-9c2e'),
    )

    assert all(steer.startswith('dibs ') for steer in steers)
    assert output.SYNC_BOARD.format('dibs-7f3a-9c2e') == (
        'dibs sync --plan dibs-7f3a-9c2e'
    )
    assert 'init' in output.BOARD_EXISTS
