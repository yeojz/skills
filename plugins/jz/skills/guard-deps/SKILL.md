---
name: guard-deps
description: Use when the work is dependency or supply-chain maintenance, from advisory remediation to vetting a package before adopting it. Triggers on requests like "pnpm audit", "npm audit", "dependabot", "CVE-2025-12345", "add it to the audit ignore", "why is it not honoring overrides", "pin actions to a hash", "minimumReleaseAge", "cooldown", "should we add this dependency", "is this package maintained", or when the user pastes a GitHub security alert URL.
---

# guard-deps

## Overview

Dependency and supply-chain work: fixing advisories, hardening GitHub
Actions, setting install-time delays, and vetting a package before it's
adopted. No config key is written before its live documentation is read and
cited; an upgrade beats an override, and an override beats an ignore; every
ignore has a reason and an expiry; actions are pinned to commit SHAs.

## Modes

Run only the mode asked for. If two are asked for, run them in this order
and say so.

| Request | Mode |
|---|---|
| "fix the audit issues", a Dependabot alert URL, a CVE or GHSA id | 1. Remediate |
| "pin the actions", "Node 20 actions are deprecated", "no more third-party actions" | 2. Harden actions |
| "add minimumReleaseAge", "dependabot cooldown", "supply chain concerns" | 3. Install-time delay |
| "should we add X", "is X maintained", "alternatives to X", "is ISC ok" | 4. Vet (read-only) |

## Shared steps

**Branch first** (not in mode 4), as the `pr` skill's Worktree section
describes: `fix/deps-patch-<advisory-or-package>`, `chore/deps-bump-<pkg>`,
`ci/actions-pin-to-sha` or `chore/supply-chain-<setting>`.

**Package manager** from the lock file, never assumed; with no lock file,
the `packageManager` field; otherwise ask. Record its version, because
setting names move between majors.

| Manager | Audit |
|---|---|
| pnpm | `pnpm audit` |
| npm | `npm audit` |
| yarn | `yarn npm audit` |
| bun | `bun audit` |

**Read every key's live docs before writing it.** Fetch the page, confirm
the key exists, its spelling, type, units and file, and that it applies to
the installed version; cite the URL with its anchor next to the change. If
the fetch fails or the key isn't there, stop and ask for the docs. Memory of
a key name is not evidence.

| Configuring | File | Docs |
|---|---|---|
| pnpm settings (install-time settings live here, not `.npmrc` or `package.json`) | `pnpm-workspace.yaml` | https://pnpm.io/settings |
| `minimumReleaseAge`, its exclusions | `pnpm-workspace.yaml` | https://pnpm.io/settings/dependency-resolution#minimumreleaseage |
| `overrides` (workspace root only) | `pnpm-workspace.yaml` | https://pnpm.io/settings/dependency-resolution#overrides |
| Audit level and ignore list (an `audit` section; the old `auditConfig` keys are deprecated or gone) | `pnpm-workspace.yaml` | https://pnpm.io/cli/audit |
| Dependabot `cooldown`, `groups`, `schedule` | `.github/dependabot.yml` | https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference |
| Workflow syntax | `.github/workflows/*.yml` | https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax |
| Action pinning and risk | `.github/workflows/*.yml` | https://docs.github.com/en/actions/reference/security/secure-use |

The notes in the first column were true when written; confirm them on the
live page too.

**Read what's there** (`pnpm-workspace.yaml`, `.github/dependabot.yml`,
`.github/workflows/`) so the change is a diff: keep existing keys, comments
and order, and ask before changing a key that's already set differently.

**Finish** (not in mode 4) with the `verify` skill, even for a YAML-only
change, then hand the commit and PR to the `pr` skill with: what changed,
every override and every ignore with its reason and expiry under
Trade-offs, and unfixed advisories and expiry dates under Follow-ups.

## Mode 1: Remediate

**Gather from every source**, not just the pasted alert:

```bash
mkdir -p .verify-logs; pnpm audit --json > .verify-logs/audit.json; pnpm audit --prod; pnpm audit --dev
gh api -X GET repos/{owner}/{repo}/dependabot/alerts -f state=open --paginate \
  --jq '.[] | {number, ghsa: .security_advisory.ghsa_id, severity: .security_advisory.severity, pkg: .dependency.package.name, scope: .dependency.scope, fix: .security_vulnerability.first_patched_version.identifier}'
```

Never stage `.verify-logs/`. A `403` means the token lacks `security_events` or the account isn't an
admin: say so and continue with the audit. A pasted
`.../security/dependabot/<n>` URL is `gh api repos/<o>/<r>/dependabot/alerts/<n>`.
Check existing ignore lists too: a suppressed advisory doesn't show up.

**Triage** into one table, keyed by GHSA id (with the CVE when there is
one), before changing anything:

| Advisory | Severity | Package | Path (`pnpm why`) | Scope | Fixed version |
|---|---|---|---|---|---|

Production and development scope are different risks; say which. A null
patched version means no fix exists.

**Apply the ladder** for each row, in order, saying which rung and why the
one above failed:

1. **Upgrade.** A direct dependency: `pnpm update <pkg>@<fixed>`. A
   transitive one: upgrade the dependent that pins it
   (`pnpm why <pkg>`, then `pnpm update <dependent> --latest`). Confirm with
   `pnpm why <pkg>` that the vulnerable version is gone.
2. **Scoped override**, only when no upgrade exists: scoped to the affected
   edge where the syntax allows, an exact version or tight range, at the
   workspace root, and inside the dependent's declared range (or flagged as
   breaking). Prove it with `pnpm install` and `pnpm why <pkg>`:

   | Symptom | Cause |
   |---|---|
   | No effect | Wrong file or key; re-read the docs |
   | Ignored in one package | Declared outside the root |
   | Graph unchanged | Lockfile not refreshed |
   | Old and new both present | Another edge declares an incompatible range |
   | Peer warning | The pin violates a peer range |

   Stop after 3 attempts and paste the graph; don't fall back to an ignore
   by default.
3. **Time-boxed ignore**, only with no fix and no viable override, or when
   the advisory is unreachable and you can say why. Use the id form the tool
   accepts (resolve a CVE to its GHSA id with
`gh api -X GET /advisories -f cve_id=<CVE> --jq '.[].ghsa_id'` and confirm the
mapping),
   a reason comment, an expiry as `YYYY-MM-DD` (90 days unless told
   otherwise; "temporarily" isn't one), and the same line in the PR body:

   ```yaml
   audit:
     ignore:
       # No fixed version published. Dev-only, docs build. Expires 2026-12-09.
       - GHSA-xxxx-xxxx-xxxx
   ```

   Without the owner's agreement to an ignore, leave it open as a follow-up.

**Prove it**: `pnpm install && pnpm audit`, with before and after counts by
severity, and each remaining finding with why it remains. Never "audit
clean" without the output.

## Mode 2: Harden actions

1. **Inventory** every `uses:` under `.github/workflows/` and
   `.github/actions/`, including reusable workflows. Local `./` references
   need no pin; say so.
2. **Resolve each** to its latest release, then that release's commit:

   ```bash
   tag=$(gh api repos/<o>/<r>/releases/latest --jq .tag_name)
   gh api repos/<o>/<r>/git/ref/tags/"$tag" --jq '{sha: .object.sha, type: .object.type}'
   gh api repos/<o>/<r>/git/tags/<tag-object-sha> --jq .object.sha   # only when type is tag
   ```

   With no release, use the highest semver tag and say so. Never reuse a
   SHA from memory; the full 40 characters, from the action's own repo.
3. **Rewrite** as `uses: actions/checkout@<sha> # v5.0.0`, keeping the
   comment in sync. A Dependabot `github-actions` entry updates both.
4. **Deprecated runtimes**: read each action's `runs.using`
   (`gh api repos/<o>/<r>/contents/action.yml --jq .content | base64 -d`)
   against the runtimes the live Actions docs support, and name the version
   that fixes it.
5. **Prefer `gh`** in a `run:` step with `GH_TOKEN: ${{ github.token }}`
   over a third-party action, and say which action it removes. When there's
   no `gh` equivalent, vet the action with mode 4's checks.
6. **Check**: `actionlint` if installed (never install it), otherwise parse
   the YAML. Then `grep -rn "uses:.*@" .github/workflows/ .github/actions/ 2>/dev/null | grep -v "@[0-9a-f]\{40\}"`
   must print nothing, or each line must be explained.

## Mode 3: Install-time delay

Read both docs pages first: the file, the units (minutes), what the
exclusion list accepts, and where `cooldown` and `groups` nest.

```yaml
# pnpm-workspace.yaml
minimumReleaseAge: 10080 # 7 days x 1440
minimumReleaseAgeExclude:
  - '@myorg/*'
```

Show the arithmetic and the default the installed version already applies.
Exclusions are only for first-party packages and urgent security fixes, each
with its reason. Note that a security fix newer than the window is blocked
until it passes or is excluded.

```yaml
# .github/dependabot.yml, under the updates entry
    cooldown:
      default-days: 7
    groups:
      dev-dependencies:
        dependency-type: "development"
        update-types: ["minor", "patch"]
```

Check the cooldown range, which per-semver keys the ecosystem supports, and
whether cooldown applies to security updates. Configure a `github-actions`
entry too, without assuming the same keys work. Then parse the YAML, run
`pnpm install --lockfile-only`, re-read every key against its page, and tell
the owner to check the repo's Dependabot page after merge; a local parse
doesn't prove the config is valid.

## Mode 4: Vet before adopting

Read-only. The default answer is no.

1. **Does something already do it?** A workspace dependency
   (`pnpm list --recursive --depth 0`), a Node built-in, a framework the
   repo uses, or thirty lines in the repo. If so, recommend that and stop.
2. **Evidence**:

   ```bash
   npm view <pkg> version time.modified license dist.unpackedSize dependencies deprecated repository.url
   gh api repos/<o>/<r> --jq '{archived, open_issues_count, pushed_at, license: .license.spdx_id}'
   ```

   | Signal | Reads as |
   |---|---|
   | Last release | Stale past about 12 months in an active area |
   | Deprecated or archived | An automatic no |
   | Open PRs with no merges | Maintenance has stopped |
   | Direct dependencies | Many on a utility multiplies supply-chain risk |

   | Licence, for an MIT or ISC repo | Verdict |
   |---|---|
   | MIT, ISC, BSD-2/3, Apache-2.0, 0BSD, Unlicense | Yes (Apache adds a notice) |
   | MPL-2.0 | Usually; its files stay MPL |
   | LGPL | Ask first |
   | GPL, AGPL, none, custom | No |

   Name the SPDX id you read, not the README's claim. ISC is equivalent to
   MIT here.
3. **Recommend one**: don't add it (and what covers the need), add this
   alternative instead (vetted the same way, with migration cost), or add it
   (which package, prod or dev, how pinned). Adding it later is a new
   request starting at branch first.

## Common Mistakes

| Mistake | Fix |
|---|---|
| A config key from memory | Fetch the docs page, confirm, cite |
| pnpm settings in `.npmrc` | `pnpm-workspace.yaml`, per the live page |
| A CVE id where the tool keys on GHSA | Resolve the mapping first |
| An ignore with no expiry | Id, reason, `YYYY-MM-DD` expiry, PR line |
| Starting at an ignore | Upgrade, then override, then ignore |
| "The override worked" without the graph | `pnpm why`, pasted |
| An action pinned to a tag or short SHA | Full SHA of the latest release, with a version comment |
| A new third-party action without checking `gh` | Check for a `gh` step first |
| "Audit clean" with nothing pasted | Before and after counts |
| A survey instead of a recommendation | One answer; default no |
