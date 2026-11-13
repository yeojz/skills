---
name: factory
description: Use when a spec whose criteria are signed off has to be built with no one watching each step, or when such a run has to be continued, queried or answered. Triggers on requests like "run the factory on docs/specs/x.md", "factory docs/specs/x.md", "build the spec unattended", "drain the spec", "resume the factory", "what is the factory waiting on", "the factory stopped", "answer for job 02", or when the owner replies to a question a factory job asked.
---

# factory

## Overview

This session becomes the one orchestrator of a run: it takes every eligible
step of a signed-off spec through build, gate, review, approval and merge
into the integration branch, then opens the final pull request for the owner
to merge. It writes no code, review, decision or `job.json`, reads no diff,
log or file body, and merges only through the job script. Each next action
comes from that script, so a compacted or new session continues the run
without a hand-over note.

## Workflow

Run every command from the main checkout. The two scripts sit beside this
file:

```bash
job="<skill dir>/scripts/job"; gate="<skill dir>/scripts/gate"
spec="docs/specs/<slug>.md"; run="docs/plans/factory-<slug>"
```

### Step 1: Plan the run

```bash
"$job" plan "$spec"
python3 -m json.tool "$run/run.json"
```

The script checks the status line and refuses a spec that is not `criteria
signed off`; on a refusal, report its line and offer the `criteria` skill.
Do not open the spec to check it yourself. It reads the spec as committed on
the current branch and refuses one with uncommitted edits, so the spec is
committed through the `pr` skill first. On a spec that already has a run,
`plan` starts nothing over.

Write `$run/flow.md` with the file-write tool so the compaction hooks find
the run: `flow: factory`, `state: running` and `session: ${CLAUDE_SESSION_ID}`,
one line each, leaving the last out when its value still reads as a
placeholder. Only this session writes it. `job next` holds where the run
stands; set `state: done` at Step 10 once no job waits on the owner.

Report each ineligible step with the reason the script printed, and say that
it stays with `coordinate`. `run.json` names the mode: `direct` for one
eligible step, whose pull request targets the default branch, and
`integration` for more, on `factory/<slug>`.

### Step 2: Ask the script what is next

```bash
"$job" next "$spec"
```

Run this after every finished agent and script, and at the start of any
session that picks the run up. Do exactly what each line says:

| Line | Do |
|---|---|
| `start <job> planned` | `"$job" advance "$run/jobs/<job>" build`, then Step 4 |
| `resume <job> <stage>` | That stage's step, unless an agent or script for the job is still running in this session: `build` is Step 4, `gate` 5, `review` 6, `approve` 7, `merging` 8 |
| `hold <job>` | Nothing; a slot or a Blocked by step is not free yet |
| `wait <job> needs-owner` | Step 9 |
| `done <job>` | Nothing; the job is merged, merge-ready or blocked |
| `stop <reason>` | Start no job. Tell the owner which circuit breaker tripped, in the script's words. Jobs past `planned` still finish through their own lines |

When no line asks for an action and an agent is still running, wait for it.
When every line reads `done`, `wait` or a `hold` that nothing running can free, go to Step 10. Never choose the next
action from memory of the run, and never start a job the script did not
print as `start`.

### Step 3: Spawn every agent from its template

Read a job's fields from its `job.json`, the one state file read whole:

```bash
dir="$run/jobs/<job>"; python3 -m json.tool "$dir/job.json"
```

Every agent is a background subagent, and its prompt is the filled template
and nothing else: the header of paths, the round and its purpose. Never
paste text from the spec, a diff, a log or another agent's file into a
prompt; the agent reads the paths. Each agent replies with one line, and a
reply is a claim: after it, read only the first three lines of the file the
agent wrote, with `head -3`.

| Agent | Template | Subagent type | Tier, from `rules/models.md` |
|---|---|---|---|
| Builder | `template-builder.md` | `general-purpose` | Strong; top when the step's Surfaces include `security` or its Risk is `high` |
| Reviewer | `template-reviewer.md` | `jz:<name>` for each name in the job's `reviewers` | Strong; top for a `security` surface or a job past its first fix round. The other family where present, at that tier |
| Approver | `template-approver.md` | `general-purpose`, fresh | Top, or the other family where present |

Name the host's model and reasoning effort for the tier in every spawn. Risk
changes how many reviewers the script routed, never their tier, and no
reviewer or approver runs below strong.

### Step 4: Build

Every round gets a new builder; none is resumed. The round's purpose field
is one of these:

| Round | Purpose field | Tier |
|---|---|---|
| First | First build | From Step 3 |
| After `GATE: FAIL` | The path of the failed `round-<N>/checks.md` | The last round's |
| After `VERDICT: CHANGES` | The paths of that round's review files | The last round's |
| A fix round that follows a fix round | The same paths, and one sentence per earlier round naming its files | One tier above the last round's, up to top |
| After the owner's answer | The path of `feedback-<K>.md` | From Step 3 |

When the builder replies:

```bash
head -3 "$dir/build.md"
gh pr list --head "<branch>" --state open --json number --jq '.[0].number'
"$job" advance "$dir" gate --pr <number>
```

Pass `--pr` on the first round only. `STATUS: BLOCKED` or `STATUS: FORK`
takes the other move instead:

```bash
"$job" advance "$dir" needs-owner
```

When the script refuses the move to `gate`, start one new builder with the
refusal as its purpose; a second refusal is the `needs-owner` move.

### Step 5: Gate

Run the gate yourself, as a background command, on the builder's worktree.
The diff is measured against the job's `gate_base`, and the spec is read at
the run's base sha, both from `job.json`, never from the branch's own copy:

```bash
"$gate" --spec "$spec" --step <N> --base "<gate_base>" --spec-ref "<base sha>" --worktree "<worktree>" --out "$dir/round-<N>"
head -3 "$dir/round-<N>/checks.md"
```

| Line 1 | Do |
|---|---|
| `GATE: PASS` | `"$job" advance "$dir" review`, then Step 6 |
| `GATE: FAIL` | `"$job" advance "$dir" build`, then Step 4 with the `checks.md` path |

No reviewer starts on a failed gate. Do not open `checks.log` or the table
below the header; the next builder reads them. On the last round the script
refuses `build`: run `"$job" advance "$dir" needs-owner` instead, here and in
Step 6.

### Step 6: Review

Start every routed reviewer in one message, so they run concurrently, and
wait for all of them. After a resume, start only the reviewers whose file
for this round is missing. Then read each header:

```bash
head -3 "$dir"/round-<N>/review-*.md
```

| Headers | Do |
|---|---|
| Every one `VERDICT: PASS` | `"$job" advance "$dir" approve`, then Step 7 |
| Any `VERDICT: CHANGES` | `"$job" advance "$dir" build`, then Step 4 with the review paths |

A verdict whose `COMMIT` is not the head is refused by the script; start
that reviewer again on the head.

### Step 7: Approve

Start one fresh approver. It never sees the builder's reasoning, and it is
never a reviewer of this job asked a second time.

```bash
head -3 "$dir/decision.md"
"$job" advance "$dir" merging        # integration mode
"$job" advance "$dir" merge-ready    # direct mode
```

| Result | Do |
|---|---|
| `APPROVE`, and the move is accepted | Step 8 in integration mode; in direct mode the job is finished |
| `APPROVE`, and the script refuses on the gate's `ESCALATE:` line | Nothing more: the refusal moved the job to `needs-owner` with the reasons as its question |
| `ESCALATE` | `"$job" advance "$dir" needs-owner --reason "<line 3 of decision.md>"` |

Hard escalation conditions are the script's to enforce. Never argue one
away, and never ask an approver to decide again.

### Step 8: Merge into the integration branch

```bash
"$job" merge "$dir"
```

The script syncs the branch, gates it again, and merges the step's pull
request into `factory/<slug>` pinned to the head commit. On any failure it
moves the job to `needs-owner` itself. This is the only merge in a run:
never type `gh pr merge`, and never push to the integration branch.

### Step 9: Needs-owner and blocked

Send the owner one line per waiting job: the job, the one specific question,
and the file that holds the detail. Take the question from the note on the
`wait` line; when the note is empty, from line 3 of the file that caused the
stop:

| Cause | File |
|---|---|
| `STATUS: FORK` | `fork-<K>.md`, the builder's lettered options |
| `STATUS: BLOCKED` | `build.md` |
| A hard escalation condition | `round-<N>/checks.md`, the `ESCALATE:` line |
| The approver's `ESCALATE` | `decision.md` |

```text
Job 02-the-gate-script needs you: keep the lock file change or drop the new package? Options in docs/plans/factory-parsers/jobs/02-the-gate-script/fork-1.md.
```

Then keep going: run Step 2 and drain every job that does not depend on the
waiting one. When the owner answers, pass their words unchanged, never a
summary or a letter you chose for them. Save the reply to
`$dir/owner-reply.txt` with the file-write tool, never through a shell
heredoc, where a guard may deny the wording or a line may end the heredoc:

```bash
"$job" answer "$dir" --from "$dir/owner-reply.txt"
```

The script saves it as `feedback-<K>.md` and moves the job to `build`.

A hard escalation condition on an approved job is the one case with a second
way out. When the owner accepts the condition as it stands, pass their words
to `"$job" accept "$dir" --from <file>` the same way; the script records what was accepted
and moves the job on to `merging` or `merge-ready`. When they want a change,
use `answer`. Only the owner's own words go to `accept`, never a reply from
`handsfree` or an agent.

When the run was started through `handsfree`, a `STATUS: FORK` question is
answered there instead: hand the fork file's path to the `handsfree` round,
and pass the answer it writes through `job answer` the same way. Every other
cause in the table still goes to the owner, and so does a fork `handsfree`
leaves to them.

A `blocked` job gets one line too: the job and the question on line 3 of its
`build.md`. The owner's reply goes through `answer`. A job the plan blocked
behind an ineligible step stays blocked until that step is done elsewhere.

### Step 10: End the run

When every job is merged, in integration mode:

```bash
"$job" final "$spec"
"$job" status "$spec"
```

`final` gates the integration branch and opens the final pull request as a
draft against the default branch. With a job still at `needs-owner` or
`blocked`, or in direct mode, skip `final` and run `status` alone. Report
the table as printed, then one line:

```text
Final pull request 57 (draft) for parsers: 3 jobs merged; job 04 waits on you (fork-1.md); steps 5 and 6 are ineligible and stay with coordinate.
```

The owner merges the final pull request on GitHub. Never mark it ready
unless the owner said so in this conversation, and never merge it.

**Resume.** After a compaction, or in a session that loads this skill on a
spec with a run: Step 1, which starts nothing over, then Step 2. "What is it
waiting on" is answered from `status`: each job's stage, and the question
behind each `needs-owner` row.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Reading a diff, a log or a review body to judge a job | `head -3` of the file; the script and the next agent read the rest |
| Starting reviewers while the gate reads `GATE: FAIL` | `job advance <dir> build`, then a new builder with the `checks.md` path |
| Resuming a builder, or retrying a failed fix round on the same tier | A new builder from the pushed head, one tier up, up to top |
| Deciding a builder's fork, or rewording the owner's answer | One line to the owner; their words, saved to a file, to `job answer --from` |
| Editing `job.json` or `run.json` to move a job | `job advance`; a refusal names the evidence that is missing |
| Pasting spec text, a diff or findings into a prompt | The filled template: paths, round and purpose |
| `gh pr merge`, or marking the final pull request ready | `job merge` for a step; the owner merges the final pull request |
| Continuing from memory after a compaction | `job next`, then exactly what its lines say |
