# Decide job <job id>

<!--
Filled by the factory skill once every routed reviewer of the round reads
VERDICT: PASS. The approver is a fresh subagent at the top tier, or on the
other family where present, and never the builder or a reviewer of this job.
The prompt carries paths only. Delete this comment before sending.
-->

Job directory: <absolute path to docs/plans/factory-<spec-slug>/jobs/<job id>>
Repo: <absolute path to the main checkout>
Worktree: <absolute path; run in it, never edit it>
Branch: `<branch>`, pull request <number>
Base: `<base branch>` at `<base sha>`
Diff base: `<gate_base from job.json>`, which the change is measured against; the spec is read at the base sha
Spec: `<spec path>`, Step <N>
Round: <N>
Model tier: <top, and the host's model and reasoning effort for it>

You decide whether this job merges or goes to the owner. You did not build
or review it, and you edit nothing.

## Read, in this order

1. `AGENTS.md` and `CONTEXT.md`
2. The spec as the base has it: `git show <base sha>:<spec path>`. Read Step <N>, the requirements it serves, their rows in the Criteria table, and the ADRs the step lists
3. The head and the diff:

```bash
git -C "<worktree>" rev-parse HEAD
git -C "<worktree>" diff "<diff base>...HEAD"
```

4. The gate's report for this round, `<job directory>/round-<N>/checks.md`: its three header lines and its two tables
5. Every `<job directory>/round-<N>/review-*.md`: header, Summary and findings table, the Low findings included
6. From `<job directory>/build.md`, the header and the Criteria table only

Do not read the Summary of `build.md` or any reasoning the builder wrote.
Your decision rests on the spec, the diff and what you run, not on the
builder's account of it.

## Run at least one criterion yourself

Pick the criterion that proves the most about this step, and run its command
in the worktree exactly as the base's spec writes it. Paste the command, its
output and its exit code into `decision.md`. Run more when the diff gives a
reason to doubt a row. Confirm the worktree is unchanged afterwards:

```bash
git -C "<worktree>" status --porcelain
```

## Decide

`APPROVE` only when all three hold:

- Every criterion of the requirements the step serves is met on this head: the gate's criteria table reads pass for each runnable one, and your own run agrees.
- The change stays inside Step <N>: nothing outside its Owns, nothing a later step owns, no decision taken that an ADR or the spec's Decisions leave to the owner.
- No review note describes a real problem. Read each Low finding and each Summary bullet as a claim to check against the diff; one that holds is a reason to escalate, whatever its severity.

Otherwise `ESCALATE`, and state the exact decision you need from the owner
as one question they can answer in a sentence. "Please review" is not a
question; "C2.1 passes only because the fixture skips the expired case: fix
the fixture, or accept the gap?" is.

Hard escalation conditions, such as a dependency manifest change, a deleted
test, a skip marker or a high Risk, are the job script's: it reads the
gate's `ESCALATE:` line and sends the job to the owner whatever you decide.
Do not derive them again and do not weigh them; decide on the three points
above.

## Write `decision.md`

Write `<job directory>/decision.md`, replacing any earlier one:

```markdown
APPROVE
COMMIT: <the head sha you decided on>
QUESTION: none

## Summary

- <three to five bullets: what was read, what was run, what decided it>

## Criterion run here

<the command, its pasted output and its exit code>

## Checks against the three points

| Point | Holds | Evidence |
|---|---|---|
| Every criterion met | yes | <rows and the run above> |
| Inside the step | yes | <the changed paths against Owns> |
| No real problem in a review note | yes | <each note and why it does not hold, with `file:line`> |
```

Line 1 is `APPROVE` or `ESCALATE`, with no label before it. Line 2 is the
sha from `rev-parse`. Line 3 is `QUESTION: none` on an approval, and the one
question for the owner on an escalation.

## Forbidden

- Editing anything in the worktree or the repo, and writing any file except `decision.md`
- Posting to GitHub, approving or merging the pull request, or marking it ready
- Approving with a criterion not run by anyone, or on a commit other than the head
- Emoji, model names, AI identifiers or session links in `decision.md`

## Reply

Reply with one line and nothing else. The factory session reads the header
of `decision.md`, not your message:

```text
APPROVE <job id> <head sha>
ESCALATE <job id> <head sha> <the question>
```
