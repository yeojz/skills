---
name: coordinate
description: Use when a spec's steps have to be driven through separate worker and reviewer sessions to merge-ready, with the owner merging on GitHub. Triggers on requests like "coordinate the spec", "drive the spec with workers", "start worker sessions for steps 2 to 4", "drain the steps across sessions", "I will review on GitHub", "where are we", "PR 42 is ready for review", "the reviewer said after fixes", or when a session that starts other sessions picks up a step of a spec in docs/specs/.
---

# coordinate

## Overview

Drives a spec's steps to merge-ready: one worker session per step in its
own worktree, one fresh reviewer per pull request, bounded fix rounds that
escalate a tier when one fails, and one line to the owner when a PR is ready
to merge. Every brief comes from this skill's templates, and every session,
verdict and decision is written to two ledgers, so "where are we" is
answered from a file. This session never implements, never reviews and
never merges.

## Workflow

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
notes="<notes folder>"; mkdir -p "$notes" || echo "cannot create $notes"
[ -f "$notes/units.tsv" ] || printf 'id\ttitle\tsession\tbranch\tbase\tpr\thead\tverdict\tstate\n' > "$notes/units.tsv"
[ -f "$notes/decisions.tsv" ] || printf 'when\tunit\tkind\tdecision\tevidence\tresult\n' > "$notes/decisions.tsv"
```

`units.tsv` has one row per step, rewritten as it moves; `base` is the
default branch or `<parent branch>@<sha>` for a stacked step.
`decisions.tsv` is append-only: one row per fork, verdict or relay,
with a pointer to its evidence.

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

### Step 3: Pick the next steps

```bash
grep -n -E '^### Step|^- (Serves|Blocked by|Owns|Review gate):' docs/specs/<slug>.md
sed -n '/^## Criteria/,/^## Steps/p' docs/specs/<slug>.md
```

A step whose requirements lack a criterion is written as `parked` and goes
to `criteria`. Start every other step whose Blocked by is merged and whose
Owns overlaps no running step. A step blocked only by an unmerged PR starts
on that PR's branch; record the parent tip in the brief and the `base`
column, since after a squash merge it is the only boundary between the
parent's commits and the child's:

```bash
git fetch origin <parent branch>; git rev-parse "origin/<parent branch>"
```

### Step 4: Brief and start the worker

Fill every field of `template-phase.md`; a blank field is where the worker
stalls. Copy the step's criteria as written, and list in Owns the step's
status line and the Status cells of its Criteria rows, where `implement`
records progress. The tier is the coordinating tier from `rules/models.md`,
one up for a subtle or security-sensitive step, never the model this
session runs on.

Save it as `phase-<id>.md` in the notes folder and write the row as
`scoped`. Start a fresh session in its own worktree with the brief: in the
desktop app, `start_session` with fresh context and a worktree. Never fork
this session into a worker. Move the row to `running`.

### Step 5: Check the worker's report

A report is a claim. Check it before the row moves to `ready`:

```bash
gh pr view <number> --json url,isDraft,headRefOid,state
git fetch origin <branch> && git rev-parse "origin/<branch>"
```

| Claimed | Must match |
|---|---|
| Head sha | `headRefOid` and `origin/<branch>` |
| Gate | A pasted `verify` block on that head, with exit codes |
| Criteria | One row per criterion of the step, each `pass` or `met` |
| Behaviour | At or above the brief's target; any level when the target is none |
| Ready | `isDraft` false, only when the brief named ready |

Anything missing goes back to the worker in one line naming it. Record the
PR and head; in the desktop app, bind the PR and turn its monitor on once.
Past 55% context use, run `handoff` with the notes folder before starting
anything new.

### Step 6: Brief and start the reviewer

Fill `template-review.md` and start a fresh reviewer: never the worker, a
fork of it, or this session. Tier first, from `rules/models.md`: strong, or
top for a subtle or security-sensitive step, an escalated fix round, or an
ADR-tier decision. Then the family: the other one where present, at that
tier, with model and effort named. The step's Review gate sets the brief's
Post field. A contested design gets a second reviewer on the other family
with the same brief. Check its verdict like a worker's report: gate,
criteria rows, one COMMENT review. Move the row to `in-review`; log the
verdict.

### Step 7: Fix rounds

The first row that matches wins:

| The fix needs | Run it in |
|---|---|
| A round after one whose findings came back not fixed | A fresh session one tier above the last round's, up to top, from the pushed head |
| State only the worker has: uncommitted changes, a running process, a half-done rebase | The worker, by relay |
| Anything else | A fresh session |

A fresh session gets the phase brief plus every later directive,
consolidated, and the review file path. Before an escalated round starts,
relay one line to the last round's session: abort any rebase and stop its
processes. Its unpushed work does not carry over; the new brief names what
each round tried. A relay follows the phase template's Standing orders,
Forbidden and Report sections, with one commit per finding.

Log the route, the tier and why. The reviewer re-checks the new head and
marks each finding fixed, not fixed or no longer applicable. After three
rounds the row is `blocked`: report the open findings and what each round
tried.

### Step 8: Report merge-ready, start the next

```text
PR 42 merge-ready: merge as is, review in review-pr42.md, gate green on a9c1f3e detached (make validate exit 0), C1.1 and C2.1 pass, 2 P2 fixed and re-checked.
```

Move the row to `merge-ready` and start the next ready step at once. Never
run `gh pr merge` or arm auto-merge. A merge doesn't wake the monitor, so in
Claude Code keep one recurring `CronCreate` check, about every 25 minutes
off the hour and half hour, that runs `gh pr view <number> --json
state,headRefOid` on each `merge-ready` row and Step 9 on each `MERGED`.
Delete it when no row is `merge-ready`; recreate it after a handoff or when
it expires. Elsewhere, the owner's "merged" is the trigger.

### Step 9: After the merge

Prove `MERGED`, then run the `pr` skill's Cleanup in the worker's context,
or relay it. Move the row to `merged` once the branch deletion and worktree
removal are pasted.

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
`--force-with-lease="<branch>:$old"`, and set `base` to the default branch.

### Step 10: Forks

| Fork | Members | Do |
|---|---|---|
| New dependency | A package, service or tool the repo does not use yet | Owner |
| ADR-tier | Public API shape, data model, a specification reading, anything that would earn an ADR or that grill's hand-back listed as the owner's | Owner |
| Everything else | Naming inside a package, test layout, an internal helper, commit order | Decide |

**Owner:** lettered options with a recommendation; park the row and keep
draining the others. When the owner answers, append a row with the same
`unit` and `decision`, the letter in `result`, and relay it in their words.

**Decide:** log a `fork` row with the reason, tell the worker, and name it
in the next report.

A run started through `handsfree` has its ADR-tier forks answered by that
skill, which holds the rules for it. Log each answer as a `fork` row with
its decision number as evidence, and name each one in the next report to
the owner. A new dependency stays the owner's.

### Step 11: "Where are we"

```bash
notes="<notes folder>"
column -t -s $'\t' "$notes/units.tsv"; tail -20 "$notes/decisions.tsv"
```

Answer from the table, plus the forks the owner owes. Correct a row that
disagrees with `gh pr view` in the file first.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Moving a row on a session's word | Check it against `gh pr view` and the brief |
| Retrying a failed fix round on the same tier, or carrying its unpushed work | One tier up, fresh, from the pushed head |
| A plain rebase of a stacked step after a squash merge | `rebase --onto` the parent tip, then range-diff |
| Deciding an ADR-tier fork or a new dependency here | Lettered options to the owner; park the row |
| Paraphrasing the standing orders | Paste them verbatim, in every brief and relay |
