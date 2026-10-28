---
name: coordinate
description: Use when a roadmap of phases has to be driven through worker and reviewer sessions to merge-ready, with the owner merging on GitHub. Triggers on requests like "coordinate the roadmap", "run phases 12 to 14", "drain the roadmap", "start the next phase", "I will review on GitHub", "where are we", "PR 42 is ready for review", "the reviewer said after fixes", "proceed with the next row", or when a session that starts other sessions picks up a docs/roadmap.md row.
---

# coordinate

## Overview

Runs the coordinator loop over a roadmap: one fresh worker session per phase
in its own worktree, one fresh reviewer session per pull request, fix rounds
relayed or restarted, and one line to the owner when a phase is merge-ready.
Every brief is filled from `template-phase.md` or `template-review.md` in
this skill's directory, never typed from memory, and every session, verdict
and decision lands in two ledgers in the group's notes folder, `units.tsv`
and `decisions.tsv`, so "where are we" is answered from a file.

Three things hold throughout: the reviewer is never the implementer, "done
means" names a gate and a behaviour level rather than a feeling, and every
decision the coordinator takes without the owner is in `decisions.tsv` by the
morning. Merge stays the owner's click on GitHub.

## Workflow

### Step 1: Read the roadmap and the standing orders

```bash
ls AGENTS.md CONTEXT.md docs/roadmap.md docs/design.md 2>/dev/null
ls docs/adr 2>/dev/null
awk '/^## /{p = ($0 == "## Standing orders")} p' AGENTS.md
```

The `awk` starts at the exact `## Standing orders` heading and stops at the
next level-two heading whatever its name, so a following `## Security notes`
section never leaks into a brief. It prints nothing when the heading is
missing.

Read every file that exists. A repo with no `docs/roadmap.md` has nothing to
coordinate: say so and offer `grill` in kickoff mode, which writes the
roadmap, the glossary and the standing orders.

The standing orders are the lines every worker and reviewer must follow. They
live under one `## Standing orders` heading in the repo's `AGENTS.md` and are
pasted verbatim into every brief and every fix relay, so a worker in any
agent reads the same words. When the heading is missing, the default block
in `template-phase.md` stands in, and "add the Standing orders section to
`AGENTS.md`" goes into the first unit's scope so the next brief can read it
from the repo.

### Step 2: Open the ledgers

The group's notes folder is the one the session's brief or the app names for
this group of sessions. Without one, use `docs/plans/<date>-coordinate-<slug>/`,
never committed.

```bash
notes="<notes folder>"
mkdir -p "$notes" || echo "cannot create $notes"
[ -f "$notes/units.tsv" ] || printf 'id\ttitle\tsession\tbranch\tbase\tpr\thead\tverdict\tstate\n' > "$notes/units.tsv"
[ -f "$notes/decisions.tsv" ] || printf 'when\tunit\tkind\tdecision\tevidence\tresult\n' > "$notes/decisions.tsv"
cat "$notes/units.tsv"
```

The folder is created first because the default one does not exist yet on
a fresh group and every later step writes into it. If `mkdir` fails, stop
before starting any session: nothing below has durable state without the
ledgers.

`units.tsv` has one row per phase and is rewritten in place as the phase
moves. Its `base` column is the default branch, or `<parent branch>@<sha>`
for a row stacked on an unmerged PR, where the sha is the parent tip the
worker branched from; Step 9 rebases from that boundary. `decisions.tsv` is append-only, one row per fork, verdict, relay or
decision, with a pointer to the evidence (a PR URL, a `file:line`, a log).

| State | Meaning |
|---|---|
| `scoped` | Row read, brief filled, no session yet |
| `running` | Worker session started |
| `ready` | Worker reported head SHA, gate counts and a ready PR |
| `in-review` | Reviewer session started |
| `fixing` | Verdict was after fixes or rework; a fix round is running |
| `merge-ready` | Verdict merge as is; reported to the owner |
| `merged` | `gh pr view` reads `MERGED`; cleanup done |
| `parked` | Waiting on the owner for an ADR-tier fork |
| `blocked` | Three fix rounds exhausted, or a gate nobody can run |

### Step 3: Pick the next row and check it is scoped

A roadmap row carries depends on, owns, builds, you see, done means and
review gate. Print the candidate rows:

```bash
grep -n -i 'not scoped' docs/roadmap.md
```

Refuse to start a row that has a `not scoped` field or a missing one. The
field is a question, so ask it as a lettered question or hand it to `grill`,
and start the next row that is fully scoped instead. Never fill the field
yourself.

A row whose dependency is an unmerged PR is not blocked: base the worker's
branch on that PR's branch and record the parent tip it starts from, because
the repo squash-merges and that tip is the only boundary that tells the
child's commits from the parent's once the parent has landed:

```bash
git fetch origin <parent branch>
parent_tip="$(git rev-parse "origin/<parent branch>")"
```

Write `<parent branch>@$parent_tip` in the brief under "Decisions already
made" and in the row's `base` column, and note in the report shape that the
PR must rebase once the dependency merges. Do not wait on a merge to start
independent rows.

Start every row that is independent of the running ones: different packages
or files, no output feeding another. Two rows that own the same file run in
order.

### Step 4: Fill the phase brief

Read `template-phase.md` from this skill's directory and fill every field.
Do not restructure it and do not drop a section: a field left blank is the
question the worker will stall on.

| Field | Filled from |
|---|---|
| Read order | `AGENTS.md`, `CONTEXT.md`, the ADRs, this roadmap row, the previous unit's hand-over note in the notes folder |
| Decisions already made | The ADRs and `docs/design.md` lines that touch this row, plus any base-on-branch decision from Step 3 |
| Scope and owns | The row's owns and builds fields, as absolute paths |
| Not asked for now | The neighbouring rows, so the worker stops at the boundary |
| Done means | The row's done means field: the repo's real gate commands read from `package.json` or the Makefile, the behaviour level `verify` reports, and any conformance or fixture run |
| Model tier | The tier `rules/models.md` gives a scoped unit with named files and a done condition; one tier up when the row is subtle or security-sensitive. Name the tier in the brief |
| Ship | The `ship` skill, with the go-ahead for push, draft PR, gate on a clean detached checkout and ready granted in the brief, so the worker asks for none of them |
| Standing orders | The `AGENTS.md` block from Step 1, verbatim |

Save the filled brief as `phase-<id>.md` in the notes folder, so the
reviewer and any fix session read the same words. Write the `units.tsv` row
with state `scoped`, then start the worker as a
fresh session in its own worktree on the named tier: in the desktop app,
`start_session` with fresh context and a worktree; under another agent, open
a new session and paste the brief. Never fork the coordinator's context into
a worker, and never implement the row in this session. Move the row to
`running` with the session id.

### Step 5: Drain worker reports

A worker's report is a claim. Before moving its row to `ready`, check the
three things it must name:

```bash
gh pr view <number> --json url,isDraft,headRefOid,state
git fetch origin <branch> && git rev-parse "origin/<branch>"
```

| Claimed | Must match |
|---|---|
| Head SHA | `headRefOid` and `origin/<branch>` |
| Gate counts | A pasted run on a clean detached checkout, as `ship` Step 11 produces, with exit codes |
| Ready | `isDraft` false, only when the brief named ready as the signal |

A report with a missing item goes back to the worker as one line naming it.
Then write the `units.tsv` row with PR number and head, and go to Step 6.

In the desktop app, bind the PR and turn the monitor on once per PR instead
of polling: it wakes the coordinator on CI failures, conflicts and review
comments.

After each drain, check context usage. Past 55 percent, run `handoff` into a
continuation session, with the notes folder and both ledgers named in the
prompt, before starting anything new.

### Step 6: Fill the review brief and start the reviewer

Read `template-review.md` from this skill's directory and fill it for the
PR. The reviewer is a fresh session on the review tier from `rules/models.md`
and is never the worker session, never a fork of it, and never this session.
A second opinion on a contested design runs on a different model family,
through Codex where its plugin is present, with the same brief.

The brief fixes what the review must do, so the reviewer cannot trade it
away: gates on a clean detached checkout, a correctness probe of base against
candidate, measurement reproduction with interleaved samples when the PR
claims a number, design and maintainability at the same weight as
correctness, guard-deletion sampling over the new rejecting branches,
findings P1 to P3 each with a `file:line`, one COMMENT review posted on the
PR, never an approval or a request for changes, a `review-pr<number>.md` in
the notes folder, and a verdict of merge as is, after fixes, or rework.

Move the row to `in-review` with the reviewer's session id and write a
`decisions.tsv` row of kind `verdict` when the reviewer reports.

### Step 7: Run fix rounds

On merge as is, go to Step 8. On after fixes or rework, decide where the fix
runs:

| The fix needs | Run it in |
|---|---|
| State that lives only in the worker session: its worktree with uncommitted changes, a running process, a half-finished rebase | The existing worker, by a relay message |
| Anything else | A fresh session with the original phase brief plus every later directive consolidated into it |

Never restart a stopped session to continue a fix, and never send a fix as a
bare list of findings: the relay carries the standing orders verbatim, the
review file path, the rule that each finding gets its own commit, that no
test is weakened to clear a finding, that the PR stays draft until the gate
is green on a clean detached checkout again, and the report shape from the
phase template. Write a `decisions.tsv` row of kind `relay` naming which
route was taken and why.

When the fix is reported, the reviewer re-checks through Step 6 on the new
head; a second pass classifies each earlier finding as fixed with a line,
not fixed with a line, or no longer applicable. Bound this at three rounds
per PR. After the third, move the row to `blocked` and report to the owner
with the open findings and what each round tried.

### Step 8: Report merge-ready and start the next row

One line to the owner per PR, carrying the verdict and its evidence:

```text
PR 42 merge-ready: verdict merge as is, review in review-pr42.md, gate green on a9c1f3e detached (make validate exit 0), 2 P2 fixed and re-checked.
```

Move the row to `merge-ready`. Then start the next independent row at once;
the roadmap is the queue and the owner's merge is not a prerequisite for a
row that does not depend on this one.

Merging is the owner's action on GitHub. Never run `gh pr merge` and never
arm auto-merge unless the owner asked for it.

### Step 9: Clean up after the merge

When the monitor or the owner reports a merge, prove it before touching
anything, then run the `ship` skill's post-merge cleanup in the worker's
worktree context, or relay it to the worker when its session is still open:

```bash
gh pr view <number> --json state,mergedAt,headRefOid
```

Move the row to `merged` once the branch deletion and worktree removal have
been pasted as output.

A dependent row whose branch was based on this PR's branch rebases now, in
its own session. Not with an ordinary `git rebase "origin/$base"`: the repo
squash-merges, so the parent's commits are not ancestors of the default
branch, and a plain rebase replays them as if they were the child's and
conflicts on the first one. Rebase onto the default branch from the parent
tip recorded in the row's `base` column, after the ancestor check `ship`
Step 13 makes:

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
parent_tip="<sha from the base column>"
git fetch origin "$base" "<branch>"
old="$(git rev-parse "origin/<branch>")"
git merge-base --is-ancestor "$old" HEAD && echo "remote tip is in local HEAD" || echo "DIVERGED"
git rebase --onto "origin/$base" "$parent_tip"
git range-diff "$parent_tip..$old" "origin/$base..HEAD"
```

`DIVERGED` is a stop, as in `ship` Step 13. The range-diff pairs each child
commit that was on the remote with its rebased copy: it must show no `<` line
and none of the parent's commits. Then continue with `ship` Step 13 from the
gate on the rebased tree: `verify` Step 7, the gate, and the push with
`--force-with-lease="<branch>:$old"`. Set the row's `base` column to the
default branch once the push has landed.

### Step 10: Forks, in two tiers

A worker or reviewer that hits a design question sends it to the coordinator.
Sort it:

| Tier | Members | Do |
|---|---|---|
| ADR-tier | Public API shape, data model, a new dependency, a specification interpretation, anything that would earn an ADR, and anything the kickoff listed as owner-decided | Present lettered options with a recommendation to the owner, move the row to `parked`, keep draining the other rows, and never decide it in the owner's absence |
| Everything else | Naming inside a package, test layout, an internal helper's shape, the order of two commits | Decide it, write a `decisions.tsv` row of kind `fork` with the choice and the reason, tell the worker, and name it in the next report so it can be reversed |

When the owner answers, append a `decisions.tsv` row with the letter chosen
and relay it in the words they used.

### Step 11: Answer "where are we" from the ledger

```bash
column -t -s $'\t' "$notes/units.tsv"
tail -20 "$notes/decisions.tsv"
```

The answer is the table, one line per row with its state, plus the parked
questions still owed by the owner. Nothing in it comes from recollection; a
row that disagrees with `gh pr view` is corrected in the file first.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Typing a phase brief from memory | Read `template-phase.md` and fill every field. A blank field is where the worker stalls |
| Starting a row with a `not scoped` field | The field is a question. Ask it or hand it to `grill`; start the next scoped row |
| Reviewing in the worker session, or in this one | The reviewer is a fresh session on the review tier and never the implementer |
| Forking the coordinator's context into a worker | Fresh context plus the brief. The ledgers and notes carry what it needs |
| Naming no model tier in a brief | Pick the tier by the job from `rules/models.md` and write it in the brief; never below the review tier for a reviewer |
| Standing orders paraphrased or left out of a relay | Paste the `AGENTS.md` block verbatim into every brief and every fix relay |
| Moving a row to `ready` on the worker's word | Check head SHA, pasted detached gate with exit codes, and `isDraft` against `gh pr view` |
| Restarting a stopped worker to run a fix | Relay only when the state lives there; otherwise a fresh session with the consolidated brief |
| A fix relay that is a bare list of findings | Standing orders, review file, one commit per finding, no weakened tests, stay draft until gated |
| Waiting on an unmerged PR before starting a dependent row | Base on its branch, record `<parent branch>@<tip>` in the brief and the `base` column, rebase from that tip after the merge |
| A plain `git rebase "origin/$base"` on a stacked child after the parent squash-merged | The parent's commits replay as the child's and conflict. `git rebase --onto "origin/$base" <parent tip>`, then a range-diff with no `<` line |
| Deciding a public API or data model fork alone | ADR-tier: lettered options to the owner, park the row, drain the others |
| Deciding nothing without the owner | Below the ADR tier, decide, log in `decisions.tsv`, report. Over-blocking is the failure this loop removes |
| Polling the PR for its state | Bind it and turn the monitor on once; let the wake report |
| Running `gh pr merge` or arming auto-merge | Merge is the owner's click. Report merge-ready and move on |
| Answering "where are we" from memory | `units.tsv` is the answer. Correct the file against `gh pr view` first |
| Running past the context limit mid-drain | Check usage after each drain; past 55 percent, `handoff` with the ledgers named |
| Fix rounds without a bound | Three per PR, then `blocked` and a report with what each round tried |
