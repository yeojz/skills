# Factory and intake

Status: draft

Glossary: `CONTEXT.md`. ADRs: `docs/adr/`.

## Problem

The owner settles a spec with `grill` and `criteria`, and then has to stay in
the loop for every step: `coordinate` reports each pull request and waits for
a merge. A fully specified, machine-checkable spec cannot run from sign-off to
a finished product on its own, and a small bug fix has to go through a full
`grill` interview before anything can build it. A long run also has to stay
within one session's context without the owner managing it.

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
- **R9 Intake.** The owner names a request as typed text, a failing command or
  an issue number, and `intake` answers with one of three outcomes: a spec to
  approve, the fewest questions that only the owner can answer, or a
  rejection with the reason. Nothing starts intake except the owner's
  request.
- **R10 Intake approval.** An accepted request is shown to the owner on one
  screen: the problem, the cause with its file and line and the pasted
  failing output for a bug, the requirements, the criteria, what is out of
  scope and every decision made for the owner. The spec's status becomes
  `criteria signed off` only on the owner's approval, and the factory refuses
  it before that.
- **R11 One bug or a batch.** A single approved bug runs as one job whose pull
  request targets the default branch and stops at merge-ready. Several bugs
  approved in one reply share one integration branch and one final pull
  request.
- **R12 Handsfree answers for the owner.** Any skill started through `handsfree` has its
  design questions answered without the owner. `handsfree` writes its own pick
  for every question before it reads the asking skill's recommendation. An
  ADR-tier question always gets a second opinion from another model, and
  any other question gets one when the first two picks differ. Every answer
  is logged with a number, the options, each pick and the reason. A question
  whose picks do not settle it under the decision rules, a new dependency,
  and a question only the owner can answer go to the owner, collected and
  asked once. `handsfree` never answers a sign-off, a merge, or a remote write
  that asks.
- **R14 Overturning.** A spec produced through `handsfree` lists its decisions
  with ADR-tier ones first. The owner overturns any decision by its number
  and letter, and the affected requirements, criteria and steps are
  rewritten before approval is asked again.
- **R15 One coordinate mode.** `coordinate` on its own brings every ADR-tier
  fork to the owner. The same run started through `handsfree` has those forks
  answered as R12 describes, and reports each one in its next line to the
  owner.
- **R13 Bounded context.** Every agent's reply to the factory session is one
  line, every script prints one line per job, and the factory session reads
  no diff, log or file body during a run. What to do next comes from the job
  script after every finished job, so a session that was compacted or
  replaced continues the run with no hand-over note and no question to the
  owner.

## Out of scope

- Merging into the default branch. The owner merges the final pull request on
  GitHub; ADR-0001.
- A queue that drains on its own, a schedule, or a label that starts work. A
  run starts when the owner asks for one.
- Deploying anything.
- Cost per job. The subagent transcript format it would read is not a
  documented interface.
- A dashboard. The summary table is the report.
- Changing `coordinate` beyond moving its auto mode out. Its ledgers stay as
  they are; the gate script can be run by hand from either flow.
- Changing how `grill` interviews the owner. The interview stays for work the
  owner wants to settle in person; `intake` is the path that answers for
  them.

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
- A request too large for one step stays in `intake`; the owner reads the
  finished spec and overturns what they disagree with (round 5).
- `handsfree` is its own skill: it answers in the owner's place for any skill
  that asks lettered questions, and it replaces `coordinate`'s auto mode
  (round 8). `coordinate`'s option review template moves to it.
- `handsfree` takes any command: it wraps whichever skill the owner names,
  the factory included. Under it a factory job's ADR-tier fork is answered
  rather than parked, and a hard escalation condition still goes to the
  owner (round 9).
- `handsfree` never answers a question its own context framed. `grill` and
  `criteria` run as subagents and `handsfree` answers them; under `coordinate`
  the workers raise the forks and the session running `handsfree` answers them.
- `handsfree` is a second assessor on every question, never a pass-through
  (round 8). The decision rules: below the ADR tier, two matching picks
  decide and a second opinion breaks a split, with the dissent logged; at
  the ADR tier, the recommendation, `handsfree`'s pick and the second opinion
  must all match, otherwise the owner chooses.
- The second opinion comes from the other family where present, otherwise
  from this family, and it sees the question and options only. The majority
  rule below the ADR tier is the owner's choice (round 10, Q6 option A).
- Second opinions are asked once per round, covering every question in that
  round that needs one, never once per question.
- Below the ADR tier the second opinion comes from one assessor thread per
  run, at the standard tier, which reads the spec, the glossary and the ADRs
  once and works from the facts the asking skill gathered. At half its
  context it is retired and a new one starts from the decision log.
- An ADR-tier second opinion comes from a fresh session at the top tier that
  does its own research, since these are few and independence matters most
  there.
- A question the asking skill states as an assumption gets no second
  opinion; `handsfree` objects to it or lets it stand.
- `intake` writes no spec text itself. It investigates, reproduces a bug,
  then runs `grill` in spec mode and `criteria` through `handsfree`, so both
  skills run the same way on both paths. The owner's one approval of the
  intake spec is the sign-off `criteria` asks for (rounds 6 and 7).
- Each round passes through files: the asking skill writes its questions in
  one file and its recommendations in another and stops, and `handsfree` writes
  its picks, reads the recommendations, writes the answers and starts the
  skill again from the spec written so far. The session running `handsfree`
  holds the decisions, never the interview.
- `grill` gains two things: each question is marked ADR-tier or not, and a
  round can be written to files as above. Its interview of the owner is
  otherwise unchanged.
- An ADR from an `handsfree` decision carries the model sign-off line, naming the
  session running `handsfree`, the asking skill's session and the second
  opinion.
- A new dependency chosen by `intake` is always listed as an ADR-tier
  decision, and a step that adds one stays ineligible for the factory.
- Each builder, reviewer and approver starts fresh and reads the spec step,
  the diff and the first lines of earlier verdict files. A fix round after a
  failed one starts a new builder from the pushed head rather than resuming
  the old one.
- Every file an agent writes opens with its verdict line and a summary of
  three to five bullets, and the gate's report holds the last 80 lines of a
  log with the full log beside it.
- A job branch is `factory-job/<spec-slug>/<job id>`, since git cannot hold
  both a branch `factory/<slug>` and one beneath it.
- An owner who accepts a hard escalation condition as it stands does so
  through the job script's `accept` command, which records what was accepted
  and lets the job merge; without it the unchanged condition would escalate
  again after every build round.
- `blocked` is reached only when the builder reports it cannot go on, or
  when the plan finds a job behind an ineligible step.
- The gate measures a job's diff against the integration branch and reads
  the spec, the criteria and `factory.json` at the run's base sha.
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

- Status: built; no criteria were written or signed off
- Serves: R4, R8
- Blocked by: none
- Owns: `plugins/jz/skills/grill/template-spec.md`, `plugins/jz/skills/grill/SKILL.md`, `plugins/jz/skills/grill/evals/evals.json`
- You see: a spec written by `grill` carries a Risk line and a Surfaces line on every step, with the values the owner chose
- ADRs: none
- Review gate: none
- Risk: low
- Surfaces: none

### Step 2: The gate script

- Status: built; no criteria were written or signed off
- Serves: R3
- Blocked by: Step 1
- Owns: `plugins/jz/skills/factory/scripts/gate`, `plugins/jz/skills/factory/config.json`, the gate's tests, `Makefile`, `validate.sh`
- You see: the gate run by hand on a branch prints `GATE: PASS` or `GATE: FAIL` with the reason, and fails a branch that edits a criterion's check
- ADRs: none
- Review gate: none
- Risk: medium
- Surfaces: security

### Step 3: The job script

- Status: built; no criteria were written or signed off
- Serves: R2, R7, R8
- Blocked by: Step 1
- Owns: `plugins/jz/skills/factory/scripts/job`, the job script's tests
- You see: the plan command lists one job per eligible step and each ineligible step with its reason, and an illegal stage move is refused with the reason
- ADRs: none
- Review gate: none
- Risk: medium
- Surfaces: none

### Step 4: One job to merge-ready

- Status: built; no criteria were written or signed off
- Serves: R3, R4, R6, R13
- Blocked by: Step 2, Step 3
- Owns: `plugins/jz/skills/factory/SKILL.md`, `plugins/jz/skills/factory/evals/evals.json`, the builder, reviewer and approver briefs under `plugins/jz/skills/factory/`
- You see: the factory run on a one-step spec opens a pull request against the default branch, gates it, reviews it, and reports merge-ready or one question
- ADRs: none
- Review gate: owner reviews before merge
- Risk: medium
- Surfaces: none

### Step 5: Integration branch and the full run

- Status: built; no criteria were written or signed off
- Serves: R1, R5, R7
- Blocked by: Step 4
- Owns: the merge and final pull request commands of `plugins/jz/skills/factory/scripts/job`, the run section of `plugins/jz/skills/factory/SKILL.md`
- You see: the factory run on a three-step spec merges three step pull requests into `factory/<spec-slug>` and opens one final pull request against the default branch
- ADRs: ADR-0001
- Review gate: owner reviews before merge
- Risk: high
- Surfaces: security

### Step 6: The handsfree skill

- Status: built; no criteria were written or signed off
- Serves: R12, R14, R15
- Blocked by: Step 1
- Owns: `plugins/jz/skills/handsfree/`, `plugins/jz/skills/coordinate/`, the question tier mark and round files in `plugins/jz/skills/grill/SKILL.md` and its evals
- You see: `grill` started through `handsfree` produces a spec whose decisions are numbered with every pick, an ADR-tier decision shows three picks, and `coordinate` no longer has a Modes section
- ADRs: none
- Review gate: owner reviews before merge
- Risk: medium
- Surfaces: none

### Step 7: Intake

- Status: built; no criteria were written or signed off
- Serves: R9, R10, R11, R14
- Blocked by: Step 4, Step 6
- Owns: `plugins/jz/skills/intake/`
- You see: a typed bug report produces a one-step spec with a criterion seen failing, the factory refuses that spec until the owner approves it, and replying with a number and letter rewrites the steps that decision affects
- ADRs: none
- Review gate: owner reviews before merge
- Risk: medium
- Surfaces: none

### Step 8: Documentation

- Status: built; no criteria were written or signed off
- Serves: R1, R9
- Blocked by: Step 5, Step 7
- Owns: `README.md`, `AUTHORING.md`
- You see: the README's first-session walkthrough names both flows and says when to use each
- ADRs: none
- Review gate: none
- Risk: low
- Surfaces: none
