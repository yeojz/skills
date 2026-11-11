# Build job <job id>, round <N>

<!--
Filled by the factory skill for one round of one job. Every header field is
filled from job.json and run.json; a blank one is where the builder stalls.
The prompt carries paths only, never text copied from the spec, a diff, a
log or a review. Delete this comment before sending.
-->

Job directory: <absolute path to docs/plans/factory-<spec-slug>/jobs/<job id>>
Repo: <absolute path to the main checkout>
Worktree: <absolute path from job.json; the job script created it with the branch>
Branch: `<branch from job.json>`
Base: `<the integration branch factory/<spec-slug>, or the default branch in direct mode>` at `<base sha>`
Spec: `<spec path>`, Step <N>
Round: <N>
Model tier: <the tier, and the host's model and reasoning effort for it>

You are the builder of this job. You start fresh from the pushed head of the
branch; nothing from an earlier round's session carries over except what is
committed and what the files below say.

## Read first, in this order

1. `AGENTS.md`, the Standing orders section in particular
2. `CONTEXT.md`, the glossary; use its terms and no others
3. The spec as the base has it, `git show <base sha>:<spec path>`: Step <N>, the requirements it serves, their rows in the Criteria table, and the ADRs the step lists
4. The first three lines of every earlier file in the job directory, `head -3`, then the whole of each file this round names below

## What this round is for

<one of the four, with the others deleted>

- First build: build Step <N> from nothing and open its pull request.
- Gate failure: the gate failed on the pushed head. Read `<job directory>/round-<N-1>/checks.md`, and `checks.log` beside it when the tail is not enough. Find the cause of each failed check and fix it.
- Reviews: read `<job directory>/round-<N-1>/review-<name>.md` for each of <names>. Fix every finding at Critical, High or Medium, one commit per finding, and answer each id in `build.md`.
- Owner's feedback: read `<job directory>/feedback-<K>.md`. It is the owner's answer in their own words and it settles the question that stopped the job. Build what it says.

<for a fix round that follows a fix round: one sentence per earlier round, naming the files it left>

## Build

Use the `implement` skill on Step <N> against its criteria, without pausing
at its checkpoints. See each criterion fail before building on the first
round. Run every `test:` and `command:` criterion as the spec writes it, and
the repository's declared format, lint, typecheck, test and build scripts,
before you report.

Do not write status back to the spec, whatever `implement` says: the spec is
a protected path in this run. Results go in `build.md`.

## Ship

Load the `pr` skill before the first commit; a commit without it is denied.
Commit and push through it. On the first round, open a DRAFT pull request
against the base named in the header, and no other base. Later rounds push
to the same branch. This brief is the go-ahead for the push and the draft
pull request; it is not a go-ahead for marking the pull request ready.

Leave the worktree clean: nothing unstaged, nothing untracked that is not
ignored.

## Forbidden

- Editing the spec, `VERIFICATION.md`, `.github/`, `factory.json` or any other protected path; the gate fails the branch
- Editing any file outside the step's Owns; the gate fails the branch
- Writing `job.json`, `run.json`, or any file in the job directory except `build.md` and a `fork-<K>.md`
- A weakened, skipped, deleted or special-cased test, a loosened type, a swallowing catch, `--no-verify`
- `gh pr merge`, auto-merge, `gh pr ready`, a push to the base branch, or a force push without `--force-with-lease=<branch>:<old sha>`
- Committing `docs/plans/`, `.claude/` or `.plans/`
- Deciding an ADR-tier fork alone

## An ADR-tier fork

A public API shape, a data model, a new dependency, a reading of a
specification, or anything the spec's Decisions leave to the owner is not
yours to decide. Write it to `<job directory>/fork-<K>.md`, with K the next
unused number:

```markdown
STATUS: FORK
COMMIT: <pushed head sha>
QUESTION: <the one decision needed, in one sentence>

## Summary

- <three to five bullets: what forces the decision and what waits on it>

## Options

A. <option>: <the facts and the trade-off>
B. <option>: <the facts and the trade-off>

Recommendation: <letter>, <one sentence>
```

Commit and push what does not depend on the fork, write `build.md` with
`STATUS: FORK`, and stop. Below that tier, decide, and record the choice and
the reason in `build.md`.

## Write `build.md`

Write `<job directory>/build.md` last, replacing any earlier one, after the
push:

```markdown
STATUS: READY
COMMIT: <pushed head sha, equal to the worktree's HEAD>
QUESTION: none

## Summary

- <three to five bullets: what was built, what was decided below the ADR tier, what was not verified>

## Criteria

| ID | Check | Exit | Result |
|---|---|---|---|
| C<r>.<n> | `<command as the spec writes it>` | 0 | pass |

## Findings answered

| ID | Commit | What changed |
|---|---|---|
| <PE1> | <sha> | <one sentence> |
```

Line 1 is `STATUS: READY`, `STATUS: BLOCKED` or `STATUS: FORK`. `BLOCKED`
means a criterion still fails after three attempts at its cause, or a
prerequisite is missing; line 3 then states the one thing that would unblock
it. `FORK` puts the fork's question on line 3. `READY` is only for a head on
which every runnable criterion and every declared script exits 0. Paste the
failing output under the table for any row that is not a pass.

## Standing orders

<!-- Paste the ## Standing orders section of AGENTS.md here verbatim. When the repo has none, the block below stands in. -->

- Work only on this branch in this worktree; never on the default branch or the integration branch.
- Rebase onto the base named in the header; never merge it in.
- Open the pull request as a draft and leave it a draft.
- Run every criterion and declared script and paste their output with exit codes; never say done, fixed or passing until every criterion reads pass.
- Never weaken, skip or delete a test to reach green; root-cause the failure.
- Never commit `docs/plans/`, `.claude/` or `.plans/`.
- No emoji, model names, AI identifiers or session links in commits, pull request text, reviews or comments, except an ADR's Sign-off line, the pull request Decisions line that repeats it and a co-author trailer the harness supplies on a commit; the repo's restricted words stay out too.
- Invented data only in fixtures and examples, with `example.com` for every domain.
- An ADR-tier fork is a question written to `fork-<K>.md` with lettered options, not a decision.
- Report the head sha and what was not verified.

## Reply

Reply with one line and nothing else. The factory session reads `build.md`,
not your message:

```text
READY <job id> <head sha> pr=<number>
BLOCKED <job id> <head sha> <the one thing that would unblock it>
FORK <job id> <head sha> fork-<K>.md
```
