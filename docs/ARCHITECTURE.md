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

**Design strategy that makes WPS pass by construction:**

1. Every module has a **member budget ≤ 6** (one under the cap; `transitions.py` sits at 7 by exception, see §3).
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

## 3. Package layout with member budgets

Member = top-level function or class (constants don't count). Budgets are the plan, not a hope: an implementation that needs one more member in a module stops and flags instead of exceeding.

```
dibs/
├── __init__.py     DIBS_VERSION constant only                     [0]  L—
├── __main__.py     zipapp/module entry → cli.main()               [0]  L5
├── runtime.py      Context, Reply, DibsError                      [3]  L0
├── records.py      Status, EventKind, Task, Event, Agent          [5]  L0
├── store.py        connect, ensure_schema, registry_record,
│                   registry_lookup  (+SCHEMA, PRAGMAS)            [4]  L1
├── planfile.py     PlanItem, SyncPlan, parse_plan,
│                   compute_sync, annotate_lines, title_hash       [6]  L1
├── output.py       render_reply, render_error,
│                   format_event, next_hint, format_preview        [5]  L1
├── trace.py        TraceRecord, trace_path, write_trace
│                   (+TRACE_DIR, OUTCOME_CAP) — D23 lens           [3]  L1
├── transitions.py  claim, finish, release, housekeeping,
│                   record_note, import_author_done,
│                   register_agent                                 [7]* L2
├── queries.py      board_snapshot, deliver_events, prior_claim,
│                   resolve_task, verify_actor, newly_unlocked     [6]  L2
├── names.py        mint_identity, mint_board_key
│                   (+ADJECTIVES, ANIMALS tuples)                  [2]  L3
├── cli.py          main, build_parser, resolve_actor,
│                   resolve_board (+VERB_TABLE: MappingProxyType)  [4]  L5
└── verbs/
    ├── __init__.py empty (WPS bans logic in __init__)             [0]  L—
    ├── work.py     join_session, claim_task, done_task, drop_task [4]  L4
    └── board.py    init_board, sync_board, note_verb, list_board,
                    verify_board                                   [5]  L4
```

\* `transitions.py` is **at the cap by design**. The first new write transition forces a split into two write modules (e.g., `transitions_work.py` / `transitions_plan.py`) — do **not** raise the limit and do not add it elsewhere.

The package sits at 15 files — exactly the SSoT §2 file budget. The next new module is a stop-and-re-scope flag, not a 16th file.

`list_board`, `task_id`, `agent_id`: builtin shadowing (`list`, `id`) is banned by the naming rules; these are the canonical replacements everywhere.

## 4. Layering — allowed import direction

A module imports only **strictly lower** levels (plus stdlib). No cycles, mechanically checkable by eye:

| Level | Modules | May import |
|---|---|---|
| L0 | `runtime`, `records` | stdlib only |
| L1 | `store`, `planfile`, `output`, `trace` | L0 |
| L2 | `transitions`, `queries` | L0–L1 |
| L3 | `names` | L0–L2 (uses `transitions.register_agent`) |
| L4 | `verbs/*` | L0–L3 |
| L5 | `cli`, `__main__` | L0–L4 |

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
class Agent:   agent_id, name

# runtime.py — execution plumbing. Zero internal imports.
@dataclass(frozen=True)
class Context: conn, plan_path, db_path, actor, now              # actor: str | None
@dataclass(frozen=True)
class Reply:   lines: tuple[str, ...], events: tuple[Event, ...], hint: str
class DibsError(Exception): message: str, steer: str             # steer = literal next command (D14, I10)

# store.py
def connect(db_path) -> Connection        # applies PRAGMAS: WAL, busy_timeout=5000, foreign_keys (D2)
def ensure_schema(conn) -> None           # SSoT §5 tables + meta(key, value): board_key, max_hand, plan_mtime, schema_version
def registry_record(key, plan_path) -> None   # write-once file in ~/.local/state/dibs/ (D20); self-heal on drift
def registry_lookup(key) -> Path | None       # key → absolute plan path, or None if unknown/stale

# transitions.py — every public function: exactly ONE transaction,
# outcome = rowcount truth (I1), exactly one event appended on success (I6).
def claim(conn, actor, now, task_ids=None) -> tuple[Task, ...]   # affinity→seq (D7) or exact bundle all-or-none (D6);
                                                                 # hand limit enforced via holdings subquery in the same
                                                                 # WHERE (max_hand from meta); gating too — NOT EXISTS an
                                                                 # open (todo/doing) child (D22); refusal diagnostics come
                                                                 # from a follow-up read (hand full / waiting / empty),
                                                                 # correctness from the statement
def finish(conn, actor, now, task_id, note) -> Task              # WHERE owner=:actor (I2); annotgrammar note
def release(conn, actor, now, task_id, note) -> Task             # drop → todo
def housekeeping(conn, actor, now) -> tuple[Event, ...]          # reap stale by TTL + refresh caller lease (D9)
def record_note(conn, actor, now, text, to_name=None) -> Event   # broadcast / directed (D10)
def import_author_done(conn, now, task_id) -> Task               # sync: hand-checked [x] → done by 'human' (§8 SSoT)
def register_agent(conn, agent) -> bool                          # INSERT; False on UNIQUE collision (I1)

# queries.py — reads (deliver_events also advances the cursor: one txn, honest piggyback).
def board_snapshot(conn) -> tuple[Task, ...]
def deliver_events(conn, actor) -> tuple[Event, ...]             # unseen for actor, cursor advanced (D10)
def prior_claim(conn, task_id) -> Event | None                   # reap-history warning on re-claim (§6 SSoT)
def resolve_task(conn, raw) -> Task                              # exact → fuzzy; miss raises DibsError with steer
def verify_actor(conn, actor) -> bool                            # supplied identity must exist on THIS board (D8, D18)
def newly_unlocked(conn, task_id) -> Task | None                 # parent of task_id if this done made it claimable (D22, D7)

# planfile.py — PURE: text in, records out. No I/O, no DB, no clock.
@dataclass(frozen=True) class PlanItem: line_no, parent_line, checkbox, title, body, section   # parent_line: nearest
                                                                                                 # less-indented checkbox (D22)
@dataclass(frozen=True) class SyncPlan: new, vanished, checked, reordered,
                                        reparented, regressed    # §8 rows: 're-indented' and '[ ] over doing/done'
def parse_plan(text) -> tuple[PlanItem, ...]                     # SSoT §8 recognition
def compute_sync(plan_items, tasks) -> SyncPlan                  # hash-matched diff (§8 sync table); 'items' trips WPS110
def annotate_lines(text, tasks) -> str                           # rewrites ONLY grammar lines (I4)
def title_hash(title) -> str                                     # normalized (lowercase, collapsed whitespace)

# names.py
def mint_identity(conn) -> Agent                                 # pick + register_agent retry loop (D8, §7 SSoT)
def mint_board_key() -> str                                      # 'dibs-' + 8 hex chars in two groups (D20)

# output.py — the only formatter; owns terseness caps (D14).
def render_reply(reply) -> str                                   # result lines + events (one line each, capped) + hint
def render_error(err) -> str                                     # "<message>\nRun: <steer>"
def format_event(event) -> str
def next_hint(verb, context_bits) -> str                         # template lookup
def format_preview(plan_items) -> tuple[str, ...]                # verify view: sections, would-be IDs, titles, body
                                                                 # presence + inline warnings (bodiless, duplicate
                                                                 # titles) computed here, not in verbs (C5/C6, D21)

# trace.py — the D23 debugging lens. Never truth, never read back; env read stays in cli (C1).
@dataclass(frozen=True) class TraceRecord: ts, argv, actor, plan, verb, exit_code, outcome
def trace_path(plan_path, now) -> Path       # .logs/<plan-name>.<UTC date>.jsonl; unbound fallback under CWD
def write_trace(path, record) -> None        # append one JSON line, mkdir as needed; best-effort, NEVER raises

# verbs/*.py — orchestration only: (ctx, args) -> Reply. ≤10 statements each.
def claim_task(ctx, args) -> Reply       # etc. — one function per SSoT §6 verb

# cli.py
def main(argv=None) -> int               # the pipeline (§6 below); the ONLY process-edge module
def build_parser() -> ArgumentParser     # tolerant forms: --task A3 / --task=A3 / positional (D14); global --plan
def resolve_actor(args) -> str | None    # --as, else $DIBS_AS, else None
def resolve_board(args) -> tuple[Path, Path]   # (plan, .{plan}.dibs): --plan | $DIBS_BOARD | upward walk;
                                               # value may be a board key (store.registry_lookup first, D20)
                                               # or a path; many → enumerating DibsError; none → cd/--plan steer (D18)
```

## 6. Flow of operations — the per-command pipeline

Every invocation runs the same pipeline; verbs never skip steps (C10).

```
main(argv):
 1  build_parser().parse_args()                → verb + args
 2  cli.resolve_board (D18/D20): --plan | $DIBS_BOARD | upward walk for .*.dibs
      value tried as board key (registry) first, then as path
      many → DibsError enumerating runnable steers; none → steer "cd or --plan"
      (init only as an author aside — workers never steered into creating boards)
 3  store.connect + ensure_schema
 4  resolve_actor: --as | $DIBS_AS | None; if supplied → queries.verify_actor,
      unknown → DibsError "identity not on this board" + board-check steer (D8)
 5  auto-sync: meta.plan_mtime ≠ file mtime    → run sync path first (I9); skipped by `init`
 6  transitions.housekeeping                    reap stale + refresh caller lease (D9, I8)
 7  VERB_TABLE[verb](ctx, args) → Reply         verb's own transaction(s) commit here
 8  queries.deliver_events → Reply.events       piggyback, cursor advanced (D10)
 9  if state changed: read plan.md →
    planfile.annotate_lines → write plan.md     (I4; write via tempfile + os.replace)
10  print(output.render_reply(reply)); exit 0
except DibsError as e:  stderr ← render_error(e);           exit 1   # steered user error (I10)
except sqlite3.Error:   stderr ← generic + steer "retry";   exit 2   # environment
finally: if $DIBS_TRACE — trace.write_trace(TraceRecord)             # success AND both error paths; best-effort (D23)
```

Notes: a lost claim race is **not** an error — no-arg `claim` auto-picks the next task; a partial bundle raises `DibsError` naming the taken member (D6). A zero-row claim is diagnosed by one follow-up read into three distinct steers — *hand full* (names held tasks), *nothing available yet* (names what the remaining tasks wait on; D22), *board empty* — with correctness resting on the statement (D6). `done` follows its transaction with `queries.newly_unlocked` and, if a parent became claimable, appends a ready `claim --task` hint to the reply (D7, D22). `init` bypasses steps 5–6 (no DB yet), mints + registers the board key (D20), and step 9 runs unconditionally for it. `verify` runs only step 1 plus a pure parse-and-render — no board resolution, no DB, no identity, no annotation (D21); a hand-full check does not apply to it. The D23 trace wraps the whole pipeline as a `finally`: parse failures and unresolved boards still produce a line (`verb`/`plan` None), and a trace write failure is swallowed inside `write_trace` — it never touches output or exit codes.

## 7. Flow of data

```
           parse_plan              compute_sync            transitions.*
plan.md ──► PlanItem[] ──┐       ┌──► SyncPlan ──────────► SQLite  (state truth, D4)
   ▲                     └─diff──┘                            │
   │                                                          ├── queries.* ──► records ──► output ──► stdout
   └────────── annotate_lines ◄── Task[] ◄────────────────────┘
              (text truth stays in the file; only grammar lines change)
```

## 8. Contracts (C-rules — cite them in code review)

- **C1** — Process edges (argv, env, stdout/stderr, exit codes, `print`) exist only in `cli.py`.
- **C2** — SQL text exists only in `store/transitions/queries`; placeholders only, never string interpolation.
- **C3** — Every public `transitions` function = one transaction; success ⇔ rowcount says so (I1); exactly one event per success, same transaction (I6).
- **C4** — `planfile` is pure: no I/O, no DB, no clock. File reads/writes happen in verbs via `pathlib` (two calls: read, atomic write).
- **C5** — All formatting and terseness caps live in `output` (D14). Nothing else builds user-facing strings.
- **C6** — Verbs orchestrate only: ≤10 statements, no SQL, no regex, no formatting.
- **C7** — One error channel: raise `DibsError(msg, steer)`; `cli` catches `DibsError` and `sqlite3.Error` only. Every steer is a runnable command (I10).
- **C8** — No mutable module state anywhere; state flows through `Context` or lives in the DB.
- **C9** — Decisions branch in SQL, Python reads rowcounts. If a verb grows an if-tree, the WHERE clause is missing something.
- **C10** — Every command runs the §6 pipeline in order; housekeeping precedes the verb so `claim` sees freshly reaped tasks.

## 9. Verb → modules → SSoT trace

| Verb | Orchestrates | Implements |
|---|---|---|
| `init` | store (schema + registry), names.mint_board_key, planfile, transitions, output | §6, §8, D4, D20 |
| `verify` | planfile, output (tree + waits-for) | D21, D22, §8 |
| `sync` | planfile, transitions (`import_author_done`), output | §8, I5, I9, D22 |
| `join` | names, output | D8 |
| `claim` | transitions.claim, queries.prior_claim, output | D6, D7, D9, D16, D22, §6 |
| `done` | queries.resolve_task, transitions.finish, queries.newly_unlocked, planfile annotate | D11, I2, I4, D22 |
| `drop` | transitions.release | §6, D9 |
| `note` | transitions.record_note | D10 |
| `list` | queries.board_snapshot, output (child progress `2/3`) | §6, D14, D22 |

## 10. WPS pre-satisfaction map

| WPS constraint | Answered by |
|---|---|
| Module members ≤ 7 (WPS202) | §3 budgets, one under cap; `transitions` split-trigger |
| Args ≤ 5 (WPS211) | `Context` carries conn/paths/actor/now; verb signature is `(ctx, args)` |
| Locals ≤ 5 (WPS210), complexity caps | ≤10-statement functions; branching pushed into SQL (C9) |
| Magic numbers (WPS432) | Named constants at top of owning module: `REAP_TTL_SECONDS`, `EVENT_CAP`, `ID_DIGITS`… (D3) |
| Overused strings (WPS226) | `Status`/`EventKind` enums; verb names only in `VERB_TABLE`; long SQL strings are unique literals, inherently safe |
| Mutable module constants (WPS407) | tuples + `MappingProxyType` |
| Nested functions/classes | none — flat module functions only |
| Logic in `__init__` (WPS412) | `verbs/__init__.py` is docstring-only; `dibs/__init__.py` holds only `DIBS_VERSION`, which WPS 1.x still counts as logic — sanctioned per-file-ignore (a zipapp has no dist-info to read a version from); `VERB_TABLE` lives in `cli.py` |
| Docstrings + naming bundle | one-line docstrings on every public member; no builtin shadowing (`list_board`, `task_id`) |
| `assert` ban (S101) | asserts only under `tests/` per-file-ignore |

`setup.cfg` — start from the wemake documented flake8+isort baseline; the only project deviations (rationales in setup.cfg):

```ini
[flake8]
max-line-length = 80
select = WPS                  # WPS 1.x split: ruff carries the classic bundle
per-file-ignores =
    dibs/__init__.py: WPS412
    tests/*.py: S101, D, WPS202, WPS204, WPS210, WPS226, WPS432
```

If any other rule fires during implementation, the fix-preference order is: delete code → simplify inline → move to the owning module — never a new layer. A rule that survives all three gets a targeted `# noqa: <code>  # <one-line reason>` and a flag to the maintainer.

## 11. Testing plan (pytest, three tiers)

Fixtures in `conftest.py`: `plan_text` (sample document), `board(tmp_path)` (initialized DB + plan), `two_agents`.

| Tier | Targets | Key cases |
|---|---|---|
| Unit (pure) | `planfile`, `names.pick`, `output` | §8 recognition table incl. nested checkboxes → `parent_line`, indented prose stays body (D22); annotation grammar; hash normalization; event one-liners; `verify` rendering incl. tree/waits-for and bodiless/duplicate-title warnings (D21, D22) |
| Property / metamorphic | `planfile`, `transitions` | `annotate_lines` preserves every non-grammar byte (I4) across generated docs; `sync` is idempotent; claim order respects affinity→seq (D7); **gating invariant:** a parent is never claimable while any todo/doing child exists, across random trees and completion orders (D22) |
| Integration (tmp DB) | `transitions`, `queries`, `store` | **the CAS race:** two threads claim one task, exactly one wins (I1/I2); bundle all-or-none and must fit the hand (D6); **hand limit:** claim refused at capacity, respawned identity steered back to its held task (D6); **gating:** no-arg claim skips gated parents, explicit `--task` on one is refused naming open children, orphaned children don't block, three distinct zero-row diagnoses (D22, D6); `newly_unlocked` fires exactly on the last child's `finish` (D22); `finish` rejects non-owner (I2); TTL reap + lease refresh (D9); `register_agent` UNIQUE retry; cursor advance (D10); board-key registry record/lookup + self-heal (D20) |
| End-to-end | `cli.main` | full loop init→join→claim→done; init prints the key and `--plan <key>` resolves from an unrelated CWD (D20); assert final plan.md text and exit codes |

Definition of done per module: its tests green **and** `flake8` clean. No module is "done" while either fails.

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

1. `runtime.py`, `records.py` — types only.
2. `store.py` — schema + pragmas + key registry; test: pragmas active, schema idempotent, registry record/lookup.
3. `planfile.py` — parse/annotate/diff; the property tests land here (I4 is the crown jewel).
4. `transitions.py` — CAS claim first, with the two-thread race and hand-limit tests; then the rest.
5. `queries.py` — deliver_events cursor semantics.
6. `names.py` — mint retry loop + board keys.
7. `output.py` — caps, hints, steering errors.
8. `verbs/` — thin orchestration over 1–7.
9. `cli.py`, `__main__.py`, `trace.py` — pipeline §6 with the D23 trace; end-to-end + trace tests.
10. zipapp build; smoke-test `dibs.pyz` on PATH.

Steps 3–9 are `plan.md`-ready tasks with complete briefings — once step 4 lands, dibs can be dogfooded to build the rest of dibs.
