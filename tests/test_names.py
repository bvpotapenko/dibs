"""Unit + integration: identity minting and vocabulary (SSoT §7)."""

import re

from dibs import names, transitions
from dibs.records import Agent, EventKind

MIN_COMBOS = 2000  # SSoT §7: ~2,500 pairs keep UNIQUE retries rare
KEY_RE = re.compile(r'^dibs-[0-9a-f]{4}-[0-9a-f]{4}$')  # D20, SSoT §13
DRAWS = 20  # enough board keys to catch a constant or a short group
SQUATTER = Agent('brave-otter-0001', 'brave-otter')  # holds the name
COLLIDE_THEN_SETTLE = ('brave', 'otter', 'happy', 'elephant')
JOIN_EVENTS = 2  # the squatter's, then the mint that finally landed
COUNT_KIND = 'SELECT count(*) FROM events WHERE kind = ?'


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

    Pre-register every name but one (or monkeypatch the picker to
    collide once), then assert mint_identity still lands and the id
    ends in ID_DIGITS digits.
    """
    picks = iter(COLLIDE_THEN_SETTLE)
    monkeypatch.setattr(names, 'choice', lambda _words: next(picks))
    transitions.register_agent(board.conn, SQUATTER)

    minted = names.mint_identity(board.conn)

    assert minted.name == 'happy-elephant'
    assert minted.agent_id.rsplit('-', 1)[0] == minted.name
    assert minted.agent_id.rsplit('-', 1)[1].isdigit()
    assert len(minted.agent_id.rsplit('-', 1)[1]) == names.ID_DIGITS
    # The lost insert wrote nothing: one join event per real mint (I6).
    assert board.conn.execute(
        COUNT_KIND, (EventKind.JOIN.value,),
    ).fetchone()[0] == JOIN_EVENTS


def test_mint_identity_registers_on_the_board(board):
    """D8/§7: the minted identity is the one the board now knows."""
    minted = names.mint_identity(board.conn)

    assert board.conn.execute(
        'SELECT name FROM agents WHERE id = ?', (minted.agent_id,),
    ).fetchone() == (minted.name,)
    assert minted.name.split('-')[0] in names.ADJECTIVES
    assert minted.name.split('-')[1] in names.ANIMALS


def test_mint_board_key_format():
    """D20/§13: 'dibs-' + 8 hex chars in two dash-separated groups."""
    keys = {names.mint_board_key() for _draw in range(DRAWS)}

    assert all(KEY_RE.match(key) for key in keys)
    # Random, not derived: DRAWS draws must not collapse to one value.
    assert len(keys) > 1
