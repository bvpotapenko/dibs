# dibs

A small CLI coordination board for AI agents working the same task list in parallel.

## The problem

You have one `plan.md` full of tasks and several agent sessions to burn through it. If the agents coordinate through the file itself, they race: two sessions read the same version, both claim task N, both do the work. No file format fixes this — the race lives in the gap between reading and writing, not in write access. Dead sessions leave tasks marked "in progress" forever, there is no channel for "I changed something you may depend on", and an agent that can see the whole plan is one hallucination away from skipping coordination and doing everything solo.

Local agents with small context windows add one more problem: no worker can hold the whole plan plus its own work at once.

## What dibs does

dibs puts a SQLite board next to your plan — a file named after it, so `plan.md` gets `.plan.md.dibs` — and gives you an opaque board key to hand to workers instead of the file path. Agents never edit `plan.md` and never need to know where it lives; they call verbs whose state changes are single atomic SQL statements, so a task can be claimed exactly once no matter how many sessions try. Each worker holds a limited hand of tasks (one, by default) and must report before claiming more. The tool writes status back into your checkboxes, returns claims from dead sessions to the pool after a timeout, and appends a shared event feed to every command output. The board doubles as external memory: each worker's context holds one task briefing; the global picture lives in the database.

## Using it as the human

Write `plan.md` as you always would — tasks as checkbox lines, details indented beneath them. Write task bodies as complete briefings (paths, symptom, what done looks like): workers act on them without exploring. If you would rather have an agent write or decompose the plan, the `dibs-plan` skill does exactly that — `/dibs-plan` followed by the goal produces a plan that follows every rule on this page.

```
## Parser
- [ ] Fix date parsing in src/export.py
      Dates render US-style in exports; switch to ISO-8601.
      Done = tests in tests/test_export.py pass.
```

Then:

1. `dibs verify plan.md` — a dry run that shows the plan exactly as dibs will parse it (sections, task IDs, bodies, warnings for bodiless tasks). It creates and changes nothing; adjust the file until the preview matches your intent.
2. `dibs init plan.md` — creates the board and prints its key:

```
board created: dibs-7f3a-9c2e   (23 tasks: A1..A23)
hand to each session:   /dibs dibs-7f3a-9c2e
```

Add `--max-hand 3` if workers may hold up to three related tasks at once; the default hand is one.
3. Give each agent session the key. With the dibs skill installed, that is one message: `/dibs dibs-7f3a-9c2e`. No skill? Paste this instead:

```
You are one of several agents working board dibs-7f3a-9c2e in parallel.
Coordinate only through the dibs CLI; you never need the plan file itself.
Loop: dibs claim -> do the task -> dibs done <ID> --note "what changed" -> claim again.
Blocked: dibs drop <ID> --note "why".  Cross-cutting change: dibs note "...".
Stop when claim says no tasks remain.
```

4. If your launcher can set environment variables, bind board and identity up front so the model never handles either: `export DIBS_BOARD=dibs-7f3a-9c2e` and `export DIBS_AS=$(dibs join)`.
5. Watch checkboxes flip in your editor. Add or reorder tasks at any time — the board picks them up on the next command anyone runs.
6. Review at the end: `dibs list` plus the done-notes are the review checklist; `git diff` holds the actual work. (`list` also reprints the key if you lose it.)

Handing workers a key instead of a path is deliberate: it resolves identically from any directory, and it keeps the plan's location out of the agent's context — the path of least resistance becomes `dibs claim`, not "read the plan and do everything myself." It is a groove, not a wall: agents with shell access could find the file, but drift follows the easy path, and unclaimed work stays visible at review.

## Ordering work

Nest a checkbox under another to make it a prerequisite. The parent becomes claimable only when everything nested beneath it is done, so a test can wait on any number of units, and an integration step can wait on the pieces it integrates:

```
- [ ] Write tests for the export module in tests/test_export.py
      Cover ISO dates, quoting, and the empty-file case.
  - [ ] Implement parse_dates() in src/export.py
  - [ ] Implement format_row() in src/export.py
  - [ ] Implement write_csv() in src/export.py
    - [ ] Create the CsvWriter skeleton (class, __init__, method stubs)
```

This is the ordinary outline reading — the big deliverable on top, its parts beneath, the top line finishing last — and it works in either direction: under TDD, nest the implementation beneath its test. Gating is per branch, not per level: `write_csv` unlocks the moment its skeleton is done, whatever the neighbors are doing. Use headings or plain bullets for grouping that has no work of its own; a checkbox is always a task. `verify` and `list` show the tree and what each parent is waiting for; the plan file itself is never marked up with it.

The one shape nesting cannot express is a single shared prerequisite that many tasks wait on. Split it per consumer where that is honest (a skeleton per class rather than one "boilerplate" task), and put genuinely shared setup first in the file — order is priority, though a nudge rather than a gate.

## Several plans in parallel

Boards are per-plan, not per-directory, so unrelated swarms can run side by side — one crew on a codebase, another on errands or research — without ever seeing each other's tasks, names, or notes:

```
~/family/errands.md   ->  ~/family/.errands.md.dibs   ->  dibs-7f3a-9c2e
~/family/trip.md      ->  ~/family/.trip.md.dibs      ->  dibs-b41d-0e77
```

A plan does not have to be about code:

```
- [ ] Order groceries for the week
      Budget 8000 JPY, prefer the usual store, delivery tomorrow evening.
```

Each session binds to its own board — by the `/dibs <key>` argument, by `export DIBS_BOARD=<key>` in its launcher, or by `--plan <key>` on every call (paths work in all three places too, for authors). Unbound sessions resolve the board by searching upward from the current directory; if several boards match, dibs refuses and lists them with exact commands instead of guessing. Identities belong to one board, so an id used against the wrong board fails loudly instead of claiming the wrong work.

## Using it as the agent

The whole loop is claim, work, report, repeat. With `DIBS_BOARD` and `DIBS_AS` set by the launcher:

```
$ dibs claim
you are happy-elephant
claimed A2: Fix date parsing in src/export.py
  Dates render US-style in exports; switch to ISO-8601.
  Done = tests in tests/test_export.py pass.
-- while you were away --
done A1 by brave-otter: "regex was greedy, anchored it"

$ dibs done A2 --note "strftime replaced with isoformat"
```

Without the environment set, the first `claim` prints your id, and every later call takes `--as <your-id>`. Your hand is limited: `claim` refuses while it is full and names what you hold — finish or drop before claiming more. Blocked? `dibs drop A2 --note "why"` and claim something else. Changed something others may depend on? `dibs note "renamed util.load to util.read_cfg"`. If `claim` says nothing is available *yet*, the remaining tasks are waiting on work others hold — that is waiting, not finished: retry after a bit, or stop and report idle. When your `done` unlocks a parent task, the output says so; claim it, since you have the freshest context for it. When `claim` says no tasks remain, stop. Every response — including every error — ends with the exact next command, so a session that lost its context can recover from tool output alone.

## Verbs

| Verb | Purpose |
|---|---|
| `verify plan.md` | Dry run: show the plan as dibs parses it; touches nothing |
| `init plan.md [--max-hand N]` | Parse the plan once, create its board, print the board key |
| `sync` | Reconcile plan and board after human edits (also runs automatically) |
| `join` | Mint an identity; for launcher scripts |
| `claim [--task ID ...]` | Atomically take the next task, or a specific bundle that fits your hand |
| `done ID --note "..."` | Report completion; note is mandatory |
| `drop ID [--note "..."]` | Give a task back |
| `note "..." [--for name]` | Broadcast (or direct) a message to other agents |
| `list` | Board overview, recent events, and the board key, for humans |

Every verb accepts `--plan <key or file>` to target a specific board when several exist.

## Guarantees and limits

A task is held by at most one agent, a hand holds at most `max-hand` tasks (default one), and contested claims are decided by the database, not by politeness. A dead session's claim returns to the pool after a timeout (default 45 minutes); a crashed or confused agent can cause delay, never corruption. Names like `happy-elephant` are per-board display identities and board keys are drift prevention, not security — everything runs as your OS user, on one machine. And dibs coordinates work; it does not make agents more capable. Review stays with you.

## More

`SSoT.md` holds the decisions and invariants and is authoritative; `ARCHITECTURE.md` is the implementation reference; `skills/dibs/SKILL.md` is the protocol workers load, and `skills/dibs-plan/SKILL.md` the one plan authors load.

Status: implementation in progress — the interface above is fixed (SSoT Rev 9); `ARCHITECTURE.md` §13 tracks what has landed.
