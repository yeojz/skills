---
name: implement
description: Use when building the steps of a spec, or working through a written plan, remediation list or phased task document item by item, with status written back and a checkpoint per item. Triggers on requests like "implement step 2", "build the next step", "implement the plan", "execute the plan", "work through @docs/plans/...", "start priority 3", "continue with the plan", "write the test first", "TDD", "red green refactor", "add a regression test", or when the user asks which items are complete, skipped or blocked.
---

# implement

## Overview

Builds a spec's steps, or a plan's items, one at a time against evidence. For
a spec step, the step's criteria are seen failing before anything is built,
run again while building, and recorded in the spec when they pass. For a
plain plan, each item is checked, built, proven with `verify` and recorded.
Nothing is reported done without the command that shows it.

## Workflow

### Step 1: Read the work and fix the scope

Read the whole spec or plan before acting. Number the items: a spec's steps
are `Step 1`, `Step 2`; a plan keeps its own numbering or gets `<group>.<n>`
in document order. Print the list and say which are in scope:

| Request | In scope |
|---|---|
| "execute step 2", "start priority 3" | That step or group only |
| "execute the plan" | Everything, in order |
| "continue" | The first item not done, onward |

For a spec, the status line must read `criteria signed off`. If it doesn't, stop
and run the `criteria` skill first. A request with no spec or plan, such as
"write the test first for X" or "add a regression test", is one item whose
check is a test: run it through Step 3b's test rules.

Branch before the first edit, as the `pr` skill's Worktree section
describes. Ask when an item's meaning or order is
unclear; never reconstruct a plan from memory.

### Step 2: Serial or parallel

Two items conflict if they touch the same file or one's output feeds the
other (a step's Blocked by says so). Fan independent items out to subagents,
one each, with the item, its files and its criteria. Run conflicting items in
order and say why in one line. When unsure, serialise.

### Step 3: Per item, check, build, prove

**3a. Check it isn't already done.** Read the files the item names. If it's
already satisfied, record that with the command that shows it and move on.

**3b. See the checks fail first.** For a spec step, the checks are the criteria
of every requirement the step serves; a requirement with no criterion stops the
step: hand it to `criteria` and go on with the rest. For a plan item, the check
is the command that will prove it; for a standalone request, the test. Run
each check and record `fail` or `not met`. For a `test` check, write the
test now:

- one behaviour per test, named for it; an "and" in the name means two tests
- it calls the code the way a consumer will, using real code; mock only what
  is slow or external, and assert on the result, never on the mock
- run it with the repo's own test script, never an invented command
- it must fail on its assertion. Failing on an import or type error is the
  wrong reason: add the smallest stub and run it again. Passing already means
  the behaviour exists or the assertion is empty; find out which.

**3c. Build the least change that makes it pass.** Change only what the item
describes. Note anything adjacent under Follow-ups instead of fixing it. Run
the step's criteria as you go, and the whole suite once they pass. If an unrelated test fails, find its cause with the `debug` skill before going on. Never change
an expected value to match the output, skip a test, or loosen a type to get
green. Refactor only while green, and add nothing new while refactoring.

When the build forces a decision that is hard to reverse, surprising, and a
real trade-off, stop and put it to the owner as lettered options. Write the
answer as an ADR from the `grill` skill's `template-adr.md` and link it from
the step.

**3d. Prove and record.** Run the `verify` skill. Write the result back
before the checkpoint, not at the end:

- a spec step: each of its criteria's Status becomes `pass` or `fail`, or
  `met` or `not met` for an inspection, and the step's Status line under its
  heading reads `done`, `blocked` or `not started`. The spec edit goes into
  the same checkpoint commit as the code it describes. The sha that proves
  it lives in the verify block and the PR body, never in the spec, since a
  squash merge would orphan it
- a plan item: a status line beneath it

| Status | When | Records |
|---|---|---|
| `done` | Built or already satisfied, and verify passed | The evidence command and its result |
| `blocked` | A check still fails, or a prerequisite is missing | The failing command and what blocks it |
| `skipped` | The owner said so, or it no longer applies | The reason and who decided |
| `not started` | Out of scope this run | Nothing more |

A failing check is `blocked`, never `done`. Never stage `docs/plans/`.

### Step 4: Checkpoint

By default, stop after each item: show `git diff --stat` and the criteria
results, and wait before committing through the `pr` skill. Honour a cadence
the owner names ("pause after 2", "no need to pause"), and say it back at
Step 1. Silence is not approval.

### Step 5: Report

One row per item, out-of-scope ones included:

```markdown
| Item | Status | Evidence |
|---|---|---|
| Step 1 | done | C1.1 pass, C1.2 met (verify at 4f2a9c1) |
| Step 2 | blocked | C2.2 fail: `pnpm test -- -t "expired cookie"` exit 1 |
| Step 3 | not started | out of scope this run |
```

Give the counts per status and name every item that isn't done. Never write
"all done".

## Common Mistakes

| Mistake | Fix |
|---|---|
| Building before the step's criteria were seen failing | Run them first; write the test first for a test check |
| Building a step whose requirement has no criterion | Stop the step and hand it to `criteria` |
| A test that passed on its first run | It proves nothing until you know why; check the behaviour or strengthen the assertion |
| Counting an import error as the red step | Stub until it fails on the assertion |
| Changing the expected value or skipping a test to reach green | Fix the code, or stop at `blocked` |
| Deciding an ADR-tier fork alone | Lettered options to the owner, then the ADR |
| Ticking an item with no evidence command | No evidence, not `done` |
| Updating status in a batch at the end | Write it back after each item |
| "All done" | The table, with counts and every item that isn't done |
