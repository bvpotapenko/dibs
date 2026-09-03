"""Unit + integration: identity minting and vocabulary (SSoT §7)."""

import re

from dibs import names, transitions
from dibs.records import EventKind
from tests.boards import NOW, OTTER, peek_events

MIN_COMBOS = 2000  # SSoT §7: ~2,500 pairs keep UNIQUE retries rare
ID_RE = re.compile(r'[a-z]+-[a-z]+-[0-9]{4}')  # SSoT §7: name-NNNN
KEY_RE = re.compile(r'dibs-[0-9a-f]{4}-[0-9a-f]{4}')  # SSoT §13, D20
SAMPLES = 5


def test_word_lists_are_clean():
    """§7 curation: lowercase single words, unique, no cross-list dupes."""
    combined = names.ADJECTIVES + names.ANIMALS
    assert all(word.isalpha() and word.islower() for word in combined)
    assert len(set(names.ADJECTIVES)) == len(names.ADJECTIVES)
    assert len(set(names.ANIMALS)) == len(names.ANIMALS)
    assert not set(names.ADJECTIVES) & set(names.ANIMALS)


def test_word_lists_give_enough_combos():
    """§7: ~2,500 combos keep UNIQUE-collision retries rare."""
    assert len(names.ADJECTIVES) * len(names.ANIMALS) >= MIN_COMBOS


def test_mint_identity_retries_on_collision(board, monkeypatch):
    """I1: a UNIQUE collision re-rolls; never check-then-insert.

    The picker is scripted to roll brave-otter (already registered) and
    then calm-fox: mint_identity lands on calm-fox-NNNN, both rolls are
    consumed, and the refused roll left no join event (I6).
    """
    assert transitions.register_agent(board.conn, OTTER, NOW)
    rolls = iter((
        names.ADJECTIVES.index('brave'), names.ANIMALS.index('otter'),
        names.ADJECTIVES.index('calm'), names.ANIMALS.index('fox'),
    ))
    monkeypatch.setattr(
        names.secrets, 'choice', lambda words: words[next(rolls)],
    )
    agent = names.mint_identity(board.conn, NOW)
    assert (agent.name, next(rolls, None)) == ('calm-fox', None)
    assert ID_RE.fullmatch(agent.agent_id)
    assert agent.agent_id.rsplit('-', 1)[0] == agent.name
    joins = [
        (row['agent'], row['text'], row['ts'])
        for row in peek_events(board, EventKind.JOIN.value)
    ]
    assert joins == [
        (OTTER.agent_id, OTTER.name, NOW), (agent.agent_id, 'calm-fox', NOW),
    ]


def test_mint_board_key_format():
    """D20/§13: 'dibs-' + 8 hex chars in two dash-separated groups."""
    keys = {names.mint_board_key() for _ in range(SAMPLES)}
    assert all(KEY_RE.fullmatch(key) for key in keys)
    assert len(keys) > 1  # random, not a constant
