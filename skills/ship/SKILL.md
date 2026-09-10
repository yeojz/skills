---
name: ship
description: Use when the user wants to save work to git, from branching through to a pull request. Triggers on requests like "commit", "commit and push", "commit, push and open pr", "branch, commit and open pr", "push this", "save my work to git", or when a feature or fix is finished and needs to be persisted.
---

# ship

## Overview

The branch-through-PR loop: branch first, run the repo's own scripts, verify,
stage cleanly, write a conventional commit, then push and open a draft PR as
separate confirmed steps. Guarantees that nothing is committed on `main`, no
worktree is created, no `.claude/` or plan files are staged, and no push or PR
happens without an explicit yes.

## Modes

Pick the mode from what the user asked for. Do not do more than they asked.

| User asked | Mode | Runs steps |
|---|---|---|
| "commit", "commit my changes", "save my work to git" | commit only | 1-8 |
| "commit and push", "push this" | commit and push | 1-9 |
| "commit, push and open pr", "branch, commit and open pr" | commit, push, PR | 1-10 |

If the mode is ambiguous, do the commit and ask before going further. Never
upgrade a mode on your own initiative.

## Workflow

### Step 1: Never create a worktree

Work directly in the current folder. Do not run `git worktree add`, do not
suggest a worktree, and do not switch to an existing one, unless the user
explicitly asks for a worktree in this session. Branching is the isolation
mechanism here.

If a worktree skill or helper offers itself, decline it.

### Step 2: Branch-first gate

This is a hard gate. Check the current branch and the repo's default branch:

```bash
git rev-parse --abbrev-ref HEAD
git symbolic-ref --quiet --short refs/remotes/origin/HEAD | sed 's|^origin/||'
```

If the current branch is the default branch (`main`, or `master` in an older
repo), refuse to commit. Create a branch first:

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

Never assume. Check for a lock file in the repo root, or the nearest ancestor
that has a `package.json`:

| Lock file | Package manager |
|---|---|
| `pnpm-lock.yaml` | `pnpm` |
| `bun.lockb` or `bun.lock` | `bun` |
| `yarn.lock` | `yarn` |
| `package-lock.json` | `npm` |

If no lock file is present, read the `packageManager` field in `package.json`.
If that is also absent, ask rather than guessing.

A `pnpm-lock.yaml` means `pnpm`, even if `bun` or `npm` is faster to type. Do
not mix package managers in one repo.

If there is no `package.json` at all, skip steps 4 to 6.

### Step 4: Format

Read `package.json` scripts and run the repo's own script. Look for `format`,
`fmt`, or a script whose command contains `prettier` or `biome format`:

```bash
<pkg-manager> run format
```

If no such script exists, skip silently. Never invent an ad-hoc
`npx prettier --write .` style command.

### Step 5: Lint fix

Look for `lint:fix`, `lint-fix`, `fix`, or a script whose command contains
`--fix` or `--write`:

```bash
<pkg-manager> run lint:fix
```

If no such script exists, skip silently.

### Step 6: Verify

Delegate the full check to the `verify` skill before committing. It runs the
repo's own lint, typecheck, test and build scripts and pastes real output.

If `verify` is unavailable, run the repo's `package.json` scripts directly and
paste the output. Either way, do not commit on top of a failing check: root-cause
the failure, do not route around it, and do not weaken a test to make the suite
green.

### Step 7: Stage with hygiene

Show the user the current state before staging:

```bash
git status
```

Never stage these, whatever `git add -A` would pick up:

| Path | Reason |
|---|---|
| `.claude/` | Local agent configuration |
| `docs/plans/` | Plan files are working notes, not deliverables |
| `.plans/` | Same |

Honour an explicit exclusion too. When the user says something like
"commit all unstaged changes, ignore `notes.local.md`", that path is excluded
for this run.

Stage everything else, then unstage the excluded paths:

```bash
git add -A
git reset -- .claude docs/plans .plans <user-excluded-paths>
```

Show the staged list and confirm it looks right before committing:

```bash
git diff --staged --name-status
```

If nothing is staged after the exclusions, stop and report "nothing to commit".

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

Authorship: the repo owner is the author. Attribution follows the harness,
not this skill. Read `settings.json` before composing the message:

| Setting | Effect on the message |
|---|---|
| `includeCoAuthoredBy` is `false` | Add no `Co-Authored-By` trailer |
| `includeCoAuthoredBy` is `true` or absent | Add `Co-Authored-By: Claude <noreply@anthropic.com>` |
| `attribution.commit` is a non-empty string | Use that as the trailer instead |
| `attribution.commit` is an empty string | Add no trailer |

Check both the project and the user settings file, project first:

```bash
cat .claude/settings.json 2>/dev/null
cat ~/.claude/settings.json
```

Never put a Claude session link, a model name, or any other AI identifier in the
subject or body.

Commit, bounded at 3 attempts:

```bash
# Trailer argument included only when settings ask for one.
git commit -m "<subject>" -m "<body>"
```

On a pre-commit hook failure:

1. Read the full hook output. Hooks usually fail on lint, type, test or format
   errors, and the message names the file.
2. Fix the root cause. Never pass `--no-verify`, and never delete or disable the
   hook.
3. Re-stage the fixed files, re-applying the step 7 exclusions.
4. Retry. That is attempt 2.
5. After 3 failed attempts, stop. Report what is blocking the commit and what
   you tried. Do not keep retrying and do not bypass.

### Step 9: Push, only after confirmation

Ask first, in plain words, and wait for a yes:

> Commit `<sha>` is on `<branch>`. Push to `origin`?

Do not treat "commit my changes" as permission to push.

```bash
git push --set-upstream origin <branch>
```

Never push to the default branch.

### Step 10: Open a PR, only after separate confirmation

Pushing is not permission to open a PR. Ask again and wait for a yes:

> Open a draft PR from `<branch>` into `<default-branch>`?

Opening a PR is externally visible and hard to take back, so it carries its own
confirmation rather than inheriting the one given for the push. Make the ask
explicit every time.

PR title is a Conventional Commit subject. The repo squash-merges, so the PR
title becomes the commit on the default branch, and CI rejects titles that do
not match the convention.

PR body has exactly three sections and nothing else:

```markdown
## Summary

What changed and why, in a few sentences.

## Trade-offs

The decisions taken and what was given up. "None" if there genuinely were none.

## Follow-ups

What is deliberately left for later. "None" if there is nothing.
```

Strip all of the following. They are not part of the body:

| Do not include | Why |
|---|---|
| `## Test Plan` | Verification already happened in step 6 |
| Chat narrative, step-by-step story of the session | Not useful to a reviewer |
| Security-review commentary | Belongs in a review, not the PR body |
| Release-type or version-bump opinions | That decision belongs to the repo owner |
| Claude session links, model names, AI identifiers | House rule |

Open as a draft unless the user says otherwise:

```bash
gh pr create --draft --base <default-branch> --title "<conventional subject>" --body-file <file>
```

### Step 11: Report

State plainly:

- The branch, and whether it was created in this run
- Which format, lint and verify commands ran, or were skipped and why
- The staged file list, and anything excluded
- The commit message and sha
- Any hook retries and what was root-caused
- Push result, or that push was not requested
- PR URL and draft status, or that no PR was requested

## Common Mistakes

| Mistake | Fix |
|---|---|
| Committing while on `main` or `master` | Hard gate. Create `<type>/<scope>-<description>` first, then commit. |
| Creating a git worktree to isolate the work | Never, unless the user asks for one in this session. Branch in the current folder. |
| Using `bun` or `npm` in a repo with `pnpm-lock.yaml` | Detect from the lock file, then the `packageManager` field. Never assume. |
| Inventing `npx vitest run` or similar ad-hoc commands | Run the scripts defined in `package.json`. |
| Using `--no-verify` to get past a hook | Never. Read the error, fix the root cause, re-stage, retry, max 3 attempts. |
| Retrying a failing hook indefinitely | Stop at 3 attempts and report what is blocking. |
| Staging `.claude/`, `docs/plans/` or `.plans/` | Unstage them after `git add -A`, every time. |
| Committing with nothing staged | Check `git status` first; report "nothing to commit". |
| Choosing the wrong type, such as `feat` for a refactor | Match intent: user-visible is `feat`/`fix`, internal is `refactor`/`chore`. |
| Pushing because the commit succeeded | Push is a separate step with its own confirmation. |
| Opening a PR because the push succeeded | PR is a separate step with its own confirmation. |
| Putting a `## Test Plan` in the PR body | Summary, trade-offs, follow-ups only. |
| Adding release-type or version opinions to the PR | That is the repo owner's decision. |
| A non-conventional PR title | Squash-merge makes it the commit on `main`; CI rejects it. |
| Opening a PR ready for review by default | Open as a draft unless told otherwise. |
| Claude as commit author, or a session link in the body | Repo owner is the author. Never put a session link or model name in the message. |
| Adding a `Co-Authored-By` trailer that settings turned off | Read `includeCoAuthoredBy` and `attribution.commit` first. Settings decide attribution, not this skill. |
