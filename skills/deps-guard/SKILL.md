---
name: deps-guard
description: Use when the work is dependency or supply-chain maintenance, from advisory remediation to vetting a package before adopting it. Triggers on requests like "pnpm audit", "npm audit", "fix the audit issues", "dependabot", "address the security findings", "security advisory", "CVE-2025-12345", "add it to the audit ignore", "check if we can override ajv safely", "why is it not honoring overrides", "pin the actions", "pin actions to a hash", "supply chain", "minimumReleaseAge", "cooldown", "should we add this dependency", "is this package maintained", or when the user pastes a GitHub security alert URL such as https://github.com/<owner>/<repo>/security/dependabot/<n>.
---

# deps-guard

## Overview

Dependency and supply-chain work: remediating advisories, hardening GitHub
Actions, configuring install-time supply-chain settings, and vetting a package
before it is adopted. Guarantees that no configuration key is written before its
authoritative documentation has been fetched and cited, that a real upgrade is
preferred over an override and an override over an ignore, that every ignore
carries a reason and an expiry, that actions are pinned to commit SHAs rather
than tags, and that nothing is edited on `main`.

## Modes

Pick the mode from what the user asked for. Run only that mode. If two modes are
genuinely requested in one message, run them in the order listed and say so.

| User asked | Mode | Section |
|---|---|---|
| "fix the pnpm audit issues", "address the github security findings", a pasted `security/dependabot/<n>` URL, a CVE or GHSA id | Remediate advisories | Mode 1 |
| "pin the actions", "pin them via hash", "Node 20 actions are deprecated", "I don't want another third-party action" | Harden GitHub Actions | Mode 2 |
| "add minimumReleaseAge", "add cooldown for dependabot", "fix the versions of all dependencies", "supply chain concerns" | Install-time supply chain | Mode 3 |
| "should we add X", "is X maintained", "any alternatives to X", "any concerns with the ISC license" | Vet before adopting | Mode 4 |

If the mode is ambiguous, state which one you are about to run and why, then run
it. Do not widen the scope on your own initiative: an audit fix is not licence
to also pin every action.

## Workflow

Steps 1 to 4 are shared. Step 5 runs the mode. Steps 6 and 7 are shared again.

### Step 1: Branch first

Hard gate, before any file is touched. Mode 4 is read-only and skips this step;
every other mode runs it.

```bash
git rev-parse --abbrev-ref HEAD
```

If the current branch is the repo's default branch, create a branch before
editing anything:

```bash
git checkout -b <type>/<scope>-<description>
```

Dependency work is `chore`, `fix` or `ci`:

| Work | Branch |
|---|---|
| Advisory remediation | `fix/deps-patch-<advisory-or-package>` |
| Dependency bump with no advisory | `chore/deps-bump-<package>` |
| Action pinning, workflow hardening | `ci/actions-pin-to-sha` |
| Install-time settings | `chore/supply-chain-minimum-release-age` |

Do not create a git worktree. Do not stash. If the checkout is blocked, stop and
report.

### Step 2: Detect the package manager

Never assume. Read the lock file in the repo root, or the nearest ancestor that
has a `package.json`:

| Lock file | Package manager | Audit command |
|---|---|---|
| `pnpm-lock.yaml` | `pnpm` | `pnpm audit` |
| `bun.lockb` or `bun.lock` | `bun` | `bun audit` |
| `yarn.lock` | `yarn` | `yarn npm audit` |
| `package-lock.json` | `npm` | `npm audit` |

If no lock file is present, read the `packageManager` field in `package.json`.
If that is also absent, ask rather than guessing. Never mix package managers in
one repo.

Record the exact version too, because settings names move between majors:

```bash
pnpm --version
```

### Step 3: Resolve every configuration key against live documentation

This step is mandatory and it comes before writing any key, any file, any YAML
fragment. Configuration schemas drift: keys are renamed, moved between files and
retired between releases, so a key is written only after it has been seen on the
vendor's current documentation page. The memory of a key name is not evidence
that the key exists.

For each key you are about to write:

1. Fetch the canonical page for that key from the table below with `WebFetch`.
2. Confirm the key exists, its exact spelling, its value type and units, and
   which file it belongs in.
3. Confirm it applies to the detected tool version. Note the "Added in" version
   where the docs give one, and check it against the version from step 2.
4. Cite the URL, with its anchor, in your message to the user next to the change.
5. If the fetch fails or the key is not on the page, stop. Say the key could not
   be verified and ask for the documentation URL. Do not write an unverified key.

Canonical sources:

| What you are configuring | File | Documentation |
|---|---|---|
| pnpm settings, index and general rules | `pnpm-workspace.yaml` | https://pnpm.io/settings |
| `minimumReleaseAge`, `minimumReleaseAgeExclude` | `pnpm-workspace.yaml` | https://pnpm.io/settings/dependency-resolution#minimumreleaseage |
| pnpm `overrides` | `pnpm-workspace.yaml`, root project only | https://pnpm.io/settings/dependency-resolution#overrides |
| pnpm audit level and ignore list | `pnpm-workspace.yaml` | https://pnpm.io/cli/audit |
| Dependabot `cooldown`, `groups`, `schedule` | `.github/dependabot.yml` | https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference |
| Workflow syntax, `uses`, `permissions`, `jobs` | `.github/workflows/*.yml` | https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax |
| Action pinning and third-party action risk | `.github/workflows/*.yml` | https://docs.github.com/en/actions/reference/security/secure-use |
| Dependabot alerts REST API | n/a, read only | https://docs.github.com/en/rest/dependabot/alerts |

Two claims that hold at the time of writing, and that are themselves the kind of
claim this step exists to check. Confirm both against the live pages rather than
trusting this file:

- pnpm install-time settings live in `pnpm-workspace.yaml`. Not `.npmrc`, which
  carries only auth and registry settings, and not `package.json`.
- The audit ignore list and the audit level moved into an `audit` section of
  `pnpm-workspace.yaml`. The older `auditConfig.ignoreGhsas` spelling is
  deprecated, and `auditConfig.ignoreCves`, which took CVE identifiers, is no
  longer recognised at all. A user asking to "add a CVE to the audit ignore" is
  describing intent, not schema: resolve the CVE to its GHSA id and use whatever
  key the live page documents.

### Step 4: Read what the repo already has

Before proposing anything, read the current state so the change is a diff and not
a rewrite:

```bash
cat pnpm-workspace.yaml 2>/dev/null
cat .github/dependabot.yml 2>/dev/null
ls .github/workflows/ 2>/dev/null
```

Preserve existing keys, comments and ordering. If a key you are asked to add is
already present with a different value, say so and ask before changing it.

### Step 5: Run the mode

Go to the matching mode section below and run its steps in order.

### Step 6: Verify

Call the `verify` skill. It runs the repo's own lint, typecheck, test and build
scripts and pastes real output. A dependency change breaks a build silently, so
this is not optional, including for a change that only touches YAML.

If `verify` is unavailable, run the repo's `package.json` scripts directly and
paste the output. Do not report success without pasted output, and do not weaken
a test or a lint rule to absorb a dependency change: root-cause it.

### Step 7: Hand off to ship

Call the `ship` skill for the branch, commit and pull request. Do not commit,
push or open a PR by hand from this skill.

Give `ship` the material it needs for the PR body:

- Summary: which advisories, actions, settings or packages changed.
- Trade-offs: every override, and every ignore with its reason and expiry date.
- Follow-ups: advisories with no fix available, and any ignore expiry that will
  need revisiting, with the date.

---

## Mode 1: remediate advisories

### Step M1.1: Gather findings from every source the repo has

Do not work from a single source. A pasted alert is one row of a longer table.

Package manager audit, machine readable:

```bash
pnpm audit --json > /tmp/audit.json
pnpm audit
```

Split production from development scope, because it changes the priority:

```bash
pnpm audit --prod
pnpm audit --dev
```

GitHub Dependabot alerts, if the repo is on GitHub and `gh` is authenticated:

```bash
gh api -X GET repos/{owner}/{repo}/dependabot/alerts \
  -f state=open --paginate \
  --jq '.[] | {number, ghsa: .security_advisory.ghsa_id, severity: .security_advisory.severity, pkg: .dependency.package.name, scope: .dependency.scope, manifest: .dependency.manifest_path, fix: .security_vulnerability.first_patched_version.identifier}'
```

If this returns `403`, the token lacks the `security_events` scope or the account
lacks admin access on the repo. Report that and continue with the audit output
alone rather than silently dropping the source.

A pasted alert URL of the form
`https://github.com/<owner>/<repo>/security/dependabot/<n>` maps directly to one
alert:

```bash
gh api repos/<owner>/<repo>/dependabot/alerts/<n>
```

Also check whether the repo already suppresses findings, since a suppressed
advisory will not appear in the audit output at all: look for an audit ignore
list in `pnpm-workspace.yaml` and for `ignore` entries under
`.github/dependabot.yml`.

### Step M1.2: Triage into one table

Merge every source into one table, deduplicated by advisory id, and show it
before changing anything:

| Advisory | Severity | Package | Path | Scope | Fixed version |
|---|---|---|---|---|---|
| GHSA-xxxx-xxxx-xxxx | high | `ajv` | `pkg-a > ajv-formats > ajv` | production | 8.17.1 |

Fill each column from evidence, not inference:

- Advisory: the GHSA id is the primary key. Record the CVE alongside it when the
  advisory has one, because users refer to CVEs.
- Path: `pnpm why <package>` shows which dependents pull it in.
- Scope: production or development. A dev-only advisory in a build tool is a
  different risk from the same one in a shipped runtime dependency. Say which it
  is; do not treat them identically.
- Fixed version: the advisory's first patched version. A null patched-versions
  field in the audit JSON means no fix exists, which is not the same as a fix
  that is awkward to take.

### Step M1.3: Apply the remedy ladder in order

For each row, try A, then B, then C. Never start at C. State which rung you used
and why the one above it did not work.

**A. Real upgrade. Preferred.**

If the vulnerable package is a direct dependency, bump it:

```bash
pnpm update <package>@<fixed-version>
```

If it is transitive, upgrade the dependent that pins it, since that removes the
advisory rather than papering over it:

```bash
pnpm why <package>
pnpm update <dependent> --latest
```

Re-check the graph and confirm the vulnerable version is gone:

```bash
pnpm why <package>
```

**B. Scoped override, pinned to an exact version range.**

Use this only when no upgrade path exists, for instance when the dependent has
not released a fixed version yet. Confirm the override key and file against the
docs from step 3 first, then:

- Scope it to the affected edge rather than the whole graph where the syntax
  allows, so an unrelated consumer of the same package is not silently moved.
- Pin an exact version or a tight range. A wide range reintroduces the problem on
  the next install.
- Overrides can only be declared at the root of the workspace. An override placed
  in a nested package's manifest does nothing.
- Confirm the override is compatible: read the dependent's declared range for the
  overridden package and check the pinned version satisfies it. If it does not,
  say so and treat the override as a breaking change rather than a silent one.

Then prove it took effect:

```bash
pnpm install
pnpm why <package>
pnpm list <package> --recursive --depth Infinity
```

If the old version is still in the graph, the override is not being honoured.
Work through these causes in order before concluding the tool is at fault:

| Symptom | Cause | Fix |
|---|---|---|
| Override has no effect at all | Written in the wrong file or under the wrong key | Re-read the docs from step 3 and move it |
| Override ignored in one package only | Declared outside the workspace root | Move it to the root |
| Graph unchanged after editing | Lockfile not refreshed | Re-run install so the lockfile is regenerated |
| Both old and new versions present | Another edge still declares an incompatible range | Widen the override's scope, or upgrade that dependent instead |
| Install warns about peers | The pinned version violates a peer range | Pick a version that satisfies the peer, or upgrade the peer |

Bound this at 3 attempts. If the override still is not honoured after 3, stop,
paste the graph output, and report what you tried rather than escalating to an
ignore by default.

**C. Time-boxed ignore. Last resort.**

Only when there is no fixed version and no viable override, or when the advisory
is unreachable from any code path the repo executes and you can say why. An
ignore accepts risk, so it must be visible. Every ignore carries, without
exception:

- The advisory id in the form the tool actually accepts. If the user gave a CVE
  and the tool keys on GHSA ids, resolve it first: `gh api /advisories/<GHSA>`,
  or search the GitHub advisory database for the CVE, and confirm the mapping
  before writing it.
- A reason, in a comment on the line above the entry.
- An explicit expiry date, in a comment, as `YYYY-MM-DD`. Default to 90 days from
  today unless the user names a date. "Temporarily" is not an expiry.
- A line in the PR body under Trade-offs, repeating the id, the reason and the
  date, so the decision survives outside the config file.

Shape of the entry, with the key names taken from the live docs in step 3 and not
from this example:

```yaml
audit:
  ignore:
    # No fixed version published. Dev-only, used by the docs build.
    # Expires 2026-12-09. Re-check upstream before then.
    - GHSA-xxxx-xxxx-xxxx
```

If there is no fixed version and no override and the user has not agreed to an
ignore, leave the finding open and list it as a follow-up. An open, documented
finding is better than a silent suppression.

### Step M1.4: Re-run the audit and paste the proof

```bash
pnpm install
pnpm audit
```

Paste the real output. Show the before and after counts by severity. If findings
remain, list each one with the reason it remains: no fix available, deliberately
ignored with an expiry, or out of scope for this change.

Never write "audit clean" without the output above it.

Then go to shared step 6.

---

## Mode 2: harden GitHub Actions

### Step M2.1: Inventory every action reference

```bash
grep -rn "uses:" .github/workflows/ .github/actions/ 2>/dev/null
```

Build a table of every distinct `owner/repo` and its current ref. Include
composite actions the repo calls, and reusable workflows referenced with `uses:`
at job level. Local references beginning with `./` need no pinning; say so rather
than skipping them silently.

### Step M2.2: Resolve each action to its latest release, then to that release's commit SHA

Two lookups per action. Never reuse a SHA from memory or from another repo.

```bash
tag=$(gh api repos/<owner>/<repo>/releases/latest --jq .tag_name)
gh api repos/<owner>/<repo>/git/ref/tags/"$tag" --jq '{sha: .object.sha, type: .object.type}'
```

If `type` is `commit`, that `sha` is the pin. If `type` is `tag`, the tag is
annotated and the value is a tag object, so dereference it to reach the commit:

```bash
gh api repos/<owner>/<repo>/git/tags/<tag-object-sha> --jq .object.sha
```

If the action has no GitHub release, fall back to the highest semver tag from
`gh api repos/<owner>/<repo>/tags` and say that you did, because "latest release"
and "latest tag" are not the same claim.

Verify the SHA belongs to the action's own repository and not to a fork. Use the
full 40 character SHA. A short SHA is not a pin.

### Step M2.3: Rewrite each reference

```yaml
- uses: actions/checkout@<40-character-sha> # v5.0.0
```

The trailing comment carries the human-readable version so the next reader, and
Dependabot, can tell what the pin means. Keep the comment in sync with the SHA;
a stale comment is worse than none.

If the repo has a Dependabot entry for `github-actions`, note that it updates
both the SHA and the comment, so pinning does not freeze the action forever.

### Step M2.4: Flag deprecated runtimes

For each action, read the runtime it declares:

```bash
gh api repos/<owner>/<repo>/contents/action.yml --jq .content | base64 -d | grep -n "using:"
```

Compare `runs.using` against the runtimes GitHub currently supports, read from
the live Actions documentation. Do not assert from memory which Node major is
deprecated; that changes. Composite and Docker actions declare no Node runtime
and are not affected.

Report every action on a deprecated runtime, with the version that moves it to a
supported one. If the latest release is still on a deprecated runtime, say that
the action is behind and treat it as a candidate for replacement in step M2.5.

### Step M2.5: Prefer a `gh` CLI step over a third-party action

Every third-party action is a supply-chain dependency with its own maintainers
and its own transitive actions. Before adding one, check whether a `gh` CLI step
in a `run:` block does the same job with the token the workflow already has.

```yaml
- run: gh release create "$TAG" --generate-notes
  env:
    GH_TOKEN: ${{ github.token }}
```

When proposing a replacement, say explicitly that it removes a third-party action
dependency, and name the action being removed. When no `gh` equivalent exists,
say that too, and report the candidate action's maintenance status using Mode 4's
checks before recommending it.

First-party `actions/*` actions are not free of risk either, but they do not need
the same justification as a marketplace action from an unknown owner.

### Step M2.6: Verify the workflow files still parse

```bash
actionlint
```

If `actionlint` is not installed, do not install it and do not invent a linter.
Parse the YAML instead and confirm the top-level keys against the workflow syntax
documentation from step 3:

```bash
node -e "const y=require('node:fs').readFileSync(process.argv[1],'utf8');require('yaml');" 2>/dev/null || \
python3 -c "import sys,yaml;[yaml.safe_load(open(f)) for f in sys.argv[1:]];print('yaml ok')" .github/workflows/*.yml
```

Confirm every rewritten `uses:` line still resolves:

```bash
grep -rn "uses:.*@" .github/workflows/ | grep -v "@[0-9a-f]\{40\}"
```

Anything that line prints is still on a tag or a branch. Either pin it or state
why it is exempt.

Then go to shared step 6.

---

## Mode 3: install-time supply chain

This mode puts a delay between a package being published and it being installed,
so a compromised release is caught before it lands, and batches updates so they
are reviewed rather than trickled in.

### Step M3.1: Read the documentation for every key first

Do not skip step 3 because the keys feel familiar. This mode is entirely
configuration, so it is entirely exposed to the failure step 3 prevents. Fetch
the pnpm dependency-resolution settings page and the Dependabot options reference
before writing anything, cite both, and confirm on the live pages:

- Which file the pnpm settings belong in.
- The units of the release-age setting. It is expressed in minutes, so "1 week"
  is a conversion the user is asking you to make, not a value they gave you.
- Whether the exclusion setting takes bare names, patterns, versioned entries, or
  all three.
- Where `cooldown` and `groups` nest inside `.github/dependabot.yml`, and which
  cooldown sub-keys the target ecosystem supports.

### Step M3.2: Configure the minimum release age and its exclusions

In `pnpm-workspace.yaml`, alongside the existing keys:

```yaml
minimumReleaseAge: 10080 # 7 days, in minutes
minimumReleaseAgeExclude:
  - '@myorg/*'
```

Show the arithmetic for the value in your message: days times 1440. State the
default that the installed pnpm version already applies, from the docs, so the
user knows whether this is a change or a restatement.

Exclusions exist for packages that must be installable the moment they publish:
first-party packages the workspace publishes to a registry, and any package where
a security fix must not wait out the window. Keep the list short, say why each
entry is on it, and never add one speculatively.

Note the interaction with Mode 1: a security fix newer than the window is blocked
by this setting until the window passes or the package is excluded. Check the
docs for whether the audit fix path handles that automatically on the installed
version.

### Step M3.3: Configure Dependabot cooldown and grouping

In `.github/dependabot.yml`, nested under the relevant `updates` entry rather
than at the top level:

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    cooldown:
      default-days: 7
    groups:
      dev-dependencies:
        dependency-type: "development"
        update-types:
          - "minor"
          - "patch"
```

Check against the reference before writing: the permitted range for cooldown
days, whether the per-semver-level cooldown keys are supported for the ecosystem
you are configuring, whether cooldown applies to security updates as well as
version updates, and the precedence between the include and exclude lists.

If the repo also has a `github-actions` ecosystem entry, configure it too, and
say whether it supports the same cooldown keys as the npm entry rather than
assuming symmetry.

### Step M3.4: Verify the configuration is well formed

YAML is not validated by anything until it runs, so check it now:

```bash
python3 -c "import yaml;print(yaml.safe_load(open('.github/dependabot.yml')))"
pnpm install --lockfile-only
```

Then re-read each key you wrote against the documentation page one final time and
confirm the spelling character by character. State in your report that you did.

GitHub reports `dependabot.yml` errors on the repository's Dependabot page after
the file is pushed, so tell the user to check there once the PR is merged. Do not
claim the Dependabot config is valid on the basis of a local YAML parse alone.

Then go to shared step 6.

---

## Mode 4: vet before adopting

Read-only. Changes no files, so it skips step 1. Its default answer is no.

### Step M4.1: Check whether the workspace already does the job

Before evaluating the candidate at all:

```bash
grep -rn "\"<capability-keyword>" package.json packages/*/package.json apps/*/package.json 2>/dev/null
pnpm list --recursive --depth 0
```

Also consider whether the platform covers it: a Node built-in module, a
capability already present in a framework the repo depends on, or thirty lines
written directly in the repo. If any of these cover the need, recommend that and
stop. The rest of this mode is for candidates that survive this check.

### Step M4.2: Collect the evidence

```bash
npm view <package> version time.modified license dist.unpackedSize dependencies deprecated repository.url
```

Then the repository's health, using the URL from the previous command:

```bash
gh api repos/<owner>/<repo> --jq '{archived, disabled, open_issues_count, pushed_at, license: .license.spdx_id}'
gh api "repos/<owner>/<repo>/pulls?state=open&per_page=1" --jq 'length'
gh api "repos/<owner>/<repo>/commits?per_page=1" --jq '.[0].commit.committer.date'
```

### Step M4.3: Report one table, then a recommendation

| Signal | Finding | Reading |
|---|---|---|
| Last release | date, and months ago | Stale past roughly 12 months for an active area |
| Last commit | date | A repo with commits but no releases is a different risk from a dead one |
| Deprecated flag | set or not | A deprecated package is an automatic no |
| Archived | yes or no | Archived is an automatic no |
| Open issues and PRs | counts | High open PR count with no merges means maintenance has stopped |
| License | SPDX id | See below |
| Install size | unpacked size | |
| Direct dependencies | count and names | A utility with a long dependency list is a supply-chain multiplier |
| Already in the workspace | yes or no | If yes, stop and use it |

Licence compatibility, for a repo published under MIT or ISC:

| Licence | Compatible | Note |
|---|---|---|
| MIT, ISC, BSD-2-Clause, BSD-3-Clause, Apache-2.0, 0BSD, Unlicense | Yes | Permissive. Apache-2.0 adds a patent grant and a notice requirement. |
| MPL-2.0 | Usually, with care | File-level copyleft. Modifications to its files stay under MPL. |
| LGPL | Ask first | Linking terms depend on how the package is bundled. |
| GPL, AGPL | No | Copyleft, incompatible with shipping under MIT or ISC. |
| No licence field, or a custom licence | No | Treat an unlicensed package as not usable. |

ISC is functionally equivalent to MIT for these purposes and is compatible with
it. Say so directly when asked, and name the SPDX id you actually read rather
than the one the README claims.

### Step M4.4: Recommend

Give a recommendation, not a survey. One of:

- **Do not add it.** The default. Say what covers the need instead: an existing
  workspace dependency, a platform built-in, or code written in the repo.
- **Add this alternative instead.** Required when the candidate is unmaintained,
  deprecated or archived. Name a specific alternative, and run steps M4.2 and
  M4.3 on it too, so the alternative is evidenced to the same standard rather
  than asserted. Note the migration cost.
- **Add the candidate.** Only when it is maintained, permissively licensed,
  proportionate in size, and nothing already present does the job. Say which
  package it goes into, whether it is a production or a development dependency,
  and how it should be pinned.

Mode 4 ends here. It writes nothing, so it does not run steps 6 and 7. If the
user then asks to add the package, that is a new request and it starts at step 1.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing a config key from memory without reading its documentation | Step 3 is mandatory. Fetch the canonical page, confirm spelling, type, units and file, and cite the URL next to the change. |
| Trusting a key name because it appeared in an older config or an older answer | Key names move between majors. Check the version the repo runs against the "Added in" note on the docs page. |
| Putting pnpm install-time settings in `.npmrc` or `package.json` | They belong in `pnpm-workspace.yaml`. Confirm against the live settings page, not against this table. |
| Writing a CVE id into a tool that keys on GHSA ids | Resolve the CVE to its GHSA id first and confirm the mapping. Take the user's CVE as intent, not as schema. |
| Adding an ignore without an expiry | Every ignore carries an advisory id, a reason comment, an expiry date as `YYYY-MM-DD`, and a line in the PR body. "Temporarily" is not an expiry. |
| Reaching for an ignore before trying an upgrade or an override | Ladder order is upgrade, then scoped override, then ignore. State which rung you used and why the one above failed. |
| A wide or unscoped override | Pin an exact version, scope it to the affected edge, and declare it at the workspace root only. |
| Declaring the override worked without checking the graph | Run install then `pnpm why <package>` and paste the output. |
| Pinning an action to a tag, a branch, or a short SHA | Pin to the full 40 character commit SHA of the latest release, with the version as a trailing comment. |
| Reusing a SHA from memory or from another repo | Resolve it live per action, dereferencing annotated tag objects to the commit. |
| Adding a third-party marketplace action without considering `gh` | Check for a `gh` CLI equivalent first, and say so explicitly when proposing the replacement. |
| Editing on `main` instead of branching first | Hard gate in step 1. Create `<type>/<scope>-<description>` before touching a file. |
| Claiming the audit is clean without output | Re-run the audit and paste it, with before and after counts by severity. |
| Skipping `verify` because the change is only YAML | A dependency or workflow change breaks builds silently. Always run step 6. |
| Committing or opening the PR from this skill | Hand off to `ship`, which owns branch, commit and PR. |
| Recommending a dependency without checking the workspace first | Step M4.1. If something already present does the job, stop there. |
| Answering a vetting question with a survey instead of a decision | End with one recommendation. The default is do not add. |
