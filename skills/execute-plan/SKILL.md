---
name: execute-plan
description: Use when working through a written plan, remediation list or phased task document item by item, with status written back into the plan and a commit checkpoint per item. Triggers on requests like "execute the plan", "implement the following plan", "work through @docs/plans/...", "start priority 3", "continue with the plan", "address the remaining tasks", "execute remediations in priority order", or when the user asks to mark which plan tasks are complete, skipped or blocked.
---

# execute-plan

## Overview

Turns a plan document into an ordered, tracked run: parse the plan into
identified items, check each one against the current tree before touching it,
implement what is genuinely outstanding, prove it with the `verify` skill, and
write the result back into the plan file. Guarantees that no item is reported as
done without an evidence command, and that no item outside the requested scope is
implemented.

Plans live at `docs/plans/YYYY-MM-DD-HHMM-<slug>.md` and are never committed.
Editing the plan file is expected; staging it is not.

## Workflow

### Step 1: Read the plan and parse it into items

Read the whole plan file before doing anything. Do not start from a summary and
do not act on a single quoted heading without reading the surrounding structure.

```bash
ls docs/plans/
cat docs/plans/2026-09-10-1030-auth-remediation.md
```

Build an ordered item list. Each item needs:

| Field | Source |
|---|---|
| `id` | Existing numbering, or `<phase>.<n>` assigned in document order |
| Title | The item heading or bullet text, verbatim |
| Group | Phase, priority band or section the item sits under |
| Files | Paths the item names, or paths implied by its description |
| Evidence | The command that will prove it, filled in at Step 5 |

If the plan has no numbering, assign ids in document order and use those ids in
every later message so the user can refer to them.

### Step 2: Echo the parsed list and the scope before starting

Print the parsed items as a table and state exactly which subset is in scope for
this run, then start. Scope comes from the user's words:

| Request | In scope |
|---|---|
| "execute the plan" | Every item, in document order |
| "start Priority 3" / "phase 2 only" | That group only |
| "continue with the plan" | Items not marked done, from the first such item |
| "address items 1 and 2 first" | Items 1 and 2, then stop at the checkpoint |

If the plan is ambiguous about ordering or an item's meaning, ask before
starting rather than guessing. If the plan file does not exist at the given
path, list `docs/plans/` and ask which file is meant. Do not reconstruct a plan
from memory.

### Step 3: Check dependencies and choose serial or parallel

Two items conflict if either is true:

1. They touch the same file.
2. One item's output is the other's input, such as an item that introduces a
   type or module a later item consumes, or a rename a later item depends on.

Items with no conflict are independent. Fan independent items out to subagents
concurrently, one item per subagent, with the item id, the item text, the files
it may touch, and the instruction to run `verify` on its own change. Run
conflicting items in order, and say in one line why they are serialised, for
example "3.2 and 3.4 both edit `src/auth/session.ts`, running in order".

When in doubt about a conflict, treat the items as conflicting and serialise.
A wrong parallel run corrupts the tree; a wrong serial run only costs time.

### Step 4: Per item, validate before implementing

For every item, in this order. Never invert steps 4a and 4b.

**4a. Validate whether it is already mitigated.** Read the files the item names
and check for the described condition in the current tree.

```bash
rg -n "createSession" src/auth
git log --oneline -5 -- src/auth/session.ts
```

If the item is already satisfied, mark it `done` in the plan with the command
that shows it, state "already mitigated, no change" and move to the next item.
Do not re-implement it and do not reformat the code to look like work happened.

**4b. Implement it.** Change only what the item describes. Do not fold in a
neighbouring fix, and do not implement any item from a group later than the one
in scope. If an adjacent problem is spotted, note it under a `Follow-ups`
heading in the plan and keep going.

**4c. Verify it.** Call the `verify` skill and capture the command and its
result. Never tick an item off a plan without a verify run behind it.

**4d. Record the outcome.** One of four statuses, written back into the plan at
Step 5 before the checkpoint.

| Status | When | Must record |
|---|---|---|
| `done` | Implemented or already mitigated, and verify passed | The evidence command and its result |
| `skipped` | The user asked to skip it, or it no longer applies | The reason, and who decided |
| `blocked` | Attempted and verify failed, or a prerequisite is missing | The failing command, its output, and what is blocking |
| `not started` | Out of scope for this run, or the run stopped earlier | Nothing beyond the status |

A failing verify makes the item `blocked`, never `done`. Root-cause the failure
if it is within the item's scope; if the fix would exceed the item's scope or
needs a decision, stop that item at `blocked` and continue with the rest.

### Step 5: Write status back into the plan file

Update the plan file itself after each item, not in a batch at the end. Each
item carries its status line directly beneath it:

```markdown
- [x] 3.2 Replace the hand-rolled session parser
      status: done
      evidence: pnpm --filter @acme/auth test:ci --project node -> 41 passed
- [ ] 3.3 Rotate the signing key on refresh
      status: blocked
      evidence: pnpm --filter @acme/auth test:ci --project node -> 2 failed
      blocked by: key rotation needs the KMS binding decided in phase 4
- [ ] 3.4 Drop the legacy cookie fallback
      status: skipped
      reason: user asked to defer, 2026-09-10
```

A ticked checkbox with no `evidence` line is a lie. If there is no evidence
command, the status is not `done`.

Never stage the plan file:

```bash
git status --short
git add src/auth/session.ts src/auth/session.test.ts
```

### Step 6: Pause at the commit checkpoint

Default cadence is a pause after every item. Stop, show the diff summary and the
verify output, and wait for the user before committing and moving on.

```bash
git status --short
git diff --stat
```

Honour a cadence the user names instead, and repeat it back at Step 2:

| Request | Cadence |
|---|---|
| (none given) | Pause after each item |
| "pause after task 2" | Run 1 and 2, pause, then continue on the go-ahead |
| "address 1 and 2 first, pause to commit then continue with 3" | Pause after 2, then after 3 |
| "commit after each issue fix" | The default, confirm it explicitly |
| "no need to pause" | Commit per item without pausing, still one commit per item |

One commit per item, Conventional Commits subject, referencing the item id in
the body. Branch before the first edit; never edit on the default branch. Never
use `--no-verify`.

If the user does not respond to a checkpoint, stop. Do not continue to the next
item on the assumption that silence is approval.

### Step 7: Final report

Report a table of every item in the plan, including out-of-scope ones, with its
status and evidence:

```markdown
| Item | Title | Status | Evidence |
|---|---|---|---|
| 3.1 | Validate token audience | done | already mitigated: src/auth/token.ts:44 |
| 3.2 | Replace session parser | done | pnpm --filter @acme/auth test:ci --project node -> 41 passed |
| 3.3 | Rotate signing key | blocked | 2 failed, needs phase 4 KMS decision |
| 3.4 | Drop cookie fallback | skipped | deferred by user |
| 4.x | Phase 4 (all items) | not started | out of scope for this run |
```

Rules for this report:

- Anything without an evidence command is reported as `not proven`, never as
  done.
- Never write "all phases complete" or "all tasks done". State the counts per
  status and name every item that is not `done`.
- If the user asks "is everything complete?", answer from this table, not from
  memory of what was attempted.
- List remaining `blocked` and `not started` items as the explicit next step.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Ticking an item without running verify | Every `done` carries an evidence command and its output. No verify run means the status is not `done` |
| Implementing an item from a later phase | Only the requested group is in scope. Note the later item under `Follow-ups` and leave it `not started` |
| Silently skipping an item | Every item in the plan gets an explicit status. A skip records the reason and who decided it |
| Claiming "all phases complete" | Report the per-item table with per-item evidence. State counts per status and name every item that is not done |
| Re-implementing something already in the tree | Validate first (Step 4a). Already mitigated means mark and move on with no edit |
| Marking a failed item `done` because the fix is "nearly there" | A failing verify is `blocked`, with the failing command and what is blocking |
| Batching plan-file updates until the end | Write status back after each item, before the checkpoint |
| Fanning out items that touch the same file | Two items conflict if they share a file or one feeds the other. When unsure, serialise |
| Continuing past a checkpoint without a reply | Silence is not approval. Stop and wait |
| Staging the plan file with the code change | Never stage `docs/plans/`, `.plans/` or `.claude/` |
| Reformatting or refactoring around an item | Change only what the item describes; note adjacent problems as follow-ups |
