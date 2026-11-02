---
name: coordinate
description: Use when a spec's steps have to be driven through worker and reviewer sessions to merge-ready, with the owner merging on GitHub. Triggers on requests like "coordinate the spec", "run steps 2 to 4", "drain the steps", "start the next step", "coordinate the roadmap", "I will review on GitHub", "where are we", "PR 42 is ready for review", "the reviewer said after fixes", "proceed with the next one", or when a session that starts other sessions picks up a step of a spec in docs/specs/.
---

# coordinate

## Overview

Drives a spec's steps to merge-ready: one fresh worker session per step in
its own worktree, one fresh reviewer per pull request, bounded fix rounds,
and one line to the owner when a PR is ready to merge. Every brief comes
from this skill's templates, and every session, verdict and decision is
written to two ledgers, so "where are we" is answered from a file. The
reviewer is never the implementer, and merging stays the owner's click.

## Workflow

### Step 1: Read the spec and the standing orders

```bash
ls AGENTS.md CONTEXT.md docs/specs docs/adr 2>/dev/null
awk '/^## /{p = ($0 == "## Standing orders")} p' AGENTS.md
```

Read every file that exists: the glossary and ADRs go into every brief. The
`awk` prints exactly the `## Standing orders` section, or nothing. Those
lines are pasted verbatim into every brief and relay. With none, the default
block in `template-phase.md` stands in, and adding the section to
`AGENTS.md` goes into the first step's scope.

The spec's status line must read `criteria signed off`; if it doesn't, stop
and offer the `criteria` skill. With no spec, offer `grill` in spec mode,
then `criteria`.

### Step 2: Open the ledgers

The notes folder is the one the brief or the app names for this group of
sessions; otherwise `docs/plans/<date>-coordinate-<slug>/`, never committed.

```bash
notes="<notes folder>"; mkdir -p "$notes" || echo "cannot create $notes"
[ -f "$notes/units.tsv" ] || printf 'id\ttitle\tsession\tbranch\tbase\tpr\thead\tverdict\tstate\n' > "$notes/units.tsv"
[ -f "$notes/decisions.tsv" ] || printf 'when\tunit\tkind\tdecision\tevidence\tresult\n' > "$notes/decisions.tsv"
```

If the folder can't be created, start nothing. `units.tsv` has one row per
step, rewritten as it moves; `base` is the default branch or
`<parent branch>@<sha>` for a stacked step. `decisions.tsv` is append-only:
one row per fork, verdict or relay, with a pointer to its evidence.

| State | Meaning |
|---|---|
| `scoped` | Brief filled, no session yet |
| `running` | Worker started |
| `ready` | Worker's report checked against `gh pr view` |
| `in-review` | Reviewer started |
| `fixing` | Verdict after fixes or rework; a fix round is running |
| `merge-ready` | Verdict merge as is; reported to the owner |
| `merged` | `gh pr view` reads `MERGED`; cleanup done |
| `parked` | Waiting: on the owner for an ADR-tier fork, or on `criteria` for a requirement with none |
| `blocked` | Three fix rounds used, or a gate nobody can run |

### Step 3: Pick the next steps

```bash
grep -n -E '^### Step|^- (Serves|Blocked by|Owns|Review gate):' docs/specs/<slug>.md
sed -n '/^## Criteria/,/^## Steps/p' docs/specs/<slug>.md
```

A step is ready when every requirement it serves has a criterion; one that
doesn't goes to `criteria`, and its row is written as `parked`. Start every ready step whose Blocked
by is merged and whose Owns overlaps no running step. A step blocked only by
an unmerged PR starts on that PR's branch; record the parent tip it starts
from in the brief and the `base` column, because after a squash merge that
tip is the only boundary between the parent's commits and the child's:

```bash
git fetch origin <parent branch>; git rev-parse "origin/<parent branch>"
```

### Step 4: Brief and start the worker

Fill every field of `template-phase.md`; a blank field is where the worker
stalls. The step's criteria go under Done means, copied as written. The
behaviour target is the highest level the step's checks can reach:
`live-verified` when any is a drive check, `unit-only` when any is a test
check, otherwise none, and the criteria alone decide. The owner can set it
otherwise. Name the model tier
`rules/models.md` gives a scoped unit, one up for a subtle or
security-sensitive step.

Owns also lists the two parts of the spec that `implement` records
progress in, and nothing else in it: this step's status line under its
heading, and the Status cells of this step's rows in the Criteria table. If
two steps' rows conflict in a rebase, each keeps its own status.

Save it as `phase-<id>.md` in the notes folder, write the row as `scoped`,
then start the worker fresh in its own worktree on that tier: in the desktop
app, `start_session` with fresh context and a worktree; elsewhere, a new
session with the brief pasted. Never fork this session into a worker and
never implement the step here. Move the row to `running`.

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
| Behaviour | At or above the target in the brief; any level when the target is none |
| Ready | `isDraft` false, only when the brief named ready |

Anything missing or short goes back to the worker in one line naming it.
Record the PR and head. In the desktop app, bind the PR and turn its monitor
on once. After each check, look at context use: past 55%, run `handoff`
with the notes folder and ledgers named, before starting anything new.

### Step 6: Brief and start the reviewer

Fill `template-review.md` for the PR and start a fresh session on the review
tier: never the worker, never a fork of it, never this session. A contested
design gets a second reviewer on another model family, through Codex where
its plugin is present, with the same brief. The reviewer runs the gate and
every criterion on a detached checkout, probes base against candidate, runs
the `review` skill's change mode, posts one COMMENT review (never approve or
request changes), writes `review-pr<number>.md`, and returns merge as is,
after fixes, or rework. The step's Review gate sets the brief's Post field:
"owner reviews before merge" posts the review on the PR for the owner;
"none" keeps it in the review file until the owner asks. Move the row to `in-review`; log the verdict.

### Step 7: Fix rounds

| The fix needs | Run it in |
|---|---|
| State only the worker has: uncommitted changes, a running process, a half-done rebase | The worker, by relay |
| Anything else | A fresh session: the phase brief plus every later directive, consolidated |

A relay carries the standing orders verbatim, the review file path, one
commit per finding, no weakened tests, draft until `verify` passes on the
pushed head and no check has failed, and the phase template's report shape.
Never restart a stopped session. Log the route and why. The
reviewer re-checks the new head and marks each finding fixed, not fixed or
no longer applicable. After three rounds, the row is `blocked`: report the
open findings and what each round tried.

### Step 8: Report merge-ready, start the next

```text
PR 42 merge-ready: merge as is, review in review-pr42.md, gate green on a9c1f3e detached (make validate exit 0), C1.1 and C2.1 pass, 2 P2 fixed and re-checked.
```

Move the row to `merge-ready` and start the next ready step at once. Never
run `gh pr merge` or arm auto-merge. A merge doesn't wake the monitor, so in
Claude Code schedule one recurring `CronCreate` check, about every 25
minutes off the hour and half hour: for each `merge-ready` row, run
`gh pr view <number> --json state,headRefOid`, and Step 9 for each `MERGED`.
Delete it with `CronDelete` when no row is `merge-ready`; recreate it after
a handoff or when it expires after seven days. Elsewhere, the owner's
"merged" is the trigger.

### Step 9: After the merge

Prove `MERGED`, then run the `pr` skill's Cleanup in the worker's context,
or relay it. Move the row to `merged` once the branch deletion and worktree
removal are pasted.

A step stacked on that PR rebases now, in its own session, from the parent
tip in its `base` column, not with a plain rebase, which would replay the
parent's squashed commits as its own:

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
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

| Tier | Members | Do |
|---|---|---|
| ADR-tier | Public API shape, data model, a new dependency, a specification reading, anything that would earn an ADR or that grill's hand-back listed as the owner's | Lettered options with a recommendation to the owner; park the row; keep draining the others; never decide it alone |
| Everything else | Naming inside a package, test layout, an internal helper, commit order | Decide, log it as a `fork` with the reason, tell the worker, name it in the next report |

When the owner answers, append a row with the same `unit` and `decision` and
the letter chosen in `result`, and relay it in their words.

### Step 11: "Where are we"

```bash
notes="<notes folder>"
column -t -s $'\t' "$notes/units.tsv"; tail -20 "$notes/decisions.tsv"
```

Answer from the table, plus the parked questions the owner owes. Correct a
row that disagrees with `gh pr view` in the file first.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Typing a brief from memory | Fill the template; every field |
| Starting a step whose requirement has no criterion | Send it to `criteria` |
| Moving a row to `ready` on the worker's word | Check sha, criteria rows, behaviour and `isDraft` |
| Reviewing in the worker session, or here | A fresh reviewer on the review tier |
| Forking this session into a worker | Fresh context plus the brief |
| Paraphrasing the standing orders | Paste them verbatim, in every brief and relay |
| Waiting on an unmerged PR | Base on its branch and record the parent tip |
| A plain rebase of a stacked step after a squash merge | `rebase --onto` the parent tip, then range-diff |
| Deciding an ADR-tier fork alone | Options to the owner; park; drain the rest |
| Running `gh pr merge` | Merging is the owner's click |
| Fix rounds without a bound | Three, then `blocked` |
