"""Property tier over transitions: invariants across random boards (§11).

Seeded stdlib random (no hypothesis - see test_property_planfile
docstring). Each seed writes its own plan and opens its own WAL board
through plansync, exactly the way init does: from step 8 on there is no
test-only writer of task rows (ARCHITECTURE §11, §13 step 8a).
"""

from itertools import groupby

from conftest import NOW, open_plan, pick, resync

from dibs import queries, transitions
from dibs.records import Agent

SEEDS = 20  # each seed builds and drains its own WAL board
TREE_SIZE = 8
FLAT_SIZE = 9
SECTIONS = ('Parser', 'Docs', 'Build')
DEPTHS = 2  # a line nests at most one step deeper than the one above

WORKER = 'brave-otter-1111'
PLAN_NAME = 'seed{0}.md'
HEAD = '## {0}'
TASK = '{0}- [ ] Task {1}'
BODY = '{0}  A briefing for task {1}.'
STEP = '  '  # one nesting level in the generated document (D22)
EOL = '\n'
SHUFFLED_STAMP = 2_000_000_000  # a later mtime, so the CAS re-applies

SET_HAND = "UPDATE meta SET value = ? WHERE key = 'max_hand'"
SELECT_OPEN_CHILDREN = """
SELECT id FROM tasks
WHERE parent_id = ? AND status IN ('todo', 'doing')
"""


def tree_text(seed, size):
    """A random nested plan; every parent precedes its children (D22)."""
    lines = []
    depths = [0]
    for index in range(size):
        deeper = pick(seed, index, depths[-1] + DEPTHS)
        depths.append(deeper if index else 0)
        if not depths[-1]:
            lines.append(HEAD.format(
                SECTIONS[pick(seed, index + size, len(SECTIONS))],
            ))
        lines.append(TASK.format(STEP * depths[-1], index))
        lines.append(BODY.format(STEP * depths[-1], index))
    return EOL.join(lines) + EOL


def flat_text(seed, size, order):
    """One block per section, each block's tasks following `order`."""
    blocks = {section: [] for section in SECTIONS}
    for index in order:
        section = SECTIONS[pick(seed, index + size, len(SECTIONS))]
        blocks[section].append(index)
    return EOL.join(
        EOL.join((HEAD.format(name), *(
            TASK.format('', member) for member in members
        )))
        for name, members in blocks.items() if members
    ) + EOL


def shuffle(seed, size):
    """A seeded permutation of range(size) - reordering by hand (D7)."""
    draws = {index: pick(seed, index, size) for index in range(size)}
    return sorted(draws, key=draws.get)


def build_board(tmp_path, seed, text):
    """A board holding this plan, hand widened, one agent registered."""
    ctx = open_plan(tmp_path, text, PLAN_NAME.format(seed))
    size = len(queries.board_snapshot(ctx.conn))
    ctx.conn.execute(SET_HAND, (str(size),))
    ctx.conn.commit()
    transitions.register_agent(ctx.conn, Agent(WORKER, 'brave-otter'))
    return ctx


def open_children(conn, task_id):
    """Ids of the task's children that are still todo or doing (D22)."""
    return [row[0] for row in conn.execute(SELECT_OPEN_CHILDREN, (task_id,))]


def claim_and_finish(conn):
    """Drain the board one task at a time; nothing gated may be picked."""
    taken = []
    while True:
        got = transitions.claim(conn, WORKER, NOW)
        if not got:
            return tuple(taken)
        assert not open_children(conn, got[0].task_id)
        taken.append(got[0].task_id)
        transitions.finish(conn, WORKER, NOW, got[0].task_id, 'done')


def claim_all(conn):
    """Claim every task without finishing any; keep the claim order."""
    picked = []
    while True:
        got = transitions.claim(conn, WORKER, NOW)
        if not got:
            return tuple(picked)
        picked.extend(got)


def assert_children_first(tasks, taken):
    """A parent is claimed only after every child of its own (D22)."""
    at = {task_id: index for index, task_id in enumerate(taken)}
    for task in tasks:
        if task.parent_id:
            assert at[task.task_id] < at[task.parent_id]


def test_gating_invariant_random_trees(tmp_path):
    """D22 invariant: across random task trees and random completion
    orders, a parent is NEVER claimable while any todo/doing child
    exists beneath it - and unlocks the moment its own last child
    finishes, regardless of siblings elsewhere."""
    for seed in range(SEEDS):
        ctx = build_board(tmp_path, seed, tree_text(seed, TREE_SIZE))
        tasks = queries.board_snapshot(ctx.conn)
        parents = {task.parent_id for task in tasks} - {None}

        for parent_id in sorted(parents):
            assert not transitions.claim(ctx.conn, WORKER, NOW, (parent_id,))

        taken = claim_and_finish(ctx.conn)

        assert parents
        assert sorted(taken) == sorted(task.task_id for task in tasks)
        assert_children_first(tasks, taken)


def test_claim_order_affinity_then_seq(tmp_path):
    """D7 invariant: for boards whose ids no longer follow their line
    order - the author reordered by hand between syncs - repeated no-arg
    claims by one agent stay in-section while possible, then follow seq
    among available tasks only (D22 filters first)."""
    for seed in range(SEEDS):
        ctx = build_board(
            tmp_path, seed, flat_text(seed, FLAT_SIZE, range(FLAT_SIZE)),
        )
        resync(
            ctx,
            flat_text(seed, FLAT_SIZE, shuffle(seed, FLAT_SIZE)),
            SHUFFLED_STAMP,
        )
        tasks = queries.board_snapshot(ctx.conn)
        picked = claim_all(ctx.conn)
        sections = [task.section for task in picked]

        assert len(picked) == len(tasks)
        assert picked[0].seq == min(task.seq for task in tasks)
        # Each section is entered once and drained before the next.
        assert len([key for key, _run in groupby(sections)]) == len(
            set(sections),
        )
        for section in set(sections):
            seqs = [task.seq for task in picked if task.section == section]
            assert seqs == sorted(seqs)
