---
name: release
description: Use when preparing or publishing a release in a pnpm workspace, from writing a changeset through to the version PR and the publish workflow. Triggers on requests like "add a changeset", "write a changeset", "prepare a release", "cut a release", "publish the packages", "version bump PR", "the publish workflow failed", or when a release job fails with a 403 for github-actions[bot].
---

# release

## Overview

Release preparation and publishing for pnpm workspaces: detect the release
mechanism the repo actually uses, derive the semver impact from the real diff,
show the changeset before writing it, prove the package is publishable, then let
CI publish behind a labelled version PR. Guarantees that nothing is published,
tagged or pushed without an explicit yes, that no changelog or migration guide
appears unless the repo already asked for one, and that the release type stays
the repo owner's decision.

## Modes

Pick the mode from what the user asked for. Do not run steps they did not ask
for.

| User asked | Mode | Runs steps |
|---|---|---|
| "add a changeset", "write a changeset", "changeset for this branch" | changeset | 1-4 |
| "prepare a release", "cut a release", "version bump PR" | version PR | 1-7 |
| "publish the packages", "release it" | publish | 1-8 |
| "the publish workflow failed", a 403 for the Actions bot | workflow triage | 1, 9 |

If the mode is ambiguous, do the changeset and ask before going further. Never
upgrade a mode on your own initiative.

## Workflow

### Step 1: Detect the release mechanism

Read the config. Never assume Changesets just because the repo is a pnpm
workspace, and never assume semantic-release because there is a tag workflow.

```bash
ls -d .changeset 2>/dev/null
cat .changeset/config.json 2>/dev/null
cat release.config.json 2>/dev/null
ls .releaserc* release.config.* 2>/dev/null
cat package.json | grep -n '"release"\|"changeset"\|"version"\|"publish"'
ls .github/workflows
```

| Evidence | Mechanism | Version command |
|---|---|---|
| `.changeset/` with `config.json` | Changesets | `pnpm changeset version` |
| A bespoke config that groups packages, for example a `release.config.json` of the repo's own | In-house convention | Whatever that config's scripts define |
| `.releaserc*`, `release.config.js`, `semantic-release` dep | semantic-release | Driven by commit messages, no changeset file |
| None of the above | Manual | Ask before touching versions |

When the mechanism is Changesets, read the config for grouping before writing
anything:

```bash
cat .changeset/config.json
```

| Field | Meaning for this release |
|---|---|
| `fixed` | Every package in the group moves to the same version. A patch on one bumps all of them. |
| `linked` | Packages share a version only when they are released together. |
| `ignore` | Those packages are never versioned by this changeset. |
| `changelog` | What generates changelog entries, or `false` for none. |
| `updateInternalDependencies` | How workspace dependents get bumped alongside. |

A `fixed` group changes the blast radius of a bump. Name the affected packages
explicitly when you present the classification in step 3. Some repos group
packages through a bespoke config of their own instead. That is a local
convention rather than a standard, so read whichever file the repo actually uses
for the same information rather than inferring it from directory layout.

If the mechanism is semantic-release, there is no changeset to write. Say so,
and explain that the bump comes from the Conventional Commit subjects on the
branch. Then stop unless the user asks for something else.

### Step 2: Read the actual diff against `main`

Derive the impact from code, never from the chat history or the branch name.
Use the three-dot form so the comparison is against the merge base, not against
whatever `main` has drifted to:

```bash
git fetch origin main
git diff --stat origin/main...HEAD
git diff origin/main...HEAD
```

Also list which workspace packages are touched:

```bash
git diff --name-only origin/main...HEAD | sed -n 's|^\(packages\|apps\|internal\)/\([^/]*\)/.*|\1/\2|p' | sort -u
```

If the diff is empty, stop and report that there is nothing to release. Do not
write an empty changeset.

Pay particular attention to the published surface, because that is what decides
the bump:

```bash
git diff origin/main...HEAD -- '**/package.json' '**/src/index.ts' '**/*.d.ts'
```

### Step 3: Classify the semver impact per package

One classification per touched package, each with the reasoning written out.

| Change in the diff | Level | Why |
|---|---|---|
| New exported function, type or option, existing calls unchanged | minor | Additive |
| Bug fix behind an unchanged signature | patch | No surface change |
| Internal refactor, tests, tooling, no published surface touched | none | Nothing for a consumer to see |
| Docs only, or a private package | none | Not published |
| New required parameter, or a removed or renamed export | major | Existing calls stop compiling |
| New parameter with a default that preserves today's behaviour | minor | Existing calls keep working unchanged |
| Changed default value that alters existing behaviour | major | Silent behaviour change for current users |
| Dropped runtime or raised `engines` floor | major | Existing installs break |
| Dependency bump that leaks through the public types | matches the dependency's own level | The break is re-exported |

The minor-versus-major line is the one that matters most here. Before calling
something breaking, check whether it can honestly land as a minor:

1. Can an existing caller keep their current source unchanged and get the same
   behaviour? If yes, it is a minor.
2. Is the new option defaulted to the old behaviour? If yes, it is a minor.
3. Is the removed thing actually exported from the package entry point, or was
   it internal? Internal means it is not breaking.

Say which of these applied. If the change can land as a minor only by adding a
default, say that too, and say what the default is, so the owner can see the
reasoning rather than take the label on trust. Do not inflate a bump to be safe,
and do not deflate one that genuinely breaks a caller.

Present it in this shape:

```
packages/core      minor  adds `retry` option, defaulted to `false`, existing calls behave identically
packages/cli       patch  fixes argv parsing for empty `--flag`, signature unchanged
internal/testing   none   test helpers only, package is private
```

### Step 4: Show the changeset, then wait

Show the full file content, path and body, before writing anything to disk:

```markdown
---
"@scope/core": minor
"@scope/cli": patch
---

Add a `retry` option to the client, defaulted to `false`.

Fix argv parsing for flags passed with an empty value.
```

Then ask, in plain words, and wait for a yes:

> Write this changeset to `.changeset/<name>.md`?

Do not write and then offer to amend. The user asks for confirmation on
changeset content explicitly, every time. If they ask for edits, show the
revised content and ask again.

After a yes, write the file. Prefer the repo's own command when the user asked
for it that way:

```bash
pnpm changeset
```

`pnpm changeset` is interactive. In a non-interactive session, write the file
directly to `.changeset/<kebab-case-summary>.md` with the content that was just
approved, matching the format above.

Summary text rules:

- One line per user-visible change, imperative, no chat narrative.
- No package-level CHANGELOG entry written by hand.
- No migration guide unless the user asked for one.
- Never reference an issue or a version the user did not name. If they asked for
  a specific reference, such as "referencing v2.4.0", put that reference in the
  summary text.
- Never name a model or AI identifier.

Committing the changeset follows the `ship` skill: branch first, conventional
subject, confirmation before push. Do not commit and push it in one silent move.

### Step 5: Changelog policy

Do not add package-level changelog generation. If `.changeset/config.json`
already sets a `changelog` entry, leave it exactly as it is.

| Situation | Do |
|---|---|
| `changelog` is `false` or absent | Leave it. No per-package `CHANGELOG.md`. |
| `changelog` is `@changesets/changelog-git` | Leave it. Do not swap in a custom script. |
| `changelog` is a custom script and it is failing | Offer `@changesets/changelog-git` as an option, do not switch unilaterally. |
| User asks for a changelog | Configure it in `.changeset/config.json`, not with a bespoke script. |

Never hand-write a migration guide, a release-notes document, or an upgrade doc
unless the user asked for one in this session.

### Step 6: Release readiness checks

Run these before any publish, and paste the real output of each. Claiming a
check passed without its output is not allowed.

The full test suite is not run here. Delegate that to the `verify` skill and
reference its result.

1. The package builds from a clean state:

```bash
pnpm --filter <pkg> run build
```

2. Every path in `exports` and `main`/`module`/`types` exists in the build
   output:

```bash
cat packages/<pkg>/package.json
ls -R packages/<pkg>/dist
```

3. The declared exports resolve for both consumer shapes, under each runtime the
   repo supports. Do this against the packed tarball, not the source tree, so it
   tests what a consumer would install:

```bash
cd packages/<pkg>
pnpm pack
mkdir -p /tmp/release-check && tar -xzf *.tgz -C /tmp/release-check
```

| Consumer | Check | Expected |
|---|---|---|
| ESM | `node --input-type=module -e "import x from '<pkg>'; console.log(typeof x)"` | Resolves, no `ERR_MODULE_NOT_FOUND` |
| CommonJS | `node --input-type=commonjs -e "const x = require('<pkg>'); console.log(typeof x)"` | Resolves, no `ERR_REQUIRE_ESM` |
| Types, ESM | `node --input-type=module -e "..."` plus the `.d.mts`/`.d.ts` path from `exports.types` | The declaration file the map names exists |
| Types, CJS | Same against the `require` condition | The declaration file the map names exists |

Check the extensions actually shipped, whether `.mjs`, `.cjs` or `.js`, and
confirm they agree with the `type` field. A `"type": "module"` package shipping
a `.js` CommonJS file under the `require` condition is a real break, even though
the build succeeded. Run the same two checks under Bun and Deno when the repo
has scripts for those runtimes.

4. The `files` list contains what is needed and nothing else:

```bash
pnpm --filter <pkg> pack --dry-run
```

Read the file list. `dist`, `README.md`, `LICENSE` and `package.json` belong.
Source maps belong only if the repo already ships them. `src/`, tests, fixtures,
`tsconfig.json`, `.env*` and CI config do not.

5. `engines` matches the CI matrix:

```bash
grep -n '"engines"' -A 4 packages/<pkg>/package.json
grep -n 'node-version' .github/workflows/*.yml
```

If the matrix tests a Node version below the `engines` floor, or `engines`
allows a version CI never tests, report the mismatch and stop. Do not quietly
widen `engines` to make it agree.

6. A publish dry run succeeds:

```bash
pnpm --filter <pkg> publish --dry-run --no-git-checks
```

Read the output for the version, the tarball contents and the registry it would
target. If any of checks 1 to 6 fails, stop. Report the failure and fix the root
cause. Do not publish past a failing check.

### Step 7: Version PR flow

Bump, open a PR, label it, let CI publish. Do not publish from a laptop when the
repo has a publish workflow.

```bash
git checkout -b chore/release-version-packages
pnpm changeset version
pnpm install --lockfile-only
git add -A
git reset -- .claude docs/plans .plans
git diff --staged --name-status
```

Commit with a conventional subject, then open the PR after a confirmation:

```bash
gh pr create --draft --base main \
  --title "chore(release): version packages" \
  --body-file <file>
```

PR title is a Conventional Commit subject, because the repo squash-merges and
the title becomes the commit on `main`.

PR body is summary, trade-offs, follow-ups. It states which packages move and to
which versions, as fact read from the diff. It carries no opinion about whether
this should have been a minor or a major, because that is the repo owner's
decision.

Apply the label the publish workflow gates on. Read the workflow rather than
guessing the label name:

```bash
grep -n 'labels\|label\|github.event.pull_request.labels' .github/workflows/*.yml
gh pr edit <number> --add-label <release-label>
```

If the workflow auto-starts only when the PR carries that label, say so
explicitly, and confirm the label is applied before expecting a publish.

When editing or creating the workflow itself, prefer `gh` CLI steps over
third-party marketplace actions:

| Instead of | Use |
|---|---|
| `softprops/action-gh-release` | `gh release create <tag> --notes-file <file>` |
| `peter-evans/create-pull-request` | `gh pr create` in a `run:` step |
| A marketplace tagging action | `git tag` plus `git push origin <tag>` |
| A marketplace label action | `gh pr edit --add-label` |

`gh` is preinstalled on GitHub-hosted runners and needs only `GH_TOKEN` in the
step environment. Fewer third-party actions means fewer supply-chain surfaces
and fewer version pins to chase.

Name workflows and jobs for what they do, consistently. A `<verb>-<target>`
shape is one way to do that, so a repo might end up with names along the lines
of `publish-cli` or `release-version-pr`. The pattern matters more than the
particular words: if the repo already has one, follow it rather than
introducing a second one.

### Step 8: Publishing is a remote write

Three separate confirmations. Each is asked in plain words, each waits for a
yes. None of them is implied by the previous one.

> Publish `<pkg>@<version>` to the registry?

> Tag this release as `<tag>`?

> Push tag `<tag>` to `origin`?

Preconditions, checked and pasted before asking any of them:

```bash
git status --porcelain
git rev-parse --abbrev-ref HEAD
git fetch origin
git rev-list --left-right --count origin/main...HEAD
```

| Condition | Action |
|---|---|
| Working tree dirty | Stop. Never publish from a dirty tree. |
| Branch behind upstream | Stop. Pull and re-run the readiness checks. |
| Not on the branch the release is cut from | Stop and report. |
| Dry run from step 6 not run in this session | Run it first. |

Never use `--no-git-checks` for a real publish. It is for the dry run only, and
only when the tree is otherwise clean.

Publishing and tagging cannot be undone. A published version cannot be reused
even after an unpublish. Treat every one of these as irreversible.

### Step 9: Workflow permission failures

A release workflow that fails with a 403 for `github-actions[bot]`, for example
`Permission to <org>/<repo>.git denied to github-actions[bot]` or
`remote: Write access to repository not granted`, is a permissions problem. It
is not flaky. Do not re-run the job, and do not re-run it with a delay.

Report what to check, in this order:

1. The workflow's `permissions` block. A job that pushes a commit, a tag or a
   PR needs write scope, and the default is often read-only:

```yaml
permissions:
  contents: write
  pull-requests: write
  id-token: write
```

```bash
grep -n 'permissions:' -A 5 .github/workflows/*.yml
```

2. The repository setting **Settings, Actions, General, Workflow permissions**.
   If it is set to read-only for the repo or inherited from the organisation, no
   in-file `permissions` block can grant write.

3. The setting **Allow GitHub Actions to create and approve pull requests**,
   which is separate and must be on for a workflow that opens the version PR.

4. Branch protection on `main`. A protected branch rejects a bot push even with
   `contents: write`. The fix is an allowance for the bot, or routing the change
   through a PR instead of a direct push.

5. If the workflow uses a PAT or an app token instead of `GITHUB_TOKEN`, check
   that the token has not expired and still carries the scopes above.

Note the knock-on effect: a push made with `GITHUB_TOKEN` does not trigger other
workflows. If the release push is meant to start a publish job, that job will
not fire, and the fix is an app token or a `workflow_dispatch`, not a retry.

State which of these to check and why. Change a workflow file only after the
user says which fix they want, since 2, 3 and 4 are repository settings that
only the owner can change.

### Step 10: Report

State plainly:

- Which release mechanism was detected and from which file
- Any `fixed` or `linked` group that widens the blast radius, and the packages in it
- The classification per package with the reasoning, minor versus major called out
- Whether the changeset was shown and confirmed before being written, and its path
- Which readiness checks ran, with their pasted output, and which failed
- What was published, tagged or pushed, and what was only prepared
- For a workflow failure, the cause identified and the specific setting or block to change
- The recommended release type, marked as a recommendation, not a decision

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing a changeset file before showing its content | Show the full file, ask, wait for a yes. Every time, without exception. |
| Assuming a bump level from the branch name or the chat | Derive it from `git diff origin/main...HEAD`, per package, with reasoning. |
| Publishing without a dry run | Run `pnpm publish --dry-run` and read the tarball contents first. |
| Re-running a 403'd release job | A 403 for `github-actions[bot]` is permissions. Check the `permissions` block, then the repo Actions settings. |
| Generating a changelog the repo did not ask for | No package-level `CHANGELOG.md` and no migration guide unless already configured or requested. |
| Assuming Changesets because it is a pnpm workspace | Read `.changeset/config.json`, `.releaserc*` or whatever bespoke release config the repo keeps before acting. |
| Ignoring a `fixed` group when classifying | A patch on one member moves the whole group. Name every affected package. |
| Using two-dot `git diff main..HEAD` | Three dots compares against the merge base; two dots picks up unrelated drift on `main`. |
| Calling a defaulted new parameter breaking | If existing calls compile and behave the same, it is a minor. Say why. |
| Deflating a genuine break to keep it a minor | A removed export or a changed default is a major. Do not soften it. |
| Checking exports against `src/` instead of the tarball | `pnpm pack`, extract, then resolve. That is what a consumer installs. |
| Testing only the ESM entry point | Resolve under both `import` and `require`, and check the shipped extensions match the `type` field. |
| Shipping `src/`, tests or `tsconfig.json` in the tarball | Read `pack --dry-run` output and trim the `files` list. |
| Widening `engines` to make it match CI | Report the mismatch and stop. The floor is a decision, not a formality. |
| Publishing from a dirty tree or a branch behind upstream | Check `git status --porcelain` and `git rev-list --left-right --count`. Stop on either. |
| Treating a publish confirmation as covering the tag and the push | Three separate asks, three separate yeses. |
| Using `--no-git-checks` on a real publish | Dry run only. It exists to skip checks you actually want. |
| Reaching for `softprops/action-gh-release` or `peter-evans/create-pull-request` | Use `gh release create` and `gh pr create` in `run:` steps. |
| Expecting CI to publish without the gating label | Read the workflow for the label it gates on and apply it with `gh pr edit --add-label`. |
| Putting a release-type opinion in the PR body | Recommend it in chat with reasoning. The PR body states facts only. |
| Asserting "this must be a major" | The release type is the repo owner's decision. Recommend, never decide. |
| Running the full test suite as part of the readiness checks | Delegate to the `verify` skill and reference its result. |
