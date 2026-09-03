"""Unit: rendering, caps, hints, steers (C5, D14, I10; §13 steps 6, 9).

Feed hand-built records/Reply values; no DB, no board fixture needed.
"""

from types import MappingProxyType

from dibs.output import Refusal, steer
from dibs.runtime import DibsError

# One plausible names tuple per Refusal, in the slot order the catalog
# documents (ARCHITECTURE §5 steer).
SAMPLE_NAMES = MappingProxyType({
    Refusal.UNKNOWN_TASK: ('B7', 'A7', 'claim'),
    Refusal.NOT_OWNER: ('A2', 'brave-otter'),
    Refusal.TAKEN: ('A1', 'brave-otter'),
    Refusal.GATED: ('A2', 'A2.1, A2.2', 'A2.1'),
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


def test_render_reply_lines_events_hint_order(plan_text):
    """D14: result lines, then events one per line, hint last."""
    raise NotImplementedError('needs render_reply (§13 step 9)')


def test_events_capped_with_overflow_hint():
    """SSoT §13: more than EVENT_CAP unseen events collapse into
    '... and N more' pointing at `dibs list`."""
    raise NotImplementedError('needs render_reply (§13 step 9)')


def test_render_error_ends_with_run_steer():
    """I10: render_error output ends with 'Run: <steer>' verbatim."""
    raise NotImplementedError('needs render_error (§13 step 9)')


def test_format_event_is_one_line():
    """D14: every EventKind formats to exactly one line, no banners."""
    raise NotImplementedError('needs format_event (§13 step 9)')


def test_next_hint_has_exact_syntax():
    """D14: hints carry runnable syntax (e.g. `dibs done A2 --note
    "..."`), not descriptions of it."""
    raise NotImplementedError('needs next_hint (§13 step 9)')


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
