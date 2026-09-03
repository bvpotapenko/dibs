"""Integration: read-side queries on a tmp board (§11, §13 step 5)."""


def test_deliver_events_advances_cursor(board, two_agents):
    """D10: first call returns unseen events; an immediate second call
    returns nothing - cursor moved in the same transaction."""
    raise NotImplementedError('needs deliver_events (§13 step 6)')


def test_deliver_events_filters_directed(board, two_agents):
    """D10: a note --for otter reaches otter, never elephant;
    broadcasts reach both."""
    raise NotImplementedError('needs deliver_events (§13 step 6)')


def test_prior_claim_reports_reap(board, two_agents):
    """SSoT §6 claim row: a reaped task's re-claimer learns the prior
    claimant and when the reap happened."""
    raise NotImplementedError('needs prior_claim (§13 step 6)')


def test_resolve_task_exact_beats_fuzzy(board):
    """D14: an exact id wins even when a fuzzier candidate exists."""
    raise NotImplementedError('needs resolve_task (§13 step 6)')


def test_resolve_task_miss_steers(board):
    """I10: a miss raises DibsError whose steer is a runnable claim
    command naming the nearest id ('did you mean A7?')."""
    raise NotImplementedError('needs resolve_task (§13 step 6)')


def test_verify_actor_only_this_board(board, two_agents):
    """D8/D18: a registered id verifies; an id from another board (or
    invented) does not."""
    raise NotImplementedError('needs verify_actor (§13 step 6)')


def test_newly_unlocked_last_child_only(board, two_agents):
    """D22: None while siblings stay open; the parent Task exactly on
    the last child's finish."""
    raise NotImplementedError('needs newly_unlocked (§13 step 6)')


def test_board_snapshot_in_seq_order(board):
    """§6 list: snapshot follows current seq, not id or insert order."""
    raise NotImplementedError('needs board_snapshot (§13 step 6)')


def test_board_snapshot_carries_meta_and_events(board):
    """§5 Board: key '' before init, max_hand from meta, plan_mtime, and
    the last EVENT_CAP events newest-last."""
    raise NotImplementedError('needs board_snapshot (§13 step 6)')


def test_claim_refusal_five_kinds(board, two_agents):
    """D6/D22/C9: the same zero-row claim is explained as TAKEN (holder
    named), GATED (children named), HAND_FULL (held ids), WAITING
    (holders of what remaining todo rows wait on), EMPTY - one CASE picks,
    one names query per kind; the names feed output.steer verbatim."""
    raise NotImplementedError('needs claim_refusal (§13 step 6)')
