"""Unit: multi-line bodies (C5; §13 step 9). Hand-built records, no DB."""


def test_board_shows_tree_progress_and_key(plan_text):
    """D21/D22/D20: format_board renders the key header when given,
    sections, ids, state, owner NAME (I7), and 2/3 progress on gated
    parents."""
    raise NotImplementedError('needs views.format_board (§13 step 9)')


def test_board_warns_bodiless_and_dupes(plan_text):
    """D21: bodiless tasks and duplicate titles get inline warnings -
    computed here, not in verbs (C5/C6). PLAN_TEXT's 'Cover the empty
    file' child is the bodiless case."""
    raise NotImplementedError('needs views.format_board (§13 step 9)')


def test_verify_rows_render_like_a_live_board(plan_text):
    """D24: format_board(compute_sync(items, ()).rows, '') equals
    format_board(snapshot rows, key) minus the key header, for a board
    freshly inited from the same text."""
    raise NotImplementedError('needs views.format_board (§13 step 9)')


def test_briefing_identity_title_body_priors():
    """D8/D14/SSoT §6: 'you are <name>', 'claimed A2: <title>', body
    indented, and one 'previously claimed by ... reaped ...' line per
    prior reap event."""
    raise NotImplementedError('needs views.format_briefing (§13 step 9)')


def test_sync_summary_counts_and_warnings():
    """§8: counts + ids for new / orphaned / imported, one warning line per
    regressed id; same text as the SYNC event body."""
    raise NotImplementedError('needs views.format_sync (§13 step 9)')
