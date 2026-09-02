"""Property tier over transitions: invariants across random boards (§11).

Seeded stdlib random (no hypothesis - see test_property_planfile
docstring). Each case builds a fresh tmp board per seed.
"""


def test_gating_invariant_random_trees(tmp_path):
    """D22 invariant: across random task trees and random completion
    orders, a parent is NEVER claimable while any todo/doing child
    exists beneath it - and unlocks the moment its own last child
    finishes, regardless of siblings elsewhere."""
    raise NotImplementedError('needs claim + finish (§13 step 4)')


def test_claim_order_affinity_then_seq(tmp_path):
    """D7 invariant: for shuffled boards, repeated no-arg claims by one
    agent stay in-section while possible, then follow seq among
    available tasks only (D22 filters first)."""
    raise NotImplementedError('needs transitions.claim (§13 step 4)')
