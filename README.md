```
       ___ __
  ____/ (_) /_  _____
 / __  / / __ \/ ___/
/ /_/ / / /_/ (__  )
\__,_/_/_.___/____/      [ ]  ->  [~ happy-elephant]  ->  [✓]
```

Call dibs on tasks. A tiny CLI board so several AI agents can work one `plan.md` in parallel without doing the same task twice.

Agents coordinating through a shared text file race: two sessions read the same version and both take task N. dibs keeps state in a SQLite board next to the plan; a claim is one atomic SQL statement, so each task goes to exactly one agent. Dead sessions' claims return to the pool, and every command ends with what the others did.

## Author

```
- [ ] Write tests for the export module in tests/test_export.py
      Cover ISO dates, quoting, the empty-file case.
  - [ ] Implement parse_dates() in src/export.py
        Returns ISO-8601 or None. Done = docstring cases hold.
```

Checkbox = task. Indented text = the briefing a worker gets. Nested checkbox = prerequisite: the parent unlocks when everything beneath it is done. Then:

```
dibs verify plan.md     # preview the parse; touches nothing
dibs init plan.md       # creates the board, prints a key: dibs-7f3a-9c2e
```

Hand workers the key, never the path. Edit the plan any time; sync is automatic.

## Worker

Start each session with `/dibs dibs-7f3a-9c2e` (no skill installed? "Work dibs-7f3a-9c2e with dibs, alongside others."). The loop:

```
dibs claim                            # one task briefing, plus what others did
dibs done A2 --note "what changed"    # note is mandatory
dibs claim                            # ... until it says no tasks remain
```

`dibs drop A2 --note "why"` when blocked; `dibs note "..."` for changes others depend on. A worker holds one task at a time (`init --max-hand N` allows more).

## Skills

- **`dibs`** — the worker protocol: bind to the board, run the loop, what to do when things go wrong.
- **`dibs-plan`** — the author protocol: `/dibs-plan` followed by a goal writes a plan that follows every rule above.

## Notes

Boards are per plan (`.plan.md.dibs` beside it), so unrelated swarms run side by side. Keys and agent names are grooves against drift, not security; a confused agent can cause delay, never corruption. Decisions and invariants: `SSoT.md`. Implementation reference: `ARCHITECTURE.md`. Longer walkthrough: `GUIDE.md`.

Status: implementation in progress — interface fixed (SSoT Rev 9); `docs/ARCHITECTURE.md` §13 tracks what has landed.
