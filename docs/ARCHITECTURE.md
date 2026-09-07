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
4. **Data in frozen dataclasses and str-enums; behavior in module functions.** No behavior classes, no methods to count, no inheritance beyond `Enum` — with one receipted exception: `cli.Parser(ArgumentParser)` overrides `error`, argparse's documented funnel for *every* usage failure, so a malformed invocation becomes `output.steer(BAD_USAGE, …)` like any other refusal (SSoT §6). The receipt is an external contract: on Python 3.10–3.11 no function-shaped hook exists (`exit_on_error=False` misses the required-argument and unrecognized-argument paths), and `error` is the one method argparse guarantees to call. One class, one method, no state.
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
├── __main__.py     zipapp/module entry → cli.main()               [0]  L6
├── runtime.py      Context, Reply, DibsError                      [3]  L0
├── records.py      Status, EventKind, Task, Event, Agent, Board,
│                   agent_name                                     [7]* L0
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
│                   resolve_board, Parser (argparse's error funnel)
│                   (+VERB_TABLE, DEFAULTS: MappingProxyType)      [6]  L5
└── verbs/
    ├── __init__.py empty (WPS bans logic in __init__)             [0]  L—
    ├── work.py     join_session, claim_task, done_task, drop_task [4]  L4
    └── board.py    init_board, sync_board, note_verb, list_board,
                    verify_board                                   [5]  L4
```

\* **At the cap (7), with the split seam named.** `planfile.py`: the md→db half (`PlanItem`, `SyncPlan`, `parse_plan`, `compute_sync`, `mint_id`, `title_hash`) and the db→md half (`annotate_lines`, which would take `LINE_RE` and `LINE_FORMS` with it) — the D4 direction seam. `queries.py`: pipeline reads (`board_snapshot`, `deliver_events`, `verify_actor`) and verb-context reads (`prior_claim`, `resolve_task`, `newly_unlocked`, `claim_refusal`). `records.py`: rows (`Task`, `Event`, `Agent`, `Board`) and vocabulary (`Status`, `EventKind`, `agent_name`). No split is wanted today; each is written down so that an 8th member has exactly one honest move.

All three pass the wps-refactor homogeneity test — every member of `planfile` is a pure text↔record function, every member of `queries` a read returning records, every member of `records` a zero-logic row type or the one idiom that names its actor — which is why 7 is a budget here and not a debt. `cli.py` is at 6 with two kinds of member — the pipeline (`main`, `run`, `open_context`) and argv (`build_parser`, `Parser`, `resolve_board`) — so its seam is named too: a 7th member splits argv into `argv.py`, and C1 then reads "cli and argv".

The package sits at 17 files against the SSoT §2 budget of 18. The 18th is the last; the 19th is a stop-and-re-scope flag. `plansync.py` and `views.py` are the two splits §2 predicts along the role seam, made when their concepts arrived (Rev 9) rather than when a counter tripped. Since Rev 11 the member budgets, the layering table (§4), the file count, and the SSoT §2 line ceiling are asserted by `tests/test_architecture.py` (§11): a budget that drifts fails the suite, not a review.

`list_board`, `task_id`, `agent_id`: builtin shadowing (`list`, `id`) is banned by the naming rules; these are the canonical replacements everywhere. Display names derive from ids by one idiom, `records.agent_name` (`agent_id.rsplit('-', 1)[0]`, the SSoT §7 grammar `name-NNNN`), used at three render sites: `planfile.annotate_lines`, `output.format_event`, `views.format_board`.

## 4. Layering — allowed import direction

A module imports only **strictly lower** levels (plus stdlib). No cycles, mechanically checkable by eye:

| Level | Modules | May import |
|---|---|---|
| L0 | `runtime`, `records` | stdlib only |
| L1 | `store`, `planfile`, `output`, `views`, `trace` | L0 |
| L2 | `transitions`, `queries` | L0–L1 (`queries` raises through `output.steer`) |
| L3 | `names`, `plansync` | L0–L2 (`names` uses `transitions.register_agent`; `plansync` reads through `queries.board_snapshot` inside its own write transaction — see C11) |
| L4 | `verbs/*` | L0–L3 |
| L5 | `cli` | L0–L4 |
| L6 | `__main__` | `cli` only — the entry stub (`sys.exit(cli.main())`) sits above the composition root, so the strict rule has no same-level exception |

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
def agent_name(agent_id) -> str                                  # 'happy-elephant-4821' -> 'happy-elephant' (I7); 'human'
                                                                 # and 'system' pass through; None -> '' (the one idiom, §3)

# runtime.py — execution plumbing. Zero internal imports.
@dataclass(frozen=True)
class Context: conn, plan_path, db_path, actor, now              # actor: str | None; now: int (UTC seconds), the ONE clock
@dataclass(frozen=True)
class Reply:   lines: tuple[str, ...], events: tuple[Event, ...], hint: str
class DibsError(Exception): message: str, steer: str             # steer = literal next command (D14, I10)

# store.py
def connect(db_path) -> Connection        # applies PRAGMAS: WAL, busy_timeout=5000, foreign_keys (D2)
def ensure_schema(conn) -> None           # SSoT §5 tables + meta(key, value): board_key, max_hand, plan_mtime, schema_version
def registry_record(key, plan_path) -> None   # key -> absolute plan path under ~/.local/state/dibs/ (D20): a no-op
                                              # on an empty key (unfounded board) and when the recorded path already
                                              # matches (read, compare, then write) — so every board command may
                                              # call it and only drift, i.e. a moved plan, causes a write
def registry_lookup(key) -> Path | None       # key → absolute plan path, or None if unknown/stale

# planfile.py — PURE: text in, records out. No I/O, no DB, no clock.
@dataclass(frozen=True) class PlanItem: line_no, parent_line, checkbox, title, body, section   # parent_line: nearest
                                                                                                 # less-indented checkbox (D22)
@dataclass(frozen=True) class SyncPlan:
    rows: tuple[Task, ...]        # EVERY checkbox line as the row it should be, in document order: a paired line is its
                                  # DB row with the text-cached columns refreshed (seq, section, parent_id, title, body);
                                  # an unpaired line is a fresh row (mint_id): todo and unowned, or done by human when
                                  # hand-checked — the one state the diff itself decides, so verify previews what init
                                  # creates (D21, D24). Every other state column passes through untouched; apply_sync
                                  # only stamps done_at (and the DONE event) on `checked` (D4).
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
def record_note(conn, actor, now, text, to_name=None) -> Event | None   # broadcast / directed (D10); the INSERT's
                                                                 # WHERE requires the audience to exist (agents.name
                                                                 # or id) or be absent — None ⇔ zero rows, and the
                                                                 # verb raises steer(UNKNOWN_AUDIENCE, (name, text))
def register_agent(conn, agent, now) -> bool                     # INSERT + join event stamped `now` (I6 — one clock per
                                                                 # invocation, never the SQLite clock); False on UNIQUE (I1)

# plansync.py — AUTHOR writes: the md→db direction of D4. Same one-transaction / one-event contract as transitions.
def found_board(conn, now, key, max_hand) -> bool                # UPDATE meta SET value=:key WHERE key='board_key' AND
                                                                 # value='' — rowcount 0 ⇔ already founded (init refuses,
                                                                 # steering to sync); sets max_hand; one INIT event
def apply_sync(conn, now, plan_items, plan_mtime) -> SyncPlan    # under the write lock: board_snapshot → compute_sync →
                                                                 # UPSERT every row (insert fresh; on conflict refresh only
                                                                 # the text-cached columns) → orphan vanished → stamp
                                                                 # done_at on checked (one done event each; the rows
                                                                 # already say done by human) → one SYNC event carrying
                                                                 # the summary, ONLY when the diff is non-empty (a
                                                                 # no-op sync journals nothing, SSoT §8) → stamp
                                                                 # plan_mtime. Returns the SyncPlan it applied (facts
                                                                 # for views). Init IS this on an empty board (D24).

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
    UNKNOWN_AUDIENCE,                                            # note --for a name no agent here carries (SSoT §6)
    BOARD_EXISTS, NO_BOARD, MANY_BOARDS, UNKNOWN_ACTOR,
    BAD_USAGE,                                                   # (message, verb): the parser's one-line message, the
                                                                 # verb's canonical form from USAGE (SSoT §6); verb ''
                                                                 # when no verb parsed → the generic form
    OLD_SQLITE, DB_ERROR                                         # environment: the floor, and sqlite3.Error (exit 2)
def render_reply(reply) -> str                                   # lines + events (one line each, capped) + hint; empty
                                                                 # parts vanish, so `join` prints exactly the bare id
def render_error(err) -> str                                     # "<message>\nRun: <steer>"
def format_event(event) -> str                                   # one line; agent shown by NAME (I7)
def next_hint(moment, names) -> str                              # HINTS[moment].format(*names); moments: claim, done,
                                                                 # unlocked, drop, note, sync, verify, init, list — each
                                                                 # a runnable command (D14); no 'empty' moment: EMPTY
                                                                 # is a refusal, and a refusal carries its own steer
def steer(kind, names) -> DibsError                              # CATALOG[kind] = (message, command) templates; positional
                                                                 # slots documented per entry; the one DibsError factory (C7).
                                                                 # Two constants word verb-shaped steers: VERB_FORMS (the
                                                                 # id-taking verbs with the id slot, for UNKNOWN_TASK) and
                                                                 # USAGE (every verb's canonical runnable form, for
                                                                 # BAD_USAGE: `dibs done <ID> --note "..."`, `dibs claim`…)

# views.py — multi-line bodies, records in → tuple[str, ...] out. No caps here (output's job), no DB.
def format_board(tasks, key) -> tuple[str, ...]                  # list AND verify AND init's roster: key header when key
                                                                 # is non-empty, sections, ids, state, owner name, child
                                                                 # progress `2/3` on gated parents (D22); inline warnings —
                                                                 # bodiless (body == ''), duplicate titles (repeated
                                                                 # text_hash) — computed here, not in verbs (C5/C6, D21)
def format_briefing(tasks, actor_id, priors, minted=False) -> tuple[str, ...]
                                                                 # claim: "you are <id>" (SSoT §6 id reminder, I7: the
                                                                 # owner's own I/O), with " - export DIBS_AS=<id>" when this
                                                                 # call minted it (D8), "claimed A2: <title>", body
                                                                 # indented, "previously claimed by … reaped …" per prior.
                                                                 # LIVE_BOARD (a constant) is verify's one-line "this plan
                                                                 # already has a board" (D21)
def format_sync(plan) -> tuple[str, ...]                         # counts + ids for new/orphaned/imported + regressed
                                                                 # warnings; the same text is the SYNC event's body

# trace.py — the D23 debugging lens. Never truth, never read back; env read stays in cli (C1).
@dataclass(frozen=True) class TraceRecord: ts, argv, actor, plan, verb, exit_code, outcome
def trace_path(plan_path, now) -> Path       # .logs/<plan-name>.<UTC date>.jsonl; unbound fallback under CWD
def write_trace(path, record) -> None        # append one JSON line, mkdir as needed; best-effort, NEVER raises

# verbs/*.py — orchestration only: (ctx, args) -> Reply. ≤10 statements each; at most one rowcount `if … raise`.
def claim_task(ctx, args) -> Reply       # etc. — one function per SSoT §6 verb
def verify_board(args) -> Reply          # the one pure verb: no ctx (D21) — read, parse, compute_sync(items, ()),
                                         # views.format_board(plan.rows, ''); if the board file exists, one line
                                         # (views.LIVE_BOARD, selected not formatted) and the hint points to list
def join_session(ctx, _args) -> Reply    # ctx.actor is None by route (identity-free, D8): Reply is the bare id, no
                                         # hint, and the settle tail delivers nothing
def note_verb(ctx, args) -> Reply        # record_note None → its one `if … raise`: steer(UNKNOWN_AUDIENCE, (name, text))

# cli.py — the ONLY process-edge module
def main(argv=None) -> int               # args = Namespace(**DEFAULTS) before the try; the ONE try statement is
                                         # text = render_reply(run(build_parser().parse_args(argv, args))) — argparse
                                         # fills that namespace in place, so a parse failure still traces: verb None
                                         # (or the subparser's name, which argparse stamps before parsing its
                                         # arguments), plan None, actor as $DIBS_AS said; except DibsError → 1,
                                         # sqlite3.Error → 2; finally trace (§6). -h exits 0 through argparse untouched.
def run(args) -> Reply                   # the §6 route table: verify (pure) | board verbs — open_context with actor None
                                         # for the identity-free verbs (init, join), args.actor otherwise — then the
                                         # settle tail
def open_context(args, actor) -> Context # connect + ensure_schema + verify_actor (when actor given) + registry
                                         # self-heal + auto-sync (unless the verb is an importer: init, sync) +
                                         # housekeeping — §6 steps 3-5: what makes a Context ready for a verb
def build_parser() -> Parser             # tolerant forms: --task A3 / --task=A3 / positional (D14); global --plan and
                                         # --as, whose defaults are $DIBS_BOARD and $DIBS_AS read at build time (the
                                         # env fallback lives in the parser, not in a resolver); subparsers are
                                         # Parser too (parser_class=Parser). No set_defaults: the slot defaults
                                         # (DEFAULTS — task, note, to_name, text, max_hand, plan_path, verb) travel
                                         # in the namespace main hands to parse_args, and DEFAULTS never names an
                                         # env-backed dest (plan, actor): an attribute already on the namespace
                                         # makes argparse skip that action's default
class Parser(ArgumentParser)             # the one subclass (§1): error(message) raises steer(BAD_USAGE, (message,
    def error(self, message) -> NoReturn #   verb)) — verb from self.prog ('dibs done' → 'done', 'dibs' → '') — so a
                                         #   usage error is a refusal with the verb's form, exit 1 (SSoT §6)
def resolve_board(args) -> tuple[Path, Path]   # (plan, .{plan}.dibs): --plan (already env-backed) | upward walk;
                                               # value may be a board key (store.registry_lookup first, D20)
                                               # or a path; many → MANY_BOARDS steer; none → NO_BOARD (D18); a
                                               # path whose board file is missing → NO_BOARD naming `init` (authors
                                               # use paths, D20) — except for `init`, which needs only the plan
```

Signature changes against Rev 8, all landed by §13 step 5 before any new module is written: `SyncPlan` reshaped (`rows`, `new` as ids; `reordered`/`reparented` deleted — subsumed by the UPSERT), `mint_id` added, `register_agent(conn, agent, now)`, `mint_identity(conn, now)`, `finish`/`release` documented as `Task | None`, `import_author_done` deleted (its case moves to `plansync.apply_sync`), `board_snapshot` returns `Board`, `resolve_task` takes `verb`, `format_preview` replaced by `views.format_board`, `next_hint(verb, context_bits)` becomes `next_hint(moment, names)`.

Rev 11 changes (§13 steps 13–15, against the landed steps 10–12): `cli.Parser` added and `cli.resolve_actor` deleted (its concept is the parser's `--as` default); `record_note` returns `Event | None`; `apply_sync` journals only a non-empty diff; `registry_record` is drift-only; `Refusal` gains `UNKNOWN_AUDIENCE` and `BAD_USAGE` and `HINTS` loses `empty`. Already landed at steps 10–12 and sanctioned here: `Refusal.DB_ERROR`, `HINTS['verify']`, `format_briefing(…, minted)`, `views.LIVE_BOARD`, `records.agent_name`, and `open_context` owning §6 steps 3–5. Rev 12 (docs only, after step 14 landed): no signature changes; `__main__` gets its own level L6 (§4) so the layering test needs no exception, and §11 / §13 step 14 record the two test moves step 14 made beyond its list.

## 6. Flow of operations — the per-command pipeline

Every invocation runs the same pipeline; verbs never skip steps (C10). Three routes exist, and `cli.run` is the only place that knows which verb takes which — verbs and lower modules never branch on a verb name.

```
main(argv):
 0  args = Namespace(**DEFAULTS); now = one clock             the slot defaults, and the trace's fallback
 1  build_parser().parse_args(argv, args)          → fills args in place: env-backed --plan/--as first (only
                                                     where the namespace lacks the attribute), then argv; a
                                                     usage error is Parser.error →
                                                     steer(BAD_USAGE, (message, verb)) — a refusal like any
                                                     other (SSoT §6); -h/--help exits 0 through argparse
    run(args):
    sqlite3.sqlite_version_info < (3, 35)          → steer(OLD_SQLITE)   (§1 floor; exit 1, not a "retry")
    verify ─► pure route: read plan → parse_plan → compute_sync(items, ()) → views.format_board(rows, '')
              no board resolution, no DB, no identity, no annotation (D21); board file exists → LIVE_BOARD
              line, hint → list
    board verbs ─►
              2  resolve_board (D18/D20): --plan (its default is $DIBS_BOARD) | upward walk for .*.dibs
                 value tried as board key (registry) first, then as path; many → MANY_BOARDS; none → NO_BOARD;
                 init needs only the plan, every other verb the board file too
              3  open_context(args, actor): actor is None for the identity-free verbs — init (the author's
                 command) and join (mints, never acts; D8) — and args.actor otherwise (--as, default $DIBS_AS);
                 store.connect + ensure_schema; a supplied actor → queries.verify_actor, unknown →
                 steer(UNKNOWN_ACTOR) (D8); board = queries.board_snapshot; store.registry_record(board.key,
                 plan) — the D20 self-heal, a no-op unless the registry drifted; Context.now = one clock
              4  unless the verb is an importer (init founds and imports; sync IS the import and reports it):
                 if plan.stat().st_mtime_ns != board.plan_mtime: plansync.apply_sync(conn, now,
                 parse_plan(read plan), mtime)                                     auto-sync (I9), silent; it
                                                                                   journals only if something changed
              5  transitions.housekeeping                                          every board verb, init included
                                                                                   (a no-op on its empty board):
                                                                                   reap stale + refresh lease (D9, I8)
              6  VERB_TABLE[verb](ctx, args) → Reply                               verb's own transaction(s) commit here
    settle tail (every board verb):
              7  queries.deliver_events → Reply.events                             piggyback, cursor advanced (D10);
                                                                                   actor None → () — so join and
                                                                                   init print no feed
              8  text = read plan; annotated = planfile.annotate_lines(text, board_snapshot().tasks);
                 if annotated != text: neighbour file + os.replace                 (I4; idempotent, so always computed,
                                                                                   written only on change)
 9  print(output.render_reply(reply)); exit 0
except DibsError as e:  stderr ← render_error(e);                    exit 1   # every refusal, usage errors included (I10)
except sqlite3.Error:   stderr ← render_error(steer(DB_ERROR));      exit 2   # environment; the steer says retry
finally: if $DIBS_TRACE — trace.write_trace(TraceRecord)                      # success AND both error paths; best-effort (D23)
```

Notes: a lost claim race is **not** an error — no-arg `claim` auto-picks the next task. A zero-row `claim` is diagnosed by exactly one follow-up read, `queries.claim_refusal`, whose `(Refusal, names)` pair feeds `output.steer` directly: *unknown task* (a member no row carries — nearest id, D14), *taken* (bundle member held — names the holder, D6), *gated* (`--task` on a parent with open children — names them, D22), *oversized* (a bundle larger than the hand — names size and hand, offers the first member alone, D6), *hand full* (names held tasks), *waiting* (names who holds what the remaining tasks wait on), *empty*. Correctness rests on the claim statement; the read only words the refusal. `claim` with no identity mints one first (`names.mint_identity`) and the briefing opens with `you are <id> - export DIBS_AS=<id>` (D8, the id reminder SSoT §6 promises; with a supplied identity the line is `you are <id>` alone). `done` follows its transaction with `queries.newly_unlocked` and, if a parent became claimable, its hint is `next_hint('unlocked', (parent_id,))` (D7, D22). `finish`/`release` returning `None` is the verb's one `if … raise` (`steer(NOT_OWNER, (task_id, holder_name))` — the holder comes from the `resolve_task` row read moments earlier; an empty holder is worded as the row's status, the reaped case). `record_note` returning `None` is `note_verb`'s one `if … raise` (`steer(UNKNOWN_AUDIENCE, (name, text))`, whose command is the same note as a broadcast). The D23 trace wraps the whole pipeline as a `finally`: parse failures and unresolved boards still produce a line (`verb`/`plan` None, from the `DEFAULTS` namespace `main` starts with), and a trace write failure is swallowed inside `write_trace` — it never touches output or exit codes.

Why the tool's own annotation write never echoes as a sync: step 8 changes the plan's mtime, so the next command's step 4 re-reads and re-diffs the file — and finds an empty diff, which writes nothing and journals nothing (SSoT §8). The redundant parse is the price of keeping `plan_mtime` a single fact stamped in one place (`apply_sync`); it is milliseconds, and it needs no member.

Two `run` shapes pass WPS: guards on `args.verb` ahead of a shared tail, or a `ROUTES` MappingProxyType of route functions. Either is fine; what is not fine is a per-verb flag record or a stage framework (rapier). The two verb sets `run`/`open_context` consult are constants: `ANONYMOUS = (init, join)` — no caller identity — and `IMPORTERS = (init, sync)` — no auto-sync ahead of the verb.

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

- **C1** — Process edges (argv, env, stdout/stderr, exit codes, `print`, the SQLite version check) exist only in `cli.py`; env is read once, as the parser's defaults for `--as` and `--plan` and the `DIBS_TRACE` gate.
- **C2** — SQL text exists only in `store/transitions/plansync/queries`; placeholders only, never string interpolation.
- **C3** — Every public `transitions` and `plansync` function = one transaction opened with `BEGIN IMMEDIATE`; success ⇔ rowcount says so (I1); exactly one event per mutation, same transaction (I6). A sync with a non-empty diff is one mutation with one SYNC event; each hand-checked import inside it is its own mutation with its own DONE event; a sync whose diff is empty mutated nothing and journals nothing (SSoT §8) — the SYNC INSERT decides that in its own WHERE, bound to the diff's emptiness.
- **C4** — `planfile` is pure: no I/O, no DB, no clock. Plan-file reads and the atomic write (`tempfile` + `os.replace`) happen in `cli.run` (steps 4 and 8) and in the `init`/`sync`/`verify` verbs, via `pathlib` — nowhere else.
- **C5** — All user-facing text lives in `output` (envelope, hints, every error message) and `views` (bodies). Nothing else builds user-facing strings; `DibsError` is constructed only by `output.steer`.
- **C6** — Verbs orchestrate only: ≤10 statements, no SQL, no regex, no formatting, at most one rowcount `if … raise`. Selecting a whole constant line from `views` (`(views.LIVE_BOARD,) * founded`) or mapping `output.format_event` over rows is composition, not formatting; filling a template's slots is formatting and belongs to `views`/`output`.
- **C7** — One error channel: `raise output.steer(kind, names)`; `cli` catches `DibsError` and `sqlite3.Error` only. Every steer is a runnable command (I10). argparse's usage errors reach the same channel through `cli.Parser.error` (§1), so no path exits with the parser's own text or code.
- **C8** — No mutable module state anywhere; state flows through `Context` or lives in the DB.
- **C9** — Decisions branch in SQL, Python reads rowcounts. If a verb grows an if-tree, the WHERE clause is missing something; if a read needs to pick between outcomes, it returns a `Refusal` from a `CASE`.
- **C10** — Every command runs the §6 pipeline in order; housekeeping precedes the verb so `claim` sees freshly reaped tasks.
- **C11** — **Sync reads under the lock it writes with.** `apply_sync` opens `BEGIN IMMEDIATE`, *then* reads `board_snapshot`, *then* computes and writes. Two workers auto-syncing the same edit therefore serialize: the second sees the first's rows, finds nothing new, and journals nothing — the SYNC event is bound to the diff, so one edit leaves one event however many workers sync it (SSoT §8). `compute_sync` is a deterministic function of (snapshot, text), so even the unlocked case would converge; the lock is what keeps a fast second edit from reassigning an id (I5). The UPSERT refreshes only text-cached columns (`seq`, `section`, `parent_id`, `title`, `body`) and never a state column (a fresh row is inserted whole, hand-checked ones as done by human); ids are minted from *all* rows, orphaned included, so an id is never reused (I5).

## 9. Verb → modules → SSoT trace

| Verb | Orchestrates | Implements |
|---|---|---|
| `init` | names.mint_board_key, plansync.found_board + apply_sync, store.registry_record, views.format_board | §6, §8, D4, D20, D24 |
| `verify` | planfile (parse + compute_sync against no rows), views.format_board | D21, D22, D24, §8 |
| `sync` | plansync.apply_sync, views.format_sync — the pipeline's auto-sync stands down for it (an importer) | §8, I5, I9, D22, C11 |
| `join` | names.mint_identity; identity-free by route (actor None), so the reply is the bare id and the settle tail delivers nothing | D8 |
| `claim` | names.mint_identity (fallback), transitions.claim, queries.claim_refusal / prior_claim, views.format_briefing | D6, D7, D9, D16, D22, §6 |
| `done` | queries.resolve_task, transitions.finish, queries.newly_unlocked | D11, I2, I4, D22 |
| `drop` | queries.resolve_task, transitions.release | §6, D9 |
| `note` | transitions.record_note (None → steer UNKNOWN_AUDIENCE, the broadcast form) | D10, §6 |
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
| Imports ≤ 12 (WPS201) | `cli`, the composition root, sits at the cap by role: the seven package modules it wires (§4 L5 imports L0–L4) plus stdlib; a 13th import is the §3 seam firing — split `argv.py`, never a noqa |
| Subclassing | none beyond `Enum` — except `cli.Parser`, the receipted argparse `error` funnel (§1): one method, no state |
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
| Unit (pure) | `planfile`, `names.pick`, `output`, `views` | §8 recognition table incl. nested checkboxes → `parent_line`, indented prose stays body (D22); annotation grammar; hash normalization; **id minting** — letters by first appearance, ordinals never reused (an orphaned `A2` means the next is `A3`), dotted children, a child under a new parent minted in the same pass, letters past `Z`; `SyncPlan.rows` refreshes seq/section/parent/body, passes state through, and carries a hand-checked todo line as done by human; event one-liners; every `Refusal` renders a runnable steer; `format_board` renders tree, `2/3` progress, bodiless/duplicate warnings, and the same text for verify's rows as for a snapshot (D21, D22, D24) |
| Property / metamorphic | `planfile`, `transitions` | `annotate_lines` preserves every non-grammar byte (I4) across generated docs; **sync is idempotent in one pass**: apply a computed `SyncPlan`, recompute against the settled text → every field empty, no deferral (the Rev 8 "reparented on the second pass" clause is gone with `mint_id`); minted ids are unique across the applied rows and never collide with orphaned ones; claim order respects affinity→seq (D7); **gating invariant:** a parent is never claimable while any todo/doing child exists, across random trees and completion orders (D22) |
| Integration (tmp DB) | `transitions`, `plansync`, `queries`, `store` | **the CAS race:** two threads claim one task, exactly one wins (I1/I2); bundle all-or-none and must fit the hand (D6); **hand limit:** claim refused at capacity, respawned identity steered back to its held task (D6); **gating:** no-arg claim skips gated parents, explicit `--task` on one is refused naming open children, orphaned children don't block, `claim_refusal` returns each of the six kinds with the right names (D22, D6); `newly_unlocked` fires exactly on the last child's `finish` (D22); `finish` rejects non-owner (I2); TTL reap + lease refresh (D9); `register_agent` UNIQUE retry and join event stamped with `now`; `record_note` returns None for an unknown audience and logs nothing (an id is accepted as an audience like a name); cursor advance (D10); board-key registry record/lookup + self-heal (D20); **plansync:** `found_board` wins once (rowcount, two calls → True/False, one INIT event), `apply_sync` on an empty board inserts every row + imports hand-`[x]` as done by human, with the whole journal pinned row by row (the DONE import, then the SYNC event carrying `format_sync`'s text — the C5 pin `test_views` cross-references), a second `apply_sync` on the same text writes nothing and journals nothing (Rev 11: the SYNC event needs a non-empty diff; `plan_mtime` is stamped regardless), edits to body/heading/indent/order refresh the cached columns and never a state column, a vanished line orphans, two connections syncing the same edit under `BEGIN IMMEDIATE` converge on one row set and one SYNC event — exactly one thread's diff is non-empty, and the journal grows by that thread's event alone (C11, SSoT §8) |
| End-to-end | `cli.main` | full loop init→join→claim→done; init prints the key and `--plan <key>` resolves from an unrelated CWD (D20); auto-sync after a human edit (I9); every refusal exits 1 with a `Run:` line — a usage error included (`dibs done A3` with no `--note`, an unknown verb: exit 1, the verb's canonical form, no usage dump); `join` with `DIBS_AS` already set prints the bare id and nothing else; `sync` after an edit reports the real diff (the auto-sync stood down); `note --for` an unknown name exits 1 steering to the broadcast form and logs nothing; a second agent's feed after another's `claim` carries no sync line (the annotation write journals nothing); a parse failure still traces — verb None for an unknown verb, `$DIBS_AS` as the actor when set (D23); SQLite below the floor exits 1 with the OLD_SQLITE steer (monkeypatched version tuple); assert final plan.md text and exit codes |
| Architecture guard | `tests/test_architecture.py` | §3 member budgets per module (AST count of top-level defs and classes; constants free); §4 layering (every top-level `from dibs…` import resolves to a strictly lower level, `TYPE_CHECKING`-guarded ones exempt by position; the dotted `import dibs.x` form is WPS301-banned and a bare `import dibs` reaches only `__init__`, so `from`-imports are the complete edge set; `__main__` sits at L6 so the entry's `cli` edge is downward); SSoT §2: code lines ≤ the hard stop, counted as §2 defines them, and ≤18 package files. The numbers live in the test as one table; changing one is a documented amendment, never a test edit alone |

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

Steps 1–14 are landed (`dist/dibs.pyz` smoke-tested at 12; the Rev 11 invocation edges and journal hygiene at 13–14). Step 15 is open. Nobody returns to an earlier step — every change to a landed module is a briefing below, and each step ends lint-clean with the whole suite green.

1. ✅ `runtime.py`, `records.py` — types only.
2. ✅ `store.py` — schema + pragmas + key registry.
3. ✅ `planfile.py` — parse/annotate/diff; I4 property tests.
4. ✅ `transitions.py` — CAS claim, race + hand-limit tests, then the rest.
5. ✅ **Rev 9 amendments to 1–4** (one step, one commit): `records.Board`; `planfile.SyncPlan` → `rows/new/vanished/checked/regressed` (delete `reordered`, `reparented`), `planfile.mint_id`, `compute_sync` minting in one pass, docstring deferral clause removed; `transitions.register_agent(conn, agent, now)` (`JOIN_EVENT_SQL`/`AGENT_SQL` take `?3`), `finish`/`release` docstrings state the `None` contract; `tests/boards.py` builds rows from `compute_sync(items, ()).rows` and drops `assign_ids`/`task_rows`; `test_property_planfile` drops its `pair`/`mint_id`/`deferred_by_new_parent` mirrors and asserts one-pass idempotence; `test_planfile` gains the minting cases. `import_author_done` stays until step 7 takes its case.
6. ✅ `queries.py` — `board_snapshot → Board`, `deliver_events` cursor semantics, `resolve_task(conn, raw, verb)`, `claim_refusal` (six kinds; raises need `output.Refusal` + `steer`, so land those two `output` members here, stubs for the rest).
7. ✅ `plansync.py` — `found_board`, `apply_sync` (C11); delete `transitions.import_author_done` and move its test; `tests/boards.build_board` switches to `apply_sync`.
8. ✅ `names.py` — `mint_identity(conn, now)` retry loop + board keys.
9. ✅ `output.py` + `views.py` — envelope, caps, hint and steer catalogs; `format_board`/`format_briefing`/`format_sync`.
10. ✅ `verbs/` — thin orchestration over 5–9; `verify_board(args)` is the one pure verb.
11. ✅ `cli.py`, `__main__.py`, `trace.py` — pipeline §6 with the three routes and the D23 trace; end-to-end + trace tests.
12. ✅ zipapp build; smoke-test `dibs.pyz` on PATH.
13. ✅ **Rev 11 — the invocation edges (`cli.py`, `output.py`, `verbs/work.py`; one commit).** Make the stubs real: `cli.Parser.error` raises `output.steer(Refusal.BAD_USAGE, (message, verb))` where `verb` is `self.prog.removeprefix(PROG).strip()` — `'done'` for the `dibs done` subparser, `''` for the top parser; `build_parser` returns a `Parser` and passes `parser_class=Parser` to `add_subparsers`; `--plan` and `--as` get `default=os.environ.get(…)` at build time and `resolve_actor` is deleted (`run` and the trace read `args.actor`; `resolve_board` reads `args.plan` only). `parser.set_defaults(**DEFAULTS)` is deleted with it: `set_defaults` rewrites the default of every already-registered action whose dest it names, which would erase the env-backed defaults, so the slot defaults travel the other way — `main` builds `args = Namespace(**DEFAULTS)` before its `try` and hands it to `parse_args(argv, args)`, which fills it in place, applying an action's default only where the namespace lacks the attribute. Hence `DEFAULTS` gains `verb: None` and must never name `plan` or `actor` (say so in its comment: a pre-set attribute shadows the env default). The `try` stays one statement, `text = output.render_reply(run(build_parser().parse_args(argv, args)))` — WPS229 by its reason: both calls raise the one exception the handlers catch, and binding the namespace cannot raise, so it sits outside; the shape is verified WPS-silent (WPS221 included). A parse failure therefore traces `verb` None (or the subparser's name — argparse stamps it before parsing that verb's arguments, so `dibs done` with no `--note` traces `verb: done`), `plan` None, and `actor` as `$DIBS_AS` said — the truer record for a lens (D23); `test_trace_parse_failure` pins the unbound case (env unset → actor None). `run`: `ANONYMOUS = (INIT, JOIN)` picks `actor=None`; `open_context` reads the snapshot once, calls `store.registry_record(snapshot.key, plan_path)`, skips the auto-sync for `IMPORTERS = (INIT, SYNC)`, and runs `housekeeping` for every board verb. `output`: `Refusal.UNKNOWN_AUDIENCE` and `Refusal.BAD_USAGE` with catalog entries (`UNKNOWN_AUDIENCE`: `'No agent named {0} on this board - names are the ones events show.'` / `'dibs note "{1}"'`; `BAD_USAGE`: `'{0}'` / the `USAGE` form of `{1}`, falling back to `dibs claim`); the `USAGE` MappingProxyType — every verb's canonical runnable form: `init <plan.md>`, `verify <plan.md>`, `sync`, `join`, `claim`, `done <ID> --note "..."`, `drop <ID>`, `note "..."`, `list`; `steer` selects it for `BAD_USAGE` the way it selects `VERB_FORMS` for `UNKNOWN_TASK`; delete the `empty` hint moment. `store.registry_record` becomes drift-only (empty key → return; recorded path already equal → return). Tests: `test_output` gains sample names for both kinds and drops `empty` from `MOMENTS`; the `test_cli` stubs `test_usage_error_steers_exit_one`, `test_join_ignores_inherited_identity`, `test_sync_verb_reports_the_diff` and the `test_trace` stub `test_trace_parse_failure` go green; `test_store` keeps its three registry cases and gains "re-record of an unchanged path leaves the file's mtime alone". WPS shape notes: `main` keeps five locals (`now`, `args`, `stream`, `text`, `code`); `open_context` binds `ctx` early and reads `ctx.conn`/`ctx.now` (locals `plan_path`, `db_path`, `ctx`, `snapshot`, `edited`).
14. ✅ **Rev 11 — journal hygiene (`plansync.py`, `transitions.py`, `verbs/board.py`; one commit).** `plansync.apply_sync`: the SYNC `INSERT … SELECT … WHERE ?7` (or equivalent) is bound to the diff's emptiness — `bool(plan.new or plan.vanished or plan.checked or plan.regressed)` — so a no-op sync journals nothing (C3, SSoT §8); `plan_mtime` is still stamped. `transitions.record_note`: `NOTE_SQL` becomes `INSERT … SELECT … WHERE ?3 IS NULL OR EXISTS (SELECT 1 FROM agents WHERE name = ?3 OR id = ?3)` with `to_agent = (SELECT id FROM agents WHERE name = ?3 OR id = ?3)`; rowcount 0 → `None`, no `EVENT_BY_ID` read. `note_verb`: `if event is None: raise output.steer(Refusal.UNKNOWN_AUDIENCE, (args.to_name, args.text))`. Tests (changed pinned decisions, amended here, never weakened silently): `test_plansync.test_apply_sync_same_text_only_journals` becomes `…_journals_nothing` (event count unchanged, `plan_mtime` stamped); `test_transitions.test_record_note_broadcast_and_directed`'s `stray` case asserts `None` and no NOTE row, and a new case accepts an id as the audience; the `test_cli` stubs `test_note_unknown_name_refused` and `test_tool_writes_never_journal_syncs` go green. Landed (ca34e33) with two test moves beyond this list, recorded so the pinned decisions stay named: `test_apply_sync_converges_under_contention` counts one SYNC event beyond the build's — its `sorted(plan.new for plan in outcomes) == [(), ('B2',)]` line pins C11's single winner, and the journal grows by that winner's event alone, since the loser's diff is empty (SSoT §8); and the pin that the SYNC event carries `format_sync`'s text moved from the idempotence case, which no longer has an event to read, into `test_apply_sync_empty_board_is_init`, widened to the whole event row (`tuple(row)[1:]`: every column but the autoincrement id, in DDL order) for the DONE import and the SYNC alike.
15. **Rev 11 — the budget as a test (`tests/test_architecture.py`; one commit).** Make the three test stubs real over the six measurement helpers stubbed beside them — one pure function per noun, so each test is one comparison against its table and passes WPS by construction (wps-refactor rung 2: named values, never a split by line count). Helpers: `members_of(path) -> int` — top-level `FunctionDef`/`ClassDef` in `ast.parse(...).body`, constants free (§3); `import_edges(path) -> tuple[tuple[str, str], ...]` — importer key `path.relative_to(PACKAGE).with_suffix('').parts[0]` (so `verbs/work.py` is `verbs`); iterate `tree.body` only — a `TYPE_CHECKING` block is an `If` there and is skipped by position, and nested imports are WPS-banned anyway; bind `froms = [node for node in tree.body if isinstance(node, ast.ImportFrom)]` first, then one two-`for` comprehension over `froms` filtered on `node.module.startswith(PACKAGE.name)` and `node.names` (WPS224/WPS307 hold: two `for`s, one `if` each); `imported_key(node, alias) -> str` — `(node.module.partition('.')[2] or alias.name).partition('.')[0]`: `from dibs import output` → `output`, `from dibs.records import Task` → `records`, `from dibs.verbs import board` → `verbs`; the dotted `import dibs.x` form is WPS301-banned and a bare `import dibs` reaches only `__init__`, so `ImportFrom` is the complete edge reader; `token_lines(source) -> set[int]` — every row a token touches except `SKIPPED_TOKENS` (`COMMENT`, `NL`, `NEWLINE`, `INDENT`, `DEDENT`, `ENCODING`, `ENDMARKER`), a multi-line `STRING` spanning `start[0]..end[0]`; `docstring_lines(tree) -> set[int]` — `ast.walk`; for a `Module`/`ClassDef`/`FunctionDef` whose `ast.get_docstring` is not None, the rows of `body[0]`; `code_lines(path) -> int` — `len(token_lines(source) - docstring_lines(tree) - blank)`, `blank` the rows whose text is whitespace: a blank line inside a SQL body is still a blank line (SSoT §2). Tests: `test_member_budgets` — the set of `.py` files under `dibs/` (as `dibs/...` posix paths relative to the repo root, resolved from `__file__`, never the CWD) equals `MEMBER_BUDGETS`' keys, and the dict of over-budget modules is empty; `test_layering` — over every file, `[(importer, imported) … if LEVELS[importer] <= LEVELS[imported]]` is empty; `test_size_budget` — `sum(code_lines)` ≤ `HARD_STOP` with the total in the assertion message, and the file count ≤ `FILE_CAP`. `LEVELS['__main__']` is already 6 (Rev 12, §4: the entry imports `cli` at L5, so the strict rule would have gone red on the entry stub). The one touch to a landed module: `dibs/__main__.py`'s docstring says "level L5" → "L6". Then measure: the §2 counter gives 1654 at ca34e33 (calibration: 1599 at e0bbf83, the number Rev 11 recorded); if the test's total differs, the test's counter is §2's reference implementation — correct SSoT §2's "Measured at Rev 12" sentence in the same commit, never the stop. WPS shape notes: `assert not over` / `assert not upward` (WPS520 bans `== []`); unpack `for importer, imported in edges` rather than subscripting; the f-string in the size assertion holds two bare names (WPS237). Nothing else changes: this step exists so that the next drift is a red test, not a review finding.

Every step is a `plan.md`-ready task with a complete briefing — dibs can be dogfooded to build the rest of dibs.
