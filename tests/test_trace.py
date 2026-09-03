"""Unit + e2e: the DIBS_TRACE debugging lens (D23; §13 step 9).

A lens, never a ledger: nothing reads a trace back, and a trace
failure must be invisible to the traced command. E2e cases drive
cli.main with monkeypatched env.
"""


def test_trace_path_shape():
    """D23: .logs/<plan-name>.<UTC date>.jsonl beside the plan; date
    derived from the epoch `now` in UTC."""
    raise NotImplementedError('needs trace.trace_path (§13 step 11)')


def test_trace_path_unbound_fallback():
    """D23: plan None -> relative .logs/unbound.<UTC date>.jsonl."""
    raise NotImplementedError('needs trace.trace_path (§13 step 11)')


def test_trace_off_by_default(tmp_path, monkeypatch):
    """D23: with DIBS_TRACE unset or empty, no .logs/ ever appears."""
    raise NotImplementedError('needs cli.main + trace (§13 step 11)')


def test_trace_line_per_invocation(tmp_path, monkeypatch):
    """D23: DIBS_TRACE=1 -> each cli.main call appends exactly one JSON
    line carrying ts/argv/actor/plan/verb/exit_code/outcome."""
    raise NotImplementedError('needs cli.main + trace (§13 step 11)')


def test_trace_captures_refused_attempts(tmp_path, monkeypatch):
    """D23: a DibsError invocation (e.g. hand-full claim, wrong board)
    still traces - exit_code 1, outcome = the steered message. This is
    the visibility the I6 mutation journal deliberately omits."""
    raise NotImplementedError('needs cli.main + trace (§13 step 11)')


def test_trace_failure_never_breaks_command(tmp_path, monkeypatch):
    """D23: an unwritable .logs/ leaves stdout, stderr, and the exit
    code byte-identical to the untraced run."""
    raise NotImplementedError('needs cli.main + trace (§13 step 11)')
