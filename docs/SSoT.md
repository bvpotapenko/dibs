# dibs — Single Source of Truth

**Status:** implementation in progress — `ARCHITECTURE.md` §13 tracks which steps have landed.
**Rev:** 10 — (r10) oversized-bundle refusal: D6, §6 amended — a bundle larger than the hand can never fit, so `claim` refuses it as such and steers to its first member; *hand full* is reserved for a bundle that would fit an empty hand. (r9) one import path + budgets met by measurement: D24 new; §2 budget restated; §5 SQLite floor + `plan_mtime`; §8 sync is one transaction, ids minted in one pass, cached text refreshed; I5 clarified; §13 id lettering settled. (r8) invocation tracing for debugging: D23 new; §6 env note; §12 + deferred `log --jsonl`. Earlier: (r2) small-context workers: D16–D17; D5, D7, D8, D14, I10. (r3) implementation architecture: D3, §2 budget; `ARCHITECTURE.md`. (r4) parallel plans + skill invocation: D2, D8, D13; D18–D19. (r5) board keys, hand limit, verify: D6, D18–D19 amended; D20–D21 new; §2, §5–§6, §8, §10–§13 touched. (r6) leaves-first prerequisites: D22 new; D6–D7 amended; §5–§6, §8, §10–§13 touched. (r7) author skill `dibs-plan`: D1, D13 amended; §2 budget; §10 split into two skill specs. 
**Precedence:** this file supersedes conversation history, README prose, and code comments. When anything disagrees with this file, this file wins until amended here.

---

## 1. Problem

N parallel agent sessions work one shared correction list (`plan.md`). Coordination through the text file fails structurally: between agent A reading the file and writing "I take task N," agent B acts on the same stale read and also takes task N. File locking cannot fix this — the race lives in the read-think-write gap (TOCTOU), not in write access. Secondary failures: agents reformat the file while editing it, dead sessions leave tasks marked "in progress" forever, and there is no channel for "I changed something you may depend on." A second, independent pressure: local coding agents with small context windows cannot hold the whole plan plus their own work — the plan must be split so each worker carries exactly one task briefing, while the global picture lives somewhere durable.

## 2. Solution in one paragraph

A tiny CLI, **`dibs`**, backed by SQLite sitting next to the plan. Agents never write `plan.md`; they call verbs (`claim`, `done`, `drop`, `note`) whose state transitions are single atomic SQL statements. The DB owns *state*; the human owns the *text*; the tool annotates checkbox lines in place and carries all coordination in one append-only events table, delivered piggyback on every command. Agent behavior lives in two skills: **`dibs`** for working a board and **`dibs-plan`** for writing one. The launch instruction shrinks to:

> **`/dibs dibs-7f3a-9c2e`** — the board key `init` prints (a plan path also works) — or, where slash commands don't exist: **"Work `dibs-7f3a-9c2e` with dibs, alongside others."**

For small-context local workers (a first-class target, D16) the board doubles as **external memory**: the global picture lives in the DB, each worker's context holds one briefing plus its own work, and a single agent in a claim → work → done → die → respawn loop is served as well as N parallel ones.

**Budget:** a stdlib-only package shipped as a single file `dibs.pyz`; two skill files (`dibs`, `dibs-plan`); one board file per plan. Size is measured in *code lines* (non-blank, non-comment, non-docstring): target ~1000, hard stop and re-scope at 1500, across ≤18 small files. Physical lines run about 2× code lines by construction — every member carries a docstring and every SQL statement a placeholder legend (D3) — so they are not the budget. Measured at Rev 9 with four of ten modules landed: 679 code / 1222 physical lines in 15 files.
**Not building (v1):** daemon, heartbeats, point-to-point mail, dependency graph, auth, config file, multi-machine support. See §12 for revisit triggers.

---

## 3. Decisions

- **D1 — Name.** `dibs`, for the tool and the worker skill; the author skill is `dibs-plan`. One brand: the word appearing in any prompt, board key, or skill name triggers the right manual.
- **D2 — Backend.** SQLite in WAL mode, `busy_timeout=5000`. The board file derives from the plan file: `<dir>/errands.md` → `<dir>/.errands.md.dibs`, so N plans in one directory get N fully isolated boards — identities, events, reaping, and history are all per-board and can run in parallel. Gitignore `.*.dibs*` (WAL creates siblings). Scope: one machine (SQLite over network filesystems is out).
- **D3 — Implementation shape.** Source: a small package of flat, single-purpose modules, pre-shaped to pass strict WPS/flake8 (module-member, argument, and complexity caps) — see `ARCHITECTURE.md`. Deployment: still one file on PATH — `dibs.pyz` built with stdlib `zipapp` (`pipx` as alternative). Zero *runtime* dependencies; flake8+WPS and pytest are dev-only. No config file; tunables are constants at the top of their owning module.
- **D4 — Split truth.** The DB is authoritative for *state*: status, ownership, timestamps, notes, events. `plan.md` is authoritative for *text*: task titles, descriptions, prose, and ordering. Text flows md→db on sync; status flows db→md via annotation.
- **D5 — Writers of plan.md.** The plan author (authoring) and the tool (annotating) only; workers never. "Plan author" is one privileged role — a person, or a single big-model planner session decomposing work for small workers; either way I3 is unchanged. The tool rewrites only checkbox lines it recognizes; every other byte is preserved verbatim.
- **D6 — Claiming is compare-and-swap.** `UPDATE … WHERE id=:task AND status='todo'`; you won iff `changes()==1`. No check-then-act anywhere. Default `claim` takes the next available task ("take a ticket"); `claim --task A3 A4` claims an explicit bundle atomically — all listed tasks or none. **Hand limit:** an agent holds at most `max_hand` active claims (per-board setting: `init --max-hand N`, default 1); the cap is enforced *inside* the claim statement's WHERE via a holdings subquery, and a bundle must fit in the hand — refused whole, never trimmed. A bundle larger than the hand itself can never fit, whatever is held, so that refusal says so ("a bundle of 3 exceeds the hand of 1") and offers the first member alone; *hand full* is reserved for a bundle that would fit an empty hand. On refusal the steer distinguishes *hand full* ("you hold A2 — finish or drop it first") from *board empty*; a follow-up read may compose that message, but correctness rests on the single statement alone (I1). Side benefit: a respawned worker carrying the same env identity is pointed back at its own open task instead of grabbing new work. **Availability** also requires that a task has no open nested children (D22), so `claim` distinguishes three refusals with distinct steers: *hand full*; *nothing available yet* ("4 tasks wait on A3 (doing, brave-otter) — retry after finishing something else, or stop if your launcher respawns workers"), which is waiting, not completion; and *board empty* ("no tasks remain; stop"). An explicit `--task` on a gated parent is refused with its open children named.
- **D7 — Priority = section affinity, then document order — among available tasks (D22).** `claim` first prefers the next available `todo` in the caller's last-claimed section — a worker that just fixed parser code has parser context warm, so feeding it the next parser task amortizes exploration, and one-agent-per-area emerges naturally (reinforcing D12) — then falls back to current file order. The human reprioritizes by reordering lines in `plan.md` (sync updates queue order without touching IDs); explicit `--task` overrides everything. When a `done` unlocks a parent, the `done` output says so with a ready claim command — the finishing worker has the freshest context for it, so affinity happens through D14's hint rather than ordering logic.
- **D8 — Identity.** Per-session generated `adjective-animal` name plus id `name-NNNN`. IDs are for command input; names are for display. This is confusion resistance (an agent can't hallucinate an id it never saw), **not security** — all sessions share one OS user and could open the DB directly. Preferred flow: the *launcher* mints identity — `export DIBS_AS=$(dibs join)` before starting the session — so small models never handle identity at all, and the env var survives context compaction; `claim`-time minting remains as fallback. A *supplied* identity unknown to the resolved board is an addressing error — fail with a steer (it almost always means the wrong board, D18) rather than silently minting; auto-mint happens only when no identity was supplied at all.
- **D9 — Liveness by passive reaping.** No heartbeats. Claims carry `claimed_at`; any read command reverts claims older than the TTL to `todo` and logs an event. Any command from an agent refreshes `claimed_at` on that agent's active claims (activity extends the lease). `drop` releases voluntarily.
- **D10 — One events table.** Journal and bulletin are the same append-only table. `note` broadcasts; `note --for <name>` sets a nullable `to` column — a filter, not a mailbox. Delivery is piggyback: every command's output ends with events the calling agent hasn't seen.
- **D11 — `done` is an assertion, not a fact.** Requires ownership (`WHERE owner=:me`) and requires `--note` describing what changed. Verification stays with the human: `dibs list` + done-notes + `git diff`.
- **D12 — File-level collisions: prevention over negotiation.** Task locks don't lock files. Rungs: (1) partition in the plan — same-file corrections become one task or one bundle; (2) claims are broadcast as events, so future claimers see what's being touched; (3) advisory `--touch` overlap warnings and per-session git worktrees are deferred (§12).
- **D13 — Mechanism/protocol split.** Script = mechanism (atomicity, identity, reaping, rendering), global. Skills = protocol, global, two of them: **`dibs`** (worker loop, etiquette, failure playbook) and **`dibs-plan`** (decomposing work into dibs-readable plans: grammar, briefings, nesting, sections, the verify→init→key handoff). Separate skills because the audiences and moments differ — executing a task versus composing the work — and a small worker must not carry authoring text in its context (D16); the worker skill holds only a one-line pointer to `dibs-plan`. Project-local artifacts: each `plan.md` and its `.<plan>.dibs` board only.
- **D14 — Teach in the skill, remind in the output.** All tool output — stdout *and* stderr — is prompt surface. Every response ends with the next expected verb, exact syntax included. Every **error steers rather than diagnoses**: it contains the literal next command ("Unknown task B7 — did you mean A7? Run: `dibs claim --task A7`"), with fuzzy ID matching and tolerant argument forms (`--task A3`, `--task=A3`, positional `dibs claim A3`). Output is terse by contract, not preference — events one line each, no banners; in an 8k window every dibs token competes with code. `claim` is the only rich response, because the task body is the briefing. A context-wiped agent can limp through the loop on tool output alone.
- **D15 — Scale path.** Dozens of local agents are comfortably in range. Multi-machine means swapping the backend behind the same CLI (e.g., Postgres) — explicitly out of scope for v1.
- **D16 — Small-context workers are a first-class workload.** The board is external memory: no worker ever holds the global picture, and the stateless loop — claim → work → done → die → respawn — is as supported as parallel operation. Honest scope limit: dibs coordinates, it does not add competence; under weak models its job is to make failure *visible and cheap* (drop-notes, reap events, done-notes as the review queue). The accepted cost of this architecture is review burden on the plan author.
- **D17 — Tasks are briefings.** A small-context worker cannot afford exploration, so each task body must be complete enough to act on alone: file paths, what wrong looks like, what done looks like. Writing such bodies is the plan author's core responsibility (D5) and is taught by the skill (§10).
- **D18 — Board resolution.** The board is found in this order: `--plan` flag → `$DIBS_BOARD` env → upward directory walk from CWD collecting `.*.dibs` files. Flag and env accept a **board key or a plan path**: keys resolve through the registry first (D20), then the value is tried as a path. Exactly one found → use it. Several found → **refuse and enumerate**, each option with a runnable steer ("Run: `dibs claim --plan errands.md`") — guessing is forbidden, because the failure mode of a guess is a cross-plan claim (a food-ordering agent taking a refactoring task). None found → the error steers workers to `cd` or `--plan`; `init` is mentioned only as an aside for plan authors, so a lost worker is never invited to create an empty board in the wrong place.
- **D19 — Skill invocation.** `/dibs <board>` invokes the skill with a board key or plan path as argument; the argument *is* the board selector, and the skill's first instruction is to bind it (`export DIBS_BOARD=<it>`, or `--plan` on every call). The skill also triggers on natural mention of dibs or plan-working (D1). Where slash commands don't exist, the universal fallback remains the one-line launch instruction (§2).
- **D20 — Opaque board keys.** `init` mints a key like `dibs-7f3a-9c2e` (random hex; the `dibs-` prefix makes every handoff line its own skill trigger), stores it in the board's `meta` table (truth), and records key → absolute plan path in a write-once registry under `~/.local/state/dibs/` (a cache that self-heals on any path-addressed command). **Workers are handed keys; authors use paths** — the same role split as D5. A key resolves identically from any CWD (killing the relative-path wrong-board footgun) and keeps the plan's location out of worker context: a *groove against drift*, not access control (same honesty as D8 — shell access can find anything; the defense is that the lowest-energy action is `dibs claim`, and unclaimed rogue work stays visible at review per D16). Lost key → `dibs list --plan <path>` reprints it.
- **D21 — Verify before trust.** `dibs verify <plan>` renders how dibs would parse the plan — sections, would-be IDs, titles, body presence, hand-written `[x]`, plus warnings (bodiless tasks, duplicate titles) — while creating and touching **nothing**: no board, no events, no identity required. Parse behavior is inspectable before `init` and is never a surprise. If a board already exists, verify says so in one line and points to `list`.
- **D22 — Leaves-first prerequisites.** A checkbox nested under a checkbox is a *prerequisite* of it: the parent becomes claimable only when every checkbox nested beneath it is done (recursively, since each child is gated by its own children). This is the ordinary outline reading — big deliverable on top, its parts beneath, top line finishes last — so there is nothing new to teach authors. Fan-in is native: one test waits on 3–10 units. Gating is per-parent, not per-level: a parent unlocks the moment *its* children finish, regardless of siblings elsewhere. Orphaned children (lines deleted from the plan) do not block — they left the plan. Pure grouping with no work of its own is a heading or a plain bullet, never a checkbox; a checkbox umbrella is merely claimed last — harmless, but noisy. Gating is *derived* state: never written into the file, always visible in `list` (`2/3` on gated parents) and `verify` (tree with a waits-for column). Structure (`parent_id`) is text truth and flows md→db on sync (D4). The dual gap — one shared prerequisite before many tasks (fan-out) — is answered by splitting the prerequisite per consumer, by document order as a nudge (D7), or by the deferred heading barrier (§12).
- **D23 — Trace is a lens, never a ledger.** With env `DIBS_TRACE` set (non-empty; `DIBS_TRACE=1` canonical — launcher-set, like `DIBS_AS`/`DIBS_BOARD`), every CLI invocation appends one JSON line — ts, argv, actor, plan, verb, exit code, outcome summary — to `.logs/<plan-name>.<UTC date>.jsonl` beside the resolved plan; unresolved invocations fall back to `.logs/unbound.<UTC date>.jsonl` under the CWD, so even addressing failures stay visible. Purpose: understanding what agents *attempt* — refusals and errors included, which the mutation-only journal (I6) deliberately omits. Not a second truth: the DB remains sole authority for state (D4), and nothing ever reads a trace back. Best-effort by contract: a trace failure never changes behavior, output, or exit code. Gitignore `.logs/` next to `.*.dibs*` (D2).
- **D24 — One import path.** Text enters the board through exactly one door: sync. `init` is sync against an empty board (found the board — key, hand limit — then import everything as new); `verify` is the same diff computed against no rows and rendered exactly as `list` renders a live board, so what the author previews is what `init` creates and what `list` will show. A sync is one transaction that reads the board under the write lock it will write with, mints ids for new lines in document order (a child under a brand-new parent gets its dotted id in the same pass), refreshes every text-cached column of every matched line — order, section, nesting, title spelling, *body* — and touches no state column. Consequence for authors: rewording a briefing, renaming a heading, re-nesting, or reordering never disturbs ids or ownership (D4, I5); only retitling does (§8).

---

## 4. Invariants

These must hold at all times; any change that breaks one requires amending this file first.

- **I1 — Atomic transitions only.** Every state change is a single SQL statement; success is judged solely by affected-row count. Applies to claims, drops, dones, and name minting (UNIQUE + retry, never check-then-insert).
- **I2 — One owner max.** A task has at most one owner; `done` and `drop` require ownership, enforced in the WHERE clause, not in application logic.
- **I3 — Agents never write plan.md.**
- **I4 — Byte preservation.** Tool writes to `plan.md` modify only lines matching its own annotation grammar (§8); all other content is untouched.
- **I5 — IDs are stable.** Once assigned, a task ID is never renumbered or reused. Sync adds and orphans; it never deletes. New ids are minted against *every* existing row, orphaned ones included, so an orphaned `A2` keeps its ordinal forever and the next task in that section is `A3`.
- **I6 — Append-only journal.** Every mutation writes exactly one event. Events are never updated or deleted.
- **I7 — IDs stay private by hygiene.** Session ids appear only in the owning agent's own command I/O; all shared surfaces (plan.md, list output, events shown to others) display names only.
- **I8 — Bad agents cause delay, never corruption.** A crashed, stalled, or confused agent can at worst hold a task until the TTL; reaping guarantees every task eventually returns to `todo`. Correctness never depends on agent cooperation.
- **I9 — The human may edit plan.md at any time.** The tool syncs (by mtime check) before any operation that reads or writes plan-derived state. Mid-flight task injection is a supported workflow, not an edge case.
- **I10 — Self-sufficient output.** Every command's output — success *or error* — is alone enough for an agent with no other context to take its next correct step.

---

## 5. Data model (indicative, not final column-for-column)

```sql
tasks (
  id         TEXT PRIMARY KEY,   -- "A3", child "A3.1": section letter + creation ordinals, stable (I5)
  parent_id  TEXT,               -- enclosing checkbox, NULL at top level; gates claimability (D22)
  seq        INTEGER,            -- current document order; drives claim priority (D7)
  section    TEXT,               -- nearest heading text, or "" if none
  title      TEXT,
  body       TEXT,               -- indented non-checkbox lines under the checkbox, cached from md
  text_hash  TEXT,               -- normalized-title hash, used by sync matching
  status     TEXT,               -- todo | doing | done | orphaned
  owner      TEXT,               -- agents.id, NULL unless doing/done
  claimed_at INTEGER,
  done_at    INTEGER,
  done_note  TEXT
);

agents (
  id              TEXT PRIMARY KEY,   -- "happy-elephant-4821"
  name            TEXT UNIQUE,        -- "happy-elephant"; UNIQUE drives mint-retry
  created_at      INTEGER,
  last_seen       INTEGER,
  last_event_seen INTEGER,            -- piggyback-delivery cursor
  last_section    TEXT                -- drives section-affinity claim order (D7)
);

events (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       INTEGER,
  agent    TEXT,                 -- actor id ("human" and "system" are valid actors)
  kind     TEXT,                 -- init | sync | join | claim | done | drop | note | reap
  task_id  TEXT,                 -- NULL for free-standing notes
  to_agent TEXT,                 -- NULL = broadcast (D10)
  text     TEXT
);
```

Required pragmas at every connection: `journal_mode=WAL`, `busy_timeout=5000`. A small `meta(key, value)` table carries board facts: `board_key` (D20; `''` until `init` founds the board), `max_hand` (D6), `plan_mtime` (the plan file's `st_mtime_ns` as last synced, I9), `schema_version`. SQLite floor: 3.35 with the JSON functions — `RETURNING`, `INSERT … ON CONFLICT DO UPDATE`, and `json_each` are how single statements carry the whole decision (I1, D6); the CLI refuses older libraries up front with a steer rather than failing mid-command.

---

## 6. CLI contract

Every verb accepts identity via `--as <id>` or env `DIBS_AS` (env preferred; see `join`), and a board via `--plan <key or file>` or env `DIBS_BOARD` — board keys or plan paths, resolved per D18/D20; the no-board error steers workers to `cd` or `--plan`, never to `init`. With `DIBS_TRACE` set (non-empty), every invocation — success or failure — additionally appends one trace line (D23). Argument parsing is tolerant and errors steer (D14): fuzzy ID matching, `--task A3` / `--task=A3` / positional all accepted, and every error message ends with the literal command to run next. Every response ends with: unseen events for the caller (one line each, capped; overflow says "run `dibs list`"), then the next-expected-verb hint.

| Verb | Does | On failure / edge |
|---|---|---|
| `init <plan.md> [--max-hand N]` | Parse once, create `.<plan>.dibs`, mint and print the board key with a paste-ready handoff line, print the task roster. `--max-hand` sets the per-board hand limit (default 1). | Refuses if the board exists — points to `sync`. |
| `verify <plan.md>` | Dry run: render the parse — sections, would-be IDs, titles, body presence, the nesting tree with a waits-for column (D22), warnings — creating and touching nothing; no board required (D21). | Board already exists → noted in one line, points to `list`. |
| `sync` | Reconcile plan ↔ DB per §8. Runs automatically before other verbs when plan mtime changed; manual call forces it. | Ambiguities are reported, never guessed silently. |
| `join` | Mint identity and print the bare id — for launcher scripts: `export DIBS_AS=$(dibs join)` — so workers never handle identity (D8). | — |
| `claim [--task ID …]` | Mint identity on first use (fallback when `join` wasn't used); CAS-claim the next *available* task — no open children (D22) — by section affinity, then `seq` (D7), or the exact bundle (atomic, all-or-none, must fit the hand). Returns id reminder, task title + body, events, next verb. If the task was previously claimed and reaped, output names the prior claimant: "previously claimed by brave-otter, reaped 20 min ago — verify before redoing." | Lost race → tool auto-picks next (no-arg) or reports which bundle member was taken. Hand full → "finish or drop" steer naming the held task(s) (D6). Bundle larger than the hand → refused as such, naming size and hand, steering to `claim --task <first member>` (D6). Nothing available yet → names what the remaining tasks wait on; retry later or stop if the launcher respawns (D6, D22). Explicit `--task` on a gated parent → refused, open children named. Empty board → "no tasks remain; stop." |
| `done <ID> --note "…"` | Ownership-checked completion; annotates plan line. `--note` is mandatory. If this completion unlocks a parent, the output names it with a ready `claim --task` command (D7, D22). | Rejected (not owner) → almost always means reaped; see playbook §11. |
| `drop <ID> [--note "…"]` | Release back to `todo`, log why. | — |
| `note "…" [--for <name>]` | Append event; broadcast by default. | Unknown name → still logged, warned. |
| `list` | Board + recent events, headed by the board key (D20 — `list --plan <path>` is how a lost key is recovered); gated parents show child progress (`2/3`, D22); also triggers reaping, as does any read. | — |

---

## 7. Identity & naming

Two short hardcoded word lists (~50 friendly adjectives × ~50 animals ≈ 2,500 combos — curated: these names appear in `plan.md` next to their work). Mint = `INSERT` with random pick; on UNIQUE violation, re-roll (I1). Id = `name-` + 4 random digits. Scope is per-board only: two boards each having a `happy-elephant` is two offices each having a Dave — they never meet, and the numeric suffix disambiguates any cross-board log aggregation. No external name library: generation is a 20-line job (D3). The `join` verb exists so identity can be minted by the launcher rather than the model (D8); its output is the bare id, suitable for `export DIBS_AS=$(dibs join)`.

## 8. plan.md contract

**Recognition (at init and sync):** a task is any line matching `- [ ]` / `- [x]` / `- [~ …]`. Indented content directly beneath it travels with the task as `body` — except an indented *checkbox*, which is a child task whose parent is the nearest less-indented checkbox above it (D22); nesting depth is free, and the parser never invents structure from prose or plain bullets. The nearest heading above becomes its `section`; sections are lettered `A, B, C…` in document order (no headings → single implicit section); children take dotted IDs (`A3.1`, creation order, stable per I5). All other content is the human's prose and is ignored and preserved. Authors can preview exactly this parse, without side effects, via `dibs verify <plan>` (D21).

**Annotation grammar (the only lines the tool may rewrite):**

```
- [ ] <title>                              todo
- [~ <name>] <title>                       doing
- [x] <title>  ✓ <name>: <done-note>       done
```

**Body standard (D17)** — a content norm, not a parsing rule: each body should brief a context-poor worker completely — file paths, the observed symptom, the acceptance criterion. Sync never enforces this; the skill teaches it, and a deferred lint may warn (§12).

**Sync semantics** (mtime-triggered, hash-matched on normalized title; duplicates matched by order; one transaction, D24). Matching decides identity; everything else on a matched line — position, section, nesting, title spelling, body — is text truth and is simply re-cached from the file:

| File says | DB says | Result |
|---|---|---|
| new checkbox line | — | new task, next free ID under its parent or in its section — minted in document order in the same pass, so a child under a new parent gets `A5.1` alongside `A5` |
| `[x]` | todo | imported as done, owner `human` |
| `[ ]` | doing / done | DB wins, line re-annotated, warning emitted |
| line vanished | any | task → `orphaned`: excluded from claim, kept in list, flagged |
| title edited | — | old task orphaned + new task created; both flagged (accepted v1 limitation) |
| lines reordered | — | `seq` updated; IDs untouched (D7, I5) |
| line re-indented under another checkbox | — | `parent_id` updated; ID untouched — structure is text truth (D4, D22) |
| body reworded, heading renamed, title re-spelled (same normalized hash) | — | cached `body` / `section` / `title` refreshed; ID, status, owner untouched (D4, D17) |
| `[x]` on a parent with open children | todo | imported as done (author's call), with a warning; the children stay independently claimable |

**Escape hatch** for pure-prose plans: a one-time LLM normalization pass into checkboxes *before* `init`. External to the tool; the parser never gets smarter than the rules above.

## 9. Events & delivery

One table (§5), append-only (I6). Delivery is exclusively piggyback: after any command, the caller receives events with `id > last_event_seen` addressed to all or to them, then the cursor advances. No polling loop, no push, no read-receipts. `messages.md` from the original sketch is dropped in favor of `dibs list` (§12 has the revive trigger).

## 10. The skills (protocol) — content specs

Two skills, both global (D13): **`dibs`** for working a board, **`dibs-plan`** for writing one.

### 10a. `dibs` (worker) — six short sections, nothing more

1. **Trigger:** invoked explicitly as `/dibs <board-key or plan-path>` (D19), or naturally — parallel work on a shared plan; `plan.md`, a `dibs-…` key, or dibs mentioned.
2. **Bind:** the invocation argument is the board — `export DIBS_BOARD=<it>` (or `--plan` on every call); keys and paths both work (D20); keep any `DIBS_BOARD`/`DIBS_AS` already in the environment; with multiple boards, never guess (D18). Workers never need the plan file itself: briefings come from `claim`, and an encountered plan file is the author's document — don't read it, never edit it (I3).
3. **The loop:** `claim` → work → `done --note` → `claim` again; stop when claim returns empty. The hand is limited (D6): finish or drop what you hold before claiming more. `claim` may answer *nothing available yet* — remaining tasks wait on work others hold (D22); that is waiting, not completion: retry after finishing something else, or stop and report idle if the launcher respawns workers. When your `done` unlocks a parent, the output says so — claim it; you have the freshest context for it. `list` is not part of the worker loop — `claim` output is the whole briefing; `list` is for humans and planners.
4. **Etiquette:** broadcast cross-cutting changes (`note`); work only what dibs granted you, as a bundle only if granted together; `drop` instead of sitting on blocked work; long task → drop a mid-way `note` (doubles as lease renewal, D9).
5. **Plan changes are not a worker's job:** one line pointing at `dibs-plan`; I3 restated. No authoring content here (D13, D16).
6. **Failure playbook:** = §11 verbatim.

### 10b. `dibs-plan` (author) — content spec

Triggers on: a plan for dibs, a dibs-readable plan, decomposing or splitting work for parallel agents, converting a spec/issue/review/todo list into `plan.md`, fixing a plan `verify` flagged, or `/dibs-plan <goal>`. Its body teaches, in this order:

1. **The grammar, exactly §8:** checkbox = task; indented prose = body; indented checkbox = prerequisite (D22); heading = section; `[x]` = already done; nothing else exists — no invented IDs, tags, priorities, or assignees (IDs come at init, priority is order, ownership is the board's).
2. **Briefings (D17):** title names the target; body gives paths, symptom or current state, done-criterion, constraints; the test is "a worker with 8k context and no exploration finishes this"; a weak/strong pair.
3. **Sizing (D6, D12, D16):** one task = one sitting in one place; split on "and"; two tasks touching one file become one task.
4. **Ordering (D22):** nest prerequisites under what needs them; per-branch gating; the TDD direction; umbrellas are headings or plain bullets, never checkboxes; the shared-prerequisite gap and its answers (split per consumer, else first in file).
5. **Sections are areas, not phases (D7, D12):** group by module/feature for warm context and collision avoidance; tests live in their code's section, nested.
6. **Priority (D7):** document order; reorder any time.
7. **Handoff (D21, D6, D20, §8):** `verify` until the preview matches intent and shows no warnings → `init` with a deliberate `--max-hand` → hand out the key, not the path → keep editing (reword bodies, not titles; a hand `[x]` means already done).
8. **Anti-patterns and a pre-init checklist.**

## 11. Failure playbook

- **`done` rejected** → you were probably reaped. `claim --task <ID>`: if you get it back, `done` again immediately; if someone else holds it, `note` what you already did and move on. Never force it.
- **Lost your id** (context compaction) → check the environment first: `echo $DIBS_AS` survives compaction when the launcher set it (D8). Otherwise mint a fresh identity with your next `claim` and let the orphaned claim expire via reaping.
- **`claim` refused: hand full** → you already hold work (the refusal names it). `done` or `drop` it, then claim again. If you just respawned with an inherited identity, that named task is *yours* — resume it, don't work around it.
- **`claim`: nothing available yet** → every remaining task waits on work someone else holds (the message names it). This is not the end state. Finish anything you hold, retry once or twice, then stop and report idle; never start a gated task's work "to help."
- **`claim --task` refused: waits for children** → the parent isn't ready; the refusal names its open children — claim one of those instead.
- **Identity rejected ("unknown on this board")** → you are almost certainly pointed at the wrong board (D8, D18). Check `$DIBS_BOARD` against the plan path you were given before doing anything else; fix the binding, don't mint a workaround identity.
- **Several boards found** → the error already enumerated them with runnable commands; pick the one matching the plan path from your instructions. Never guess.
- **`dibs: command not found`** → stop and tell the human; do **not** coordinate by editing `plan.md` instead — I3 holds even when the tool is missing.
- **Session died mid-task** → nothing to do; TTL returns the task to the pool and logs the reap.
- **Stop everything** → kill the sessions. All state is in the DB; tomorrow's sessions (new names, same board) resume where these stopped.
- **End state** → `claim` says no tasks remain; agents stop per the skill; `dibs list` + done-notes become the human's review checklist, `git diff` holds the work.

## 12. Deferred — with revisit triggers

Build these the day their trigger fires, not before:

- **`claim --touch <paths>` advisory overlap warnings** — trigger: same-file collisions actually observed despite plan partitioning.
- **Heading-level barriers for fan-out** (`## Functions (after Setup)` — a whole section waits on a named section; heading names, unlike IDs, are known at writing time) — nesting covers fan-in natively (D22); trigger: a real plan needs one shared prerequisite before many tasks and splitting it per consumer isn't honest.
- **`messages.md` render of events** — trigger: human finds `dibs list` / `watch dibs list` insufficient.
- **`approve` state beyond done** (renamed from `verify`, whose verb now belongs to the parse preview, D21) — trigger: review shows done-notes are unreliable.
- **Per-session git worktrees** — trigger: file collisions become chronic; isolation beats messaging at that point.
- **Multi-machine backend** — trigger: agents on more than one host; same CLI, swapped storage.
- **`claim --porcelain` (machine-readable briefing)** — trigger: someone builds the wrapper-claims-then-spawns pattern, where the worker's context contains only the task and the wrapper must parse claim output.
- **Bodiless-task lint escalation at init/sync** — `verify` already warns (D21); blocking or loud warnings at init/sync — trigger: workers observed floundering despite the preview.
- **`verify --diff` (sync preview against a live board)** — trigger: an author is surprised by a sync outcome.
- **Post-init `max-hand` change** — trigger: an author actually needs to widen or narrow the hand mid-flight; until then the limit is fixed at init (D6).
- **`dibs log --jsonl` (render of the events table, date-filterable)** — trigger: someone needs machine-readable per-plan *state* history beyond `dibs list` and the D23 trace. A render, never a second write path (I6).

## 13. Open knobs (settle at write time; defaults proposed)

- **Reap TTL:** default 45 min (constant in script).
- **Hand limit default:** `MAX_HAND_DEFAULT = 1` (per-board override at `init --max-hand`, D6).
- **Key format & registry:** `dibs-` + 8 hex chars in two groups (D20); registry directory `~/.local/state/dibs/`.
- **Piggyback cap:** show up to ~15 unseen events, then "… and N more — run `dibs list`."
- **ID cosmetics (settled r9):** lettered sections by first appearance among tasks, `A3` = letter + ordinal; past `Z` the letters continue `AA, AB, …` (spreadsheet columns) — the grammar is `[A-Z]+[0-9]+(\.[0-9]+)*`. Children: dotted `A3.1`, `A3.1.2` — the tree shows in every steer (D22).
- **Word lists:** final adjective/animal curation.
