---
name: dibs-plan
description: Write, decompose, or restructure a task plan (plan.md) that the dibs coordination board can parse and that small-context agents can execute in parallel - checkbox tasks written as complete briefings, prerequisites expressed by nesting, sections by code area, checked with dibs verify before init. Use this skill whenever the user asks for a plan for dibs, a dibs-readable or dibs-friendly plan, to split or decompose work for parallel agents or a swarm, to turn a spec, issue, code review, or todo list into plan.md, to prepare corrections for several agents, or to fix a plan that dibs verify flagged - even if the word dibs is not used. Also use it when invoked as "/dibs-plan" followed by a goal. Not for working a board; that is the dibs skill.
---

# dibs-plan — writing plans that dibs can read and agents can execute

You are the plan author: the one privileged writer of the plan file. Workers never see the file; they receive one task at a time through `dibs claim`. So every task you write must stand alone for a worker with a small context window and no ability to explore.

## What dibs reads — the whole grammar

- `- [ ] title` — a task. Nothing else is a task.
- Indented lines under a task that are not checkboxes — its body, the briefing.
- An indented checkbox under a task — a prerequisite of it (see Ordering).
- `## Heading` — a section. dibs letters sections A, B, C in order and numbers tasks A1, A2, ... at init.
- `- [x] title` — imported as already done.
- Everything else — your prose; ignored and preserved.

There is no other notation. Do not invent tags, IDs, priorities, owners, or metadata in the file: IDs are assigned at init, priority is document order, ownership belongs to the board.

## Write every task as a briefing

Title: one imperative line that names the target — `Fix date parsing in src/export.py`, not `Date bug`.
Body: where (exact paths), what is wrong or what exists now, what done looks like (a test to pass, an observable behavior), and any constraint (do not touch X, keep the public signature).
The test: could a worker who cannot open any file except the ones you name, holding 8k of context, finish this? If not, the body is incomplete.

Weak:

```
- [ ] Fix the export bug
```

Strong:

```
- [ ] Fix date parsing in src/export.py
      parse_dates() returns US-style strings; exports must be ISO-8601.
      Done = tests/test_export.py::test_iso_dates passes. Keep the CSV column order.
```

## Size for one hand

One task is one sitting of work in one place. If the title needs "and", split it. If two tasks would edit the same file, make them one task — file collisions between parallel workers are the failure the board cannot prevent for you. Prefer many small tasks over a few broad ones; the board handles the count, workers handle the size.

## Order with nesting

Nest a prerequisite under the task that needs it. A parent becomes claimable only when everything nested beneath it is done, so a test waits on all its units and an integration step waits on its pieces:

```
- [ ] Write tests for the export module in tests/test_export.py
      Cover ISO dates, quoting, and the empty-file case.
  - [ ] Implement parse_dates() in src/export.py
        Input: raw cell strings. Output: ISO-8601 or None. Done = unit cases in the docstring hold.
  - [ ] Implement format_row() in src/export.py
        Quote fields containing commas or newlines; done = round-trips through csv.reader.
    - [ ] Create the CsvWriter skeleton in src/export.py (class, __init__, method stubs)
          Stubs raise NotImplementedError; done = module imports cleanly.
```

- Gating is per branch: `format_row` unlocks the moment its skeleton is done, whatever its siblings are doing.
- Under TDD, nest the implementation beneath its test.
- A checkbox is always real work. For grouping with no work of its own use a heading or a plain bullet — a checkbox umbrella is claimed last and does nothing.
- One shared prerequisite for many tasks cannot be nested. Split it per consumer where that is honest (a skeleton per class, not one "boilerplate" task); otherwise put it first in the file — order is priority, though a nudge, not a gate.

## Sections are areas, not phases

Workers stick to the section they are in. Group tasks by code area — module, package, feature — so a worker keeps warm context and no two workers land in the same file. Do not create sections like "Tests" or "Refactoring" that span every module; they invite collisions and cold context. Tests live in the section of the code they test, nested under it.

## Priority

Document order is claim order. Urgent or unblocking work goes first; within a section, earlier lines are claimed first. Reorder freely at any time.

## Handing off

1. `dibs verify plan.md` — read the plan as dibs does: every intended task present, the tree and waits-for column correct, no warnings (bodiless tasks, duplicate titles). Fix and re-run until the preview matches your intent; it changes nothing.
2. `dibs init plan.md` — add `--max-hand N` only if workers should hold several related tasks at once; the default is one.
3. Hand workers the printed board key (`/dibs dibs-xxxx-xxxx`), never the file path.
4. Keep editing while they work: add, reorder, and re-indent freely — sync is automatic. Reword bodies, not titles: a changed title is a new task and the old one is orphaned. Check a box by hand only to mean "already done".

## Anti-patterns

- "Do everything" umbrellas written as checkboxes.
- Titles without a target file or object.
- Bodies that require exploration to understand.
- Two claimable tasks, one file.
- Phase sections spanning all modules.
- Invented IDs, tags, or assignees in the file.

## Checklist before init

- Every task: a title with a target; a body with paths, symptom or current state, done-criterion.
- No two claimable tasks edit the same file.
- Prerequisites nested under what needs them; umbrellas are headings.
- Sections follow code areas; urgent work first.
- `dibs verify` shows no warnings and the tree you intended.
