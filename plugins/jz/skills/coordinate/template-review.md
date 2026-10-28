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

Do not trust the worker's run. Check the head out detached into a throwaway worktree, install from the lock file, and run the gate named in the phase brief there:

```bash
git fetch origin <branch>
head="$(git rev-parse origin/<branch>)"
[ "$head" = "<sha the worker reported>" ] || echo "head moved since the report"
gate_dir="$(mktemp -d)"
git worktree add --detach "$gate_dir" "$head"
( cd "$gate_dir" && <real gate command> ) > review-gate.log 2>&1; echo "exit=$?"
git worktree remove --force "$gate_dir"
```

A red gate is a P1 and ends the review there; report it with the output tail.

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
| Tests | Guard-deletion sampling: for each new rejecting branch, delete the guard, run the package tests, restore. A guard whose deletion stays green is a P2 and the test that should have caught it is named |
| Scope | Anything built that Not asked for now excludes, and anything in Done means that is missing |
| Docs | A README, guide or doc comment the change made wrong |

## Findings

Every finding has a priority and a `file:line` that exists on the reviewed head. One without a line is dropped.

| Priority | Means |
|---|---|
| P1 | Blocks merge: wrong behaviour, a red gate, a claim the probe disproves, a one-way door taken without an ADR |
| P2 | Fix before merge unless the coordinator says otherwise: a surviving guard deletion, a boundary violation, a duplicate of existing code, a missing negative test |
| P3 | Fix now or in the next row: naming, a doc drift, tidying |

Format, in the review file and in the posted review:

```markdown
| ID | Priority | Location | Finding |
|---|---|---|---|
| R1 | P1 | `packages/core/src/verify.ts:42` | <one sentence> |
```

Followed by one section per finding: the cited lines quoted, why it matters here, and the fix with the command that proves it.

## Post

<one COMMENT review on the PR, as a single review, without asking first | hold the review in the session and post only when the owner says so>

Never approve and never request changes; the verdict goes to the coordinator, and the owner's merge click is the approval. No emoji, model names, AI identifiers or session links in the posted text; the repo's restricted words stay out too.

## Verdict and report

Message the coordinator with:

- Verdict: merge as is, after fixes, or rework. After fixes means every P1 and P2 has a named fix; rework means the approach is wrong for a reason an ADR or the phase brief settles
- Head SHA reviewed, and the detached gate: command, exit code, counts line
- The probe result on base and on candidate
- The findings table
- The review file path, and the URL of the posted review or that it is held
- A second pass on a new head classifies each earlier finding as fixed, not fixed or no longer applicable, each with a line
