"""Unit: rendering, caps, hints, steers (C5, D14, I10; §13 step 7).

Feed hand-built records/Reply values; no DB, no board fixture needed.
"""


def test_render_reply_lines_events_hint_order(plan_text):
    """D14: result lines, then events one per line, hint last."""
    raise NotImplementedError('needs render_reply (§13 step 7)')


def test_events_capped_with_overflow_hint():
    """SSoT §13: more than EVENT_CAP unseen events collapse into
    '... and N more' pointing at `dibs list`."""
    raise NotImplementedError('needs render_reply (§13 step 7)')


def test_render_error_ends_with_run_steer():
    """I10: render_error output ends with 'Run: <steer>' verbatim."""
    raise NotImplementedError('needs render_error (§13 step 7)')


def test_format_event_is_one_line():
    """D14: every EventKind formats to exactly one line, no banners."""
    raise NotImplementedError('needs format_event (§13 step 7)')


def test_next_hint_has_exact_syntax():
    """D14: hints carry runnable syntax (e.g. `dibs done A2 --note
    "..."`), not descriptions of it."""
    raise NotImplementedError('needs next_hint (§13 step 7)')


def test_preview_shows_tree_and_waits_for(plan_text):
    """D21/D22: format_preview renders sections, would-be IDs, the
    nesting tree, and what each parent waits for."""
    raise NotImplementedError('needs format_preview (§13 step 7)')


def test_preview_warns_bodiless_and_dupes(plan_text):
    """D21: bodiless tasks and duplicate titles get inline warnings -
    computed here, not in verbs (C5/C6). PLAN_TEXT's 'Cover the empty
    file' child is the bodiless case."""
    raise NotImplementedError('needs format_preview (§13 step 7)')
