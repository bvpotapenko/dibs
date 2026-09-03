"""End-to-end through cli.main (§11; §13 step 9).

Also the verbs' suite: C6 keeps verbs too thin to test below the
pipeline. Drive main(argv) in-process with monkeypatched cwd/env and
capsys; assert stdout, exit codes, and final plan.md bytes.
"""


def test_full_loop_init_join_claim_done(tmp_path):
    """§11: init -> join -> claim -> done. Exit 0 throughout; final
    plan.md carries '- [x] ...  ✓ <name>: <note>' on the done line and
    every prose byte untouched (I4)."""
    raise NotImplementedError('needs cli.main (§13 step 11)')


def test_init_prints_key_and_handoff(tmp_path):
    """D20/GUIDE: init output holds the dibs-xxxx-xxxx key, the task
    count, and a paste-ready '/dibs <key>' handoff line."""
    raise NotImplementedError('needs cli.main (§13 step 11)')


def test_init_refuses_existing_board(tmp_path):
    """SSoT §6 init: second init exits 1 and steers to sync."""
    raise NotImplementedError('needs cli.main (§13 step 11)')


def test_key_resolves_from_unrelated_cwd(tmp_path):
    """D20: `--plan <key>` works from a directory unrelated to the
    plan, via the registry."""
    raise NotImplementedError('needs cli.main (§13 step 11)')


def test_no_board_steers_cd_or_plan_not_init(tmp_path):
    """D18: with no board found, exit 1 and steer to cd/--plan; init
    appears only as an author aside, never as the worker steer."""
    raise NotImplementedError('needs cli.main (§13 step 11)')


def test_many_boards_enumerated_refusal(tmp_path):
    """D18: two boards in scope -> refuse and enumerate, one runnable
    steer per board; never guess."""
    raise NotImplementedError('needs cli.main (§13 step 11)')


def test_verify_touches_nothing(tmp_path):
    """D21: verify renders the preview, exits 0, and leaves the
    directory byte-identical - no board, no registry entry, no
    annotation."""
    raise NotImplementedError('needs cli.main (§13 step 11)')


def test_auto_sync_after_human_edit(tmp_path):
    """I9: edit plan.md (new task) between commands; the next claim
    sees it without an explicit sync."""
    raise NotImplementedError('needs cli.main (§13 step 11)')


def test_unknown_identity_steered(tmp_path):
    """D8/D18: --as with a foreign id exits 1 with the wrong-board
    check steer; no silent minting."""
    raise NotImplementedError('needs cli.main (§13 step 11)')


def test_sqlite_error_exits_two(tmp_path):
    """§6: an environment failure (e.g. corrupt/locked-forever board
    file) prints the generic retry steer on stderr and exits 2."""
    raise NotImplementedError('needs cli.main (§13 step 11)')
