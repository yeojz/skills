# Review job <job id>, round <N>, as <persona name>

<!--
Filled by the factory skill, once per routed reviewer per round, and sent to
the subagent type jz:<persona name>. All reviewers of a round start in one
message. The prompt carries paths only, never text copied from the spec, the
diff or another agent's file. Delete this comment before sending.
-->

Job directory: <absolute path to docs/plans/factory-<spec-slug>/jobs/<job id>>
Repo: <absolute path to the main checkout>
Worktree: <absolute path; read it, never change it>
Branch: `<branch>`, pull request <number>
Base: `<base branch>` at `<base sha>`
Spec: `<spec path>`, Step <N>
Round: <N>
Review file: `<job directory>/round-<N>/review-<persona name>.md`
Model tier: <the tier, and the host's model and reasoning effort for it>

You did not write this change and must not edit it. You are a fresh session:
judge the head as it stands, through your persona's lens.

## Read first, in this order

1. `AGENTS.md` and `CONTEXT.md`
2. The spec as the base has it, never the branch's copy: `git show <base sha>:<spec path>`. Read Step <N>, the requirements it serves, their rows in the Criteria table, and the ADRs the step lists
3. The head and the diff, in the worktree:

```bash
git -C "<worktree>" rev-parse HEAD
git -C "<worktree>" diff --stat "<base sha>...HEAD"
git -C "<worktree>" diff "<base sha>...HEAD"
```

4. Every changed file whole, and the callers of every changed signature
5. `head -3` of this round's `checks.md`, and in a round after the first, your own earlier review file whole

## What to judge

The gate already ran the declared checks and the step's criteria on this
head, so do not run them again. Judge what a script cannot:

- Correctness: the behaviour the step's You see field describes, the edge cases the criteria do not reach, and anything the diff breaks for a caller.
- Scope: every change belongs to Step <N>; nothing is built that a later step owns, and nothing the step asks for is missing.
- Cause: in a fix round, the fix removes the cause of the finding or the failed check, and does not hide the symptom.
- Tests: any test that was weakened, skipped, deleted or special-cased to pass, any assertion that proves nothing, any expected value changed to match the output. Open every changed test file.
- Your persona's own checks, as its file lists them.

In a round after the first, mark each finding of your earlier file as fixed,
not fixed or no longer applicable, each with a `file:line` on this head.

## Write the review file

Your persona is read-only for the code under review, and that holds. The one
file you write is the review file named in the header, which is run state
outside the change. Write it with a shell heredoc:

```markdown
VERDICT: PASS
COMMIT: <the head sha you reviewed>

## Summary

- <three to five bullets: what was checked, what is wrong, what was not checked>

## Findings

| id | severity | file:line | finding | suggested fix |
|---|---|---|---|---|
| <prefix>1 | High | `<path>:<line>` | <one sentence> | <one sentence> |

## Earlier findings

| id | Now | file:line |
|---|---|---|
| <prefix>1 | fixed | `<path>:<line>` |
```

- Line 1 is `VERDICT: CHANGES` when any finding is Critical, High or Medium, or any earlier finding is not fixed. Otherwise it is `VERDICT: PASS`; Low findings are listed and do not block.
- Line 2 is the sha from `rev-parse` above. A review of any other commit is refused.
- Ids use your persona's prefix and continue from your earlier file; never renumber one.
- Every finding cites a `file:line` you opened on this head. One you cannot ground is dropped.
- After the table, one short section per finding: the cited lines quoted, why it matters for this step, and the command that would prove the fix.

## Forbidden

- Editing, staging, committing or checking out anything in the worktree or the repo
- Posting to GitHub in any form: no comment, no review, no approval, no request for changes
- Writing any file except the review file, and writing `job.json` in particular
- Reading the builder's `build.md` beyond its first three lines; the diff is the evidence
- Emoji, model names, AI identifiers or session links in the review file

## Reply

Reply with one line and nothing else. The factory session reads the review
file's header, not your message:

```text
PASS <job id> <persona name> <head sha> <count> low
CHANGES <job id> <persona name> <head sha> <count> blocking
```
