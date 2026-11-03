---
name: pr
description: Use when work needs saving to git, from branch to merged pull request, or when a PR's title and body need writing. Triggers on requests like "commit", "commit and push", "commit, push and open pr", "open a draft PR", "mark the PR ready", "write the PR description", "update the PR body", "the PR body is too long", "main has moved, rebase", "PR 12 merged, clean up", "save my work to git", or when a feature or fix is finished and needs to be persisted.
---

# pr

## Overview

Takes finished work from the working tree to a merged pull request: commit,
push, draft PR with a body written from the diff, ready when asked, rebase
when the default branch moves, cleanup after the merge. The rules in
`rules/git-workflow.md` apply throughout; this skill does not repeat them.

## Modes

Do what the request named and stop. Never upgrade: "commit" never becomes a
push, a push never becomes a PR, a PR never becomes ready.

| Request | Sections |
|---|---|
| "commit" | Worktree, Commit |
| "commit and push" | Worktree, Commit, Push |
| "commit, push and open pr" | Worktree, Commit, Push, PR body |
| "... and mark ready" | the above, then Ready |
| "write / update the PR description" | PR body |
| "main has moved, rebase" | Rebase |
| "PR 12 merged, clean up" | Cleanup |

A push and a draft PR can be withdrawn, so they need no question beyond the
request. Ready, merge and force push wait for a go-ahead that names them; the
`confirm-remote-writes.sh` hook asks the host for those, so do not ask again
in prose.

## Workflow

### Worktree

Reuse the task's worktree if one exists (`git worktree list`, then
`git branch --list "*<scope>*"`); ask with lettered options when more than
one fits. Otherwise create one under `.claude/worktrees/`. In Claude Code,
`EnterWorktree` names the branch `worktree-<name>`, so rename it at once:

```bash
git branch -m <type>/<scope>-<description>
```

If the current branch is the default branch, branch before anything else.
If `.claude/` is not ignored, offer to add it to `.git/info/exclude` before
creating the worktree.

### Commit

1. Run the `verify` skill. Do not commit on top of a failing check; fix the
   cause. Keep its report for the PR body.
2. Stage the files this task changed, by name:

   ```bash
   git add -- <path> <path>
   git diff --staged --name-status
   ```

   Then check nothing of this task's was missed: `git status --short`.
   If nothing is staged and commits exist ahead of `origin/<base>`, the work
   was committed earlier: go on to Push.
3. Write the message from `git diff --staged`, not from the conversation:
   a Conventional Commit subject under 72 characters, and a body saying why.
4. On a pre-commit hook failure, read the output, fix the cause, run
   `verify` again, re-stage and retry. Stop after 3 attempts and report what
   blocks the commit.

### Push

```bash
git push --set-upstream origin <branch>
gh pr view <branch> --json number,isDraft,url
```

If a PR exists and the push changed the diff, rewrite its body (PR body,
update).

### PR body

Read the diff and the commit subjects, never the transcript:

```bash
base="$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\)[[:space:]]*HEAD$|\1|p')"
git fetch origin "$base"
git diff "origin/$base...HEAD"
git log "origin/$base..HEAD" --format='%s'
```

Three dots: two dots would describe whatever landed on the default branch
since the branch started.

Fill `template.md` from this directory. The title is a Conventional Commit
subject, because the PR squash-merges into it.

- **With a spec** (a `docs/specs/*.md` the branch serves): one line per
  requirement the PR touches, saying what changed and which criteria prove it.
  Name any ADR the PR adds under Decisions. A criterion still failing or not run
  goes under Follow-ups with the step that will close it. Do not paste the
  Criteria table.
- **Sections**: Summary, Trade-offs, Follow-ups and Verification, plus
  Requirements and Decisions when there is a spec.
- **Verification**: one bullet per command that ran on this head, with its
  exit code and the result line copied from the output. A run from before
  the last commit, from memory, or from CI is not a bullet.
- **A deliberate compromise in the diff** (an ignored advisory, a pinned
  version, a skipped test): say what, why, and a concrete revisit condition.
- Omit a section with nothing real in it. No empty headings.

Create as a draft:

```bash
gh pr create --draft --title "<title>" --body-file <file>
```

To update an existing body, show the current and proposed text, name what
is removed, and wait for a yes before `gh pr edit <n> --body-file <file>`.

### Ready

Only when the go-ahead or the brief named it, and only when `verify` passed
on the pushed head and no check has failed:

```bash
gh pr checks <n>
gh pr ready <n>
```

### Rebase

Rebase, never merge; the `rebase-not-merge.sh` hook enforces it. First prove
the local branch holds everything on the remote:

```bash
base="$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\)[[:space:]]*HEAD$|\1|p')"
git fetch origin "$base" "<branch>"
old="$(git rev-parse "origin/<branch>")"
git merge-base --is-ancestor "$old" HEAD || echo DIVERGED
```

On `DIVERGED`, stop and show `git log --oneline HEAD..$old`: someone else's
commits would be lost. Otherwise:

```bash
git rebase "origin/$base"
```

Resolve conflicts by reading both sides; never `--skip`. If one can't be
resolved, `git rebase --abort` and report the paths. Run `verify` on the
rebased tree, check with `git range-diff "origin/$base" "$old" HEAD` that
every commit survived (no `<` line), then push with a lease on the old head:

```bash
git push --force-with-lease="<branch>:$old" origin <branch>
```

If the lease fails, fetch and start again. Never fall back to `--force`.

### Cleanup

"Merged" is a claim. Check it, and check the branch didn't move after the
merge:

```bash
gh pr view <n> --json state,headRefOid
git rev-parse <branch>
git ls-remote --heads origin <branch>
git -C <worktree> status --porcelain
```

Go on only when `state` is `MERGED`, both tips equal `headRefOid` (or the
remote branch is gone), and the worktree is clean. Anything else: stop and
report it. Then, from the main checkout:

```bash
git worktree remove .claude/worktrees/<name>
git branch -D <branch>
git push --force-with-lease="<branch>:<headRefOid>" origin --delete <branch>
git fetch --prune origin
```

Skip the remote delete when `ls-remote` printed nothing.

`-D` is safe here because the merge and the tip check prove it; squash
merges make `-d` refuse. Fast-forward the main checkout if it is on the
default branch and clean.

### Report

Say what ran and what didn't: branch, commit sha and subject, push result,
PR URL and draft or ready, and for a rebase or cleanup the commands' output
lines that prove it.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Pushing after "commit", or opening a PR after "commit and push" | The request is the scope. Stop and report. |
| Asking before a push or draft PR the request named | Both can be withdrawn. Run them. |
| Writing the body from the conversation | Read the three-dot diff and commit subjects. |
| Pasting the spec's Criteria table into the body | One line per requirement: what changed, which criteria prove it. |
| A Verification bullet with no exit code, or from an earlier head | Cite the run on this head, with its output. |
| Rebasing while `origin/<branch>` has commits local lacks | Ancestor check first; `DIVERGED` is a stop. |
| Deleting a branch on the word "merged" | `MERGED`, and both tips equal `headRefOid`. |
