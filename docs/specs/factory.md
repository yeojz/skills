# Factory and intake

Status: draft

Glossary: `CONTEXT.md`. ADRs: `docs/adr/`.

## Problem

The owner settles a spec with `grill` and `criteria`, and then has to stay in
the loop for every step: `coordinate` reports each pull request and waits for
a merge. A fully specified, machine-checkable spec cannot run from sign-off to
a finished product on its own, and a small bug fix has to go through a full
`grill` interview before anything can build it.

## Requirements

- **R1 Unattended run.** The owner points the factory at a spec whose status
  reads `criteria signed off`, and every eligible step is built, gated,
  reviewed and merged into an integration branch without a question to the
  owner. The run ends with one pull request from the integration branch to
  the default branch, and a table of every job with its verdicts.
- **R2 Script-owned state.** Every job's stage is recorded by one script that
  refuses a move its evidence does not support. A new session that runs the
  factory on the same spec resumes each job from its recorded stage.
- **R3 Deterministic gate.** A job reaches review only after a script has run
  the repository's declared checks and the step's criteria, read from the
  commit the run started from, on the job's pushed head. The gate fails a
  branch that edits a protected path, edits a file outside the step's Owns,
  or fails any check, and no reviewer starts on a failed gate.
- **R4 Routed review.** Each step's Risk and Surfaces, recorded in the spec,
  decide which reviewers run, through a table in one config file. Every
  reviewer runs at the review tier of `rules/models.md` or above; risk
  changes the number of reviewers, never their tier.
- **R5 Sha-pinned merge.** A job merges only when its gate, every review and
  the approver's decision name the same head commit, after the branch is
  synced with the integration branch and gated again. The merge script
  refuses a pull request whose base is a protected branch.
- **R6 Escalation.** A job that meets a hard escalation condition, uses its
  last fix round, or reaches an ADR-tier fork stops at `needs-owner` with one
  specific question, and jobs that do not depend on it keep running. The
  owner's answer, given in their own words, starts the next round.
- **R7 Circuit breakers.** The run stops starting new jobs when two jobs in a
  row end at `needs-owner` or `blocked`, or when the configured concurrency
  is in use, and it says which condition stopped it.
- **R8 Eligibility.** A step with an owner review gate, an inspection-only
  criterion or a new dependency is not started by the factory. The plan
  lists each such step with the reason, and it stays available to
  `coordinate`.
- **R9 Intake.** The owner names a bug as typed text, a failing command or an
  issue number, and `intake` answers with one of four outcomes: a one-step
  spec to approve, the fewest questions that unblock it, a hand-over to
  `grill` with the facts gathered, or a rejection with the reason. Nothing
  starts intake except the owner's request.
- **R10 Intake approval.** An accepted bug is shown to the owner on one
  screen: the problem, the cause with its file and line, the pasted failing
  output, the requirement, the criterion, what is out of scope and every
  assumption. The spec's status becomes `criteria signed off` only on the
  owner's approval, and the factory refuses it before that.
- **R11 One bug or a batch.** A single approved bug runs as one job whose pull
  request targets the default branch and stops at merge-ready. Several bugs
  approved in one reply share one integration branch and one final pull
  request.

## Out of scope

- Merging into the default branch. The owner merges the final pull request on
  GitHub; ADR-0001.
- A queue that drains on its own, a schedule, or a label that starts work. A
  run starts when the owner asks for one.
- Deploying anything.
- Cost per job. The subagent transcript format it would read is not a
  documented interface.
- A dashboard. The summary table is the report.
- Changing `coordinate`. Its ledgers stay as they are; the gate script can be
  run by hand from either flow.
- Features through `intake`. A request that is not a reproducible bug goes to
  `grill`.

## Decisions

- Two flows share `grill` and `criteria`: `coordinate` keeps the owner in the
  loop, and `factory` runs unattended (round 1).
- The factory merges step pull requests into `factory/<spec-slug>`, and the
  owner merges one final pull request (round 2, Q1). ADR-0001.
- The builder, the reviewers and the approver are background subagents of
  the one session that runs the factory (round 1, Q2 option A).
- `factory` is a new skill with its own scripts, not a mode of `coordinate`
  (round 1, Q3 option A).
- Reviewers keep the review tier floor of `rules/models.md`; the light tier
  is used only for mechanical scans (round 2).
- `intake` takes only what the owner names, types or points to (round 4, Q4).
- The owner approves an intake spec before any build (round 4, Q5 option A).
- The scripts are Python 3, which the hooks already require, and are written
  for this repository rather than copied from any other project.
- The builder does not edit the spec. The job script records each
  criterion's result, so the whole spec file is a protected path during a
  run.
- An approver is a fresh subagent at the top tier, or the other family where
  present, that reads the spec, the diff and the verdict files, and runs at
  least one criterion itself.
- Step pull requests merge into the integration branch as merge commits, so
  one step can be reverted on its own.

## Criteria

## Steps

### Step 1: Risk and Surfaces in the spec

- Status: not started
- Serves: R4, R8
- Blocked by: none
- Owns: `plugins/jz/skills/grill/template-spec.md`, `plugins/jz/skills/grill/SKILL.md`, `plugins/jz/skills/grill/evals/evals.json`
- You see: a spec written by `grill` carries a Risk line and a Surfaces line on every step, with the values the owner chose
- ADRs: none
- Review gate: none

### Step 2: The gate script

- Status: not started
- Serves: R3
- Blocked by: Step 1
- Owns: `plugins/jz/skills/factory/scripts/gate`, `plugins/jz/skills/factory/config.json`, the gate's tests, `Makefile`, `validate.sh`
- You see: the gate run by hand on a branch prints `GATE: PASS` or `GATE: FAIL` with the reason, and fails a branch that edits a criterion's check
- ADRs: none
- Review gate: none

### Step 3: The job script

- Status: not started
- Serves: R2, R7, R8
- Blocked by: Step 1
- Owns: `plugins/jz/skills/factory/scripts/job`, the job script's tests
- You see: the plan command lists one job per eligible step and each ineligible step with its reason, and an illegal stage move is refused with the reason
- ADRs: none
- Review gate: none

### Step 4: One job to merge-ready

- Status: not started
- Serves: R3, R4, R6
- Blocked by: Step 2, Step 3
- Owns: `plugins/jz/skills/factory/SKILL.md`, `plugins/jz/skills/factory/evals/evals.json`, the builder, reviewer and approver briefs under `plugins/jz/skills/factory/`
- You see: the factory run on a one-step spec opens a pull request against the default branch, gates it, reviews it, and reports merge-ready or one question
- ADRs: none
- Review gate: owner reviews before merge

### Step 5: Integration branch and the full run

- Status: not started
- Serves: R1, R5, R7
- Blocked by: Step 4
- Owns: the merge and final pull request commands of `plugins/jz/skills/factory/scripts/job`, the run section of `plugins/jz/skills/factory/SKILL.md`
- You see: the factory run on a three-step spec merges three step pull requests into `factory/<spec-slug>` and opens one final pull request against the default branch
- ADRs: ADR-0001
- Review gate: owner reviews before merge

### Step 6: Intake

- Status: not started
- Serves: R9, R10, R11
- Blocked by: Step 4
- Owns: `plugins/jz/skills/intake/`
- You see: a typed bug report produces a one-step spec with a criterion seen failing, and the factory refuses that spec until the owner approves it
- ADRs: none
- Review gate: owner reviews before merge

### Step 7: Documentation

- Status: not started
- Serves: R1, R9
- Blocked by: Step 5, Step 6
- Owns: `README.md`, `AUTHORING.md`
- You see: the README's first-session walkthrough names both flows and says when to use each
- ADRs: none
- Review gate: none
