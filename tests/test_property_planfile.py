"""Property/metamorphic tier for the pure plan functions (§11).

Use seeded stdlib random document generation (a local generator
helper, seeds 0..N) - dev deps stay at flake8/WPS/ruff/pytest. If
hypothesis is ever adopted, these become @given strategies; amend
pyproject dev extras first.
"""


def test_annotate_preserves_nongrammar_bytes():
    """I4 crown jewel: across generated documents (prose, fences,
    weird indentation, unicode), annotate_lines changes no byte outside
    its own grammar lines. Generator + seeds 0-99."""
    raise NotImplementedError('needs annotate_lines (§13 step 3)')


def test_annotate_then_parse_is_stable():
    """Metamorphic: parse(annotate(text, tasks)) finds the same items
    (titles, parents, sections) as parse(text) - only checkbox state
    tokens differ."""
    raise NotImplementedError('needs parse_plan + annotate_lines')


def test_compute_sync_is_idempotent():
    """§8: applying a computed SyncPlan to the rows, then recomputing
    against the same text, yields an empty SyncPlan."""
    raise NotImplementedError('needs compute_sync (§13 step 3)')
