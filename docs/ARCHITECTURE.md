# dibs — Architecture (implementation reference)

**Audience:** the coding agent implementing dibs.
**Precedence:** `SSoT.md` decides *what* (current Rev governs); this file decides *how*. On conflict, SSoT wins — amend it first, then this file. D/I/§ references below point into the SSoT.
**Prime directive for the implementer:** this document pre-satisfies WPS (wemake-python-styleguide). Follow the budgets and contracts and the linter passes by construction; never "fix" a lint violation by adding a layer, class, or indirection — restructure within the budgets or stop and flag.

---

## 1. Shape, and why it is not a flat script

WPS caps module members (default 7), function arguments (5), local variables (5), and cognitive/Jones complexity; it bans magic numbers, mutable module constants, nested functions/classes, and logic in `__init__.py`. A 200-line flat script cannot pass it. Therefore:

- **Source** is a small package of flat, single-purpose modules (D3).
- **Deployment** stays one file: `python -m zipapp` (stdlib) builds `dibs.pyz` for PATH; `pipx install` is the alternative.
- **Runtime dependencies: zero.** `flake8 + wemake-python-styleguide`, `pytest` are dev-only.
- **Python floor:** 3.10 (`(str, Enum)` pattern; no 3.11-only features).
- **SQLite floor:** 3.35 with the JSON functions. `RETURNING` (3.35) and `INSERT … ON CONFLICT DO UPDATE` (3.24) carry the rowcount contract (I1); `json_each` carries bundles and id lists into single statements (D6). JSON is built in from 3.38 and a compile option (`JSON1`, on in every Python bundle and distro build we know of) before that. `cli.main` checks `sqlite3.sqlite_version_info` once and refuses below the floor with a steer (§6) — never a mid-command `OperationalError` dressed as "retry".

**Design strategy that makes WPS pass by construction:**

1. Every module has a **member budget ≤ 7**, the WPS cap. A module *at* 7 has no growth room, so §3 names its split seam in advance; needing an 8th member means splitting there by kind, never raising the limit and never parking the member elsewhere.
2. Functions: ≤ ~10 statements, ≤ 4 parameters (`Context` absorbs the rest), ≤ 5 locals.
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
├── setup.cfg                  flake8/WPS + isort config (§7)
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

Two seams run through the package and explain every split in it: the **role seam** (D5/D20 — authors write plans and use paths; workers run the loop and use keys) separates `verbs/board` from `verbs/work`, `plansync` from `transitions`, and `views` from `output`; the **direction seam** (D4 — text flows md→db on sync, state flows db→md on annotation) separates `planfile` + `plansync` from `queries` + `annotate_lines`.

## 3. Package layout with member budgets

Member = top-level function or class (constants don't count). Budgets are the plan, not a hope: an implementation that needs one more member in a module stops and flags instead of exceeding.

```
dibs/
├── __init__.py     DIBS_VERSION constant only                     [0]  L—
├── __main__.py     zipapp/module entry → cli.main()               [0]  L5
├── runtime.py      Context, Reply, DibsError                      [3]  L0
├── records.py      Status, EventKind, Task, Event, Agent, Board   [6]  L0
├── store.py        connect, ensure_schema, registry_record,
│                   registry_lookup  (+SCHEMA, PRAGMAS)            [4]  L1
├── planfile.py     PlanItem, SyncPlan, parse_plan, compute_sync,
│                   mint_id, annotate_lines, title_hash            [7]* L1
├── output.py       Refusal, render_reply, render_error,
│                   format_event, next_hint, steer                 [6]  L1
├── views.py        format_board, format_briefing, format_sync    [3]  L1
├── trace.py        TraceRecord, trace_path, write_trace
│                   (+TRACE_DIR, OUTCOME_CAP) — D23 lens           [3]  L1
├── transitions.py  claim, finish, release, housekeeping,
│                   record_note, register_agent  (worker writes)   [6]  L2
├── queries.py      board_snapshot, deliver_events, prior_claim,
│                   resolve_task, verify_actor, newly_unlocked,
│                   claim_refusal                                  [7]* L2
├── plansync.py     found_board, apply_sync  (author writes)       [2]  L3
├── names.py        mint_identity, mint_board_key
│                   (+ADJECTIVES, ANIMALS tuples)                  [2]  L3
├── cli.py          main, run, open_context, build_parser,
│                   resolve_actor, resolve_board
│                   (+VERB_TABLE: MappingProxyType)                [6]  L5
└── verbs/
    ├── __init__.py empty (WPS bans logic in __init__)             [0]  L—
    ├── work.py     join_session, claim_task, done_task, drop_task [4]  L4
    └── board.py    init_board, sync_board, note_verb, list_board,
                    verify_board                                   [5]  L4
```

\* **At the cap (7), with the split seam named.** `planfile.py`: the md→db half (`PlanItem`, `SyncPlan`, `parse_plan`, `compute_sync`, `mint_id`, `title_hash`) and the db→md half (`annotate_lines`, which would take `LINE_RE` and `LINE_FORMS` with it) — the D4 direction seam. `queries.py`: pipeline reads (`board_snapshot`, `deliver_events`, `verify_actor`) and verb-context reads (`prior_claim`, `resolve_task`, `newly_unlocked`, `claim_refusal`). Neither split is wanted today; each is written down so that an 8th member has exactly one honest move.

Both modules pass the wps-refactor homogeneity test — every member of `planfile` is a pure text↔record function, every member of `queries` a read returning records — which is why 7 is a budget here and not a debt.

The package sits at 17 files against the SSoT §2 budget of 18. The 18th is the last; the 19th is a stop-and-re-scope flag. `plansync.py` and `views.py` are the two splits §2 predicts along the role seam, made when their concepts arrived (Rev 9) rather than when a counter tripped.

`list_board`, `task_id`, `agent_id`: builtin shadowing (`list`, `id`) is banned by the naming rules; these are the canonical replacements everywhere. Display names derive from ids by one idiom — `agent_id.rsplit('-', 1)[0]` (SSoT §7 grammar `name-NNNN`) — used at exactly two render sites, `planfile.annotate_lines` and `output.format_event`; a third site would earn `records.agent_name`.

## 4. Layering — allowed import direction

A module imports only **strictly lower** levels (plus stdlib). No cycles, mechanically checkable by eye:

| Level | Modules | May import |
|---|---|---|
| L0 | `runtime`, `records` | stdlib only |
| L1 | `store`, `planfile`, `output`, `views`, `trace` | L0 |
| L2 | `transitions`, `queries` | L0–L1 (`queries` raises through `output.steer`) |
| L3 | `names`, `plansync` | L0–L2 (`names` uses `transitions.register_agent`; `plansync` reads through `queries.board_snapshot` inside its own write transaction — see C11) |
| L4 | `verbs/*` | L0–L3 |
| L5 | `cli`, `__main__` | L0–L4 |

`views` and `output` are siblings at L1 and never import each other: `views` builds bodies (tuples of lines) from records, `output` builds the envelope (events, hint, error form) and owns the steer catalog. Verbs combine the two into a `Reply`.

## 5. Core types and public signatures (the contracts, literally)

```python
# records.py — domain rows. Frozen; behavior lives in modules.
class Status(str, Enum): TODO, DOING, DONE, ORPHANED            # values: 'todo', …
class EventKind(str, Enum): INIT, SYNC, JOIN, CLAIM, DONE, DROP, NOTE, REAP

@dataclass(frozen=True)
class Task:    task_id, parent_id, seq, section, title, body, text_hash,
               status, owner, claimed_at, done_at, done_note       # parent_id: None at top level (D22)
@dataclass(frozen=True)
class Event:   event_id, ts, agent, kind, task_id, to_agent, text
@dataclass(frozen=True)
class Agent:   agent_id, name                                    # agent_id = f'{name}-NNNN' (SSoT §7)
@dataclass(frozen=True)
class Board:   key, max_hand, plan_mtime, tasks, events          # one read of the board (queries.board_snapshot):
                                                                 # meta facts + every task row in seq order + the
                                                                 # last EVENT_CAP events; key '' = founded by nobody yet

# runtime.py — execution plumbing. Zero internal imports.
@dataclass(frozen=True)
class Context: conn, plan_path, db_path, actor, now              # actor: str | None; now: int (UTC seconds), the ONE clock
@dataclass(frozen=True)
class Reply:   lines: tuple[str, ...], events: tuple[Event, ...], hint: str
class DibsError(Exception): message: str, steer: str             # steer = literal next command (D14, I10)

# store.py
def connect(db_path) -> Connection        # applies PRAGMAS: WAL, busy_timeout=5000, foreign_keys (D2)
def ensure_schema(conn) -> None           # SSoT §5 tables + meta(key, value): board_key, max_hand, plan_mtime, schema_version
def registry_record(key, plan_path) -> None   # write-once file in ~/.local/state/dibs/ (D20); self-heal on drift
def registry_lookup(key) -> Path | None       # key → absolute plan path, or None if unknown/stale

# planfile.py — PURE: text in, records out. No I/O, no DB, no clock.
@dataclass(frozen=True) class PlanItem: line_no, parent_line, checkbox, title, body, section   # parent_line: nearest
                                                                                                 # less-indented checkbox (D22)
@dataclass(frozen=True) class SyncPlan:
    rows: tuple[Task, ...]        # EVERY checkbox line as the row it should be, in document order: a paired line is its
                                  # DB row with the text-cached columns refreshed (seq, section, parent_id, title, body);
                                  # an unpaired line is a fresh row (mint_id, status todo, owner None). State columns of
                                  # paired rows pass through untouched — apply_sync never writes them (D4).
    new: tuple[str, ...]          # ids of rows that did not exist (F6 settled: ids, the rows are in `rows`)
    vanished: tuple[str, ...]     # live DB rows whose line disappeared → orphaned (I5)
    checked: tuple[str, ...]      # ids whose line is [x] while the row is todo — new [x] lines included, so init and
                                  # sync import hand-checked work through one path (§8: done, owner 'human')
    regressed: tuple[str, ...]    # [ ] in file over doing/done in DB: DB wins, line re-annotated, warning (§8)
def parse_plan(text) -> tuple[PlanItem, ...]                     # SSoT §8 recognition
def compute_sync(plan_items, tasks) -> SyncPlan                  # hash-matched diff (§8 sync table); one pass: a new
                                                                 # parent is minted before its children, so a child under
                                                                 # a brand-new parent gets its dotted id immediately —
                                                                 # apply then recompute is EMPTY (no deferral, §11)
def mint_id(head, parent_id, taken) -> str                       # next free id for a PlanItem given every row that exists
                                                                 # or was minted so far: parent_id → f'{parent_id}.N',
                                                                 # else its section's letter (from any top-level row of
                                                                 # that section, else the next unused letter: A..Z, AA..)
                                                                 # + N; N = max ordinal under that prefix + 1 over ALL
                                                                 # statuses, orphaned included — ids are never reused (I5)
def annotate_lines(text, tasks) -> str                           # rewrites ONLY grammar lines (I4)
def title_hash(title) -> str                                     # normalized (lowercase, collapsed whitespace)

# transitions.py — WORKER writes. Every public function: exactly ONE transaction (BEGIN IMMEDIATE),
# outcome = rowcount truth (I1), exactly one event appended per changed row in the same transaction (I6).
def claim(conn, actor, now, task_ids=None) -> tuple[Task, ...]   # affinity→seq (D7) or exact bundle all-or-none (D6);
                                                                 # hand limit via holdings subquery in the same WHERE
                                                                 # (max_hand from meta); gating too — NOT EXISTS an open
                                                                 # (todo/doing) child (D22); () is a refusal the verb
                                                                 # diagnoses with queries.claim_refusal
def finish(conn, actor, now, task_id, note) -> Task | None       # WHERE owner=:actor AND status='doing' (I2); None ⇔ zero
                                                                 # rows — the verb raises output.steer(NOT_OWNER, …)
def release(conn, actor, now, task_id, note) -> Task | None      # drop → todo; same None contract
def housekeeping(conn, actor, now) -> tuple[Event, ...]          # refresh caller lease, then reap stale by TTL (D9)
def record_note(conn, actor, now, text, to_name=None) -> Event   # broadcast / directed (D10)
def register_agent(conn, agent, now) -> bool                     # INSERT + join event stamped `now` (I6 — one clock per
                                                                 # invocation, never the SQLite clock); False on UNIQUE (I1)

# plansync.py — AUTHOR writes: the md→db direction of D4. Same one-transaction / one-event contract as transitions.
def found_board(conn, now, key, max_hand) -> bool                # UPDATE meta SET value=:key WHERE key='board_key' AND
                                                                 # value='' — rowcount 0 ⇔ already founded (init refuses,
                                                                 # steering to sync); sets max_hand; one INIT event
def apply_sync(conn, now, plan_items, plan_mtime) -> SyncPlan    # under the write lock: board_snapshot → compute_sync →
                                                                 # UPSERT every row (insert fresh; on conflict refresh only
                                                                 # the text-cached columns) → orphan vanished → import
                                                                 # checked (done, owner 'human', one done event each) →
                                                                 # one SYNC event carrying the summary → stamp plan_mtime.
                                                                 # Returns the SyncPlan it applied (facts for views).
                                                                 # Init IS this on an empty board (D24).

# queries.py — reads (deliver_events also advances the cursor: one txn, honest piggyback).
def board_snapshot(conn) -> Board                                # meta + tasks (seq order) + last EVENT_CAP events
def deliver_events(conn, actor) -> tuple[Event, ...]             # unseen for actor, cursor advanced (D10); actor None → ()
def prior_claim(conn, task_id) -> Event | None                   # last REAP event on task_id (§6 SSoT warning)
def resolve_task(conn, raw, verb) -> Task                        # exact → fuzzy; miss raises output.steer(UNKNOWN_TASK,
                                                                 # (raw, nearest, verb)) — the steer is the caller's own
                                                                 # command with the id corrected (D14)
def verify_actor(conn, actor) -> bool                            # supplied identity must exist on THIS board (D8, D18)
def newly_unlocked(conn, task_id) -> Task | None                 # parent of task_id if this done made it claimable (D22, D7)
def claim_refusal(conn, actor, task_ids) -> tuple[Refusal, tuple[str, ...]]
                                                                 # why claim returned (): one CASE statement picks the kind
                                                                 # (C9) — TAKEN (bundle member held/done: holder named),
                                                                 # GATED (member waits on children: children named),
                                                                 # OVERSIZED (bundle larger than max_hand: size, hand, first
                                                                 # member named), HAND_FULL (held ids named), WAITING (holders
                                                                 # of what the remaining todo rows wait on), EMPTY — then one
                                                                 # names query per kind from a MappingProxyType keyed by Refusal

# names.py
def mint_identity(conn, now) -> Agent                            # pick + register_agent retry loop (D8, §7 SSoT)
def mint_board_key() -> str                                      # 'dibs-' + 8 hex chars in two groups (D20)

# output.py — the envelope and the steer catalog; owns terseness caps (D14). The ONLY home of error text.
class Refusal(str, Enum):                                        # every way the board says no; keys of the catalog
    UNKNOWN_TASK, NOT_OWNER, TAKEN, GATED, OVERSIZED, HAND_FULL, WAITING, EMPTY,
    BOARD_EXISTS, NO_BOARD, MANY_BOARDS, UNKNOWN_ACTOR, OLD_SQLITE
def render_reply(reply) -> str                                   # lines + events (one line each, capped) + hint; empty
                                                                 # parts vanish, so `join` prints exactly the bare id
def render_error(err) -> str                                     # "<message>\nRun: <steer>"
def format_event(event) -> str                                   # one line; agent shown by NAME (I7)
def next_hint(moment, names) -> str                              # HINTS[moment].format(*names); moments: claim, done,
                                                                 # unlocked, drop, note, sync, init, list, empty — each a
                                                                 # runnable command (D14)
def steer(kind, names) -> DibsError                              # CATALOG[kind] = (message, command) templates; positional
                                                                 # slots documented per entry; the one DibsError factory (C7)

# views.py — multi-line bodies, records in → tuple[str, ...] out. No caps here (output's job), no DB.
def format_board(tasks, key) -> tuple[str, ...]                  # list AND verify AND init's roster: key header when key
                                                                 # is non-empty, sections, ids, state, owner name, child
                                                                 # progress `2/3` on gated parents (D22); inline warnings —
                                                                 # bodiless (body == ''), duplicate titles (repeated
                                                                 # text_hash) — computed here, not in verbs (C5/C6, D21)
def format_briefing(tasks, actor_name, priors) -> tuple[str, ...]  # claim: "you are <name>", "claimed A2: <title>", body
                                                                 # indented, "previously claimed by … reaped …" per prior
def format_sync(plan) -> tuple[str, ...]                         # counts + ids for new/orphaned/imported + regressed
                                                                 # warnings; the same text is the SYNC event's body

# trace.py — the D23 debugging lens. Never truth, never read back; env read stays in cli (C1).
@dataclass(frozen=True) class TraceRecord: ts, argv, actor, plan, verb, exit_code, outcome
def trace_path(plan_path, now) -> Path       # .logs/<plan-name>.<UTC date>.jsonl; unbound fallback under CWD
def write_trace(path, record) -> None        # append one JSON line, mkdir as needed; best-effort, NEVER raises

# verbs/*.py — orchestration only: (ctx, args) -> Reply. ≤10 statements each; at most one rowcount `if … raise`.
def claim_task(ctx, args) -> Reply       # etc. — one function per SSoT §6 verb
def verify_board(args) -> Reply          # the one pure verb: no ctx (D21) — read, parse, compute_sync(items, ()),
                                         # views.format_board(plan.rows, ''); if the board file exists, one line → list

# cli.py — the ONLY process-edge module
def main(argv=None) -> int               # try: run → print; except DibsError → 1, sqlite3.Error → 2; finally trace (§6)
def run(args) -> Reply                   # the §6 route table: verify (pure) | init (found + settle) | worker verbs (settle)
def open_context(args, actor) -> Context # connect + ensure_schema + verify_actor (when actor given) + now
def build_parser() -> ArgumentParser     # tolerant forms: --task A3 / --task=A3 / positional (D14); global --plan, --as
def resolve_actor(args) -> str | None    # --as, else $DIBS_AS, else None
def resolve_board(args) -> tuple[Path, Path]   # (plan, .{plan}.dibs): --plan | $DIBS_BOARD | upward walk;
                                               # value may be a board key (store.registry_lookup first, D20)
                                               # or a path; many → MANY_BOARDS steer; none → NO_BOARD (D18); a
                                               # path whose board file is missing → NO_BOARD naming `init` (authors
                                               # use paths, D20) — except for `init`, which needs only the plan
```

Signature changes against Rev 8, all landed by §13 step 5 before any new module is written: `SyncPlan` reshaped (`rows`, `new` as ids; `reordered`/`reparented` deleted — subsumed by the UPSERT), `mint_id` added, `register_agent(conn, agent, now)`, `mint_identity(conn, now)`, `finish`/`release` documented as `Task | None`, `import_author_done` deleted (its case moves to `plansync.apply_sync`), `board_snapshot` returns `Board`, `resolve_task` takes `verb`, `format_preview` replaced by `views.format_board`, `next_hint(verb, context_bits)` becomes `next_hint(moment, names)`.

## 6. Flow of operations — the per-command pipeline

Every invocation runs the same pipeline; verbs never skip steps (C10). Three routes exist, and `cli.run` is the only place that knows which verb takes which — verbs and lower modules never branch on a verb name.

```
main(argv):
 0  sqlite3.sqlite_version_info < (3, 35)          → steer(OLD_SQLITE)   (§1 floor; exit 1, not a "retry")
 1  build_parser().parse_args()                    → verb + args
    run(args):
    verify ─► pure route: read plan → parse_plan → compute_sync(items, ()) → views.format_board(rows, '')
              no board resolution, no DB, no identity, no annotation (D21); board file exists → one line → list
    init   ─► resolve_board (plan must exist; board file may not) → open_context(args, actor=None)
              → verb: names.mint_board_key → plansync.found_board (False → steer(BOARD_EXISTS, existing key))
                      → plansync.apply_sync (the whole plan is `new`, D24) → store.registry_record
                      → Reply(views.format_board(rows, key) + handoff line, hint)
              → settle tail below, minus auto-sync (init just imported) and housekeeping (nothing to reap)
    others ─► 2  resolve_board (D18/D20): --plan | $DIBS_BOARD | upward walk for .*.dibs
                 value tried as board key (registry) first, then as path; many → MANY_BOARDS; none → NO_BOARD
              3  open_context: store.connect + ensure_schema; resolve_actor (--as | $DIBS_AS | None);
                 supplied → queries.verify_actor, unknown → steer(UNKNOWN_ACTOR) (D8); Context.now = one clock
              4  board = queries.board_snapshot; if plan.stat().st_mtime_ns != board.plan_mtime:
                 plansync.apply_sync(conn, now, parse_plan(read plan), mtime)      auto-sync (I9), silent — its
                                                                                   SYNC event is the record
              5  transitions.housekeeping                                          reap stale + refresh lease (D9, I8)
              6  VERB_TABLE[verb](ctx, args) → Reply                               verb's own transaction(s) commit here
    settle tail (init and others):
              7  queries.deliver_events → Reply.events                             piggyback, cursor advanced (D10);
                                                                                   actor None → ()
              8  text = read plan; annotated = planfile.annotate_lines(text, board_snapshot().tasks);
                 if annotated != text: tempfile + os.replace                       (I4; idempotent, so always computed,
                                                                                   written only on change)
 9  print(output.render_reply(reply)); exit 0
except DibsError as e:  stderr ← render_error(e);           exit 1   # steered user error (I10)
except sqlite3.Error:   stderr ← generic + steer "retry";   exit 2   # environment
finally: if $DIBS_TRACE — trace.write_trace(TraceRecord)             # success AND both error paths; best-effort (D23)
```

Notes: a lost claim race is **not** an error — no-arg `claim` auto-picks the next task. A zero-row `claim` is diagnosed by exactly one follow-up read, `queries.claim_refusal`, whose `(Refusal, names)` pair feeds `output.steer` directly: *taken* (bundle member held — names the holder, D6), *gated* (`--task` on a parent with open children — names them, D22), *oversized* (a bundle larger than the hand — names size and hand, offers the first member alone, D6), *hand full* (names held tasks), *waiting* (names who holds what the remaining tasks wait on), *empty*. Correctness rests on the claim statement; the read only words the refusal. `claim` with no identity mints one first (`names.mint_identity`) and the briefing opens with "you are <name>" (D8). `done` follows its transaction with `queries.newly_unlocked` and, if a parent became claimable, its hint is `next_hint('unlocked', (parent_id,))` (D7, D22). `finish`/`release` returning `None` is the verb's one `if … raise` (`steer(NOT_OWNER, (task_id, holder_name))` — the holder comes from the `resolve_task` row read moments earlier). The D23 trace wraps the whole pipeline as a `finally`: parse failures and unresolved boards still produce a line (`verb`/`plan` None), and a trace write failure is swallowed inside `write_trace` — it never touches output or exit codes.

Two `run` shapes pass WPS: two guards on `args.verb` (verify, init) ahead of a shared tail, or a `ROUTES` MappingProxyType of three route functions. Either is fine; what is not fine is a per-verb flag record or a stage framework (rapier).

## 7. Flow of data

```
              parse_plan             compute_sync          plansync.apply_sync (one txn, C11)
plan.md ────► PlanItem[] ──────────► SyncPlan.rows ───────► SQLite  (state truth, D4)
   ▲              ▲                      ▲                     │
   │              │        board_snapshot().tasks ◄────────────┤
   │              │                                            ├── queries.* ──► records ──► views/output ──► stdout
   │         verify: compute_sync(items, ()) → rows → views.format_board   (no DB: D21, D24)
   └────────── annotate_lines ◄── Task[] ◄─────────────────────┘
              (text truth stays in the file; only grammar lines change)
```

## 8. Contracts (C-rules — cite them in code review)

- **C1** — Process edges (argv, env, stdout/stderr, exit codes, `print`, the SQLite version check) exist only in `cli.py`.
- **C2** — SQL text exists only in `store/transitions/plansync/queries`; placeholders only, never string interpolation.
- **C3** — Every public `transitions` and `plansync` function = one transaction opened with `BEGIN IMMEDIATE`; success ⇔ rowcount says so (I1); exactly one event per mutation, same transaction (I6). A sync is one mutation with one SYNC event; each hand-checked import inside it is its own mutation with its own DONE event.
- **C4** — `planfile` is pure: no I/O, no DB, no clock. Plan-file reads and the atomic write (`tempfile` + `os.replace`) happen in `cli.run` (steps 4 and 8) and in the `init`/`sync`/`verify` verbs, via `pathlib` — nowhere else.
- **C5** — All user-facing text lives in `output` (envelope, hints, every error message) and `views` (bodies). Nothing else builds user-facing strings; `DibsError` is constructed only by `output.steer`.
- **C6** — Verbs orchestrate only: ≤10 statements, no SQL, no regex, no formatting, at most one rowcount `if … raise`.
- **C7** — One error channel: `raise output.steer(kind, names)`; `cli` catches `DibsError` and `sqlite3.Error` only. Every steer is a runnable command (I10).
- **C8** — No mutable module state anywhere; state flows through `Context` or lives in the DB.
- **C9** — Decisions branch in SQL, Python reads rowcounts. If a verb grows an if-tree, the WHERE clause is missing something; if a read needs to pick between outcomes, it returns a `Refusal` from a `CASE`.
- **C10** — Every command runs the §6 pipeline in order; housekeeping precedes the verb so `claim` sees freshly reaped tasks.
- **C11** — **Sync reads under the lock it writes with.** `apply_sync` opens `BEGIN IMMEDIATE`, *then* reads `board_snapshot`, *then* computes and writes. Two workers auto-syncing the same edit therefore serialize: the second sees the first's rows and finds nothing new. `compute_sync` is a deterministic function of (snapshot, text), so even the unlocked case would converge; the lock is what keeps a fast second edit from reassigning an id (I5). The UPSERT refreshes only text-cached columns (`seq`, `section`, `parent_id`, `title`, `body`) and never a state column; ids are minted from *all* rows, orphaned included, so an id is never reused (I5).

## 9. Verb → modules → SSoT trace

| Verb | Orchestrates | Implements |
|---|---|---|
| `init` | names.mint_board_key, plansync.found_board + apply_sync, store.registry_record, views.format_board | §6, §8, D4, D20, D24 |
| `verify` | planfile (parse + compute_sync against no rows), views.format_board | D21, D22, D24, §8 |
| `sync` | plansync.apply_sync, views.format_sync | §8, I5, I9, D22, C11 |
| `join` | names.mint_identity | D8 |
| `claim` | names.mint_identity (fallback), transitions.claim, queries.claim_refusal / prior_claim, views.format_briefing | D6, D7, D9, D16, D22, §6 |
| `done` | queries.resolve_task, transitions.finish, queries.newly_unlocked | D11, I2, I4, D22 |
| `drop` | queries.resolve_task, transitions.release | §6, D9 |
| `note` | transitions.record_note | D10 |
| `list` | queries.board_snapshot, views.format_board (child progress `2/3`), Board.events | §6, D14, D22 |

## 10. WPS pre-satisfaction map

| WPS constraint | Answered by |
|---|---|
| Module members ≤ 7 (WPS202) | §3 budgets at or under the cap; the two modules at 7 carry a named split seam |
| Args ≤ 5 (WPS211) | `Context` carries conn/paths/actor/now; verb signature is `(ctx, args)` |
| Locals ≤ 5 (WPS210), complexity caps | ≤10-statement functions; branching pushed into SQL (C9) |
| Magic numbers (WPS432) | Named constants at top of owning module: `REAP_TTL_SECONDS`, `EVENT_CAP`, `ID_DIGITS`… (D3) |
| Overused strings (WPS226) | `Status`/`EventKind` enums; verb names only in `VERB_TABLE`; long SQL strings are unique literals, inherently safe |
| Mutable module constants (WPS407) | tuples + `MappingProxyType` |
| Nested functions/classes | none — flat module functions only |
| Logic in `__init__` (WPS412) | `verbs/__init__.py` is docstring-only; `dibs/__init__.py` holds only `DIBS_VERSION`, which WPS 1.x still counts as logic — sanctioned per-file-ignore (a zipapp has no dist-info to read a version from); `VERB_TABLE` lives in `cli.py` |
| Docstrings + naming bundle | one-line docstrings on every public member; no builtin shadowing (`list_board`, `task_id`) |
| `assert` ban (S101) | asserts only under `tests/` per-file-ignore |
| Seeded PRNG (bandit S311) | production uses `secrets`; the property tier's `random.Random(seed)` is a determinism device, ignored for `tests/*` |

Two linters, two configs, one policy. WPS 1.x dropped the classic bundle, so `setup.cfg` carries WPS only and `pyproject.toml` carries ruff (E/W/F/I/N/D/S/UP/B/C4/SIM/RET/ARG/PTH/RUF/PLR). The test-tree role policy (wps-refactor: rules whose reason the test role satisfies, relaxed once, repo-wide) is therefore spelled in both files, each listing only the codes its linter owns:

```ini
# setup.cfg — flake8 runs WPS only
[flake8]
max-line-length = 80
select = WPS
per-file-ignores =
    dibs/__init__.py: WPS412
    tests/*.py: S101, D, WPS202, WPS204, WPS210, WPS226, WPS432
```

```toml
# pyproject.toml — ruff owns the classic bundle
[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "D", "S311"]
```

`S101`/`D` appear on the flake8 line only for doc parity (flake8 never sees them). `S311` is ruff-only and belongs to the test role: seeded stdlib PRNGs are how the property tier stays reproducible (§11); production minting uses `secrets` and is never in scope. `WPS442` (fixture-name shadowing) may need adding to the flake8 test line once conftest fixtures are consumed by name; extend the line narrowly and record it here — never restructure fixtures around it.

If any other rule fires during implementation, the fix-preference order is: delete code → simplify inline → move to the owning module — never a new layer. A rule that survives all three gets a targeted `# noqa: <code>  # <one-line reason>` and a flag to the maintainer.

## 11. Testing plan (pytest, three tiers)

Fixtures in `conftest.py`: `plan_text` (sample document), `board(tmp_path)` (initialized DB + plan), `two_agents`, `make_board`. Shared builders and raw assertion peeks live in `tests/boards.py`; tiers map to files, not directories.

**Seeding boards.** Until `plansync` lands (§13 step 7) `tests/boards.build_board` seeds rows with a raw `INSERT` from `planfile.compute_sync(parse_plan(text), ()).rows` — the same rows init will insert, computed by the production function. From step 7 on it calls `plansync.found_board` + `apply_sync` and the raw insert is deleted; the test-side `assign_ids`/`task_rows`/`mint_id` mirrors go with it (production `mint_id` and `SyncPlan.rows` replace them at step 5). Peeks (`peek_task`, `peek_events`, `held_ids`, `todo_ids`, `open_children`, `peek_tree`) stay: they are assertion reads, not production paths.

| Tier | Targets | Key cases |
|---|---|---|
| Unit (pure) | `planfile`, `names.pick`, `output`, `views` | §8 recognition table incl. nested checkboxes → `parent_line`, indented prose stays body (D22); annotation grammar; hash normalization; **id minting** — letters by first appearance, ordinals never reused (an orphaned `A2` means the next is `A3`), dotted children, a child under a new parent minted in the same pass, letters past `Z`; `SyncPlan.rows` refreshes seq/section/parent/body and passes state through; event one-liners; every `Refusal` renders a runnable steer; `format_board` renders tree, `2/3` progress, bodiless/duplicate warnings, and the same text for verify's rows as for a snapshot (D21, D22, D24) |
| Property / metamorphic | `planfile`, `transitions` | `annotate_lines` preserves every non-grammar byte (I4) across generated docs; **sync is idempotent in one pass**: apply a computed `SyncPlan`, recompute against the settled text → every field empty, no deferral (the Rev 8 "reparented on the second pass" clause is gone with `mint_id`); minted ids are unique across the applied rows and never collide with orphaned ones; claim order respects affinity→seq (D7); **gating invariant:** a parent is never claimable while any todo/doing child exists, across random trees and completion orders (D22) |
| Integration (tmp DB) | `transitions`, `plansync`, `queries`, `store` | **the CAS race:** two threads claim one task, exactly one wins (I1/I2); bundle all-or-none and must fit the hand (D6); **hand limit:** claim refused at capacity, respawned identity steered back to its held task (D6); **gating:** no-arg claim skips gated parents, explicit `--task` on one is refused naming open children, orphaned children don't block, `claim_refusal` returns each of the six kinds with the right names (D22, D6); `newly_unlocked` fires exactly on the last child's `finish` (D22); `finish` rejects non-owner (I2); TTL reap + lease refresh (D9); `register_agent` UNIQUE retry and join event stamped with `now`; cursor advance (D10); board-key registry record/lookup + self-heal (D20); **plansync:** `found_board` wins once (rowcount, two calls → True/False, one INIT event), `apply_sync` on an empty board inserts every row + imports hand-`[x]` as done by human, a second `apply_sync` on the same text writes nothing but its SYNC event, edits to body/heading/indent/order refresh the cached columns and never a state column, a vanished line orphans, two connections syncing the same edit under `BEGIN IMMEDIATE` converge on one row set (C11) |
| End-to-end | `cli.main` | full loop init→join→claim→done; init prints the key and `--plan <key>` resolves from an unrelated CWD (D20); auto-sync after a human edit (I9); every refusal exits 1 with a `Run:` line; SQLite below the floor exits 1 with the OLD_SQLITE steer (monkeypatched version tuple); assert final plan.md text and exit codes |

Definition of done per module: its tests green **and** `flake8` + `ruff` clean. No module is "done" while either fails. Never delete a case to get green: when a member moves (e.g. `import_author_done` → `apply_sync`), its case moves with it.

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

Steps 1–4 are done (Rev 8 shape). Step 5 brings them to the Rev 9 contracts in §5 before any new module is written; from step 6 on, every step is a new module.

1. ✅ `runtime.py`, `records.py` — types only.
2. ✅ `store.py` — schema + pragmas + key registry.
3. ✅ `planfile.py` — parse/annotate/diff; I4 property tests.
4. ✅ `transitions.py` — CAS claim, race + hand-limit tests, then the rest.
5. **Rev 9 amendments to 1–4** (one step, one commit): `records.Board`; `planfile.SyncPlan` → `rows/new/vanished/checked/regressed` (delete `reordered`, `reparented`), `planfile.mint_id`, `compute_sync` minting in one pass, docstring deferral clause removed; `transitions.register_agent(conn, agent, now)` (`JOIN_EVENT_SQL`/`AGENT_SQL` take `?3`), `finish`/`release` docstrings state the `None` contract; `tests/boards.py` builds rows from `compute_sync(items, ()).rows` and drops `assign_ids`/`task_rows`; `test_property_planfile` drops its `pair`/`mint_id`/`deferred_by_new_parent` mirrors and asserts one-pass idempotence; `test_planfile` gains the minting cases. `import_author_done` stays until step 7 takes its case.
6. `queries.py` — `board_snapshot → Board`, `deliver_events` cursor semantics, `resolve_task(conn, raw, verb)`, `claim_refusal` (six kinds; raises need `output.Refusal` + `steer`, so land those two `output` members here, stubs for the rest).
7. `plansync.py` — `found_board`, `apply_sync` (C11); delete `transitions.import_author_done` and move its test; `tests/boards.build_board` switches to `apply_sync`.
8. `names.py` — `mint_identity(conn, now)` retry loop + board keys.
9. `output.py` + `views.py` — envelope, caps, hint and steer catalogs; `format_board`/`format_briefing`/`format_sync`.
10. `verbs/` — thin orchestration over 5–9; `verify_board(args)` is the one pure verb.
11. `cli.py`, `__main__.py`, `trace.py` — pipeline §6 with the three routes and the D23 trace; end-to-end + trace tests.
12. zipapp build; smoke-test `dibs.pyz` on PATH.

Steps 5–11 are `plan.md`-ready tasks with complete briefings — once step 7 lands, dibs can be dogfooded to build the rest of dibs.
