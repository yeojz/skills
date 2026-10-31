# Review PR <number>: <PR title>

<!--
Filled by the coordinate skill for one pull request. The reviewer is a fresh
session and never the implementer. Every field is filled. Delete this
comment before sending.
-->

Model tier: <the review tier from rules/models.md; never below it>
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

Do not trust the worker's run. Check the head out detached into a throwaway worktree, install from the lock file, and run the gate named in the phase brief there. The worktree is the candidate for the whole review: the acceptance commands, the probe and the guard sample below run in it, so it stays until the Cleanup section removes it.

```bash
git fetch origin <branch>
head="$(git rev-parse origin/<branch>)"
[ "$head" = "<sha the worker reported>" ] || echo "head moved since the report"
gate_dir="$(mktemp -d)"
git worktree add --detach "$gate_dir" "$head"
( cd "$gate_dir" && <real gate command> ) > review-gate.log 2>&1; echo "exit=$?"
```

A red gate is a P1 and ends the review there; report it with the output tail, then run the Cleanup section before reporting.

## Acceptance criteria

The phase brief lists each criterion under Done means with the command that proves it, and the worker's verify block carries one row per criterion. In `$gate_dir`, the detached checkout the gate ran in, run every criterion's command as written and record its exit code, a Drive step through the recipe's Launch and Cleanup:

```bash
( cd "$gate_dir" && <command from the brief> ) > review-accept-<n>.log 2>&1; echo "exit=$?"
```

Then check each against the worker's row:

| Criterion | Command | Exit here | Worker's row | Finding |
|---|---|---|---|---|
| <sentence from the brief> | `<command>` | 0 | pass, exit 0 | none |

A criterion whose command fails here, whose worker row is missing or reads `not run`, or whose command here differs from the one the brief names, is a P1 that names the criterion by its sentence. <the criteria, copied from the brief | "the brief lists no acceptance criteria">

## Correctness probe, base against candidate

Pick the behaviour the phase brief says you see when it works. Exercise it on the base branch and on the candidate with the same inputs, and paste both results. A difference the PR did not claim is a finding; a claim the probe cannot reproduce is a P1.

<the probe: the command, script, fixture or request to run, and the expected difference>

## Measurement reproduction

<when the PR claims a number, such as a latency, a size or a throughput: the exact command, the sample count, and that base and candidate samples are interleaved rather than run in two blocks; otherwise "the PR claims no number">

## Lenses, all at equal weight

| Lens | Look for |
|---|---|
| Correctness | A branch the probe did not cover, an error path that swallows, a spec clause the code contradicts, cited against the spec text |
| Design | A boundary crossed the wrong way, an abstraction with one use, an option nobody passes, a public surface wider than the row asked for |
| Maintainability | Duplication of something the workspace already has, a name that disagrees with the glossary or the sibling package, a comment that explains what instead of why, a file that will not survive the next row |
| Tests | Guard deletion, as the `review` skill's Step 4 runs it: inventory the new rejecting branches in the PR diff, then sample the ones that enforce a security boundary, prevent data loss or implement the rejection the change was asked for, in the detached worktree installed from the lock file. Snapshot the file, neutralise the condition so the file still parses, run the package's declared test script, restore from the snapshot. A sampled guard whose deletion stays green is a P1 that names the test that should have failed; every guard left unsampled is listed with its reason, and "not enough time" without the list is not one |
| Scope | Anything built that Not asked for now excludes, and anything in Done means that is missing |
| Docs | A README, guide or doc comment the change made wrong |

## Findings

Every finding has a priority and a `file:line` that exists on the reviewed head. One without a line is dropped. The priorities follow the `review` skill's severities so the two reports read the same: Critical and High are P1, Medium is P2, Low is P3.

| Priority | Means |
|---|---|
| P1 | Blocks merge: wrong behaviour, a red gate, a claim the probe disproves, an acceptance criterion that fails here or has no row in the worker's block, a one-way door taken without an ADR, a surviving guard deletion, a boundary violation that will cause a defect |
| P2 | Fix before merge unless the coordinator says otherwise: a duplicate of existing code, a missing negative test, a doc the change made wrong |
| P3 | Fix now or in the next row: naming, consistency, tidying |

Format, in the review file and in the posted review:

```markdown
| ID | Priority | Location | Finding |
|---|---|---|---|
| R1 | P1 | `packages/core/src/verify.ts:42` | <one sentence> |
```

Followed by one section per finding: the cited lines quoted, why it matters here, and the fix with the command that proves it.

## Cleanup

Nothing below needs the candidate checkout. Remove it now, after the last guard has been restored, whatever the verdict:

```bash
git worktree remove --force "$gate_dir"
git worktree prune
```

## Post

<one COMMENT review on the PR, as a single review, without asking first | hold the review in the session and post only when the owner says so>

Never approve and never request changes; the verdict goes to the coordinator, and the owner's merge click is the approval. No emoji, model names, AI identifiers or session links in the posted text; the repo's restricted words stay out too.

## Verdict and report

Message the coordinator with:

- Verdict: merge as is, after fixes, or rework. After fixes means every P1 and P2 has a named fix; rework means the approach is wrong for a reason an ADR or the phase brief settles
- Head SHA reviewed, and the detached gate: command, exit code, counts line
- The probe result on base and on candidate
- The acceptance table: one line per criterion with the exit code here and the worker's row, or that the brief lists none
- One line each for Design, Maintainability and Guard deletion, clean or not, with what was checked; the guard deletion line gives the counts: rejecting guards in the diff, sampled at which sha with which test command, survived, and not sampled with a reason each
- The findings table
- The review file path, and the URL of the posted review or that it is held
- A second pass on a new head classifies each earlier finding as fixed, not fixed or no longer applicable, each with a line
