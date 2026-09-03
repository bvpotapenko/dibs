# dibs — Checkpoint 1 review (ARCHITECTURE §13 steps 2–4)

Reviewed HEAD: 96e23df058fa738d5876510ea01134725430146a (`96e23df feat(core): implement store, planfile, transitions`)
git log --oneline -5:
    96e23df feat(core): implement store, planfile, transitions (ARCHITECTURE §13 steps 2-4)
    6ff102f test(runtime): pin DibsError, Context, Reply contract (ARCHITECTURE §13 step 1)
    6dd6af6 Scaffold dibs: lint-clean skeleton, test outline, tooling (SSoT Rev 8)
    2ed97f6 Init

## Rework order preamble

You are Claude Opus 5 executing a rework order for dibs at commit
96e23df. Read CLAUDE.md, docs/SSoT.md, docs/ARCHITECTURE.md;
SSoT wins. Rules: fix ONLY the findings below, smallest change that
satisfies the cited contract; §3 member budgets are ceilings; do NOT
add noqa or touch lint config; tests may be added or strengthened,
never weakened or deleted; one commit per finding ID; after each fix
run `make lint && make test` and confirm the finding's REPRO now
passes; if a finding seems wrong, STOP and report disagreement
instead of fixing around it. Finish by re-running the full suite and
reporting per-finding status.

(Tooling note for the executor: `make lint`/`make test` must run with the
repo venv on PATH — `export PATH=.venv/bin:$PATH` — the system python3 has
no pytest.)

## VERDICT: BLOCKED

Correctness core (CAS claim, hand limit, gating, ownership, TTL, event-per-row)
is sound under adversarial probing, but the step is not "done" per §11: lint is
not silent at HEAD, and the parser rewrites non-grammar lines and can emit
multi-line annotations, both demonstrable I4 breaches.

## Findings

[F1] BLOCKER
WHERE: tests/test_property_planfile.py:48,69,136; tests/test_property_transitions.py:23,42
CONTRACT: ARCHITECTURE §11 "Definition of done per module: its tests green
**and** `flake8` clean"; CLAUDE.md "make lint … must be silent"; §10 sanctioned
suppression set is exactly `dibs/__init__.py: WPS412` + the `tests/*.py` line
(`S101, D` in pyproject).
EVIDENCE: `export PATH=.venv/bin:$PATH; make lint` → `ruff check dibs tests`
prints `S311 Standard pseudo-random generators are not suitable for
cryptographic purposes` five times, `Found 5 errors.`, `make: *** [lint]
Error 1` (ruff 0.16.5; the ~/.local/bin ruff agrees). The skeleton at 6ff102f
had no `random.Random` call (only the docstring "Use seeded stdlib random");
the calls are implementer-added.
REPRO: `export PATH=.venv/bin:$PATH && make lint` (must print nothing beyond
the two command echoes and exit 0).
FIX DIRECTIVE: Seeded `random.Random` IS the documented test design (skeleton
docstring, §11 "seeded stdlib random"), so §10's delete→simplify→move ladder
has no honest rung; the sanctioned outcome per §10 is a targeted suppression
with a maintainer flag. Reviewing-architect sanction, overriding the preamble's
no-lint-config rule for this finding only: in pyproject.toml line 63 change
`"tests/*" = ["S101", "D"]` to `"tests/*" = ["S101", "D", "S311"]` with a
one-line comment ("S311: property tier uses seeded stdlib PRNG for
determinism — ARCHITECTURE §11"), and mirror the comment in setup.cfg's
per-file-ignores rationale block. Flag in the commit message that
ARCHITECTURE §10's sanctioned-set snippet needs the architect's one-line
amendment (architect edits docs). No source change, no budget impact.

[F2] BLOCKER
WHERE: dibs/planfile.py:26 (`- \[(?P<state>[^\]]*)\] ?`)
CONTRACT: SSoT §8 "a task is any line matching `- [ ]` / `- [x]` / `- [~ …]`";
I4 "Tool writes to plan.md modify only lines matching its own annotation
grammar (§8); all other content is untouched"; D5 "every other byte is
preserved verbatim".
EVIDENCE: probe_parse.py — `parse_plan('- [-] cancelled\n')` → a task with
checkbox `'-'`; `annotate_lines` on a todo row rewrites it to
`'- [ ] cancelled\n'`. Same for `- [] empty` → `- [ ] empty`, `- [wip] custom`
→ `- [ ] custom`, `- [~] t`, `- [ x ] t`; `- [ ]no space` → `- [ ] no space`,
`- [ ]\ttab` → `- [ ] \ttab`, bare `- [ ]` → `- [ ] ` (byte added).
Independent 600-seed fuzz with a strict grammar regex: 1099 non-grammar line
rewrites, all of these shapes; zero once the shapes are excluded. `- [-]` is a
common "cancelled" marker in Obsidian/Markdown tooling.
REPRO:
    .venv/bin/python -c "
    from dibs.planfile import parse_plan, annotate_lines
    from tests.boards import task_rows
    for t in ('- [-] cancelled\n','- [] empty\n','- [wip] custom\n','- [ ]no space\n'):
        f = parse_plan(t); assert not f, (t, f)
        assert annotate_lines(t, task_rows(f)) == t"
FIX DIRECTIVE: Restrict the state group to the three §8 tokens — a single
space, `x` (accepting `X` and lowercasing is fine), or `~` followed by the
name — and require the literal space separator after `]` (`\] ` not `\] ?`) so
`- [ ]no space`, `- [ ]\ttab` and bare `- [ ]` are not tasks. Add unit cases
to tests/test_planfile.py asserting each shape above is not recognized and
round-trips byte-identical through annotate_lines. Tighten
tests/test_property_planfile.py:21 `GRAMMAR_LINE` to the strict grammar
(`^[ \t]*- \[( |x|X|~[^\]]*)\] `) and add `- [-] cancel`, `- [] blank`,
`- [ ]nospace` to PROSE so the I4 fuzz covers them. No budget impact.

[F3] BLOCKER
WHERE: dibs/planfile.py:53 (done form) and :239 (`note=task.done_note`)
CONTRACT: SSoT §8 annotation grammar — done is the single line
`- [x] <title>  ✓ <name>: <done-note>`; I4 (only grammar lines change; a
newline inside the note creates a new non-grammar line the human never wrote).
EVIDENCE: probe_parse.py — rows with `done_note='first\nsecond'` on
`'- [ ] a\n- [ ] b\n'` → `annotate_lines` returns
`'- [x] a  ✓ happy-elephant: first\nsecond\n- [ ] b\n'`: line count 2 → 3, a
stray prose line `second` now sits in plan.md; `'first\r\nsecond'` embeds a
CRLF the same way. `--note` text reaches finish unmodified
(probe_bundle.py: `note stored: 'line1\nline2'`), so any agent passing a
multi-line note corrupts the plan.
REPRO:
    .venv/bin/python -c "
    import dataclasses
    from dibs.planfile import parse_plan, annotate_lines
    from dibs.records import Status
    from tests.boards import task_rows, ELEPHANT
    t='- [ ] a\n- [ ] b\n'; r=list(task_rows(parse_plan(t)))
    r[0]=dataclasses.replace(r[0],status=Status.DONE,owner=ELEPHANT.agent_id,done_note='first\nsecond')
    out=annotate_lines(t,tuple(r)); assert out.count('\n')==2, repr(out)"
FIX DIRECTIVE: In annotate_lines render the note whitespace-collapsed
(`' '.join(task.done_note.split())`, note-None path unchanged); the DB keeps
the verbatim note (D4 state truth), only the plan-line rendering is
single-line. Add a unit test (multi-line and CRLF notes render on one line)
and add a multi-line note to `mutate_rows` choices in
tests/test_property_planfile.py so the crown-jewel fuzz asserts line count.
No budget impact.

[F4] SHOULD-FIX
WHERE: dibs/planfile.py:27 (`(?:✓[^\r]*)?`)
CONTRACT: SSoT §8 grammar defines the suffix as exactly `  ✓ <name>: <done-note>`
(two spaces, check, name, colon); D4 "`plan.md` is authoritative for *text*:
task titles"; review brief "title_hash strips the done-annotation suffix" —
not any `✓`.
EVIDENCE: probe_parse.py — `'- [ ] verify ✓ marks render\n'` parses with
title `'verify'`; annotate_lines on the todo row rewrites the line to
`'- [ ] verify\n'`, deleting the author's ` ✓ marks render`. A later sync then
sees the truncated title as text truth.
REPRO:
    .venv/bin/python -c "
    from dibs.planfile import parse_plan, annotate_lines
    from tests.boards import task_rows
    t='- [ ] verify ✓ marks render\n'; f=parse_plan(t)
    assert f[0].title=='verify ✓ marks render', f[0].title
    assert annotate_lines(t, task_rows(f))==t"
FIX DIRECTIVE: Match only the grammar's own suffix — at least two spaces/tabs,
`✓ `, a name token without whitespace or colon, `:`, then the rest of the line
(e.g. `(?:[ \t]{2,}✓ [^\s:]+:[^\r]*)?`). Existing
test_hash_excludes_done_annotation must still pass; add the REPRO as a unit
case. Accepted residual ambiguity: a title that itself ends in a full
`  ✓ name: text` form. No budget impact.

[F5] SHOULD-FIX
WHERE: tests/test_property_planfile.py:244–266 (test_compute_sync_is_idempotent), assertion at :262
CONTRACT: ARCHITECTURE §11 property tier "`sync` is idempotent"; skeleton
docstring at 6ff102f: "applying a computed SyncPlan to the rows, then
recomputing against the same text, yields an empty SyncPlan"; review brief:
weakened assertions matching implementation behavior are findings.
EVIDENCE: `git diff 6ff102f HEAD -- tests/test_property_planfile.py` shows the
docstring line "against the same text, yields an empty SyncPlan." removed and
the assertion relaxed to `{**ALL_EMPTY, 'reparented': second.reparented}` —
ANY surviving reparent passes. probe_sync.py over 300 seeds: 17 seeds keep a
`reparented` after the first apply; all 17 are the documented new-parent
deferral (compute_sync docstring), so nothing is currently hidden — but the
assertion would also accept an unrelated reparent bug.
REPRO: read the assertion at tests/test_property_planfile.py:261–263.
FIX DIRECTIVE: Tighten, don't relax: for every `(task_id, parent)` in
`second.reparented` assert that the task's line in `settled` has a
`parent_line` that was one of `first.new`'s line numbers (the parent did not
exist when the first pass ran), and keep the third-pass all-empty assertion.
Restore a docstring sentence stating the exact deferred shape. Flag to the
architect: the two-pass application (insert `new`, recompute once) is now a
contract the step-8 sync verb must honor and belongs in ARCHITECTURE §5/§9.
No budget impact.

[F6] CONTRACT-POLISH
WHERE: dibs/planfile.py:175 (`new=tuple(head …)`) and the internal `pairs` map at :161–170
CONTRACT: SSoT §8 "new checkbox line → new task, next free ID in its section";
"children take dotted IDs (`A3.1`, creation order, stable per I5)"; C6 "Verbs
orchestrate only: … no SQL, no regex"; I5 IDs are never renumbered.
EVIDENCE: `SyncPlan.new` items carry only `parent_line`. To insert a new child
under an EXISTING parent the sync verb must know that parent's task id, which
only compute_sync's internal hash/duplicate pairing can resolve — the test
suite already had to reimplement that pairing test-side
(tests/test_property_planfile.py `pair()`, used by `apply_sync`). probe_parse.py
"sync new-parent": edited plan with a new child `newc` under existing `p` →
`new` reports `parent_line=3` and nothing identifies `p` as `A1`. A verb that
cannot mint `A1.1` at insert time either invents pairing logic (C6) or mints a
wrong id it can never fix (I5).
REPRO: `.venv/bin/python -c "from dibs.planfile import *; from tests.boards import task_rows; r=task_rows(parse_plan('- [ ] p\n- [ ] c\n')); print(compute_sync(parse_plan('- [ ] newp\n  - [ ] c\n- [ ] p\n  - [ ] newc\n'), r).new)"`
— note no parent task id anywhere in the output.
FIX DIRECTIVE: Architect decision required before code moves (ARCHITECTURE §5
pins SyncPlan's fields, not element shapes). Recommended: make each `new`
entry carry the resolved parent task id when the parent already exists
(e.g. `new: tuple[tuple[PlanItem, str | None], ...]`, None for top level and
for a parent that is itself new — the verb resolves those by line from the
ids it mints in document order). Opus: do NOT change the shape in this rework;
report this finding as "awaiting architect" and leave planfile's `new`
untouched. If adopted, `apply_sync` in the property test simplifies to consume
the carried id, and the F5 deferral remains. Budget: none (same six fields).

## NOTES (non-findings)

- Verified I1/C3: the claim is one `UPDATE … RETURNING` over two CTEs
  (available = todo AND NOT EXISTS open child; wanted = bundle or all), with
  the hand limit (`held + ?4 <= meta.max_hand`), all-or-none
  (`COUNT(wanted) >= ?4`), and D7 ordering (`section = last_section DESC, seq`)
  all inside the WHERE. `BEGIN IMMEDIATE` inside `with conn:` — Python legacy
  isolation (`isolation_level=''`), `in_transaction` True after the explicit
  BEGIN, no double BEGIN. Race probe: 60 rounds × 4 threads on separate
  connections behind a Barrier, and one 6-process multiprocessing run — every
  round exactly one winner, one doing row, one claim event. A second connection
  attempting `BEGIN IMMEDIATE` blocks 5.2 s then raises (busy_timeout works).
  A forced failure of the event INSERT after the UPDATE rolls the UPDATE back
  (I6 same-transaction holds).
- Verified D6: held=1/hand=3/bundle-of-2 claims both (no SQLite subquery
  re-evaluation partial-bundle hazard); bundle 5/hand 5 all-or-none with 5
  events; duplicate ids in a bundle deduped; unknown id in a bundle refuses
  whole; hand=2 third claim and bundle-of-1 refused; respawned identity sees
  its held task via the follow-up read. Non-numeric/missing `max_hand` →
  refusal (CAST → 0 / NULL).
- Verified D22: 3-deep tree — root and mid refused explicitly; no-arg order
  A1.1.1, A1.1.2, A1.1, A1.2, A1, A2; orphaned leaf does not gate; property
  gating invariant green. Consequence to record, not a defect: gating is
  direct-child only (as D22's "recursively, since each child is gated by its
  own children" describes); a grandchild injected by sync after the child was
  claimed (I9) lets the child finish and the parent become claimable while
  that grandchild is open — same family as §8's "[x] on a parent with open
  children" row.
- Verified D9: reap at exactly TTL does nothing, TTL+1 reaps every stale claim
  with one `reap` event each (agent `system`, text = prior owner), ordered by
  seq; lease refresh only for the caller and before the reap.
- I6 reading the code took: **one event per changed row** — a bundle claim of
  N writes N `claim` events, housekeeping writes one `reap` per reaped task;
  finish/release/import/note/join write exactly one. Consistent throughout.
  Bundle event insertion order follows RETURNING order, not seq; the returned
  tuple is seq-sorted.
- I2 verified: finish/release WHERE `owner = ?` — non-owner rowcount 0, no
  event.
- register_agent: join event rides the INSERT's transaction and rolls back
  with a UNIQUE collision; `last_event_seen` starts after the caller's own
  join. Uses the SQLite clock because §5 gives it no `now` — documented.
- Hazard for steps 5/8 (not a step-4 finding): the explicit `BEGIN IMMEDIATE`
  raises `cannot start a transaction within a transaction` if a caller left
  Python's implicit DML transaction open (probe_boom.py). `deliver_events`'
  cursor UPDATE and every verb-side write must commit (`with conn:`) before
  any transition runs. Alternative the architect may prefer:
  `sqlite3.connect(..., isolation_level='IMMEDIATE')` in store.connect makes
  Python's implicit BEGIN immediate and removes the seven explicit BEGIN
  lines.
- Doc gap for the architect: ARCHITECTURE §5 declares `finish`, `release`,
  `import_author_done` as `-> Task`; the implementation returns `Task | None`
  on zero rows. None is the only C5-compatible reading (transitions cannot
  build steer strings); amend §5 rather than the code.
- I4 fuzz: the committed 100-seed property passes; my independent 600-seed
  generator (tabs, fences, CRLF, no final newline, lone CR, trailing blank
  lines, `✓` in prose and notes) found only the F2 shapes. CRLF endings and
  final-newline state are preserved (raw split on `\n`, `ending` group carries
  `\r`). A line ending in `\r\r` loses one CR per pass — not a realistic
  input, noted only. CR-only (classic Mac) files parse as one line — out of
  contract.
- Mixed tab/space indentation counts a tab as one column (a 2-space child
  nests under a tab-indented child). No written rule; note for the author
  skill.
- `[x]` over doing and hand-written `[~ name]` over todo/done are silently
  DB-wins on annotation; §8's table has no row for them — not a finding.
- Fence policy: pinned in test_parse_fence_lookalike_policy (line rule wins
  inside fences, SSoT §8 unchanged) and reported in its docstring — decided.
  Bare `[x]` for a note-less done row pinned in
  test_annotate_todo_doing_done_forms — decided.
- Test diff vs skeleton: no case deleted, skipped, or tautological; every
  step-2/3/4 case asserts real behavior. Changes: `NOW` moved to new
  tests/boards.py (raw-SQL board seeding until init exists, documented);
  test_claim_prefers_last_section_then_seq now builds a purpose-built board
  via a new `make_board` fixture; two docstrings extended with pinned
  decisions; the F5 relaxation.
- Config/docs diff since 6ff102f: setup.cfg, pyproject.toml, docs/, Makefile,
  CLAUDE.md untouched; no `noqa` anywhere in dibs/ or tests/.
- Budgets by hand: store 4/4 (connect, ensure_schema, registry_record,
  registry_lookup); planfile 6/6 (PlanItem, SyncPlan, parse_plan,
  compute_sync, annotate_lines, title_hash — ROOT/TOP are constants);
  transitions 7/7; package files 15/15. Layering respected (planfile imports
  records only; transitions imports records only; store stdlib only).
- store: PRAGMAs verified on a fresh store.connect to an existing WAL file;
  Python's default connect timeout already implies busy_timeout 5000, the
  PRAGMA is explicit per D2; registry expanduser honours `$HOME`, records the
  resolved absolute path, lookup returns None for missing dir, stale file,
  directory-as-key; ensure_schema idempotent and does not reset meta.
- SQLite 3.53.3 here; `json_each` needs SQLite ≥ 3.38 or JSON1 — fine on
  every current platform, worth one line in ARCHITECTURE §1's Python floor.
- Suite state: `make test` → 58 passed, 33 failed, every failure a
  NotImplementedError from steps 5–9 (cli, names, output, queries, trace); the
  seven step-1–4 modules' suites: 56 passed.
