"""Property tier over transitions: invariants across random boards (§11).

Seeded stdlib random (no hypothesis - see test_property_planfile
docstring). Each case builds a fresh tmp board per seed.
"""

import random
from contextlib import closing

from dibs import transitions
from dibs.records import Status
from tests.boards import NOW, OTTER, build_board, open_children, peek_tree

SEEDS = range(25)
SECTIONS = ('## Alpha', '## Beta', '## Gamma')
LINE_KINDS = ('heading', 'task')
LINE_WEIGHTS = (3, 17)
MAX_DEPTH = 2


def random_tree(seed: int) -> str:
    """Plan text with 1-3 sections and nesting up to three levels deep."""
    rng = random.Random(seed)
    lines = []
    depth = 0
    for number in range(rng.randint(4, 14)):
        if number == 0 or rng.choices(LINE_KINDS, LINE_WEIGHTS)[0] == 'heading':
            lines.append(rng.choice(SECTIONS))
            depth = 0
        depth = rng.randint(0, min(depth + 1, MAX_DEPTH))
        indent = '  ' * depth
        lines.append(f'{indent}- [ ] Task {number}')
    return '\n'.join([*lines, ''])


def test_gating_invariant_random_trees(tmp_path):
    """D22 invariant: across random task trees and random completion
    orders, a parent is NEVER claimable while any todo/doing child
    exists beneath it - and unlocks the moment its own last child
    finishes, regardless of siblings elsewhere."""
    for seed in SEEDS:
        rng = random.Random(seed)
        ctx = build_board(tmp_path / f'gate{seed}', random_tree(seed))
        with closing(ctx.conn) as conn:
            assert transitions.register_agent(conn, OTTER, NOW)
            pending = [row['id'] for row in peek_tree(ctx)]
            while pending:
                task_id = rng.choice(pending)
                got = transitions.claim(conn, OTTER.agent_id, NOW, (task_id,))
                if open_children(ctx, task_id):
                    assert not got, (seed, task_id)
                    continue
                assert [task.task_id for task in got] == [task_id], seed
                assert transitions.finish(
                    conn, OTTER.agent_id, NOW, task_id, 'ok',
                )
                pending.remove(task_id)
            statuses = {row['status'] for row in peek_tree(ctx)}
            assert statuses == {Status.DONE.value}


def expected_next(rows, last_section) -> str | None:
    """D7 oracle: affinity to last_section among available, else lowest seq."""
    by_id = {row['id']: row for row in rows}
    available = [
        row for row in rows
        if row['status'] == Status.TODO.value
        and not any(
            child['parent_id'] == row['id']
            and child['status'] != Status.DONE.value
            for child in by_id.values()
        )
    ]
    warm = [row for row in available if row['section'] == last_section]
    ranked = warm or available
    return ranked[0]['id'] if ranked else None


def test_claim_order_affinity_then_seq(tmp_path):
    """D7 invariant: for shuffled boards, repeated no-arg claims by one
    agent stay in-section while possible, then follow seq among
    available tasks only (D22 filters first)."""
    for seed in SEEDS:
        ctx = build_board(tmp_path / f'order{seed}', random_tree(seed))
        with closing(ctx.conn) as conn:
            assert transitions.register_agent(conn, OTTER, NOW)
            last_section = None
            while expected_next(peek_tree(ctx), last_section) is not None:
                want = expected_next(peek_tree(ctx), last_section)
                got = transitions.claim(conn, OTTER.agent_id, NOW)
                assert [task.task_id for task in got] == [want], (seed, want)
                transitions.finish(conn, OTTER.agent_id, NOW, want, 'ok')
                last_section = got[0].section
            assert not transitions.claim(conn, OTTER.agent_id, NOW)
