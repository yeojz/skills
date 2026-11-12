---
name: coordinate
description: Use when a spec's steps have to be driven through separate worker and reviewer sessions to merge-ready, with the owner merging on GitHub. Triggers on requests like "coordinate the spec", "drive the spec with workers", "start worker sessions for steps 2 to 4", "drain the steps across sessions", "I will review on GitHub", "where are we", "PR 42 is ready for review", "the reviewer said after fixes", or when a session that starts other sessions picks up a step of a spec in docs/specs/.
---

# coordinate

## Overview

Drives a spec's steps to merge-ready: one worker session per step in its
own worktree, one fresh reviewer per pull request, bounded fix rounds that
escalate a tier when one fails, and one line to the owner when a PR is ready
to merge. Every brief comes from this skill's templates. Every step's state
and every decision sits in two ledgers that only the `unit` script writes,
and each next action comes from that script, so a compacted or new session
continues the run without a hand-over note. This session never implements,
never reviews, never merges, and reads no report or review body.

## Workflow

Run every command from the main checkout. The script sits beside this file:

```bash
unit="<skill dir>/scripts/unit"; notes="<notes folder>"
```

### Step 1: Read the spec and the standing orders

```bash
ls AGENTS.md CONTEXT.md docs/specs docs/adr 2>/dev/null
awk '/^## /{p = /^## Standing orders$/} p' AGENTS.md
```

Read every file that exists. The `awk` prints the `## Standing orders`
section, which is pasted verbatim into every brief and relay. With none, the
default block in `template-phase.md` stands in, and adding the section to
`AGENTS.md` goes into the first step's scope.

The spec's status line must read `criteria signed off`; if it doesn't, stop
and offer the `criteria` skill. With no spec, offer `grill` in spec mode,
then `criteria`.

### Step 2: Open the ledgers

The notes folder is the one the brief or the app names; otherwise
`docs/plans/<date>-coordinate-<slug>/`, never committed. If it can't be
created, start nothing.

```bash
"$unit" open "$notes"
```

`units.tsv` has one row per step and `decisions.tsv` one row per fork,
verdict or relay. The script is the only writer of both: never edit either,
and never move a row on a session's word. A refusal is one line, which goes
to the session that owes the fix.

| State | Meaning |
|---|---|
| `scoped` | Brief filled, no session yet |
| `running` | Worker started |
| `ready` | Worker's report checked |
| `in-review` | Reviewer started |
| `fixing` | A fix round is running |
| `merge-ready` | Verdict merge as is; reported to the owner |
| `merged` | `gh pr view` reads `MERGED`; cleanup done |
| `parked` | Waiting on the owner for a fork, or on `criteria` for a requirement with none |
| `blocked` | Three fix rounds used, or a gate nobody can run |

Write `$notes/flow.md` with the file-write tool when the run starts, and
again in a session that picks the run up: `flow: coordinate`, `state:
running` and `session: ${CLAUDE_SESSION_ID}`, one line each, leaving the last
out when its value still reads as a placeholder. Set `state: done` once
every step is `merged` or the owner ends the run. Only this session writes
it; the compaction hooks use it to find the folder.

**Resume.** After a compaction, or in a session that picks the run up, run
Step 3 and do what its lines say, never what memory of the run suggests.

### Step 3: Ask the script what is next

```bash
"$unit" next "$notes"
```

Run this after every message from a worker or a reviewer, on every check of
the merge frontier, and when a session picks the run up. One line per step:

| Line | Do |
|---|---|
| `brief <id>`, `start <id>` | Step 5 |
| `report <id> READY` | Step 6 |
| `report <id> BLOCKED` or `FORK`, with the question | Step 11 |
| `review <id>` | Step 7 |
| `verdict <id> after fixes` or `rework` | Step 8 |
| `verdict <id> merge as is` | Step 9 |
| `merged <id>` | Step 10 |
| `stale <id>` | The pull request moved after its verdict: `"$unit" move "$notes" <id> fixing --reason "<who pushed and why>"`, then Step 6 on the new report |
| `owner <id>`, with the question | Nothing; the owner owes the answer |
| `wait <id>`, `done <id>` | Nothing |
| `check <id>`, with a reason | Fix what the line names: a file the script could not read, or GitHub out of reach |

When no line asks for an action, start the next steps (Step 4) or wait.

### Step 4: Pick the next steps

```bash
grep -n -E '^### Step|^- (Serves|Blocked by|Owns|Review gate):' docs/specs/<slug>.md
sed -n '/^## Criteria/,/^## Steps/p' docs/specs/<slug>.md
```

Add a row for each step about to start, its id the step's number, with
`"$unit" add "$notes" <id> "<the step's title>"`. A step whose requirements
lack a criterion is added, moved to `parked` with `--reason "no criterion
for R<n>"`, and goes to `criteria`. Start every other step whose Blocked by
is merged and whose Owns overlaps no running step. A step blocked only by an
unmerged PR starts on that PR's branch; record the parent tip in the brief
and the `base` column, since after a squash merge it is the only boundary
between the parent's commits and the child's:

```bash
git fetch origin <parent branch>; git rev-parse "origin/<parent branch>"
```

### Step 5: Brief and start the worker

Fill every field of `template-phase.md`; a blank field is where the worker
stalls. Copy the step's criteria as written, and list in Owns the step's
status line and the Status cells of its Criteria rows, where `implement`
records progress. The tier is the coordinating tier from `rules/models.md`,
one up for a subtle or security-sensitive step, never the model this
session runs on.

Save it as `phase-<id>.md` in the notes folder. Start a fresh session in its
own worktree with the brief: in the desktop app, `start_session` with fresh
context and a worktree. Never fork this session into a worker. Then:

```bash
"$unit" move "$notes" <id> running --branch <branch> --session <session> --base <default branch, or parent branch@sha>
```

### Step 6: Check the worker's report

A report is a claim, and the script checks it. The worker writes
`report-<id>.md` in the notes folder and messages its first three lines:

```bash
"$unit" move "$notes" <id> ready --pr <number>
```

The row moves only when the report reads `STATUS: READY`, its commit is the
pull request's head and `origin/<branch>`, every criterion in the brief has
a verify row reading `pass` or `met`, no row reads `fail`, `not met` or `not
run`, and the `behaviour` row reaches the brief's target. A refusal names
what is missing: send that one line to the worker, and never open the
report to judge it yourself. The printed line carries `draft=`; a pull
request still in draft goes back when the brief named ready. In the desktop
app, bind the PR and turn its monitor on once.

In Claude Code, never stop for context use: after a compaction the run
continues from the ledgers. Where the compaction hooks do not run, as on
Codex, run `handoff` with the notes folder past 55% context use.

### Step 7: Brief and start the reviewer

Fill `template-review.md` and start a fresh reviewer: never the worker, a
fork of it, or this session. Tier first, from `rules/models.md`: strong, or
top for a subtle or security-sensitive step, an escalated fix round, or an
ADR-tier decision. Then the family: the other one where present, at that
tier, with model and effort named. The step's Review gate sets the brief's
Post field. Move the row once the reviewer has started:

```bash
"$unit" move "$notes" <id> in-review
```

The reviewer writes `review-pr<number>.md` in the notes folder and messages
its first three lines. A contested design gets a second reviewer on the
other family, writing `review-pr<number>-second.md`: log its verdict with
`"$unit" log`, and put a disagreement between the two to the owner.

### Step 8: Fix rounds

```bash
"$unit" move "$notes" <id> fixing
```

The script reads the verdict from the review file, logs it, and prints the
round and the finding counts. A fourth round is refused: move the row to
`blocked` with the open findings as `--reason`, and report them with what
each round tried. For a round it allows, the first row that matches wins:

| The fix needs | Run it in |
|---|---|
| A round whose counts show a finding `not fixed` | A fresh session one tier above the last round's, up to top, from the pushed head |
| State only the worker has: uncommitted changes, a running process, a half-done rebase | The worker, by relay |
| Anything else | A fresh session |

A fresh session gets the phase brief plus every later directive,
consolidated, and the review file path. Before an escalated round starts,
relay one line to the last round's session: abort any rebase and stop its
processes. Its unpushed work does not carry over; the new brief names what
each round tried. A relay follows the phase template's Standing orders,
Forbidden and Report sections, with one commit per finding.

Log the route, the tier and why with `"$unit" log "$notes" <id> relay`. The
round's session writes a new `report-<id>.md`, Step 6 runs on it, and the
reviewer rewrites the review file for the new head.

### Step 9: Report merge-ready, start the next

```bash
"$unit" move "$notes" <id> merge-ready
```

The script refuses unless the review reads `merge as is` on the head the
pull request still holds, with every criterion passing on the reviewer's
checkout. Its line carries the facts for the one line the owner gets:

```text
PR 42 merge-ready: merge as is, review in review-pr42.md, head a9c1f3e, 0 P1, 0 P2, 1 P3, 0 not fixed.
```

Start the next ready step at once. Never run `gh pr merge` or arm
auto-merge. A merge doesn't wake the monitor, so in Claude Code keep one
recurring `CronCreate` check, about every 25 minutes off the hour and half
hour, whose prompt is Step 3. Delete it when no row is `merge-ready`, and
recreate it when it expires. Elsewhere, the owner's "merged" is the trigger.

### Step 10: After the merge

On a `merged` line, run the `pr` skill's Cleanup in the worker's context, or
relay it, then move the row. The script refuses while the pull request is
not `MERGED` or origin still holds the branch:

```bash
"$unit" move "$notes" <id> merged
```

A step stacked on that PR rebases now, in its own session, onto the default
branch from the parent tip in its `base` column. A plain rebase would replay
the parent's squashed commits:

```bash
base="$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\)[[:space:]]*HEAD$|\1|p')"
git fetch origin "$base" "<branch>"
old="$(git rev-parse "origin/<branch>")"
git merge-base --is-ancestor "$old" HEAD || echo DIVERGED
git rebase --onto "origin/$base" "<parent tip>"
git range-diff "<parent tip>..$old" "origin/$base..HEAD"
```

`DIVERGED` is a stop. The range-diff must show no `<` line and none of the
parent's commits. Then `verify`, push with
`--force-with-lease="<branch>:$old"`, and record the new base with
`"$unit" move "$notes" <id> <its own state> --base <default branch>`.

### Step 11: Forks

| Fork | Members | Do |
|---|---|---|
| New dependency | A package, service or tool the repo does not use yet | Owner |
| ADR-tier | Public API shape, data model, a specification reading, anything that would earn an ADR or that grill's hand-back listed as the owner's | Owner |
| Everything else | Naming inside a package, test layout, an internal helper, commit order | Decide |

**Owner:** lettered options with a recommendation; move the row to `parked`
with the question as `--reason` and keep draining the others. When the
owner answers, move it back with their words as `--reason` and relay them
unchanged.

**Decide:** `"$unit" log "$notes" <id> fork "<the choice and the reason>"`,
tell the worker, and name it in the next report.

A run started through `handsfree` has its ADR-tier forks answered by that
skill, which holds the rules for it. Log each answer as a `fork` row with
its decision number as evidence, and name each one in the next report to
the owner. A new dependency stays the owner's.

### Step 12: "Where are we"

```bash
"$unit" next "$notes"; "$unit" status "$notes"
```

Act on a `stale`, `merged` or `check` line first, then answer from the
table and its lines for what the owner owes.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Moving a row on a session's word, or editing a ledger | `unit move`; a refusal names the evidence that is missing |
| Reading a report or a review to judge it | `head -3` at most; the script and the next session read the rest |
| Continuing from memory after a compaction | `unit next`, then exactly what its lines say |
| Retrying a failed fix round on the same tier, or carrying its unpushed work | One tier up, fresh, from the pushed head |
| A plain rebase of a stacked step after a squash merge | `rebase --onto` the parent tip, then range-diff |
| Deciding an ADR-tier fork or a new dependency here | Lettered options to the owner; park the row |
| Paraphrasing the standing orders | Paste them verbatim, in every brief and relay |
