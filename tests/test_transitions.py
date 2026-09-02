"""Integration: write transitions on a tmp WAL DB (§11, §13 step 4).

The CAS race test is the reason dibs exists; land it first, red, then
implement claim against it.
"""


def test_claim_race_exactly_one_winner(board, two_agents):
    """I1/I2: two threads claim the same lone task over one DB file;
    exactly one gets rowcount 1. Use a threading.Barrier so both hit
    the UPDATE together; separate connections per thread."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')


def test_claim_bundle_all_or_none(board, two_agents):
    """D6: a bundle with one already-taken member claims nothing, and
    the taken member is identifiable for the steer."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')


def test_claim_bundle_must_fit_hand(board, two_agents):
    """D6: a bundle larger than max_hand is refused whole, not trimmed."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')


def test_claim_hand_limit_blocks_second(board, two_agents):
    """D6: with max_hand=1 and one task held, a second claim returns
    zero rows - enforced inside the WHERE, not by Python."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')


def test_respawn_steered_back_to_held_task(board, two_agents):
    """D6 side benefit: a re-run with the same identity and a full hand
    is refused, and the follow-up read names the held task."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')


def test_claim_prefers_last_section_then_seq(board, two_agents):
    """D7: next no-arg claim lands in the caller's last section when one
    is open there, else lowest seq; explicit --task overrides."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')


def test_claim_skips_gated_parents(board, two_agents):
    """D22: no-arg claim never picks a task with an open (todo/doing)
    child; it takes the deepest ready work instead."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')


def test_claim_gated_parent_names_children(board, two_agents):
    """D22/D6: explicit claim of a gated parent yields zero rows, and
    the follow-up read lists its open children for the steer."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')


def test_claim_ignores_orphaned_children(board, two_agents):
    """D22: orphaned children left the plan; they never gate a parent."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')


def test_claim_zero_rows_three_diagnoses(board, two_agents):
    """D6/D22: the same zero-row claim is diagnosed three ways by the
    follow-up read - hand full / nothing available yet / board empty -
    each carrying the data its distinct steer needs."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')


def test_finish_rejects_non_owner(board, two_agents):
    """I2: WHERE owner=:actor - the other agent's finish is rowcount 0."""
    raise NotImplementedError('needs transitions.finish (§13 step 4)')


def test_finish_writes_one_event(board, two_agents):
    """C3/I6: one successful finish = one done event, same transaction."""
    raise NotImplementedError('needs transitions.finish (§13 step 4)')


def test_release_returns_task_to_todo(board, two_agents):
    """SSoT §6 drop: owned doing -> todo, owner cleared, drop event."""
    raise NotImplementedError('needs transitions.release (§13 step 4)')


def test_housekeeping_reaps_past_ttl(board, two_agents):
    """D9/I8: a claim older than REAP_TTL_SECONDS reverts to todo and
    logs a reap event; younger claims are untouched."""
    raise NotImplementedError('needs housekeeping (§13 step 4)')


def test_housekeeping_refreshes_callers_lease(board, two_agents):
    """D9: any command from an agent bumps claimed_at on its claims."""
    raise NotImplementedError('needs housekeeping (§13 step 4)')


def test_record_note_broadcast_and_directed(board, two_agents):
    """D10: no --for means to_agent NULL; --for sets it; both append."""
    raise NotImplementedError('needs record_note (§13 step 4)')


def test_import_author_done_owner_human(board):
    """SSoT §8: a hand-checked [x] imports as done with owner 'human'."""
    raise NotImplementedError('needs import_author_done (§13 step 4)')


def test_register_agent_false_on_collision(board):
    """I1: second INSERT of the same name returns False via UNIQUE -
    no SELECT-then-INSERT anywhere."""
    raise NotImplementedError('needs register_agent (§13 step 4)')
