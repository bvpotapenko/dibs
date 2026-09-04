"""Unit + e2e: the DIBS_TRACE debugging lens (D23; §13 step 11).

A lens, never a ledger: nothing reads a trace back, and a trace
failure must be invisible to the traced command. E2e cases drive
cli.main with monkeypatched env.
"""

import json
from pathlib import Path

from dibs import cli, trace
from tests.boards import NOW, joined, run_cli

DAY = '2023-11-14'  # NOW in UTC (tests/boards.NOW)
FIELDS = (
    'ts', 'argv', 'actor', 'plan', 'verb', 'exit_code', 'outcome',
)


def lines_of(workspace):
    """Every trace record beside the plan, oldest first (D23).

    The day in the name comes from the invocation's own UTC clock, so
    the file is found by shape rather than by a fixed date.
    """
    logs = sorted((workspace / trace.TRACE_DIR).glob('plan.*.jsonl'))
    return [
        json.loads(line)
        for written in logs
        for line in written.read_text().splitlines()
    ]


def test_trace_path_shape():
    """D23: .logs/<plan-name>.<UTC date>.jsonl beside the plan; date
    derived from the epoch `now` in UTC."""
    beside = trace.trace_path(Path('/home/crew/errands.md'), NOW)
    assert beside == Path(f'/home/crew/.logs/errands.{DAY}.jsonl')
    assert trace.trace_path(Path('plan.md'), NOW) == Path(
        f'.logs/plan.{DAY}.jsonl',
    )


def test_trace_path_unbound_fallback():
    """D23: plan None -> relative .logs/unbound.<UTC date>.jsonl."""
    assert trace.trace_path(None, NOW) == Path(f'.logs/unbound.{DAY}.jsonl')


def test_trace_off_by_default(workspace, capsys, monkeypatch):
    """D23: with DIBS_TRACE unset or empty, no .logs/ ever appears."""
    assert run_cli(capsys, 'init', 'plan.md')[0] == cli.EXIT_OK
    monkeypatch.setenv(cli.ENV_TRACE, '')
    assert run_cli(capsys, 'list')[0] == cli.EXIT_OK
    assert run_cli(capsys, 'claim', '--as', 'ghost-0000')[0] == cli.EXIT_USER
    assert not list(workspace.rglob('.logs'))


def test_trace_line_per_invocation(workspace, capsys, monkeypatch):
    """D23: DIBS_TRACE=1 -> each cli.main call appends exactly one JSON
    line carrying ts/argv/actor/plan/verb/exit_code/outcome."""
    run_cli(capsys, 'init', 'plan.md')
    actor = joined(capsys)
    monkeypatch.setenv(cli.ENV_TRACE, '1')
    monkeypatch.setenv(cli.ENV_ACTOR, actor)
    codes = [run_cli(capsys, verb)[0] for verb in ('claim', 'list')]
    traced = lines_of(workspace)
    assert codes == [cli.EXIT_OK, cli.EXIT_OK]
    assert [tuple(record) for record in traced] == [FIELDS, FIELDS]
    assert [
        (record['verb'], record['actor'], record['exit_code'])
        for record in traced
    ] == [('claim', actor, cli.EXIT_OK), ('list', actor, cli.EXIT_OK)]
    assert (traced[0]['plan'], traced[0]['argv']) == (
        (workspace / 'plan.md').as_posix(), ['claim'],
    )
    assert (
        traced[0]['outcome'].startswith(f'you are {actor}'),
        traced[0]['ts'] >= NOW,
    ) == (True, True)


def test_trace_captures_refused_attempts(workspace, capsys, monkeypatch):
    """D23: a DibsError invocation (e.g. hand-full claim, wrong board)
    still traces - exit_code 1, outcome = the steered message. This is
    the visibility the I6 mutation journal deliberately omits."""
    run_cli(capsys, 'init', 'plan.md')
    monkeypatch.setenv(cli.ENV_TRACE, '1')
    monkeypatch.setenv(cli.ENV_ACTOR, joined(capsys))
    assert run_cli(capsys, 'claim')[0] == cli.EXIT_OK
    assert run_cli(capsys, 'claim')[0] == cli.EXIT_USER  # hand full (D6)
    refused = lines_of(workspace)[-1]
    assert (refused['verb'], refused['exit_code']) == ('claim', cli.EXIT_USER)
    assert refused['outcome'].startswith('Hand full (1 at most): you hold A1')
    assert refused['outcome'].endswith('Run: dibs done A1 --note "..."')


def test_trace_failure_never_breaks_command(workspace, capsys, monkeypatch):
    """D23: an unwritable .logs/ leaves stdout, stderr, and the exit
    code byte-identical to the untraced run."""
    untraced = run_cli(capsys, 'verify', 'plan.md')
    (workspace / '.logs').write_text('a file where the directory goes')
    monkeypatch.setenv(cli.ENV_TRACE, '1')
    assert run_cli(capsys, 'verify', 'plan.md') == untraced
    assert (workspace / '.logs').is_file()


def test_trace_parse_failure(workspace, capsys, monkeypatch):
    """D23: with DIBS_TRACE=1, `dibs take` (unknown verb) still appends one
    line - verb None, plan None, exit_code EXIT_USER, argv ['take'] -
    under .logs/unbound.<UTC date>.jsonl, since no board resolved."""
    raise NotImplementedError('needs cli.main parse inside try (§13 step 13)')
