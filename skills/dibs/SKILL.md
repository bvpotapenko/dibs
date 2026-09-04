---
name: dibs
description: Coordinate parallel work on a shared plan through the dibs CLI - claim tasks atomically, report done with notes, drop blocked work, broadcast cross-cutting changes, and recover from reaped claims. Use this skill whenever it is invoked as "/dibs path/to/plan.md" or with a board key like "/dibs dibs-7f3a-9c2e", whenever any dibs-prefixed board key appears in the conversation, whenever the user asks to work a plan "with dibs" or "alongside others", and whenever several agent sessions share one task list, checklist, or plan.md - even if the user never says the word dibs. While this skill applies, never edit the plan file directly; all coordination goes through the dibs CLI.
---

# dibs — working a shared plan

You are one of several agents working the same plan in parallel. Coordinate ONLY through the `dibs` CLI. Never edit the plan file yourself — the tool annotates it; your edits would be overwritten and can break coordination for everyone.

## Bind to the board

- Invoked as `/dibs <something>`? That argument is your board — a key like `dibs-7f3a-9c2e` or a plan path. Run `export DIBS_BOARD=<it>` once (or pass `--plan <it>` on every dibs call).
- If `DIBS_BOARD` or `DIBS_AS` are already set in the environment, keep them — the launcher bound you on purpose.
- You do not need the plan file. Your briefing comes from `claim`; if you encounter the plan file while working, leave it alone — reading it invites doing unclaimed work.
- Boards are per-plan: several plans can run in parallel in one directory. If dibs reports multiple boards, use the key or path from your instructions; never guess.

## Identity

- If `$DIBS_AS` is set, that is you; dibs reads it automatically — add nothing.
- Otherwise your first `dibs claim` names you and prints the `export DIBS_AS=<your-id>` line — run it, or pass `--as <your-id>` on every call. The id is private; other agents see only your display name.

## The loop

1. `dibs claim` — you receive one task briefing: title, body, and recent events from other agents.
2. Do exactly that task, nothing else.
3. `dibs done <ID> --note "what actually changed"` — the note is mandatory; write it for reviewers and for the next agent.
4. Claim again. When claim says no tasks remain, stop and summarize your work.

Your hand is limited (usually one task): `claim` refuses while it is full and names what you hold — finish or drop before claiming more. Ask for a bundle (`claim --task A3 A4`) only when the tasks genuinely belong together and fit your hand. Some tasks wait on others: if `claim` says nothing is available *yet*, that is waiting, not finished. When your `done` unlocks a parent task, the output says so — claim it; you have the freshest context for it. `dibs list` is not part of your loop — claim output is your whole briefing; list is for humans.

## Etiquette

- Blocked or wrong task for you → `dibs drop <ID> --note "why"`, then claim something else. Never sit on work you are not doing.
- Changed something others may depend on (renamed, moved, reformatted, API changed) → `dibs note "..."` immediately.
- Long task → drop a midway `dibs note` with progress; it also keeps your claim from expiring.
- Read the "while you were away" tail on every command — that is how you learn what others did.

## Writing or changing the plan

Not a worker's job. If you are asked to write, decompose, or restructure a plan for dibs, use the `dibs-plan` skill — it holds the grammar dibs reads, the briefing standard, and the nesting rules. As a worker, never edit the plan file; dibs annotates it.

## When things go wrong

- `claim` refused, hand full → you already hold a task; the refusal names it. Finish or drop it, then claim again. Just respawned? That named task is yours — resume it.
- `claim` says nothing available yet → every remaining task waits on work someone else holds; the message names it. Not the end state: finish anything you hold, retry once or twice, then stop and report idle. Never start a waiting task's work "to help."
- `claim --task` refused, waits for children → that parent is not ready; the refusal names its open children — claim one of those instead.
- `done` rejected → your claim was probably reaped. `dibs claim --task <ID>`: got it back → `done` again immediately; someone else holds it → `dibs note` what you already did and move on. Never force it.
- Identity rejected ("unknown on this board") → you are pointed at the wrong board. Check `$DIBS_BOARD` against your plan path before doing anything else; fix the binding, do not mint a workaround identity.
- Lost your id → `echo $DIBS_AS` first (it survives context loss); only if empty, `dibs claim` mints a fresh one and your old claim expires on its own.
- Empty `claim` → the plan is finished; stop and report.
- `dibs: command not found` → stop and tell the user; do NOT fall back to coordinating by editing the plan file.
- `dibs note --for` refused (no such name) → the steer is the same note as a broadcast. Run it; names are what events show you.
- Any dibs error → its last line is the exact command to run next. Run it.
