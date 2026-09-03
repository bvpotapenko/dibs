"""Unit: multi-line bodies (C5; §13 steps 7, 9). Hand-built records, no DB."""

import dataclasses

from dibs.planfile import compute_sync, parse_plan
from dibs.records import Status
from dibs.views import format_sync
from tests.boards import OTTER, init_rows


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


def test_sync_summary_counts_and_warnings(plan_text):
    """§8: counts + ids for new / orphaned / imported, one warning line per
    regressed id; same text as the SYNC event body (test_plansync pins
    that side)."""
    rows = list(init_rows(plan_text))
    rows[0] = dataclasses.replace(
        rows[0], status=Status.DOING, owner=OTTER.agent_id, claimed_at=1,
    )
    edited = plan_text.replace('  - [ ] Cover the empty file\n', '')
    edited = f'{edited}- [x] Write the changelog\n'
    plan = compute_sync(parse_plan(edited), tuple(rows))
    assert format_sync(plan) == (
        'synced 6 tasks: 1 new (B2), 1 orphaned (A2.2), '
        '1 imported as done (B2)',
        'warning: A1 stays doing (board wins); its [ ] in the plan was '
        're-annotated',
    )
    unchanged = compute_sync(parse_plan(plan_text), init_rows(plan_text))
    assert format_sync(unchanged) == ('synced 6 tasks: nothing changed',)
