---
name: ship
description: Use when the user wants to save work to git, from branching through to a pull request and its merge. Triggers on requests like "commit", "commit and push", "commit, push and open pr", "push, draft PR, gate on a clean checkout, mark ready", "mark the PR ready", "main has moved, rebase", "PR 12 merged, clean up", "save my work to git", or when a feature or fix is finished and needs to be persisted.
---

# ship

## Overview

The branch-through-merge loop: branch first, run the repo's own scripts,
verify, stage cleanly, write a conventional commit, then on one go-ahead push,
open a draft PR, gate the pushed head on a clean detached checkout and mark the
PR ready. Rebases the branch when the default branch moves and cleans up once
the PR merges. Guarantees that every task runs on its own branch in its own
worktree, nothing is committed on the default branch, no `.claude/` or plan
files are staged, no push, PR or ready flip happens without a go-ahead that
named it, the body is refreshed by `pr-desc` on every push that changes the
diff, and ready is never flipped on the strength of a run in the working tree.

## Modes

Pick the mode from what the user asked for. Do not do more than they asked.

| User asked | Mode | Runs steps |
|---|---|---|
| "commit", "commit my changes", "save my work to git" | commit only | 1-8, 15 |
| "commit and push", "push this" | commit and push | 1-9, 15 |
| "commit, push and open pr", "branch, commit and open pr" | commit, push, PR | 1-10, 15 |
| "push, draft PR, gate on a clean checkout, mark ready", "push and mark ready" | ship to ready | 1-12, 15 |
| "main has moved, rebase", "rebase onto main and push", the app's offer to merge the base branch in | rebase after upstream merge | 13, 15 |
| "PR 12 merged, clean up", "merged" | post-merge cleanup | 14, 15 |

If the mode is ambiguous, do the commit and ask before going further. Never
upgrade a mode on your own initiative: "commit" never becomes a push, and a
push never becomes a PR or a ready flip.

### One go-ahead covers what it names

A request that names push, PR and ready in one sentence is the answer to each
of those asks. "push, draft PR, gate on a clean checkout, mark ready" runs
steps 9 to 12 with no question between them, and "commit and push" runs the
push without asking again. The separate asks in steps 9 and 10 are for a
request that stopped short, such as "commit", and then grows: each further
remote write gets its own question, and a yes to one does not carry to the
next.

The go-ahead often arrives after the commit has been made. Steps 7 and 8
then find nothing to stage and the branch already carrying the commits, and
the flow continues at step 9 with that head; step 7 says how to tell.

The `confirm-remote-writes.sh` hook still asks the harness before
`gh pr create` and before any force push. That prompt is the host's. It is not
a reason to ask a second time in prose.

## Workflow

### Step 1: Work in the task's worktree

Every task gets its own branch in its own worktree under `.claude/worktrees/`,
so the main checkout stays clean and two tasks never share a tree. Reuse before
creating: a task that was started earlier already has one.

```bash
git worktree list --porcelain
git branch --list "*<scope>*"
git check-ignore -q .claude || echo ".claude/ is not ignored"
```

Match on the task's scope word, the `<scope>` from the branch naming in step 2.

| Found | Do |
|---|---|
| One worktree whose branch matches | Enter it. In Claude Code, `EnterWorktree` with its `path`; elsewhere, `cd` into it |
| One branch matches but has no worktree | Add a worktree for that branch under `.claude/worktrees/` and enter it |
| More than one candidate | Ask, with lettered options, which one is this task's |
| None | Create one, below |

In Claude Code, create with the `EnterWorktree` tool and a `name` in the
`<type>/<scope>-<description>` form. It creates `.claude/worktrees/<name>`
from the remote's default branch and moves the session there. It names the
branch `worktree-<name>` with each `/` turned into `+`, which breaks the
branch naming rule, so rename the branch straight away:

```bash
git branch -m <type>/<scope>-<description>
```

Under an agent without that tool, do the same with git and work from the new
directory:

```bash
git worktree add -b <type>/<scope>-<description> .claude/worktrees/<type>+<scope>-<description> "origin/$base"
```

`$base` is the default branch detected in step 2. If `.claude/` is not ignored
in this repo, stop before creating anything and offer to add it to
`.gitignore` or to `.git/info/exclude`; the staging hook refuses `.claude/`
either way, but an untracked worktree directory shows up in every status.

The stash is shared across every worktree of the repo, so never run a bare
`git stash`. Set work aside with a temporary commit instead.

### Step 2: Branch-first gate

This is a hard gate. Read the default branch from the remote rather than from
a local ref, because `origin/HEAD` is unset on many clones and the name may be
`main`, `master`, `develop` or anything else:

```bash
git rev-parse --abbrev-ref HEAD
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
echo "default branch: $base"
```

If the current branch is `$base`, refuse to commit. Create a branch first:

```bash
git checkout -b <type>/<scope>-<description>
```

Branch names use the Conventional Commits vocabulary, same `type` set as commit
subjects, kebab-case description:

| Change | Branch |
|---|---|
| New user-visible capability | `feat/auth-add-refresh-tokens` |
| Bug fix | `fix/parser-handle-empty-input` |
| Internal restructure | `refactor/core-extract-client` |
| Docs only | `docs/readme-quickstart` |
| Tooling, deps, CI | `chore/deps-bump-vitest` |

Uncommitted work already in the tree carries over to the new branch, so
`git checkout -b` is safe here. If the checkout is blocked by a conflict, stop
and report rather than stashing silently.

If the current branch is already a feature branch, skip to step 3 and say so.

### Step 3: Detect the package manager

Detect the package manager from the lock file as `verify` Step 2 does: the lock
file decides, never assume. Look in the repo root, or the nearest ancestor that
has a `package.json`.

If no lock file is present, read the `packageManager` field in `package.json`.
If that is also absent, ask rather than guessing. Do not mix package managers
in one repo.

If there is no `package.json` at all, look for a `Makefile` at the repo root
and list its targets:

```bash
grep -E '^[A-Za-z0-9_-]+:' Makefile | cut -d: -f1
```

The command prefix is then `make`. Steps 4 and 5 look for targets by the
same names they look for as scripts, and step 6's verify reads the Makefile
too. Only when neither file exists are steps 4 to 6 skipped, and the report
says so.

### Step 4: Format

Read `package.json` scripts and run the repo's own script. Look for `format`,
`fmt`, or a script whose command contains `prettier` or `biome format`:

```bash
<pkg-manager> run format
```

Or `make format` when the repo's commands live in a Makefile.

If no such script or target exists, skip silently. Never invent an ad-hoc
`npx prettier --write .` style command.

### Step 5: Lint fix

Look for `lint:fix`, `lint-fix`, `fix`, or a script whose command contains
`--fix` or `--write`:

```bash
<pkg-manager> run lint:fix
```

Or `make lint-fix` when the repo's commands live in a Makefile.

If no such script or target exists, skip silently.

### Step 6: Verify

Delegate the full check to the `verify` skill before committing. It runs the
repo's own lint, typecheck, test and build scripts or Makefile targets and
pastes real output. Keep its report block: steps 9 and 10 hand it to `pr-desc`,
which turns it into the Verification section of the PR body.

This run is on the working tree, before anything is staged. Whether it proved
the commit that follows is decided in step 8, not assumed here.

If `verify` is unavailable, run the repo's `package.json` scripts or Makefile
targets directly and paste the output. Either way, do not commit on top of a
failing check: root-cause the failure, do not route around it, and do not
weaken a test to make the suite green.

### Step 7: Stage with hygiene

Show the user the current state before staging:

```bash
git status
```

Never stage these, however they show up in the status output:

| Path | Reason |
|---|---|
| `.claude/` | Local agent configuration |
| `docs/plans/` | Plan files are working notes, not deliverables |
| `.plans/` | Same |

Those names are forbidden at any depth, not only at the repo root. The
PreToolUse hook matches `(^|/)(\.claude|docs/plans|\.plans)(/|$)`, so
`packages/x/docs/plans/note.md` is as forbidden as `docs/plans/note.md`.

Honour an explicit exclusion too. When the user says something like
"commit all unstaged changes, ignore `notes.local.md`", that path is excluded
for this run.

Stage by naming the paths you changed. You made the edits, so you already know
what they are. This is the main mechanism:

```bash
git add -- src/client.ts "docs/adr/0004 retry policy.md"
```

Never run `git add -A` or `git add .`: the house rules forbid it, and the
repo's own PreToolUse hook denies it whenever an unignored `docs/plans/` file
exists.

Then cross-check for anything you missed. This enumerates every changed,
deleted and untracked path that differs from the index, with the artifact
directories removed by git's own pathspec matching rather than by filtering
text in the shell:

```bash
git -c core.quotepath=false ls-files -z --modified --others --exclude-standard -- \
  ':(exclude,glob)**/.claude/**' ':(exclude,glob)**/.claude' \
  ':(exclude,glob)**/docs/plans/**' ':(exclude,glob)**/docs/plans' \
  ':(exclude,glob)**/.plans/**' ':(exclude,glob)**/.plans' \
  | tr '\0' '\n'
```

Read that list. Add by name anything that belongs to this task and is not
staged yet. When every remaining entry belongs, pipe the same enumeration into
`git add` instead of retyping it:

```bash
git -c core.quotepath=false ls-files -z --modified --others --exclude-standard -- \
  ':(exclude,glob)**/.claude/**' ':(exclude,glob)**/.claude' \
  ':(exclude,glob)**/docs/plans/**' ':(exclude,glob)**/docs/plans' \
  ':(exclude,glob)**/.plans/**' ':(exclude,glob)**/.plans' \
  | xargs -0 git add --
```

Add one more `':(exclude)<path>'` pathspec for each user-excluded path.

Why this shape and not a `grep` over `git status --porcelain` text:

| Input | Text-filtered porcelain | `git ls-files -z` with exclude pathspecs |
|---|---|---|
| Renamed file | Porcelain emits `R  old -> new`. After `cut -c4-` that whole string reaches `git add`, which fails with `fatal: pathspec 'old' did not match any files` and drops every path after it | Emits the old and the new path as two records, both staged |
| Path with a space | Survives the cut, but any exact-match filter needs `grep -x -F` per path | One NUL-delimited record, kept whole by `xargs -0` |
| Non-ASCII path | C-quoted as `"caf\303\251.txt"`, and the escape reaches git literally, so nothing is staged | `-z` never quotes, and `core.quotepath=false` keeps the readable listing honest too |
| `packages/x/docs/plans/note.md` | An anchored `^docs/plans/` filter lets it through, it gets staged, then the commit is denied by the hook | `:(exclude,glob)**/docs/plans/**` drops it at any depth, matching the hook |

BSD `grep` has no `-z`, so on macOS there is no NUL-safe way to filter the list
in the shell. Let git do the matching, and the skill and the hook stay agreed
on what a path means.

Show the staged list and confirm it looks right before committing:

```bash
git diff --staged --name-status
```

If nothing is staged after the exclusions, what happens next depends on the
mode:

| Mode | Nothing staged means |
|---|---|
| commit only | Stop and report "nothing to commit" |
| Any mode that named a push, PR or ready | Check `git log --oneline "origin/$base..HEAD"`. Commits ahead of the default branch mean the work was committed earlier and the go-ahead came after it: skip step 8, say so, and continue at step 9 with the head that exists. No commits ahead either: stop, there is nothing to ship |

In the skipped case the step 6 run was on a clean tree that is the committed
tree, so its bullets carry that head's sha once the step 8 check below
confirms the enumeration is empty.

### Step 8: Commit

Read the staged diff and write the message from it, not from the chat history:

```bash
git diff --staged --stat
git diff --staged
```

Format:

```
<type>(<optional-scope>): <imperative subject under 72 chars>

<body: why the change was made, not what the diff already shows>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`,
`ci`, `build`. Scope is the primary package or directory touched; omit it when
the change is broad.

Authorship: the git user is the author. Attribution follows the harness, not
this skill. Never add a co-author trailer yourself.

Never put an agent session link, a model name, or any other AI identifier in
the subject or body.

Record the staged tree, then commit, bounded at 3 attempts:

```bash
staged_tree="$(git write-tree)"
git commit -m "<subject>" -m "<body>"
```

On a pre-commit hook failure:

1. Read the full hook output. Hooks usually fail on lint, type, test or format
   errors, and the message names the file.
2. Fix the root cause. Never pass `--no-verify`, and never delete or disable the
   hook.
3. Run step 6 again. The step 6 run before the fix proved a tree that no longer
   exists, and a fix is unverified until the suite runs on it.
4. Re-stage the fixed files, re-applying the step 7 exclusions, and record the
   staged tree again.
5. Retry. That is attempt 2.
6. After 3 failed attempts, stop. Report what is blocking the commit and what
   you tried. Do not keep retrying and do not bypass.

After the commit, decide what the step 6 run proved. It ran on the working
tree; the commit may hold a different tree when only part of the work was
staged or a hook rewrote a file on its way in. Two checks settle it:

```bash
[ "$(git rev-parse 'HEAD^{tree}')" = "$staged_tree" ] && echo "committed what was staged" || echo "a hook changed the commit"
git -c core.quotepath=false ls-files -z --modified --others --exclude-standard -- \
  ':(exclude,glob)**/.claude/**' ':(exclude,glob)**/.claude' \
  ':(exclude,glob)**/docs/plans/**' ':(exclude,glob)**/docs/plans' \
  ':(exclude,glob)**/.plans/**' ':(exclude,glob)**/.plans' \
  ':(exclude,glob)**/.verify-logs/**' ':(exclude,glob)**/.verify-logs' \
  | tr '\0' '\n'
```

When the trees match and the enumeration prints nothing, the tree `verify`
ran on is the tree that was committed, and the step 6 bullets carry HEAD's
sha. When either check fails, the step 6 run was a dirty working-tree run:
its bullets are labelled `working tree before commit` and carry no sha, and in
any mode that pushes, the gate runs on the commit before the push, using the
step 11 checkout detached at local `HEAD` instead of the fetched remote head.
That run carries the sha and comes back here as evidence only: no PR is
touched before the push, and steps 9 and 10 publish it with the rest of the
block once the head is on the remote. A user-excluded path left in the tree fails the
second check on purpose: `verify` ran with it present, and nothing shows it
did not matter.

### Step 9: Push, then refresh the body

Without a go-ahead that named the push, ask first in plain words and wait for a
yes:

> Commit `<sha>` is on `<branch>`. Push to `origin`?

Do not treat "commit my changes" as permission to push.

```bash
git push --set-upstream origin <branch>
```

Never push to the default branch.

Then check whether the branch already has a PR:

```bash
gh pr view <branch> --json number,isDraft,state,url
```

When it does, and the push changed the diff, run the `pr-desc` skill in update
mode. Hand it the `verify` report block from step 6 with the label step 8 gave
it, sha or `working tree before commit`, plus any gate run on the commit, so
the Summary describes the diff that is on the remote now and Verification
cites the runs on this head rather than on the one before. `pr-desc` shows the
before and after and asks before editing; that ask is its own and stands.

A push changes the diff when it carries a new or amended commit. A rebase that
replayed the same commits onto a new base did not, and the body stands as it
is. When there is no PR yet, the body is written at step 10.

### Step 10: Open a draft PR

Without a go-ahead that named the PR, ask and wait for a yes:

> Open a draft PR from `<branch>` into `<default-branch>`?

Pushing is not permission to open a PR. Opening one is externally visible and
hard to take back, so when the request did not name it, it carries its own
confirmation rather than inheriting the one given for the push.

Run the `pr-desc` skill in create mode and use the title and body it hands
back. Hand it the `verify` report block from step 6 with the label step 8 gave
it, and any gate run on the commit, so no bullet names a sha the run did not
prove. It writes the title and the Summary, Trade-offs and Follow-ups from the diff,
fills Verification from the runs it was handed, keeps the title a Conventional
Commit subject, and decides which sections appear. Do not restate or override
its rules here.

If `pr-desc` is unavailable, write the title as a Conventional Commit subject
and the body as a `## Summary` section only, and say in the report that the
skill was missing.

Open as a draft unless the user says otherwise:

```bash
gh pr create --draft --title "<title from pr-desc>" --body-file <file>
```

No `--base` flag: `gh` targets the repository's default branch when none is
given, so passing one only adds a place to get it wrong.

Draft is the default in ship-to-ready mode too. The flip in step 12 is the
review signal, and it waits for the gate in step 11.

### Step 11: Gate the pushed head on a clean detached checkout

Step 6 proved the working tree. It did not prove the commit that reached the
remote: an unstaged edit, an untracked file or a stale `node_modules` can make
the working tree pass where the pushed head fails. Check that head out detached
into a throwaway worktree and run the gate there.

```bash
git fetch origin "<branch>"
head="$(git rev-parse "origin/<branch>")"
[ "$head" = "$(git rev-parse HEAD)" ] || echo "local HEAD differs from origin/<branch>"
gate_dir="$(mktemp -d)"
git worktree add --detach "$gate_dir" "$head"
```

This step has two callers, and they differ in where the run goes afterwards:

| Called from | Checkout | The run is |
|---|---|---|
| Step 10, after the push, in ship-to-ready mode | `origin/<branch>` after the fetch above | Published: handed to `pr-desc` in refresh mode, below |
| Step 8, before the push, when the tree identity check failed | Local `HEAD`, no fetch | Evidence only: carried back to step 8 with HEAD's sha and the `clean detached checkout` label, and nothing is written to any PR |

In the pre-push case the detached copy is still what proves the commit, since
the working tree is not it. There may be no PR yet, and when there is one its
body describes the previous remote head, so neither refresh nor update can
run before the push. Step 9 updates an existing body or step 10 creates one,
after the push, with this run in the block.

Inside `$gate_dir`, install from the lock file when the repo has one, with
`pnpm install --frozen-lockfile` or the equivalent for the package manager
step 3 detected, then run the `verify` skill's Steps 2 to 4 there: discover
the commands from `package.json` or the Makefile, run them cheapest first,
capture each exit code. Write the logs under the task worktree, not under the
throwaway one:

```bash
mkdir -p .verify-logs
( cd "$gate_dir" && make validate ) > .verify-logs/gate.log 2>&1; echo "exit=$?"
tail -40 .verify-logs/gate.log
```

Remove the throwaway worktree whatever the result:

```bash
git worktree remove --force "$gate_dir"
git worktree prune
```

On a failing gate, nothing is published and nothing is flipped. Root-cause it
with `verify` Step 5 in the task worktree and commit the fix. From the
post-push caller, return to step 9: the fix is a new push, so the body is
refreshed and the gate runs again on the new head. From the pre-push caller,
return to step 8 with the fix committed; the tree identity check runs again
on the new commit. Bound this at 3 rounds either way, then stop and report
what is blocking.

On a green gate from the post-push caller, hand the run and the head sha to
`pr-desc` in refresh mode, so the Verification section carries the detached
run next to the step 6 one. Nothing else in the body changes, so `pr-desc`
writes it without a second before-and-after. On a green gate from the
pre-push caller, go back to step 8 with the run; the push has not happened yet
and the body is written or updated after it.

### Step 12: Mark ready

Flip the PR from draft to ready only when both hold:

- Step 11 passed on this head. A green run in the working tree does not count,
  and neither does a gate on an earlier head.
- The user or the brief said ready is the review signal: the go-ahead named it
  ("mark ready"), or the brief that started the task said to flip ready once
  the gate is green.

```bash
gh pr ready <number>
```

Without the second condition, stop at draft and say so in the report. The
default stays draft. Where CI runs only on ready PRs, the gate coming first is
what keeps a broken head from spending CI minutes.

### Step 13: Rebase after an upstream merge

Run this when the default branch has moved under the branch: another PR
merged, CI failed in code the diff never touched, the app offers to merge the
base branch in, or the user says to rebase. Rebase, never merge. The
`rebase-not-merge.sh` hook denies `git merge <default-branch>` on a feature
branch in any case.

Fetch, then prove that the local branch contains everything the remote has
before anything is rewritten:

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git fetch origin "$base" "<branch>"
old="$(git rev-parse "origin/<branch>")"
git merge-base --is-ancestor "$old" HEAD && echo "remote tip is in local HEAD" || echo "DIVERGED"
```

`DIVERGED` means `origin/<branch>` carries commits that local `HEAD` does
not, such as a collaborator's amendment pushed since this checkout last
pulled. A lease on `$old` would not protect them: the lease guards against
pushes made after the fetch, and these were already fetched, so the push
would succeed and erase them. Stop. Show both sides and let the user say
which wins:

```bash
git log --oneline "HEAD..$old"
git log --oneline "$old..HEAD"
```

When local `HEAD` simply lags the remote, `git merge --ff-only "$old"` brings
it level and the check passes on a second try. Anything else is a decision,
not a step.

With the check passed, record the fork point and rebase:

```bash
fork="$(git merge-base "$old" "origin/$base")"
git rebase "origin/$base"
```

On a conflict, resolve it by reading both sides. Never take one side wholesale,
and never `--skip` a commit to get through. If it cannot be resolved with what
you know, `git rebase --abort` and report the conflicting paths.

Then run `verify` Step 7 to prove the git state, and run the gate on the
rebased tree. A rebase is not complete until the tests pass on the rebased
tree; a clean `git status` proves nothing. The rebased tree is the working
tree, so that run's bullets carry the new head's sha.

Prove that every commit survived, then push with a lease on the exact old
head:

```bash
git range-diff "$fork..$old" "origin/$base..HEAD"
git push --force-with-lease="<branch>:$old" origin <branch>
```

`range-diff` pairs each commit that was on the remote with its rebased copy:
`=` is unchanged, `!` was altered by a conflict resolution, `>` is a local
commit that was never on the remote and is pushed for the first time. A `<`
line is a commit on the remote with no counterpart after the rebase, and it
is a stop: find out where it went before pushing. Say before the push what
the remote will see: `origin/<branch>` moves from `$old` to the new head, the
range-diff shows every remote commit paired and no `<` line, so no commit is
discarded. Commit counts alone do not establish that; `1 before, 1 after`
holds just as well when the one commit is someone else's.

The `confirm-remote-writes.sh` hook asks the harness before the push; a
go-ahead that named the rebase and the push has answered it in prose already.
If the lease fails, someone pushed to the branch since the fetch: return to
the fetch and the ancestor check above, and never fall back to a bare
`--force`.

A rebase whose range-diff is all `=` did not change the diff, so the body
stands. One with a `!` line may have: compare
`git diff "origin/$base...HEAD" --stat` with what the body describes and run
`pr-desc` in update mode when it differs. If the PR was already ready, run
step 11 again on the new head and report the result.

### Step 14: Clean up after the merge

Run this when the PR has merged: the user says so, or the app's PR monitor
reports it. Prove the merge before touching anything. A message saying
"merged" is a claim, not a state.

```bash
gh pr view <number> --json state,mergedAt,mergeCommit,headRefOid,headRefName
```

`state` must read `MERGED`. If it reads anything else, stop and report it.

`MERGED` proves the PR landed. It does not prove the branch still points at
what landed: a branch can gain commits after its PR merges while the PR stays
`MERGED`, and deleting it then loses work that is on no other ref. So take
`headRefOid`, the head the PR merged, and check every tip against it before
removing anything:

```bash
merged_head="<headRefOid>"
main_checkout="$(git worktree list --porcelain | awk 'NR==1 { print $2 }')"
git -C "$main_checkout" rev-parse <branch>
git ls-remote --heads origin <branch>
git -C "$main_checkout/.claude/worktrees/<name>" status --porcelain --untracked-files=all
```

| Check | Must show | Otherwise |
|---|---|---|
| Local tip | `$merged_head` | `git log --oneline "$merged_head..<branch>"` lists commits that are not on the default branch. Stop, report them, delete nothing |
| Remote tip | `$merged_head`, or no line because GitHub deleted the branch on merge | Same, with `git log --oneline "$merged_head..origin/<branch>"` after a fetch |
| Worktree status | Nothing | Uncommitted work in the worktree. Stop and report it |

With all three clean, work from the main checkout rather than from inside the
worktree being removed:

```bash
git -C "$main_checkout" worktree remove ".claude/worktrees/<name>"
git -C "$main_checkout" branch -D <branch>
git -C "$main_checkout" push --force-with-lease="<branch>:$merged_head" origin --delete <branch>
git -C "$main_checkout" fetch --prune origin
```

The repo squash-merges, so the branch's commits are not ancestors of the
default branch and `git branch -d` refuses them. `MERGED` plus a tip equal to
`$merged_head` is the proof that makes `-D` safe. `worktree remove` runs
without `--force` so git refuses a dirty tree the status check missed. The
remote deletion carries a lease on `$merged_head`: if the branch advanced
between the check and the delete, git rejects it with `stale info` instead
of removing the newer commits, and that rejection is a stop. Skip the
deletion when `ls-remote` showed no branch. The "merged" go-ahead covers
that push: a branch whose tip is the merged head is disposable once its PR
has landed.

Write the hand-over note where the brief says notes go. Without a brief, write
a short note under `docs/plans/`, never committed. The note carries the PR
number and merge commit, what landed in one or two lines, and what is left for
the next phase.

Prove the cleanup with the output of the commands, not with an empty listing
alone: `git branch -D` prints `Deleted branch <name> (was <sha>)`, the push
prints `- [deleted]`, and `git worktree list` afterwards no longer shows the
path. An empty `git branch --list <branch>` on its own is not evidence that a
deletion happened.

### Step 15: Report

State plainly:

- The branch, and whether it was created in this run
- Which format, lint and verify commands ran, or were skipped and why
- The staged file list, and anything excluded
- The commit message and sha
- Any hook retries and what was root-caused
- Push result, or that push was not requested
- Whether `pr-desc` refreshed the body, or that the diff did not change
- PR URL and draft status, or that no PR was requested
- The gate on the detached checkout: head sha, command, exit code and the tail
  of its output, or that it was not run
- Whether the PR was marked ready, or why it stayed draft
- Whether the step 6 run proved the commit, or was labelled a working-tree run
  and the commit gated separately
- After a rebase: the ancestor check, the old and new head, the range-diff, and
  that no commit was discarded
- After a cleanup: the `MERGED` state, the three tip checks against the merged
  head, the `Deleted branch` and `[deleted]` lines, and the worktree list

## Common Mistakes

| Mistake | Fix |
|---|---|
| Committing while on the default branch | Hard gate. Detect it with `git ls-remote --symref origin HEAD`, then create `<type>/<scope>-<description>` and commit there. |
| Creating a second worktree for a task that has one | Read `git worktree list` first. Reuse the match; ask when more than one could be it. |
| Leaving the branch as `worktree-<name>` after `EnterWorktree` | Rename it to `<type>/<scope>-<description>` before the first commit. |
| Using `bun` or `npm` in a repo with `pnpm-lock.yaml` | Detect from the lock file, then the `packageManager` field. Never assume. |
| Inventing `npx vitest run` or similar ad-hoc commands | Run the scripts defined in `package.json`. |
| Skipping verification because there is no `package.json` | Read the Makefile. Run its targets. Skip only when there is neither. |
| Using `--no-verify` to get past a hook | Never. Read the error, fix the root cause, re-stage, retry, max 3 attempts. |
| Retrying a failing hook indefinitely | Stop at 3 attempts and report what is blocking. |
| Running `git add -A` or `git add .` | Forbidden by the house rules and denied by the hook. Name the paths you changed and `git add --` them. |
| Piping porcelain status through `cut -c4-` into `git add` | A rename arrives as `old -> new`, git rejects it, and every path after it is silently dropped. A non-ASCII path arrives C-quoted and stages nothing. Enumerate with `git ls-files -z` and `xargs -0` instead. |
| Staging `.claude/`, `docs/plans/` or `.plans/` | Exclude them with `:(exclude,glob)**/docs/plans/**` style pathspecs, which match at any depth like the hook does. |
| Filtering the artifact names with an anchored `^docs/plans/` | It misses `packages/x/docs/plans/note.md`, which then blocks the commit. Match unanchored, at any depth. |
| Committing with nothing staged | Check `git status` first; report "nothing to commit". |
| Stopping at "nothing to commit" when the go-ahead came after the commit | Commits ahead of `origin/$base` are the work. Skip step 8 and continue at step 9. |
| Labelling the step 6 run with the pushed sha | It ran on the working tree. Prove the committed tree is that tree in step 8, or label it `working tree before commit` and gate the commit detached. |
| Refreshing or editing a PR from the pre-push gate | Before the push there may be no PR, and an existing body describes the old head. Carry the run back to step 8; steps 9 and 10 publish it after the push. |
| Retrying a failed hook without re-running `verify` on the fix | The earlier run proved a tree that no longer exists. Step 6 again, then re-stage. |
| Choosing the wrong type, such as `feat` for a refactor | Match intent: user-visible is `feat`/`fix`, internal is `refactor`/`chore`. |
| Pushing after a request that said only "commit" | Push is its own remote write. Ask, and wait for the yes. |
| Opening a PR after a request that said only "commit and push" | The PR is a further remote write. Ask again; the push's yes does not carry. |
| Asking three times after one sentence that named push, PR and ready | One go-ahead answers everything it names. Run steps 9 to 12 and report. |
| Leaving the body as it was after a push that changed the diff | Run `pr-desc` in update mode with the verify block and the new head. |
| Writing the PR body in this skill | Run `pr-desc` and use the title and body it hands back. |
| Adding release-type or version opinions to the PR | That is the repo owner's decision. |
| A non-conventional PR title | Squash-merge makes it the commit on the default branch; CI rejects it. |
| Opening a PR ready for review by default | Open as a draft unless told otherwise. |
| Marking ready on the strength of the task worktree's green run | The gate runs on a clean detached checkout of the pushed head. Only that run flips ready. |
| Marking ready when nobody said ready is the signal | Default stays draft. Flip only when the go-ahead or the brief named it. |
| Gating one head and flipping ready on another | Re-run step 11 after every push. A gate proves the head it ran on. |
| Merging the default branch into the branch | Rebase onto `origin/$base`. The hook denies the merge anyway. |
| Rebasing while `origin/<branch>` has commits local `HEAD` lacks | `git merge-base --is-ancestor "$old" HEAD` first. A lease on `$old` does not protect what was already fetched. |
| `git push --force` after a rebase | `--force-with-lease=<branch>:<old-sha>`, after a range-diff with no `<` line shows no commit is discarded. |
| Commit counts as proof that nothing was discarded | `1 before, 1 after` holds when the one commit is someone else's. Range-diff, with the ancestor check before it. |
| Calling the rebase done because `git status` is clean | `verify` Step 7, then the gate on the rebased tree. |
| Cleaning up on the word "merged" alone | `gh pr view` must read `MERGED` first. |
| Deleting a branch whose tip moved past the merged head | Compare local and remote tips with `headRefOid`. A commit beyond it is on no other ref. |
| Deleting the remote branch with a plain `--delete` | Lease it on the merged head, so a late commit rejects the delete with `stale info`. |
| `git worktree remove` from inside the worktree | Run it from the main checkout with `git -C`. |
| An empty `git branch --list` offered as proof of deletion | Paste the `Deleted branch` line and the worktree list after. |
| The agent as commit author, or a session link in the body | Repo owner is the author. Never put a session link or model name in the message. |
| Adding a `Co-Authored-By` trailer yourself | Attribution belongs to the harness. Write the subject and body only. |
