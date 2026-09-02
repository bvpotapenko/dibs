# dibs — guide for coding agents

Status: skeleton. Every signature, type, and constant exists; every
function body raises `NotImplementedError` naming its implementation
step; the pytest suite is red by design until modules land bottom-up.

## Read first (precedence order — higher wins)

1. `docs/SSoT.md` — WHAT. The current Rev governs; amend it before
   deviating from it.
2. `docs/ARCHITECTURE.md` — HOW. Budgets, layering, contracts C1–C10,
   WPS pre-satisfaction map, implementation order (§13).
3. `docs/GUIDE.md` — human-facing walkthrough (tone and UX reference).

## Hard rules (short form; the docs above are authoritative)

- Member budgets per module (ARCHITECTURE §3) are ceilings. Needing one
  more member means stop and flag, never exceed.
- Never fix a lint violation by adding a layer, class, or file. Order:
  delete → simplify inline → move to the owning module → targeted noqa
  with a one-line reason plus a maintainer flag (ARCHITECTURE §10).
- Branching lives in SQL WHERE clauses; Python reads rowcounts (C9, I1).
- `planfile.py` stays pure: no I/O, no DB, no clock (C4).
- User-facing strings only in `output.py` (C5); process edges only in
  `cli.py` (C1); SQL text only in store/transitions/queries (C2).
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
(ARCHITECTURE §11). Implementation order: ARCHITECTURE §13 — types
(done) → store → planfile → transitions → queries → names → output →
verbs → cli → zipapp.

## Skeleton conventions

- Each stub's `NotImplementedError` message names its ARCHITECTURE §13
  step, e.g. `'ARCHITECTURE §13 step 4: transitions.claim'`.
- Test stubs raise `NotImplementedError` describing what to assert.
  Make each real (red → green) while implementing its module; never
  delete a case to get green.
- SQLite WAL needs a real file: test DBs go on `tmp_path`, never
  `:memory:`.
