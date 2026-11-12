---
name: sync-docs
description: Use when documentation has drifted from the code and needs to be brought back in line, across READMEs, CONTRIBUTING, the VitePress guide, doc comments, CLI help text and llms.txt. Triggers on requests like "update the docs", "docs are out of date", "the help text and readme disagree", "some links are no longer valid", "remove duplicate information", or after an API rename, an export change, a dependency removal or a Node or package manager version bump.
---

# sync-docs

## Overview

Brings documentation back in line with the code. It lists every
documentation surface first, checks every example against the real exports
and every CLI example against real `--help` output, sweeps for dead links,
reconciles versions across files, and reports what changed and what needs a
decision. Every claim it writes is checked against a file read in this run.

## Workflow

### Step 1: Inventory every surface first

```bash
ls README.md CONTRIBUTING.md CHANGELOG.md llms.txt llms-full.txt 2>/dev/null
find . -name README.md -not -path '*/node_modules/*' -not -path '*/dist/*'
find apps/docs -name '*.md' -not -path '*/node_modules/*' -not -path '*/.vitepress/cache/*' 2>/dev/null
find . -path '*.vitepress/config*' -not -path '*/node_modules/*'
```

| Surface | Usually | Drifts in |
|---|---|---|
| Root README | `README.md` | install, quickstart, feature list |
| Package READMEs | `packages/*/README.md` | imports, export names |
| CONTRIBUTING | `CONTRIBUTING.md` | Node version, package manager, dev steps |
| Guide | `apps/docs/**/*.md` | guides, API pages |
| Sidebar and nav | `apps/docs/.vitepress/config.ts` | links to moved or deleted pages |
| Doc comments | `packages/*/src/**/*.ts` | `@param`, `@example`, `@deprecated` |
| CLI help | the command definitions | flags, examples |
| Machine-readable | `llms.txt`, `.well-known/*` | spec shape, stale links |

Show the inventory before editing: each surface found, in or out of scope
(with why), or "not present". Don't create a surface nobody asked for.

### Step 2: Check examples against the real exports

For every example, prove each imported symbol and import path is public:

```bash
jq '{name, exports, types, bin}' packages/<pkg>/package.json
grep -n '^export' packages/<pkg>/src/index.ts
grep -E '^(export|declare)' packages/<pkg>/dist/index.d.ts   # when built, this is the authority
```

| Finding | Do |
|---|---|
| Exported from the entry point | Keep |
| In the source but not re-exported | Rewrite to the public export; never document an internal |
| Renamed | Rename everywhere, doc comments included |
| Doesn't exist | Remove or rewrite, and list it as an invented reference |

An import path with no matching `exports` subpath doesn't work, whatever
the symbol.

### Step 3: Check CLI examples against `--help`

```bash
jq '.bin, .scripts' packages/<pkg>/package.json
pnpm --filter <pkg> build            # when the bin points at built output
mkdir -p .sync-docs
node packages/<pkg>/dist/cli.js --help > .sync-docs/help.txt 2>&1; echo "exit=$?"
node packages/<pkg>/dist/cli.js <subcommand> --help >> .sync-docs/help.txt 2>&1; echo "exit=$?"
```

Use the bin or script `package.json` declares rather than a guessed path, and
run `--help` for every subcommand the docs mention.

`--help` is the truth for flags and subcommands. Docs describing a better
interface than the code has is a decision for the owner, not a doc edit. If
the CLI can't be built or run, mark every CLI example unverified; never fall
back to memory. Never stage `.sync-docs/`.

### Step 4: Sweep for dead links

```bash
grep -rnoE '\]\(([^)]+)\)' --include='*.md' . | grep -v node_modules | grep -vE 'https?://'
grep -nE "link:" apps/docs/.vitepress/config.ts
grep -rnoE 'https?://[^)"[:space:]]+' --include='*.md' . | grep -v node_modules | sort -u
curl -s -o /dev/null -w '%{http_code}\n' -L --max-time 10 <url>
```

Resolve each relative link from its file, and check anchors against the
target's headings. Every sidebar `link` must hit a real page; list orphan
pages and dangling entries separately. An external 200 is alive, 404 or 410
is dead, anything else is unverified.

| Case | Do |
|---|---|
| Target moved | Update the link; note the move |
| Deleted, content lives elsewhere | Repoint |
| Deleted, content gone | Report it; keep the section; ask |
| Feature removed | Remove the reference; say so |
| External 404 | Report it; never invent a replacement URL |

Never delete a section to make a link problem go away.

### Step 5: Reconcile versions and commands

```bash
jq '{packageManager, engines, scripts}' package.json
cat .nvmrc .node-version 2>/dev/null
grep -rnE 'node-version|pnpm/action-setup' .github/workflows/
grep -rniE 'node ?v?[0-9]{2}|pnpm@|npm install|yarn add' README.md CONTRIBUTING.md
```

Compare each claim (Node version, package manager, install command, script
names) across `package.json`, `.nvmrc`, CI, README and CONTRIBUTING. Check
each documented command against its own source: `<pm> run <name>` against
`scripts`, `make <target>` against the Makefile, a CLI against `bin`, and a
built-in such as `pnpm install` against the tool's docs. A command that
resolves there is not drift. `engines`,
`packageManager` and the lock file say what the repo requires; CI says
what's exercised. The package manager comes from the lock file, never
from README prose. Report each disagreement with both `file:line`s; never
average two versions.

### Step 6: Deduplicate toward the guide

A README says what the package is, how to install it, one minimal example,
and where to read more. Full API detail and rationale live in the guide;
dev steps in CONTRIBUTING. When content is in two places, the guide keeps it
and the copy becomes one sentence and a link, after the link and anchor are
checked. Never delete a copy the guide doesn't hold: move it first, or
report it. Repoint anything that linked into a removed section.

### Step 7: House rules on everything touched

No emoji; em-dashes only where they help; placeholder secrets only and no
example that prints one (rewrite it to use the value without printing);
`example.com` for domains; no model names or AI identifiers outside an
ADR's Sign-off line, which stays as written. Removing a
name is a whole-repo sweep across every surface and the source, help text
and doc comments included:

```bash
grep -rni '<name>' --include='*.md' --include='*.ts' --include='*.json' . | grep -v node_modules
```

### Step 8: Machine-readable files follow their spec

Read the spec before writing: llmstxt.org for `llms.txt` and
`llms-full.txt` (one H1, an optional blockquote, then link sections), the
Node docs for `exports`, the VitePress docs for the installed major's config.
A file under the wrong name is drift; renaming it means fixing every link to
it.

### Step 9: Report

```markdown
## Docs sync

Surfaces inventoried: <n>. Files changed: <n>.

### Changed
| File | Change | Verified against |
|---|---|---|
| packages/x/README.md | `formatDate` example now uses `formatTimestamp` | packages/x/src/index.ts:14 |

### Found, not fixed, needs a decision
| Location | Drift | Why not fixed |
|---|---|---|
| docs/guide/cli.md:22 | documents `--json`, which `--help` doesn't list | Code change or doc change? |
```

Every changed row names the file that proved it. Every dead link is in one
of the two lists. Unverified CLI examples are listed as unverified. Run the
repo's checks through `verify` before saying the docs are in sync.

## Common Mistakes

| Mistake | Fix |
|---|---|
| An example importing something not exported | Read the entry point or `dist/*.d.ts` first |
| CLI flags from memory | Run `--help` and diff |
| Writing a flag the CLI doesn't have | Report it as a decision |
| Deleting a section to fix a dead link | Report the link and ask |
| A guessed replacement URL | Report the 404 |
| Fixing the README but not the sidebar, doc comments or help text | A rename is a whole-repo sweep |
| Editing before the inventory | Inventory first, shown |
| The package manager from README prose | The lock file decides |
| Deleting a duplicate the guide doesn't hold | Move it to the guide first |
| "Docs updated" with no per-file list | The two-list report |
