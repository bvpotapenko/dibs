"""Unit: rendering, caps, hints, steers (C5, D14, I10; §13 step 7).

Feed hand-built records/Reply values; no DB, no board fixture needed.
"""


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
    command for OLD_SQLITE / NO_BOARD) and whose message names each slot."""
    raise NotImplementedError('needs output.steer (§13 step 6)')
