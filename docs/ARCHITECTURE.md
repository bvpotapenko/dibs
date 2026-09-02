# dibs — Architecture (implementation reference)

**Audience:** the coding agent implementing dibs.
**Precedence:** `SSoT.md` decides *what* (current Rev governs); this file decides *how*. On conflict, SSoT wins — amend it first, then this file. D/I/§ references below point into the SSoT.
**Prime directive for the implementer:** this document pre-satisfies WPS (wemake-python-styleguide). Follow the budgets and contracts and the linter passes by construction; never "fix" a lint violation by adding a layer, class, or indirection — restructure within the budgets or stop and flag.
**Revision note (2026-09-02, SSoT Rev 9):** §13 steps 1–7 are implemented. This revision closes the gaps step 8 hit — no owner for task-row creation, board opening, meta reads, and verb views — by adding `plansync.py` and `views.py` (the splits §3 pre-announced), and lists the small amendments to already-landed modules in §13 step 8a. Nothing here changes a landed module's *contract* except where §13 step 8a says so.

---

## 1. Shape, and why it is not a flat script

WPS caps module members (default 7), function arguments (5), local variables (5), and cognitive/Jones complexity; it bans magic numbers, mutable module constants, nested functions/classes, and logic in `__init__.py`. A 200-line flat script cannot pass it. Therefore:

- **Source** is a small package of flat, single-purpose modules (D3).
- **Deployment** stays one file: `python -m zipapp` (stdlib) builds `dibs.pyz` for PATH; `pipx install` is the alternative.
- **Runtime dependencies: zero.** `flake8 + wemake-python-styleguide`, `ruff`, `pytest` are dev-only.
- **Python floor:** 3.10 (`(str, Enum)` pattern; no 3.11-only features). SQLite ≥ 3.35 (`RETURNING`), which every supported CPython bundles.

**Design strategy that makes WPS pass by construction:**

1. Every module has a **member budget ≤ 6** (one under the cap). A module that needs a seventh member splits along its natural seam instead — it happened once, at step 8: `transitions` → `transitions` + `plansync`, `output` → `output` + `views`.
2. Functions: ≤ ~10 statements, ≤ 4 parameters (`Context` or a record absorbs the rest), ≤ 5 locals.
3. **Branching lives in SQL** — WHERE clauses decide, Python reads rowcounts (I1). This is simultaneously the concurrency model and the complexity budget: Python stays linear.
4. **Data in frozen dataclasses and str-enums; behavior in module functions.** No behavior classes, no inheritance beyond `Enum`, no methods to count.
5. Repeated short literals (statuses, event kinds, verb names) exist exactly once, as enum members or constants — pre-empts overused-string (WPS226) and magic-number (WPS432) violations.
6. Module-level collections are immutable: `tuple` / `types.MappingProxyType` (WPS407).
7. One exception type: `DibsError(message, steer)`. No hierarchy.
8. No `assert` outside tests (bandit S101 in the wemake bundle); all printing funnels through `cli.py`, so any print-restriction rule has at most one per-file scope.
9. Every public member gets a one-line docstring (the wemake bundle enforces docstrings); small signatures keep them one-liners.

**Not building:** ORM, repository/service classes, CLI framework beyond argparse, logging framework (the events table *is* the log — I6), async, plugins, config files, abstract base classes.

---

## 2. Repository layout

```
dibs/                          repo root
├── pyproject.toml             console entry: dibs = "dibs.cli:main"; dev extras; ruff config
├── setup.cfg                  flake8/WPS + isort config (§10)
├── Makefile                   dev loop: install / lint / test / build (§12)
├── CLAUDE.md                  coding-agent guide: precedence, hard rules, dev loop
├── docs/SSoT.md               what        (authoritative, current Rev)
├── docs/ARCHITECTURE.md       how         (this file)
├── docs/GUIDE.md              human-facing walkthrough
├── skills/dibs/SKILL.md       worker protocol  (SSoT §10a) — not packaged
├── skills/dibs-plan/SKILL.md  author protocol  (SSoT §10b) — not packaged
├── tests/                     §11
└── dibs/                      the package (§3)
```

## 3. Package layout with member budgets

Member = top-level function or class (constants don't count). Budgets are the plan, not a hope: an implementation that needs one more member in a module stops and flags instead of exceeding.

```
dibs/
├── __init__.py     DIBS_VERSION constant only                     [0]  L—
├── __main__.py     zipapp/module entry → cli.main()               [0]  L5
├── runtime.py      Context, Reply, DibsError                      [3]  L0
├── records.py      Status, EventKind, Task, Event, Agent          [5]  L0
├── store.py        connect, ensure_schema, read_meta,
│                   registry_record, registry_lookup
│                   (+SCHEMA, PRAGMAS, META_DEFAULTS)              [5]  L1
├── planfile.py     PlanItem, SyncPlan, parse_plan,
│                   compute_sync, annotate_lines, title_hash       [6]  L1
├── output.py       render_reply, render_error,
│                   format_event, next_hint  (+every template)     [4]  L1
├── trace.py        TraceRecord, trace_path, write_trace
│                   (+TRACE_DIR, OUTCOME_CAP) — D23 lens           [3]  L1
├── transitions.py  claim, finish, release, housekeeping,
│                   record_note, register_agent — worker side      [6]  L2
├── plansync.py     open_board, apply_sync — author side
│                   (+AUTHOR, AUTHOR_DONE_NOTE)                    [2]  L2
├── queries.py      board_snapshot, deliver_events, recent_events,
│                   resolve_task, verify_actor, newly_unlocked     [6]  L2
├── views.py        format_preview, format_board, format_briefing,
│                   claim_refusal, format_sync, format_outcome     [6]  L2
├── names.py        mint_identity, mint_board_key
│                   (+ADJECTIVES, ANIMALS tuples)                  [2]  L3
├── cli.py          main, build_parser, resolve_actor,
│                   resolve_board, walk_boards, run_pipeline
│                   (+VERB_TABLE: MappingProxyType)                [6]  L5
└── verbs/
    ├── __init__.py empty (WPS bans logic in __init__)             [0]  L—
    ├── work.py     join_session, claim_task, done_task, drop_task [4]  L4
    └── board.py    init_board, sync_board, note_verb, list_board,
                    verify_board, annotate_plan                    [6]  L4
```

The package sits at 17 files — exactly the SSoT §2 (Rev 9) file budget. The next new module is a stop-and-re-scope flag, not an 18th file. `transitions` and `output` were split at step 8 along the seams §3 had pre-announced; every module is now ≤ 6 with no exceptions.

`list_board`, `task_id`, `agent_id`: builtin shadowing (`list`, `id`) is banned by the naming rules; these are the canonical replacements everywhere.

## 4. Layering — allowed import direction

A module imports only **strictly lower** levels (plus stdlib). No cycles, mechanically checkable by eye:

| Level | Modules | May import |
|---|---|---|
| L0 | `runtime`, `records` | stdlib only |
| L1 | `store`, `planfile`, `output`, `trace` | L0 |
| L2 | `transitions`, `plansync`, `queries`, `views` | L0–L1 (`plansync` calls `planfile.compute_sync`; `views` reads `output` templates and calls `output.format_event`) |
| L3 | `names` | L0–L2 (uses `transitions.register_agent`) |
| L4 | `verbs/*` | L0–L3 |
| L5 | `cli`, `__main__` | L0–L4 |

`views` is L2 although it touches no DB: it must import `output` (a sibling would be a cycle risk), and placing it above `output` costs nothing.

## 5. Core types and public signatures (the contracts, literally)

```python
# records.py — domain rows. Frozen; behavior lives in modules.
class Status(str, Enum): TODO, DOING, DONE, ORPHANED            # values: 'todo', …
class EventKind(str, Enum): INIT, SYNC, JOIN, CLAIM, DONE, DROP, NOTE, REAP, ORPHAN
      # INIT   board opened            agent 'human', text = board key
      # SYNC   task arrived via sync   text = title            (one per new row)
      # ORPHAN line left the plan      text = title            (one per orphaned row)
      # DONE by 'human'                text = AUTHOR_DONE_NOTE (hand-checked [x] imported)
      # REAP   directed to the former owner (to_agent), agent = that owner

@dataclass(frozen=True)
class Task:    task_id, parent_id, seq, section, title, body, text_hash,
               status, owner, claimed_at, done_at, done_note       # parent_id: None at top level (D22)
                                                                  # seq == the checkbox's line number; unique
                                                                  # among live (non-orphaned) rows — plansync
                                                                  # resolves "parent line" through it
@dataclass(frozen=True)
class Event:   event_id, ts, agent, kind, task_id, to_agent, text
@dataclass(frozen=True)
class Agent:   agent_id, name

# runtime.py — execution plumbing. Zero internal imports.
@dataclass(frozen=True)
class Context: conn, plan_path, db_path, actor, now              # actor: str | None (the SUPPLIED identity;
                                                                 # a verb that mints one passes it explicitly)
@dataclass(frozen=True)
class Reply:   lines: tuple[str, ...], events: tuple[Event, ...], hint: str   # hint '' = no hint line (join)
class DibsError(Exception): message: str, steer: str             # steer = literal next command (D14, I10)

# store.py — board bootstrap and the two registries (keys on disk, meta in the DB).
def connect(db_path) -> Connection        # applies PRAGMAS: WAL, busy_timeout=5000, foreign_keys (D2)
def ensure_schema(conn) -> None           # SSoT §5 tables + meta seeds: board_key '', max_hand, plan_mtime '0', schema_version
def read_meta(conn, key) -> str           # one board fact; list reads board_key, claim's refusal reads max_hand
def registry_record(key, plan_path) -> None   # write-once file in ~/.local/state/dibs/ (D20); self-heal on drift
def registry_lookup(key) -> Path | None       # key → absolute plan path, or None if unknown/stale

# transitions.py — worker-side writes. Every public function: exactly ONE transaction,
# outcome = rowcount truth (I1), one event per row whose state changed (I6).
def claim(conn, actor, now, task_ids=None) -> tuple[Task, ...]   # affinity→seq (D7) or exact bundle all-or-none (D6);
                                                                 # hand limit enforced via holdings subquery in the same
                                                                 # WHERE (max_hand from meta); gating too — NOT EXISTS an
                                                                 # open (todo/doing) child (D22); zero rows is NOT an
                                                                 # error here — the verb turns the snapshot into a steer
                                                                 # via views.claim_refusal; correctness from the statement
def finish(conn, actor, now, task_id, note) -> Task              # WHERE owner=:actor (I2); NOT_OWNER steer on 0 rows
def release(conn, actor, now, task_id, note) -> Task             # drop → todo
def housekeeping(conn, actor, now) -> tuple[Event, ...]          # reap stale by TTL + refresh caller lease (D9);
                                                                 # reap events: agent = former owner, to_agent = former
                                                                 # owner (directed — the one who must know, D10)
def record_note(conn, actor, now, text, to_name=None) -> Event   # broadcast / directed (D10)
def register_agent(conn, agent) -> bool                          # INSERT; False on UNIQUE collision (I1); cursor
                                                                 # last_event_seen starts at the board's high-water
                                                                 # mark (max events.id) — a joiner has no "away" (§9 SSoT)

# plansync.py — author-side writes: the plan → board direction of D4. One transaction each.
def open_board(conn, now, key, max_hand) -> Event
    # CAS: UPDATE meta SET value=:key WHERE key='board_key' AND value=''  — 0 rows ⇒ the board exists ⇒
    # DibsError(BOARD_EXISTS, steer 'dibs sync --plan <existing key>' — the key from a follow-up read);
    # then max_hand; then ONE INIT event (agent 'human', text = key). No task rows: those arrive through
    # apply_sync, which the §6 pipeline runs for init exactly as for every other verb.
def apply_sync(conn, now, plan_items, stamp) -> SyncPlan
    # stamp = str(plan_path.stat().st_mtime_ns), read by the verb together with the text (C4).
    # 1. FIRST statement, the CAS: UPDATE meta SET value=:stamp WHERE key='plan_mtime' AND value<>:stamp.
    #    0 rows ⇒ this file version is already applied (or a concurrent sync won) ⇒ commit, return the
    #    empty SyncPlan. The UPDATE also takes SQLite's write lock, so everything below is serialized
    #    against every other writer: compute-then-apply is NOT check-then-act (I1, I9).
    # 2. SELECT the snapshot inside that lock; planfile.compute_sync(plan_items, snapshot).
    # 3. Apply, in this order (each a WHERE-guarded statement, rowcount truth):
    #      vanished   → status 'orphaned' (owner kept for the record)          + ORPHAN event per row
    #      checked    → done by AUTHOR, done_at, AUTHOR_DONE_NOTE, WHERE status='todo'   + DONE event per
    #                   row actually imported (0 rows = a worker got there first; DB wins, no error)
    #      reordered  → seq = new line
    #      new        → INSERT (document order): seq = line_no; id minted per SSoT §8; status from the
    #                   checkbox ('x' → done/AUTHOR/AUTHOR_DONE_NOTE, else todo — a '[~ name]' newcomer is
    #                   todo: no such owner here); parent_id = the live row at seq = parent_line, or NULL
    #                                                                          + SYNC event per row
    #      reparented → parent_id = the live row at seq = parent_line (None → NULL)
    #      refreshed  → body, section (text truth, no event — D4, I6)
    #    "live row at seq" = SELECT id FROM tasks WHERE seq=:line AND status<>'orphaned' — one row by the
    #    seq invariant (records.Task); orphaned rows keep a stale seq and are excluded.
    # 4. commit; return the SyncPlan applied (the sync verb reports it via views.format_sync).
    # ID minting (SSoT §8): top level '<letter><n>' — letter = the one this section's existing rows carry
    # (first char of their id), else the next letter after the highest in use; n = 1 + rows ever created
    # under that letter at top level. Child '<parent id>.<n>' — n = 1 + rows ever created under that parent.
    # Orphaned rows count (I5: never reused). Computed inside the lock — SQL subqueries or a Python dict
    # built from one SELECT, implementer's choice; no minting outside the transaction.

# queries.py — reads (deliver_events also advances the cursor: one txn, honest piggyback).
def board_snapshot(conn) -> tuple[Task, ...]                     # every row, seq order (list, sync report, refusals)
def deliver_events(conn, actor) -> tuple[Event, ...]             # unseen for actor, cursor advanced (D10):
                                                                 # id > last_event_seen AND (to_agent = :actor OR
                                                                 # (to_agent IS NULL AND agent <> :actor)) — your own
                                                                 # broadcasts are never echoed; what is addressed to
                                                                 # you always arrives. actor None → () (no cursor)
def recent_events(conn, cap, task_id=None, kind=None) -> tuple[Event, ...]
                                                                 # newest first; optional filters live in the WHERE
                                                                 # (:task IS NULL OR task_id=:task) … (C9). Serves
                                                                 # list (cap, no filters) and the claim reap-history
                                                                 # warning (1, task_id, REAP) — replaces prior_claim
def resolve_task(conn, raw) -> Task                              # exact → fuzzy; miss raises DibsError with steer
def verify_actor(conn, actor) -> bool                            # supplied identity must exist on THIS board (D8, D18)
def newly_unlocked(conn, task_id) -> Task | None                 # parent of task_id if this done made it claimable (D22, D7)

# planfile.py — PURE: text in, records out. No I/O, no DB, no clock.
@dataclass(frozen=True) class PlanItem: line_no, parent_line, checkbox, title, body, section   # parent_line: nearest
                                                                                                 # less-indented checkbox (D22);
                                                                                                 # checkbox: '', 'x', '~ <name>'
                                                                                                 # — token lowercased at parse
                                                                                                 # so '[X]' reads as done (§8)
@dataclass(frozen=True) class SyncPlan: new, vanished, checked, reordered,
                                        reparented, regressed, refreshed
      # new: PlanItems (no ids yet — plansync mints them)
      # vanished / checked / regressed: task_ids
      # reordered: (task_id, new_seq)
      # reparented: (task_id, parent_LINE | None) — a LINE, not an id: the new parent may be a line this same
      #             SyncPlan creates, which has no id yet; the applier resolves line → id through seq (above).
      #             A row whose parent left the plan is re-homed to whatever the text now says (GONE_PARENT).
      # refreshed: (task_id, body, section) for matched rows whose body or section text differs — D4 text truth
      #            flowing md → db (rewording a briefing, renaming a heading). NEW at Rev 9; see §13 step 8a.
def parse_plan(text) -> tuple[PlanItem, ...]                     # SSoT §8 recognition
def compute_sync(plan_items, tasks) -> SyncPlan                  # hash-matched diff (§8 sync table); 'items' trips WPS110
def annotate_lines(text, tasks) -> str                           # rewrites ONLY grammar lines (I4)
def title_hash(title) -> str                                     # normalized (lowercase, collapsed whitespace)

# names.py
def mint_identity(conn) -> Agent                                 # pick + register_agent retry loop (D8, §7 SSoT)
def mint_board_key() -> str                                      # 'dibs-' + 8 hex chars in two groups (D20)

# output.py — the D14 rendering contract and every user-facing template (C5); no per-verb logic.
def render_reply(reply) -> str                                   # lines + feed (header, one line per event, capped) + hint;
                                                                 # empty pieces vanish — join renders as the bare id
def render_error(err) -> str                                     # "<message>\nRun: <steer>"
def format_event(event) -> str                                   # one line per kind; names, never ids (I7)
def next_hint(verb, context_bits) -> str                         # template lookup; no 'join' entry (bare id contract)
# Constants callers fill (the ONLY string building outside this module): refusal messages + steers
# (NOT_OWNER, RECLAIM, LIST_BOARD, UNKNOWN_TASK, NO_SUCH_TASK, BOARD_EXISTS, SYNC_BOARD …). Transitions,
# plansync, queries and views fill them; verbs never do (C6).

# views.py — the verb views: pure functions from records to lines or to a steered error (C5, C6).
def format_preview(plan_items) -> tuple[str, ...]                # verify: sections, would-be IDs, tree, waits-for,
                                                                 # bodiless / duplicate-title warnings (D21, D22)
def format_board(tasks, key, recent) -> tuple[str, ...]          # init + list: key header, one line per task (id, state,
                                                                 # owner name, title, child progress 2/3 on parents,
                                                                 # orphaned flag), then recent events oldest → newest
                                                                 # via output.format_event (D14, D20, D22)
def format_briefing(actor, now, claimed, prior) -> tuple[str, ...]
                                                                 # claim success: identity reminder ("you are <name>"),
                                                                 # "claimed A2: <title>", body indented, and for each
                                                                 # REAP in prior: "previously claimed by X, reaped N min
                                                                 # ago — verify before redoing" (§6 SSoT)
def claim_refusal(tasks, actor, wanted, max_hand) -> DibsError   # the zero-row diagnosis, computed from the snapshot:
                                                                 # explicit ids → per-id state (done / orphaned / held by
                                                                 # X / waits for <open children> / bundle over the hand);
                                                                 # no-arg → hand full (names held tasks) | nothing
                                                                 # available yet (names what gates, with holders) | board
                                                                 # empty. Every steer runnable (D6, D22, I10). The verb
                                                                 # raises what this returns.
def format_sync(sync_plan) -> tuple[str, ...]                    # manual sync report: counts + ids/titles per SyncPlan
                                                                 # field; regressed rows warned as "board wins, line
                                                                 # re-annotated" (§8 SSoT). Auto-sync discards it.
def format_outcome(verb, task=None, event=None, to_name=None) -> tuple[str, ...]
                                                                 # one-line confirmations by template: done/drop name the
                                                                 # task; note echoes and warns when to_name was asked but
                                                                 # event.to_agent is None (unknown recipient, §6 SSoT)

# trace.py — the D23 debugging lens. Never truth, never read back; env read stays in cli (C1).
@dataclass(frozen=True) class TraceRecord: ts, argv, actor, plan, verb, exit_code, outcome
def trace_path(plan_path, now) -> Path       # .logs/<plan-name>.<UTC date>.jsonl; unbound fallback under CWD
def write_trace(path, record) -> None        # append one JSON line, mkdir as needed; best-effort, NEVER raises

# verbs/*.py — orchestration only: (ctx, args) -> Reply. ≤10 statements each. Collaborators per §9.
def claim_task(ctx, args) -> Reply       # etc. — one function per SSoT §6 verb
def annotate_plan(ctx) -> None           # verbs/board.py; §6 step 9 helper, the ONLY writer of plan.md (D5, I3, I4):
                                         # read text + stat → planfile.annotate_lines(text, board_snapshot) → if the
                                         # text changed and the file's mtime_ns is still what was read, write via
                                         # tempfile + os.replace; otherwise leave it (the next command retries)

# cli.py
def main(argv=None) -> int               # parse, dispatch verify or run_pipeline, print, exit codes, D23 finally
def build_parser() -> ArgumentParser     # tolerant forms: --task A3 / --task=A3 / positional (D14); global --plan, --as
def resolve_actor(args) -> str | None    # --as, else $DIBS_AS, else None
def resolve_board(args) -> tuple[Path, Path]   # (plan, .{plan}.dibs): --plan | $DIBS_BOARD | walk_boards(cwd);
                                               # value may be a board key (store.registry_lookup first, D20)
                                               # or a path; many → enumerating DibsError; none → cd/--plan steer (D18)
def walk_boards(start) -> tuple[Path, ...]     # the D18 upward directory walk collecting .*.dibs files
def run_pipeline(ctx, args) -> Reply           # §6 steps 4–9 for a resolved board
```

## 6. Flow of operations — the per-command pipeline

Every invocation runs the same pipeline; verbs never skip steps (C10). Only `verify` leaves it, at step 1, because it has no board (D21).

```
main(argv):
 1  build_parser().parse_args()                → verb + args
      verify: board.verify_board(Context(None, plan, db, None, now), args) — the verb reads the
      file (C4) → planfile.parse_plan → views.format_preview (+ one line if .<plan>.dibs already
      exists, pointing to list); print; exit 0. conn is None and never touched: no board, no DB,
      no identity, no annotation.
 2  cli.resolve_board (D18/D20): --plan | $DIBS_BOARD | walk_boards
      value tried as board key (registry) first, then as path
      many → DibsError enumerating runnable steers; none → steer "cd or --plan"
      (init only as an author aside — workers never steered into creating boards)
 3  store.connect + ensure_schema → Context(conn, plan, db, actor, now)
 4  resolve_actor: --as | $DIBS_AS | None; if supplied → queries.verify_actor,
      unknown → DibsError "identity not on this board" + board-check steer (D8)
 5  sync — EVERY command, init included: board.sync_board(ctx, args), Reply discarded.
      The verb reads text + mtime_ns, parses, calls plansync.apply_sync; the mtime CAS
      inside makes the unchanged-file case one UPDATE (I9). No mtime read, no `if`.
 6  transitions.housekeeping                    reap stale + refresh caller lease (D9, I8)
 7  VERB_TABLE[verb](ctx, args) → Reply         verb's own transaction(s) commit here
 8  queries.deliver_events(conn, ctx.actor) → Reply.events   piggyback, cursor advanced (D10).
      ctx.actor is the SUPPLIED identity: join and a first-use claim (which mint inside the
      verb) have None here and get an empty feed by construction — no special case
 9  board.annotate_plan(ctx)                    EVERY command, list included (reaping changes
      state): re-render from the snapshot, write only if the text changed (I4, D5)
10  print(output.render_reply(reply)); exit 0
except DibsError as e:  stderr ← render_error(e);           exit 1   # steered user error (I10)
except sqlite3.Error:   stderr ← generic + steer "retry";   exit 2   # environment
finally: if $DIBS_TRACE — trace.write_trace(TraceRecord)             # success AND both error paths; best-effort (D23)
```

Notes:

- **init runs the whole pipeline.** Step 5 applies the plan (every line is `new` against an empty board; `plan_mtime` seeded `'0'` never equals a real stamp), step 7 is `plansync.open_board` (CAS on `board_key` — a second `init` is refused there, after a harmless re-sync) + `store.registry_record` + `views.format_board`, step 9 normalizes the hand-written lines (`[x]` gains its `✓ human:` suffix, a stray `[~ name]` reverts to `[ ]`). Event order on a fresh board is therefore N × SYNC then INIT — cosmetic, and below every future joiner's cursor.
- **Our own annotation write moves the file's mtime**, so the *next* command's CAS passes and computes an empty SyncPlan (one SELECT, one diff, one UPDATE). Accepted: it keeps meta writes inside `plansync` and needs no "state changed" flag. `annotate_plan` re-stats before `os.replace` so an author's save landing in that window is left alone rather than clobbered (I9).
- A lost claim race is **not** an error — no-arg `claim` auto-picks the next task; a partial bundle raises `DibsError` naming the taken member (D6). A zero-row claim is diagnosed by `views.claim_refusal` over one `board_snapshot` — *hand full*, *nothing available yet*, *board empty*, or the per-id state for explicit `--task` — with correctness resting on the statement (D6, D22). `done` follows its transaction with `queries.newly_unlocked` and, if a parent became claimable, appends a ready `claim --task` hint (D7, D22).
- `join`'s Reply is `(agent_id,)`, no events (step 8 yields none), hint `''` — stdout is exactly the id, so `export DIBS_AS=$(dibs join)` works (SSoT §6). `render_reply` drops empty pieces; no verb-specific branch anywhere.
- The D23 trace wraps the whole pipeline as a `finally`: parse failures and unresolved boards still produce a line (`verb`/`plan` None), and a trace write failure is swallowed inside `write_trace` — it never touches output or exit codes.

## 7. Flow of data

```
           parse_plan                 plansync.apply_sync (compute_sync inside the lock)
plan.md ──► PlanItem[] ──────────────────────────────────────────► SQLite  (state truth, D4)
   ▲                                                                  │
   │                              transitions.* (worker verbs) ───────┤
   │                                                                  ├── queries.* ──► records ──► views/output ──► stdout
   └────────── annotate_plan ◄── annotate_lines ◄── Task[] ◄──────────┘
              (text truth stays in the file; only grammar lines change)
```

## 8. Contracts (C-rules — cite them in code review)

- **C1** — Process edges (argv, env, stdout/stderr, exit codes, `print`) exist only in `cli.py`.
- **C2** — SQL text exists only in `store/transitions/plansync/queries`; placeholders only, never string interpolation.
- **C3** — Every public `transitions`/`plansync` function = one transaction; success ⇔ rowcount says so (I1); one event per row whose *state* changed, same transaction (I6) — `claim` of a bundle, `housekeeping`, `apply_sync` append several; text-truth refreshes (seq, parent_id, body, section) append none.
- **C4** — `planfile` is pure: no I/O, no DB, no clock. Plan-file reads happen in verbs via `pathlib`; the one writer is `verbs/board.annotate_plan` (atomic: tempfile + `os.replace`).
- **C5** — All user-facing text lives in `output` (templates, caps) and `views` (per-verb composition). Nothing else builds user-facing strings; lower modules only fill an `output` template with an id or a key.
- **C6** — Verbs orchestrate only: ≤10 statements, no SQL, no regex, no string building, no template filling — a verb's `Reply.lines` and every `DibsError` it raises come from `views`, its hint from `output.next_hint`.
- **C7** — One error channel: raise `DibsError(msg, steer)`; `cli` catches `DibsError` and `sqlite3.Error` only. Every steer is a runnable command (I10).
- **C8** — No mutable module state anywhere; state flows through `Context` or lives in the DB.
- **C9** — Decisions branch in SQL, Python reads rowcounts. If a verb grows an if-tree, the WHERE clause is missing something. The sync CAS is the model case: "has the plan changed, and am I the one applying it?" is one UPDATE's WHERE.
- **C10** — Every command runs the §6 pipeline in order; housekeeping precedes the verb so `claim` sees freshly reaped tasks; sync precedes housekeeping so reaping sees the current plan.

## 9. Verb → modules → SSoT trace

Each verb's collaborators, in call order. `(pipeline)` marks what §6 already did before the verb ran.

| Verb | Orchestrates | Implements |
|---|---|---|
| `init` | (pipeline: sync applied the rows) → names.mint_board_key → plansync.open_board (raises BOARD_EXISTS) → store.registry_record → queries.board_snapshot → views.format_board → output.next_hint('init', key) | §6, §8, D4, D20 |
| `verify` | pathlib read → planfile.parse_plan → views.format_preview → output.next_hint('verify', plan) — no ctx, no DB | D21, D22, §8 |
| `sync` | pathlib read + stat → planfile.parse_plan → plansync.apply_sync → views.format_sync → output.next_hint('sync'). Also the pipeline's step 5 for every verb (Reply discarded) | §8, I5, I9, D22 |
| `join` | names.mint_identity → Reply((agent_id,), (), '') | D8, §6 |
| `claim` | (ctx.actor or names.mint_identity) → queries.resolve_task per `--task` → transitions.claim → if none: raise views.claim_refusal(board_snapshot, actor, wanted, store.read_meta max_hand) → queries.recent_events(1, task_id, REAP) per claimed → views.format_briefing → output.next_hint('claim', task) | D6, D7, D9, D16, D22, §6 |
| `done` | queries.resolve_task → transitions.finish → queries.newly_unlocked → views.format_outcome → output.next_hint (a ready `claim --task <parent>` when unlocked) | D11, I2, I4, D22 |
| `drop` | queries.resolve_task → transitions.release → views.format_outcome → output.next_hint | §6, D9 |
| `note` | transitions.record_note → views.format_outcome (unknown `--for` warned) → output.next_hint | D10 |
| `list` | queries.board_snapshot → store.read_meta board_key → queries.recent_events(EVENT_CAP) → views.format_board → output.next_hint | §6, D14, D20, D22 |

Identity for `claim` with `ctx.actor` None: mint, then use the minted id for every call in the verb; the feed for that command stays empty (§6 step 8) and the briefing's "you are <name>" line is the announcement.

## 10. WPS pre-satisfaction map

| WPS constraint | Answered by |
|---|---|
| Module members ≤ 7 (WPS202) | §3 budgets, all ≤ 6; the two seams (`plansync`, `views`) already split |
| Args ≤ 5 (WPS211) | `Context` carries conn/paths/actor/now; verb signature is `(ctx, args)`; views take ≤ 4 records |
| Locals ≤ 5 (WPS210), complexity caps | ≤10-statement functions; branching pushed into SQL (C9); `cli.run_pipeline` and `board.annotate_plan` exist so `main` and the verbs stay under the caps |
| Magic numbers (WPS432) | Named constants at top of owning module: `REAP_TTL_SECONDS`, `EVENT_CAP`, `ID_DIGITS`… (D3) |
| Overused strings (WPS226) | `Status`/`EventKind` enums; verb names only in `VERB_TABLE`; long SQL strings are unique literals, inherently safe |
| Mutable module constants (WPS407) | tuples + `MappingProxyType` |
| Nested functions/classes | none — flat module functions only |
| Logic in `__init__` (WPS412) | `verbs/__init__.py` is docstring-only; `dibs/__init__.py` holds only `DIBS_VERSION`, which WPS 1.x still counts as logic — sanctioned per-file-ignore (a zipapp has no dist-info to read a version from); `VERB_TABLE` lives in `cli.py` |
| Docstrings + naming bundle | one-line docstrings on every public member; no builtin shadowing (`list_board`, `task_id`) |
| `assert` ban (S101) | asserts only under `tests/` per-file-ignore |

`setup.cfg` (WPS) and `pyproject.toml` (ruff, the classic bundle WPS 1.x dropped) — start from the wemake documented baseline; the only project deviations (rationales in the files):

```ini
[flake8]
max-line-length = 80
select = WPS                  # WPS 1.x split: ruff carries the classic bundle
per-file-ignores =
    dibs/__init__.py: WPS412
    tests/*.py: S101, D, WPS202, WPS204, WPS210, WPS226, WPS432
```

```toml
[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "D", "PLR2004", "S311"]   # the ruff twins of WPS432 (literals in asserts) and of
                                               # seeded test randomness — test idiom, mirrored from setup.cfg
```

If any other rule fires during implementation, the fix-preference order is: delete code → simplify inline → move to the owning module — never a new layer. A rule that survives all three gets a targeted `# noqa: <code>  # <one-line reason>` and a flag to the maintainer.

## 11. Testing plan (pytest, three tiers)

Fixtures in `conftest.py`: `plan_text` (sample document), `board(tmp_path)` (initialized DB + plan), `two_agents`. From step 8 on, `board` is built the way `init` builds it — `store.connect` + `ensure_schema`, `plansync.apply_sync(parse_plan(plan_text), stamp)`, `plansync.open_board(...)` — and the interim `insert_task`/`plan_tasks`/`as_task` helpers (flagged at step 4 as stand-ins) are deleted. The property tier's pure stand-in applier stays: it tests `planfile`, not the DB.

| Tier | Targets | Key cases |
|---|---|---|
| Unit (pure) | `planfile`, `names.pick`, `output`, `views` | §8 recognition table incl. nested checkboxes → `parent_line`, indented prose stays body (D22), `[X]` reads as done; annotation grammar; hash normalization; event one-liners incl. ORPHAN and SYNC; `verify` rendering incl. tree/waits-for and bodiless/duplicate-title warnings (D21, D22); `format_board` child progress `2/3` and orphan flag; `claim_refusal` — all three no-arg diagnoses and every explicit-id state, each steer starting with `dibs `; `format_sync` counts; `render_reply` of a hint-less Reply is the bare line |
| Property / metamorphic | `planfile`, `transitions`, `plansync` | `annotate_lines` preserves every non-grammar byte (I4) across generated docs; `sync` is idempotent — applying a SyncPlan and recomputing finds nothing, and `apply_sync` twice on the same stamp is a no-op (CAS); `refreshed` fires exactly on body/section edits; claim order respects affinity→seq (D7); **gating invariant:** a parent is never claimable while any todo/doing child exists, across random trees and completion orders (D22) |
| Integration (tmp DB) | `transitions`, `plansync`, `queries`, `store` | **the CAS race:** two threads claim one task, exactly one wins (I1/I2); **the sync race:** two threads `apply_sync` the same stamp, exactly one inserts (no duplicate rows); `apply_sync` mints `A1, A2, A2.1, B1…` matching `format_preview`'s would-be ids on a fresh board (D21), never reuses an orphaned id (I5), reparents under a parent created in the same pass, imports `[x]` only over todo, orphans a `doing` row and frees the hand, refreshes body; `open_board` CAS refuses a second init with a runnable steer; bundle all-or-none and must fit the hand (D6); **hand limit:** claim refused at capacity (D6); **gating:** no-arg claim skips gated parents, orphaned children don't block (D22); `newly_unlocked` fires exactly on the last child's `finish` (D22); `finish` rejects non-owner (I2); TTL reap + lease refresh, reap event directed to the former owner (D9, D10); `register_agent` UNIQUE retry and high-water cursor; `deliver_events` — never your own broadcasts, always what is addressed to you, directed note filtering (D10); `recent_events` newest-first with and without filters; `read_meta`; board-key registry record/lookup + self-heal (D20) |
| End-to-end | `cli.main` | full loop init→join→claim→done; `join` stdout is exactly the id; init prints the key and `--plan <key>` resolves from an unrelated CWD (D20); an author edit between commands is picked up by the next command without `sync` (I9); assert final plan.md text and exit codes |

Definition of done per module: its tests green **and** lint silent. No module is "done" while either fails.

## 12. Build, install, dev loop

```
pip install -e '.[dev]'   # flake8 + WPS, ruff, pytest — dev only (make install)
flake8 dibs tests         # WPS — must be silent (make lint also runs ruff)
pytest -q                 # must be green (make test)
make build                # stages dibs/ into build/zipapp, zipapps → dist/dibs.pyz
cp dist/dibs.pyz ~/bin/   # onto PATH
```

Staging is load-bearing, not ceremony: `python -m zipapp dibs -m …` fails outright (zipapp refuses `-m` while the source holds a `__main__.py`), and zipapp archives a directory's *contents*, so the `dibs/` package must sit one level inside the staging root for `dibs.cli:main` to resolve. Verified empirically; the Makefile encodes it.

## 13. Implementation order (bottom-up; each step ends lint-clean + tests green)

1. `runtime.py`, `records.py` — types only. **Done.**
2. `store.py` — schema + pragmas + key registry. **Done.**
3. `planfile.py` — parse/annotate/diff; the property tests land here (I4 is the crown jewel). **Done.**
4. `transitions.py` — CAS claim first, with the two-thread race and hand-limit tests; then the rest. **Done.**
5. `queries.py` — deliver_events cursor semantics. **Done.**
6. `names.py` — mint retry loop + board keys. **Done.**
7. `output.py` — caps, hints, steering errors. **Done.**
8. The plan→board side and the views, then the verbs — three sub-steps, each lint-clean and green before the next:
   - **8a — amendments to landed modules** (small, contract-level; every one is specified in §5 above):
     `records`: `EventKind.ORPHAN`. `planfile`: `SyncPlan.refreshed`; `CHECKBOX_RE` accepts `X`, the token is lowercased at parse. `store`: `read_meta`. `transitions`: delete `import_author_done` (absorbed by `apply_sync`; move `AUTHOR`/`AUTHOR_DONE_NOTE` to `plansync`); `register_agent` seeds the cursor at the high-water mark; `housekeeping`'s reap events get `to_agent = former owner`. `queries`: `recent_events` replaces `prior_claim`; `deliver_events` filter per §5. `output`: `format_preview` and its constants move to `views`; `EVENT_LINES` gains ORPHAN and renders SYNC as `new …`; `HINTS` loses `join`; `render_reply` drops an empty hint; add `BOARD_EXISTS`/`SYNC_BOARD` templates. `tests`: the affected cases change with their contracts — `deliver_events` cursor/own-event expectations, reap `to_agent`, the two `import_author_done` cases move to `plansync` tests, `prior_claim` cases become `recent_events` cases; `conftest.board` is rebuilt on `plansync` and the stand-in helpers deleted. No case is dropped without a replacement.
   - **8b — `plansync.py`, `views.py`** with their §11 cases (the sync race and id minting are the crown jewels here).
   - **8c — `verbs/`** — thin orchestration over everything below, per §9.
9. `cli.py`, `__main__.py`, `trace.py` — pipeline §6 with the D23 trace; end-to-end + trace tests.
10. zipapp build; smoke-test `dibs.pyz` on PATH.

Steps 8–9 are `plan.md`-ready tasks with complete briefings — dibs can be dogfooded to build the rest of dibs.
