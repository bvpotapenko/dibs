# dibs — guide for coding agents

Status: ARCHITECTURE §13 steps 1-4 landed (runtime, records, store,
planfile, transitions); step 5 brings them to the Rev 9 contracts, then
steps 6-12 land new modules bottom-up. Unlanded members exist as stubs
raising `NotImplementedError` naming their step; their tests are red by
design, and the red count may only shrink.

## Read first (precedence order — higher wins)

1. `docs/SSoT.md` — WHAT. The current Rev governs; amend it before
   deviating from it.
2. `docs/ARCHITECTURE.md` — HOW. Budgets, layering, contracts C1–C11,
   WPS pre-satisfaction map, implementation order (§13).
3. `docs/GUIDE.md` — human-facing walkthrough (tone and UX reference).

## Hard rules (short form; the docs above are authoritative)

- Member budgets per module (ARCHITECTURE §3) are ceilings; 7 is the WPS
  cap. `planfile` and `queries` sit at 7 with a named split seam; an
  8th member anywhere means stop and flag, never exceed.
- Text enters the board only through `plansync.apply_sync` (D24, C11):
  init is sync on an empty board; verify is the same diff against no
  rows. Never insert task rows or mint task ids anywhere else.
- Never fix a lint violation by adding a layer, class, or file. Order:
  delete → simplify inline → move to the owning module → targeted noqa
  with a one-line reason plus a maintainer flag (ARCHITECTURE §10).
- Branching lives in SQL WHERE clauses; Python reads rowcounts (C9, I1).
- `planfile.py` stays pure: no I/O, no DB, no clock (C4).
- User-facing strings only in `output.py` (envelope, every error) and
  `views.py` (bodies) (C5); process edges only in `cli.py` (C1); SQL
  text only in store/transitions/plansync/queries (C2).
- One error type, one factory: `raise output.steer(Refusal.X, names)`;
  every steer is a runnable command (C7, I10). Zero-row writes return
  `None`/`()`; the verb raises — never the transition.
- One clock: `Context.now` flows into every write, join events included;
  never `strftime('now')` in SQL. SQLite floor 3.35 + JSON (§1).
- Zero runtime dependencies. Dev tools: flake8 + wemake-python-styleguide,
  ruff, pytest — nothing else.

## Dev loop

    make install   # once per venv: pip install -e '.[dev]'
    make lint      # flake8 (WPS only) + ruff — must be silent
    make test      # pytest -q — red until §13 steps land
    make build     # stage + zipapp → dist/dibs.pyz

Definition of done per module: its tests green AND lint silent
(ARCHITECTURE §11). Implementation order: ARCHITECTURE §13 — steps 1-4
done → 5 Rev 9 amendments → 6 queries → 7 plansync → 8 names →
9 output + views → 10 verbs → 11 cli/trace → 12 zipapp.

## Skeleton conventions

- Each stub's `NotImplementedError` message names its ARCHITECTURE §13
  step, e.g. `'ARCHITECTURE §13 step 4: transitions.claim'`.
- Test stubs raise `NotImplementedError` describing what to assert.
  Make each real (red → green) while implementing its module; never
  delete a case to get green.
- SQLite WAL needs a real file: test DBs go on `tmp_path`, never
  `:memory:`.
- Test boards are seeded through production code: `compute_sync(items,
  ()).rows` until `plansync` lands, `apply_sync` after (ARCHITECTURE
  §11). Raw SQL in tests is for assertion peeks only.
