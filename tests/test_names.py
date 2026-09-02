"""Unit + integration: identity minting and vocabulary (SSoT §7)."""

from dibs import names

MIN_COMBOS = 2000  # SSoT §7: ~2,500 pairs keep UNIQUE retries rare


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


def test_mint_identity_retries_on_collision(board):
    """I1: a UNIQUE collision re-rolls; never check-then-insert.

    Pre-register every name but one (or monkeypatch the picker to
    collide once), then assert mint_identity still lands and the id
    ends in ID_DIGITS digits.
    """
    raise NotImplementedError('needs names.mint_identity (§13 step 6)')


def test_mint_board_key_format():
    """D20/§13: 'dibs-' + 8 hex chars in two dash-separated groups."""
    raise NotImplementedError('needs names.mint_board_key (§13 step 6)')
