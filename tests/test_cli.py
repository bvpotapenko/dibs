"""End-to-end through cli.main (§11; §13 steps 10-11).

Also the verbs' suite: C6 keeps verbs too thin to test below the
pipeline. Drive main(argv) in-process with monkeypatched cwd/env and
capsys; assert stdout, exit codes, and final plan.md bytes.
"""

from dibs import cli
from tests.boards import joined, key_of, run_cli

ERRANDS = '## Errands\n- [ ] Order the groceries\n  Budget 8000 JPY.\n'
REFACTOR = '## Code\n- [ ] Split the parser\n  Start at parse_plan.\n'
GROWN = '- [ ] Write the changelog\n  Summarize the release.\n'
NAME_PARTS = 3  # adjective-animal-NNNN (SSoT §7)


def prose(lines):
    """Every line annotation may never touch: the non-checkbox ones (I4)."""
    return [line for line in lines if not line.lstrip().startswith('- [')]


def test_full_loop_init_join_claim_done(workspace, capsys, plan_text):
    """§11: init -> join -> claim -> done. Exit 0 throughout; final
    plan.md carries '- [x] ...  ✓ <name>: <note>' on the done line and
    every prose byte untouched (I4)."""
    started = run_cli(capsys, 'init', 'plan.md')[0]
    actor = joined(capsys)
    code, briefing, _ = run_cli(capsys, 'claim', '--as', actor)
    assert (started, code, len(actor.split('-'))) == (
        cli.EXIT_OK, cli.EXIT_OK, NAME_PARTS,
    )
    assert briefing.split('\n')[:3] == [
        f'you are {actor}',
        'claimed A1: Fix off-by-one in the tokenizer',
        '  Repro: token count is 12 for fixtures/one.txt, expected 11.',
    ]
    assert briefing.rstrip().endswith('next: dibs done A1 --note "..."')
    code, _, _ = run_cli(
        capsys, 'done', 'A1', '--note', 'anchored the regex', '--as', actor,
    )
    final = (workspace / 'plan.md').read_text().split('\n')
    name = actor.rsplit('-', 1)[0]
    assert (code, final[6]) == (
        cli.EXIT_OK,
        f'- [x] Fix off-by-one in the tokenizer  ✓ {name}: anchored the regex',
    )
    assert prose(final) == prose(plan_text.split('\n'))


def test_init_prints_key_and_handoff(workspace, capsys):
    """D20/GUIDE: init output holds the dibs-xxxx-xxxx key, the task
    count, and a paste-ready '/dibs <key>' handoff line."""
    code, printed, _ = run_cli(capsys, 'init', 'plan.md')
    key = key_of(printed)
    assert (code, key.startswith('dibs-')) == (cli.EXIT_OK, True)
    assert len(key.split('-')) == NAME_PARTS
    assert printed.split('\n')[:2] == [
        f'board {key} (6 tasks)', f'hand to each session: /dibs {key}',
    ]
    assert f'next: dibs list --plan {key}' in printed
    assert (
        (workspace / '.plan.md.dibs').is_file(),
        (workspace / 'registry' / key).read_text(),
    ) == (True, str(workspace / 'plan.md'))


def test_init_refuses_existing_board(workspace, capsys):
    """SSoT §6 init: second init exits 1 and steers to sync."""
    key = key_of(run_cli(capsys, 'init', 'plan.md')[1])
    code, printed, refusal = run_cli(capsys, 'init', 'plan.md')
    assert (code, printed) == (cli.EXIT_USER, '')  # refusals go to stderr
    assert (workspace / 'registry' / key).is_file()  # the first key stands
    assert refusal.startswith(f'Board {key} already exists')
    assert refusal.strip().endswith(f'Run: dibs sync --plan {key}')


def test_key_resolves_from_unrelated_cwd(workspace, capsys, monkeypatch):
    """D20: `--plan <key>` works from a directory unrelated to the
    plan, via the registry."""
    key = key_of(run_cli(capsys, 'init', 'plan.md')[1])
    elsewhere = workspace.parent / 'elsewhere'
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    code, listed, _ = run_cli(capsys, 'list', '--plan', key)
    assert code == cli.EXIT_OK
    assert listed.startswith(f'board {key} (6 tasks)')
    assert 'A1 todo: Fix off-by-one in the tokenizer' in listed
    monkeypatch.setenv(cli.ENV_BOARD, key)
    assert run_cli(capsys, 'list')[1] == listed


def test_no_board_steers_cd_or_plan_not_init(workspace, capsys, monkeypatch):
    """D18: with no board found, exit 1 and steer to cd/--plan; init
    appears only as an author aside, never as the worker steer."""
    bare = workspace.parent / 'bare'
    bare.mkdir()
    monkeypatch.chdir(bare)
    code, _, refusal = run_cli(capsys, 'claim')
    message, steer = refusal.strip().split('\n')
    assert code == cli.EXIT_USER
    assert 'cd to the directory holding the plan' in message
    assert 'dibs init <plan.md>' in message  # the author aside only
    assert steer == 'Run: dibs claim --plan <key or plan.md>'


def test_many_boards_enumerated_refusal(workspace, capsys):
    """D18: two boards in scope -> refuse and enumerate, one runnable
    steer per board; never guess."""
    (workspace / 'errands.md').write_text(ERRANDS)
    (workspace / 'refactor.md').write_text(REFACTOR)
    (workspace / 'plan.md').unlink()
    for plan in ('errands.md', 'refactor.md'):
        assert run_cli(capsys, 'init', plan)[0] == cli.EXIT_OK
    code, _, refusal = run_cli(capsys, 'claim')
    assert code == cli.EXIT_USER
    assert refusal.strip().split('\n') == [
        'Several boards in scope - pick the one matching the plan path '
        'you were given, never guess:',
        'dibs claim --plan errands.md',
        'dibs claim --plan refactor.md',
        'Run: dibs claim --plan <one of: errands.md, refactor.md>',
    ]


def test_verify_touches_nothing(workspace, capsys, plan_text):
    """D21: verify renders the preview, exits 0, and leaves the
    directory byte-identical - no board, no registry entry, no
    annotation."""
    code, preview, _ = run_cli(capsys, 'verify', 'plan.md')
    assert code == cli.EXIT_OK
    assert preview.split('\n')[:3] == [
        '## Parser',
        'A1 todo: Fix off-by-one in the tokenizer',
        'A2 todo: Ship the tokenizer regression suite (0/2)',
    ]
    assert (
        'A3 done by human: Rename Lexer to Tokenizer !no body' in preview,
        'next: dibs init plan.md' in preview,
    ) == (True, True)
    assert (
        [path.name for path in workspace.iterdir()],
        (workspace / 'plan.md').read_text(),
    ) == (['plan.md'], plan_text)
    run_cli(capsys, 'init', 'plan.md')
    assert 'this plan already has a board' in run_cli(
        capsys, 'verify', 'plan.md',
    )[1]


def test_missing_plan_steers_not_traces(workspace, capsys):
    """I10/D14: a plan path that is not there is a steered refusal, never
    a traceback - for the pure verb as much as for the board verbs, and
    `--plan` is accepted in place of the positional (tolerant forms)."""
    (workspace / 'plan.md').unlink()
    verified = run_cli(capsys, 'verify', 'typo.md')
    inited = run_cli(capsys, 'init', '--plan', 'typo.md')
    assert (verified[0], inited[0]) == (cli.EXIT_USER, cli.EXIT_USER)
    assert verified[2].strip().split('\n')[-1] == (
        'Run: dibs verify --plan <key or plan.md>'
    )
    assert 'No board found' in inited[2]


def test_auto_sync_after_human_edit(workspace, capsys):
    """I9: edit plan.md (new task) between commands; the next claim
    sees it without an explicit sync."""
    run_cli(capsys, 'init', 'plan.md')
    actor = joined(capsys)
    run_cli(capsys, 'claim', '--task', 'A1', '--as', actor)
    plan = workspace / 'plan.md'
    plan.write_text(plan.read_text() + GROWN)
    code, briefing, _ = run_cli(capsys, 'claim', '--task', 'B2', '--as', actor)
    assert (code, 'claimed B2: Write the changelog' in briefing) == (
        cli.EXIT_USER, False,  # the hand is full: A1 is still held
    )
    run_cli(capsys, 'done', 'A1', '--note', 'done', '--as', actor)
    code, briefing, _ = run_cli(capsys, 'claim', '--task', 'B2', '--as', actor)
    assert code == cli.EXIT_OK
    assert 'claimed B2: Write the changelog' in briefing
    assert '  Summarize the release.' in briefing


def test_unknown_identity_steered(workspace, capsys):
    """D8/D18: --as with a foreign id exits 1 with the wrong-board
    check steer; no silent minting."""
    run_cli(capsys, 'init', 'plan.md')
    code, _, refusal = run_cli(capsys, 'claim', '--as', 'calm-fox-9999')
    assert code == cli.EXIT_USER
    assert refusal.startswith('Identity calm-fox-9999 is unknown on this board')
    assert refusal.strip().endswith(
        'Run: export DIBS_BOARD=<key or plan.md you were given>',
    )
    assert 'calm-fox' not in (workspace / 'plan.md').read_text()


def test_sqlite_error_exits_two(workspace, capsys):
    """§6: an environment failure (e.g. corrupt/locked-forever board
    file) prints the generic retry steer on stderr and exits 2."""
    (workspace / '.plan.md.dibs').write_text('not a database at all')
    code, printed, failure = run_cli(capsys, 'list')
    assert (code, printed) == (cli.EXIT_ENV, '')  # failures go to stderr
    assert failure.startswith('The board could not be read or written')
    assert failure.strip().endswith('Run: dibs list')
