"""Property tier over transitions: invariants across random boards (§11).

Seeded stdlib random (no hypothesis - see test_property_planfile
docstring). Each case builds a fresh tmp board per seed.
"""

from itertools import groupby

from conftest import NOW, insert_task, pick

from dibs import planfile, store, transitions
from dibs.records import Agent, Status, Task

SEEDS = 20  # each seed builds and drains its own WAL board
TREE_SIZE = 8
FLAT_SIZE = 9
SECTIONS = ('Parser', 'Docs', 'Build')
BRANCHES = 2  # pick(...) % BRANCHES: half the tasks get a parent

WORKER = 'brave-otter-1111'
DB_NAME = 'seed{0}.dibs'
TITLE = 'Task {0}'

SET_HAND = "UPDATE meta SET value = ? WHERE key = 'max_hand'"
SELECT_OPEN_CHILDREN = """
SELECT id FROM tasks
WHERE parent_id = ? AND status IN ('todo', 'doing')
"""


def make_task(task_id, parent_id, seq, section):
    """A todo row for a generated board."""
    return Task(
        task_id=task_id,
        parent_id=parent_id,
        seq=seq,
        section=section,
        title=TITLE.format(task_id),
        body='',
        text_hash=planfile.title_hash(TITLE.format(task_id)),
        status=Status.TODO,
        owner=None,
        claimed_at=None,
        done_at=None,
        done_note=None,
    )


def tree_tasks(seed, size):
    """A random forest in which every parent precedes its children."""
    rows = []
    for index in range(size):
        rows.append(make_task(
            str(index),
            rows[pick(seed, index, len(rows))].task_id
            if rows and pick(seed, index + size, BRANCHES) else None,
            index,
            SECTIONS[pick(seed, index, len(SECTIONS))],
        ))
    return tuple(rows)


def flat_tasks(seed, size):
    """A parentless board whose sections are mixed and seqs shuffled."""
    draws = {index: pick(seed, index, size) for index in range(size)}
    shuffled = sorted(draws, key=draws.get)
    return tuple(
        make_task(
            str(index),
            None,
            shuffled[index],
            SECTIONS[pick(seed, index + size, len(SECTIONS))],
        )
        for index in range(size)
    )


def build_board(tmp_path, seed, tasks):
    """A fresh WAL board holding these rows, with one registered agent."""
    conn = store.connect(tmp_path / DB_NAME.format(seed))
    store.ensure_schema(conn)
    conn.execute(SET_HAND, (str(len(tasks)),))
    for task in tasks:
        insert_task(conn, task)
    transitions.register_agent(conn, Agent(WORKER, 'brave-otter'))
    return conn


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
        tasks = tree_tasks(seed, TREE_SIZE)
        conn = build_board(tmp_path, seed, tasks)
        parents = {task.parent_id for task in tasks} - {None}

        for parent_id in sorted(parents):
            assert not transitions.claim(conn, WORKER, NOW, (parent_id,))

        taken = claim_and_finish(conn)

        assert sorted(taken) == sorted(task.task_id for task in tasks)
        assert_children_first(tasks, taken)


def test_claim_order_affinity_then_seq(tmp_path):
    """D7 invariant: for shuffled boards, repeated no-arg claims by one
    agent stay in-section while possible, then follow seq among
    available tasks only (D22 filters first)."""
    for seed in range(SEEDS):
        tasks = flat_tasks(seed, FLAT_SIZE)
        picked = claim_all(build_board(tmp_path, seed, tasks))
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
