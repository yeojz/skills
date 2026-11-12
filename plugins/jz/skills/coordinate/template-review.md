# Review PR <number>: <PR title>

<!--
Filled by the coordinate skill for one pull request. The reviewer is a fresh
session and never the implementer. Every field is filled. Delete this
comment before sending.
-->

Model tier: <the tier first, from rules/models.md: strong, or top for a subtle or security-sensitive step, one that needed an escalated fix round, or one touching an ADR-tier decision. Then the family: the other one from the coordinator's where present, otherwise the coordinator's. Name the host, its model and its reasoning effort for that tier>
Repo: <absolute path to the main checkout>
PR: <URL>, branch `<branch>` into `<default branch>`, head `<sha the worker reported>`
Notes folder: <absolute path>; write the review as `review-pr<number>.md` there
Phase brief: `<notes folder>/phase-<unit id>.md`, so the review judges the PR against what was asked

You did not write this change and must not edit it. Findings go to the PR and the review file; fixes are someone else's round.

## Read first, in this order

1. `AGENTS.md`, the Standing orders section in particular
2. `CONTEXT.md` and the ADRs the phase brief lists
3. The phase brief, for Scope, Not asked for now and Done means
4. The PR diff, three-dot against the default branch, then every changed file whole and the callers of every changed signature

## Gate on a clean detached checkout

Do not trust the worker's run. Check the head out detached into a throwaway worktree, install from the lock file, and run the gate named in the phase brief there. The worktree is the candidate for the whole review: the criteria, the probe and the guard sample below run in it, so it stays until the Cleanup section removes it.

```bash
git fetch origin <branch>
head="$(git rev-parse origin/<branch>)"
[ "$head" = "<sha the worker reported>" ] || echo "head moved since the report"
gate_dir="$(mktemp -d)"
git worktree add --detach "$gate_dir" "$head"
( cd "$gate_dir" && <real gate command> ) > review-gate.log 2>&1; echo "exit=$?"
```

A red gate is a P1 and ends the review there; report it with the output tail, then run the Cleanup section before reporting.

## Criteria

The phase brief lists the step's criteria under Done means, and the worker's verify block has a row for each. In `$gate_dir`, run every criterion's check as written (a Drive step through the recipe's Launch and Cleanup; an inspection judged against its written standard) and compare:

```bash
( cd "$gate_dir" && <check from the brief> ) > review-criterion-<id>.log 2>&1; echo "exit=$?"
```

| Criterion | Check | Result here | Worker's row | Finding |
|---|---|---|---|---|
| C<r>.<n> <scenario> | `<check>` | pass, exit 0 | pass, exit 0 | none |

A criterion that fails or is not met here, whose worker row is missing or reads `not run`, or whose check here differs from the brief's, is a P1 naming it.

## Correctness probe, base against candidate

Pick the behaviour the phase brief says you see when it works. Exercise it on the base branch and on the candidate with the same inputs, and paste both results. A difference the PR did not claim is a finding; a claim the probe cannot reproduce is a P1.

<the probe: the command, script, fixture or request to run, and the expected difference>

## Measurement reproduction

<when the PR claims a number, such as a latency, a size or a throughput: the exact command, the sample count, and that base and candidate samples are interleaved rather than run in two blocks; otherwise "the PR claims no number">

## Review

Run the `review` skill in change mode on `$gate_dir`, with its four lenses that always report (Design, Maintainability, Guard deletion, Criteria) at the same weight as correctness. The Criteria section above is that lens's run; don't repeat its checks. Add two lenses of this brief's own:

- Scope: anything built that Not asked for now excludes, and anything in Done means that is missing.
- Docs: a README, guide or doc comment the change made wrong.

## Findings

Every finding has a priority and a `file:line` that exists on the reviewed head. One without a line is dropped. The priorities follow the `review` skill's severities so the two reports read the same: Critical and High are P1, Medium is P2, Low is P3.

| Priority | Means |
|---|---|
| P1 | Blocks merge: wrong behaviour, a red gate, a claim the probe disproves, a criterion that fails or is not met here or has no row in the worker's block, a one-way door taken without an ADR, a surviving guard deletion, a boundary violation that will cause a defect |
| P2 | Fix before merge unless the coordinator says otherwise: a duplicate of existing code, a missing negative test, a doc the change made wrong |
| P3 | Fix now or in the next step: naming, consistency, tidying |

Format, in the review file and in the posted review:

```markdown
| ID | Priority | Location | Finding |
|---|---|---|---|
| F1 | P1 | `packages/core/src/verify.ts:42` | <one sentence> |
```

Followed by one section per finding: the cited lines quoted, why it matters here, and the fix with the command that proves it.

## Cleanup

Nothing below needs the candidate checkout. Remove it now, after the last guard has been restored, whatever the verdict:

```bash
git worktree remove --force "$gate_dir"
git worktree prune
```

## Post

<from the step's Review gate: "owner reviews before merge" means post one COMMENT review on the PR, as a single review, without asking first; "none" means keep it in the review file and post only when the owner says so>

Never approve and never request changes; the verdict goes to the coordinator, and the owner's merge click is the approval. No emoji, model names, AI identifiers or session links in the posted text; the repo's restricted words stay out too.

## Verdict and report

A script reads the review file's first three lines and its Criteria table, so they are exact:

```markdown
VERDICT: after fixes
COMMIT: <head sha reviewed>
FINDINGS: <n> P1, <n> P2, <n> P3, <n> not fixed
```

Line 1 is `VERDICT: merge as is`, `VERDICT: after fixes` or `VERDICT: rework`. After fixes means every P1 and P2 has a named fix; rework means the approach is wrong for a reason an ADR or the phase brief settles. `not fixed` counts the earlier findings a second pass found still open, and is 0 on a first pass. Below those lines the file carries:

- The detached gate: command, exit code, counts line
- The probe result on base and on candidate
- The criteria table: one line per criterion with the result here and the worker's row
- One line each for Design, Maintainability and Guard deletion, clean or not, with what was checked; the guard deletion line gives the counts: rejecting guards in the diff, sampled at which sha with which test command, survived, and not sampled with a reason each
- The findings table
- The URL of the posted review, or that it is held
- A second pass on a new head rewrites the file for that head and classifies each earlier finding as fixed, not fixed or no longer applicable, each with a line

Then message the coordinator with the three lines and the review file's path, and nothing else.
