---
name: ship
description: Use when the user wants to save work to git, from branching through to a pull request. Triggers on requests like "commit", "commit and push", "commit, push and open pr", "branch, commit and open pr", "push this", "save my work to git", or when a feature or fix is finished and needs to be persisted.
---

# ship

## Overview

The branch-through-PR loop: branch first, run the repo's own scripts, verify,
stage cleanly, write a conventional commit, then push and open a draft PR as
separate confirmed steps. Guarantees that nothing is committed on the default
branch, no worktree is created, no `.claude/` or plan files are staged, and no
push or PR happens without an explicit yes.

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

Authorship: the git user is the author. Attribution follows the harness, not
this skill. Never add a co-author trailer yourself.

Never put an agent session link, a model name, or any other AI identifier in
the subject or body.

Commit, bounded at 3 attempts:

```bash
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

Run the `pr-desc` skill in create mode and use the title and body it hands
back. It writes both from the diff, keeps the title a Conventional Commit
subject, and decides which body sections appear. Do not restate or override its
rules here.

If `pr-desc` is unavailable, write the title as a Conventional Commit subject
and the body as a `## Summary` section only, and say in the report that the
skill was missing.

Open as a draft unless the user says otherwise:

```bash
gh pr create --draft --title "<title from pr-desc>" --body-file <file>
```

No `--base` flag: `gh` targets the repository's default branch when none is
given, so passing one only adds a place to get it wrong.

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
| Committing while on the default branch | Hard gate. Detect it with `git ls-remote --symref origin HEAD`, then create `<type>/<scope>-<description>` and commit there. |
| Creating a git worktree to isolate the work | Never, unless the user asks for one in this session. Branch in the current folder. |
| Using `bun` or `npm` in a repo with `pnpm-lock.yaml` | Detect from the lock file, then the `packageManager` field. Never assume. |
| Inventing `npx vitest run` or similar ad-hoc commands | Run the scripts defined in `package.json`. |
| Using `--no-verify` to get past a hook | Never. Read the error, fix the root cause, re-stage, retry, max 3 attempts. |
| Retrying a failing hook indefinitely | Stop at 3 attempts and report what is blocking. |
| Running `git add -A` or `git add .` | Forbidden by the house rules and denied by the hook. Name the paths you changed and `git add --` them. |
| Piping porcelain status through `cut -c4-` into `git add` | A rename arrives as `old -> new`, git rejects it, and every path after it is silently dropped. A non-ASCII path arrives C-quoted and stages nothing. Enumerate with `git ls-files -z` and `xargs -0` instead. |
| Staging `.claude/`, `docs/plans/` or `.plans/` | Exclude them with `:(exclude,glob)**/docs/plans/**` style pathspecs, which match at any depth like the hook does. |
| Filtering the artifact names with an anchored `^docs/plans/` | It misses `packages/x/docs/plans/note.md`, which then blocks the commit. Match unanchored, at any depth. |
| Committing with nothing staged | Check `git status` first; report "nothing to commit". |
| Choosing the wrong type, such as `feat` for a refactor | Match intent: user-visible is `feat`/`fix`, internal is `refactor`/`chore`. |
| Pushing because the commit succeeded | Push is a separate step with its own confirmation. |
| Opening a PR because the push succeeded | PR is a separate step with its own confirmation. |
| Writing the PR body in this skill | Run `pr-desc` in create mode and use the title and body it hands back. |
| Adding release-type or version opinions to the PR | That is the repo owner's decision. |
| A non-conventional PR title | Squash-merge makes it the commit on the default branch; CI rejects it. |
| Opening a PR ready for review by default | Open as a draft unless told otherwise. |
| The agent as commit author, or a session link in the body | Repo owner is the author. Never put a session link or model name in the message. |
| Adding a `Co-Authored-By` trailer yourself | Attribution belongs to the harness. Write the subject and body only. |
