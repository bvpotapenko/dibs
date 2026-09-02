# dibs — guide for coding agents

Status: ARCHITECTURE §13 steps 1–8 implemented (store, planfile,
transitions, queries, names, output, plansync, views, verbs); step 9
(cli, `__main__`, trace) is next, then the zipapp smoke test. Remaining
stubs raise `NotImplementedError` naming their step; their tests are
red by design (16 cases in test_cli and test_trace).

## Read first (precedence order — higher wins)

1. `docs/SSoT.md` — WHAT. The current Rev governs; amend it before
   deviating from it.
2. `docs/ARCHITECTURE.md` — HOW. Budgets, layering, contracts C1–C10,
   WPS pre-satisfaction map, implementation order (§13). Its revision
   note and §13 step 8a list the small amendments to landed modules
   that step 8 applies first.
3. `docs/GUIDE.md` — human-facing walkthrough (tone and UX reference).

## Hard rules (short form; the docs above are authoritative)

- Member budgets per module (ARCHITECTURE §3) are ceilings, all ≤ 6.
  Needing one more member means stop and flag, never exceed. The file
  budget is 17 (SSoT §2) and the package is at it: a new module is a
  re-scope flag, not a file.
- Never fix a lint violation by adding a layer, class, or file. Order:
  delete → simplify inline → move to the owning module → targeted noqa
  with a one-line reason plus a maintainer flag (ARCHITECTURE §10).
- Branching lives in SQL WHERE clauses; Python reads rowcounts (C9, I1).
  Sync is one transaction whose first statement is the mtime CAS.
- `planfile.py` stays pure: no I/O, no DB, no clock (C4). The only
  writer of plan.md is `verbs/board.annotate_plan`.
- User-facing text only in `output.py` (templates) and `views.py`
  (per-verb composition) (C5); verbs fill no templates (C6); process
  edges only in `cli.py` (C1); SQL text only in
  store/transitions/plansync/queries (C2).
- One error type: `DibsError(message, steer)`; every steer is a runnable
  command (C7, I10).
- Zero runtime dependencies. Dev tools: flake8 + wemake-python-styleguide,
  ruff, pytest — nothing else.

## Dev loop

    make install   # once per venv: pip install -e '.[dev]'
    make lint      # flake8 (WPS only) + ruff — must be silent
    make test      # pytest -q — red until §13 steps land
    make build     # stage + zipapp → dist/dibs.pyz

Definition of done per module: its tests green AND lint silent
(ARCHITECTURE §11). Implementation order: ARCHITECTURE §13 — types →
store → planfile → transitions → queries → names → output → 8a
amendments → plansync + views → verbs (all done) → cli → zipapp.

Step 9 inherits two contracts step 8 fixed: `args.task` is a *sequence*
of raw ids for claim/done/drop (done and drop read the first), and the
pipeline's step-5 sync Reply is what the `sync` verb returns — calling
`board.sync_board` twice would report "nothing changed" (the mtime CAS
is honest).

## Skeleton conventions

- Each stub's `NotImplementedError` message names its ARCHITECTURE §13
  step, e.g. `'ARCHITECTURE §13 step 8: init_board'`.
- Test stubs raise `NotImplementedError` describing what to assert.
  Make each real (red → green) while implementing its module; never
  delete a case to get green — a case whose contract changed in step 8a
  is rewritten to the new contract, not dropped.
- SQLite WAL needs a real file: test DBs go on `tmp_path`, never
  `:memory:`.
