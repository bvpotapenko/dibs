"""Unit: multi-line bodies (C5; §13 steps 7, 9). Hand-built records, no DB."""

import dataclasses

from dibs import queries
from dibs.planfile import compute_sync, parse_plan
from dibs.records import Event, EventKind, Status
from dibs.views import format_board, format_briefing, format_sync
from tests.boards import ELEPHANT, NOW, OTTER, init_rows

KEY = 'dibs-7f3a-9c2e'
BRIEF_PLAN = '## Parser\n- [ ] Fix it\n  Repro: x.\n  Done: y.\n- [ ] Two\n'


def test_board_shows_tree_progress_and_key(plan_text):
    """D21/D22/D20: format_board renders the key header when given,
    sections, ids, state, owner NAME (I7), and 2/3 progress on gated
    parents; orphaned rows stay listed, flagged."""
    rows = list(init_rows(plan_text))
    rows[2] = dataclasses.replace(
        rows[2], status=Status.DOING, owner=OTTER.agent_id, claimed_at=1,
    )
    rows[3] = dataclasses.replace(
        rows[3], status=Status.DONE, owner=ELEPHANT.agent_id, done_note='ok',
    )
    rows[5] = dataclasses.replace(rows[5], status=Status.ORPHANED)
    lines = format_board(tuple(rows), KEY)
    assert lines[:2] == (
        f'board {KEY} (5 tasks)', f'hand to each session: /dibs {KEY}',
    )
    assert lines[2:] == (
        '## Parser',
        'A1 todo: Fix off-by-one in the tokenizer',
        'A2 todo: Ship the tokenizer regression suite (1/2)',
        '  A2.1 doing by brave-otter: Cover multi-byte input',
        '  A2.2 done by happy-elephant: Cover the empty file !no body',
        'A3 done by human: Rename Lexer to Tokenizer !no body',
        '## Docs',
        'B1 orphaned: Update the README quickstart',
    )
    assert '1111' not in '\n'.join(lines) and '2222' not in '\n'.join(lines)
    assert format_board(tuple(rows), '')[0] == '## Parser'  # no key: no header


def test_board_warns_bodiless_and_dupes(plan_text):
    """D21: bodiless tasks and duplicate titles get inline warnings -
    computed here, not in verbs (C5/C6). PLAN_TEXT's 'Cover the empty
    file' child is the bodiless case."""
    grown = f'{plan_text}- [ ] Cover the empty file\n'  # a Docs duplicate
    flagged = [
        line for line in format_board(init_rows(grown), '') if '!' in line
    ]
    assert flagged == [
        '  A2.2 todo: Cover the empty file !no body !duplicate title',
        'A3 done by human: Rename Lexer to Tokenizer !no body',
        'B2 todo: Cover the empty file !no body !duplicate title',
    ]


def test_verify_rows_render_like_a_live_board(plan_text, board):
    """D24: format_board(compute_sync(items, ()).rows, '') equals
    format_board(snapshot rows, key) minus the key header, for a board
    freshly inited from the same text."""
    preview = format_board(compute_sync(parse_plan(plan_text), ()).rows, '')
    live = format_board(queries.board_snapshot(board.conn).tasks, KEY)
    assert live[2:] == preview


def test_briefing_identity_title_body_priors():
    """D8/D14/SSoT §6: the id reminder is the ID (the value --as and
    $DIBS_AS take, I7), then 'claimed A2: <title>', body indented, and one
    'previously claimed by ... reaped ...' line per prior reap event, its
    time in UTC. An identity minted this invocation also gets the export
    line, so a fallback-minted worker can finish what it claims (D8)."""
    prior = Event(
        event_id=9, ts=NOW, agent='system', kind=EventKind.REAP,
        task_id='A1', to_agent=None, text=OTTER.name,
    )
    lines = format_briefing(init_rows(BRIEF_PLAN), ELEPHANT.agent_id, (prior,))
    assert lines == (
        'you are happy-elephant-2222',
        'claimed A1: Fix it',
        '  Repro: x.',
        '  Done: y.',
        'claimed A2: Two',
        'A1 was previously claimed by brave-otter, reaped 2023-11-14 22:13 '
        'UTC - verify before redoing',
    )
    assert format_briefing((), OTTER.agent_id, ()) == (
        'you are brave-otter-1111',
    )
    assert format_briefing((), OTTER.agent_id, (), minted=True) == (
        'you are brave-otter-1111 - export DIBS_AS=brave-otter-1111',
    )


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
