---
name: docs-sync
description: Use when documentation has drifted from the code and needs to be brought back in line, across READMEs, CONTRIBUTING, the VitePress guide, doc comments, CLI help text and llms.txt. Triggers on requests like "update the readme", "update the docs", "docs are out of date", "check the readme", "the help text and readme disagree", "fix the docs", "some links are no longer valid", "references are no longer accurate", "remove duplicate information", or after an API rename, an export change, a dependency removal or a Node or package manager version bump.
---

# docs-sync

## Overview

Brings documentation back into agreement with the code. It inventories every
documentation surface in one pass, verifies every code and CLI example against
the real exports and the real `--help` output, sweeps for dead links, reconciles
versions and commands across README, CONTRIBUTING, CI and `package.json`,
removes duplication in favour of the guide, and reports what changed per file.

The failure this exists to prevent is confidently rewritten documentation that
is still wrong: an example importing a symbol the package never exported, CLI
flags written from memory, or a README updated while the sidebar that links to
it is not. Every claim this skill writes must be checked against a file it read
in this run.

## Workflow

### Step 1: Inventory every surface before editing anything

Documentation drift hides in the surface nobody remembered. Enumerate all of
them first, in one pass, and show the inventory before making a single edit.

```bash
ls README.md CONTRIBUTING.md CHANGELOG.md llms.txt llms-full.txt 2>/dev/null
find . -name 'README.md' -not -path '*/node_modules/*' -not -path '*/dist/*'
find apps/docs -type f \( -name '*.md' -o -name '*.ts' -o -name '*.mts' \) -not -path '*/node_modules/*' -not -path '*/.vitepress/cache/*'
find . -path '*.vitepress/config*' -not -path '*/node_modules/*'
ls .github/workflows/
```

The surface table, filled from what those commands actually found:

| Surface | Where it usually lives | What drifts |
|---|---|---|
| Root README | `README.md` | quickstart, install command, feature list |
| Package READMEs | `packages/*/README.md`, `apps/*/README.md` | import examples, export names, API tables |
| CONTRIBUTING | `CONTRIBUTING.md` | Node version, package manager, dev build steps |
| Docs site pages | `apps/docs/guide/`, `apps/docs/**/*.md` | guides, API pages, migration notes |
| VitePress sidebar and nav | `apps/docs/.vitepress/config.ts` | links to pages that moved or were deleted |
| Doc comments | `packages/*/src/**/*.ts` TSDoc and JSDoc | `@param`, `@returns`, `@example`, `@deprecated` |
| CLI help text | the source that defines commands and flags | flags, descriptions, examples |
| Machine-readable | `llms.txt`, `llms-full.txt`, `.well-known/*` | spec conformance, stale link lists |

For each surface found, record the path and whether it is in scope. A surface
that exists and is out of scope is listed as out of scope with a reason, never
silently dropped. If a surface does not exist in this repo, write "not present"
in that row and move on; do not create it unasked.

Present the inventory, then start editing. Editing before the inventory is how a
README gets fixed while its sidebar entry, its doc comment and its `llms.txt`
line stay wrong.

### Step 2: Verify every code example against the real exports

This is the highest-value check in the skill. Never write or keep an example
that imports a symbol from memory.

For each example in each doc surface, list its imported symbols, then prove each
one exists in the package's public surface:

```bash
cat packages/<pkg>/package.json | jq '{name, main, module, types, exports, bin}'
cat packages/<pkg>/src/index.ts
grep -rn '^export' packages/<pkg>/src/index.ts
```

If the package is built, the emitted types are the authority on what consumers
can actually import:

```bash
cat packages/<pkg>/dist/index.d.ts | grep -E '^(export|declare)'
```

Then check each symbol used in the docs:

```bash
grep -rn 'from .@scope/<pkg>.' --include='*.md' . | grep -v node_modules
grep -rn '\b<symbolName>\b' packages/<pkg>/src/index.ts packages/<pkg>/dist/index.d.ts
```

Verdicts, one per symbol:

| Finding | Action |
|---|---|
| Symbol is exported from the entry point | Keep the example |
| Symbol exists in source but is not re-exported | Rewrite the example to use the real public export; do not document an internal |
| Symbol was renamed | Update to the new name everywhere it appears, including doc comments |
| Symbol does not exist at all | Delete or rewrite the example, and list it in the report as an invented reference that was removed |

The same rule applies to the deep import paths, the subpath `exports` map, and
the type-only imports. If `exports` has no matching subpath, the documented
import does not work regardless of whether the symbol exists.

### Step 3: Verify every CLI example against real `--help` output

Run the command. Do not paraphrase what the flags probably are.

```bash
pnpm --filter <pkg> build
node packages/<pkg>/dist/cli.js --help
node packages/<pkg>/dist/cli.js <subcommand> --help
```

Where the repo exposes the binary through a script or a linked bin, use that
instead, discovered from `package.json` rather than assumed:

```bash
cat packages/<pkg>/package.json | jq '.bin, .scripts'
pnpm --filter <pkg> exec <bin> --help
```

Capture the output to a scratch file and diff it against what the docs claim:

```bash
mkdir -p .docs-sync
node packages/<pkg>/dist/cli.js --help > .docs-sync/help.txt 2>&1; echo "exit=$?"
grep -nE '^\s+-{1,2}[a-zA-Z]' .docs-sync/help.txt
grep -rnE '^\s*(\$ )?<bin> ' --include='*.md' . | grep -v node_modules
```

`.docs-sync/` is scratch. Never stage it.

Reconcile in this direction: `--help` is the source of truth for flags and
subcommands, because it is what the user's terminal prints. If the docs describe
a better interface than the code has, that is a code change to propose, not a
doc change to write. Report it in the "needs a decision" list.

If the command cannot be built or run, say so and mark every CLI example
unverified in the report. Do not fall back to memory.

### Step 4: Sweep for dead links

Relative links first, since those break silently on every file move:

```bash
grep -rnoE '\]\(([^)]+)\)' --include='*.md' . | grep -v node_modules | grep -vE 'https?://'
```

For each relative target, resolve it from the file that contains it and check
the file exists. For a link with an anchor, check the heading exists too:

```bash
test -f apps/docs/guide/<page>.md && echo present || echo MISSING
grep -nE '^#{1,6} ' apps/docs/guide/<page>.md
```

Then the VitePress sidebar and nav, which link by route rather than by path and
so are missed by a plain file check:

```bash
grep -nE "link:|text:" apps/docs/.vitepress/config.ts
```

Every sidebar `link` must resolve to a real page file, and every guide page
should be reachable from the sidebar. Report orphan pages and dangling entries
as two separate lists.

External links last:

```bash
grep -rnoE 'https?://[^)"[:space:]]+' --include='*.md' . | grep -v node_modules | sort -u -t: -k3 | head -50
curl -s -o /dev/null -w '%{http_code} %{url_effective}\n' -L --max-time 10 <url>
```

Treat 200 and 3xx-to-200 as alive, 404 and 410 as dead, and anything else
(timeout, 403 from a bot wall, network refused) as unverified rather than dead.

The reporting rule matters more than the sweep. A dead link to a guide means
either the guide moved or the guide was deleted. Report which, with the target
and the referring `file:line`. Do not delete the surrounding section to make the
link problem disappear; that destroys content to fix a reference.

| Dead link case | Action |
|---|---|
| Target moved, new location found | Update the link, note the move in the report |
| Target deleted, content lives elsewhere | Repoint to the surviving page |
| Target deleted, content is gone | Report it, leave the section, ask before removing |
| Feature genuinely removed from the product | Remove the reference and say so explicitly in the report |
| External link 404 | Report the URL and the referring line; do not invent a replacement URL |

### Step 5: Reconcile versions and commands

Node version, package manager version, install commands and script names must
agree everywhere they appear. Gather every side before changing any of them:

```bash
cat package.json | jq '{packageManager, engines, scripts}'
cat .nvmrc .node-version 2>/dev/null
grep -rnE 'node-version|pnpm/action-setup|version:' .github/workflows/
grep -rniE 'node ?(v)?[0-9]{2}|nvm|volta|pnpm@|npm install|yarn add' README.md CONTRIBUTING.md
```

Build a table with one row per claim and one column per place it appears:

| Claim | package.json | .nvmrc | CI workflow | README | CONTRIBUTING | Agrees |
|---|---|---|---|---|---|---|
| Node version | `engines.node` | file contents | `node-version` | line n | line n | yes/no |
| Package manager | `packageManager` | - | setup step | line n | line n | yes/no |
| Install command | derived from lock file | - | install step | line n | line n | yes/no |
| Script names | `scripts` keys | - | run steps | line n | line n | yes/no |

Resolution rules:

- `package.json` `engines` and `packageManager` plus the lock file are the
  source of truth for what the repo actually requires.
- CI is the source of truth for what is actually exercised. If CI and `engines`
  disagree, that is a real inconsistency to report, not something to average.
- Detect the package manager from the lock file, never from the prose in the
  README that may itself be the stale thing.

| Lock file | Install | Run |
|---|---|---|
| `pnpm-lock.yaml` | `pnpm install` | `pnpm <script>` |
| `package-lock.json` | `npm install` | `npm run <script>` |
| `yarn.lock` | `yarn install` | `yarn <script>` |
| `bun.lockb` or `bun.lock` | `bun install` | `bun run <script>` |

Report every disagreement with the file and the line number for each side, so
the reader can see both halves without opening anything.

### Step 6: Deduplicate toward the guide

A README is a quickstart. It says what the package is, how to install it, one
minimal working example, and where to read more. It does not paste an
implementation, and it does not restate the guide.

| Content | Belongs in |
|---|---|
| One-line description, install, minimal usage | README |
| Full API reference, options tables, edge cases | the guide under `apps/docs/` |
| Implementation walk-throughs and design rationale | the guide |
| Contribution and dev-build steps | CONTRIBUTING, linked from the README |

When the same content exists in two places, the guide is the source and the
copy becomes a link. Find the duplicates before deciding:

```bash
grep -rn '^#\{1,3\} ' --include='*.md' . | grep -v node_modules
```

Rules for the replacement:

- Replace the pasted block with one sentence plus a link to the guide section.
- Verify the link and its anchor exist, per Step 4, before removing the copy.
- Never delete the copy when there is no guide page holding that content.
  Move it to the guide first, or report it and leave it.
- If the README shrinks, check whether anything else linked to a heading inside
  the removed section and repoint those links in the same change.

### Step 7: Apply the house copy rules to everything touched

Every line this skill writes or rewrites obeys these, and every file it reads
is checked against them:

| Rule | Check |
|---|---|
| No emoji anywhere | `grep -rnP '[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]' --include='*.md' .` |
| Em-dashes only where they genuinely help | `grep -rn '—' --include='*.md' .` then reduce to commas, colons or full stops |
| No secrets, tokens or credentials in examples | Use obvious placeholders, never a real-looking key |
| No real domains | Use `example.com` |
| No example that prints a secret | No `console.log(token)`, no `echo $API_KEY`, no logging a decoded payload |
| No internal or abandoned tool names | Grep the name across all surfaces, including CLI help text, and remove every hit |
| No model names or AI identifiers | Not in docs, comments, help text or examples |

Removing a tool name is a whole-repo sweep, not a README edit. When asked to
remove all mentions of something, check every surface from the Step 1 inventory
plus the source, because the help text and the doc comments are the ones that
get missed:

```bash
grep -rni '<toolname>' --include='*.md' --include='*.ts' --include='*.json' . | grep -v node_modules
```

For the "no example prints a secret" rule, rewrite rather than delete. An
example showing a secret being logged becomes one showing it being used without
being printed, so the example still teaches the API.

### Step 8: Conform machine-readable files to their spec

Where a file follows a published specification, read the spec before writing the
file. Do not infer the format from the filename or from memory.

| File | Spec | Read before writing |
|---|---|---|
| `llms.txt` | llmstxt.org | the current spec page, including the exact filename |
| `llms-full.txt` | llmstxt.org | same |
| `package.json` `exports` | Node resolution docs | subpath and condition ordering |
| VitePress config | VitePress docs | sidebar and nav shape for the installed major version |

Verify the file name against the spec, not against what is already in the repo.
A file already committed under the wrong name is drift, and renaming it means
updating every link to it found in Step 4.

For `llms.txt` specifically, check the required shape: a single H1 title, an
optional blockquote summary, then link sections. Every link in it is subject to
the Step 4 sweep like any other link.

### Step 9: Report changes and unresolved drift separately

Two lists. Never merge them, because the second is the one that needs a human.

```markdown
## Docs sync

Surfaces inventoried: <n>. Files changed: <n>.

### Changed

| File | Change | Verified against |
|---|---|---|
| packages/x/README.md | `formatDate` example replaced with `formatTimestamp` | packages/x/src/index.ts:14 |
| apps/docs/.vitepress/config.ts | sidebar link `/guide/advanced-usage` removed | file does not exist |
| CONTRIBUTING.md | Node 18 to Node 22 | package.json engines:8, .github/workflows/ci.yml:21 |

### Found, not fixed, needs a decision

| Location | Drift | Why it was not fixed |
|---|---|---|
| README.md:40 | links to `guide/examples.md`, deleted in an earlier change | Content is gone; deleting the section would lose the explanation. Restore the page or drop the section? |
| docs/guide/cli.md:22 | documents `--json`, which `--help` does not list | Docs describe a better interface than the code has. Code change or doc change? |
```

Rules for the report:

- Every "Changed" row names the file that proved the change correct. A row with
  no verification source means the change was written from memory; go back to
  Step 2 or Step 3.
- Every dead link found appears in one of the two lists. None is silently
  dropped, and none is resolved by deleting the section around it.
- CLI examples that could not be verified because the binary would not build are
  listed as unverified, not as correct.
- Do not claim the docs are in sync without this block. Route the repo's own
  checks (`lint`, `build`, and the docs build if one exists) through the `verify`
  skill before saying so.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing an example that imports a symbol the package does not export | Read the entry point or `dist/*.d.ts` and confirm every imported symbol before writing the line |
| Documenting a symbol that exists in `src/` but is not re-exported | Only public exports go in docs; internals are not a public API |
| Writing CLI flags and examples from memory | Run `<bin> --help`, capture the output, diff the docs against it |
| Documenting a flag the CLI does not have because the docs describe a nicer interface | Report it as a code-or-docs decision; do not write flags the binary lacks |
| Deleting a section to make a dead link go away | Report the dead link with the target and the referring `file:line`, and ask |
| Inventing a replacement URL for a dead external link | Report the 404 and the referring line; a guessed URL is new drift |
| Pasting an implementation into a README | READMEs are quickstarts; move the detail to the guide and link to it |
| Updating a README or guide page without updating the VitePress sidebar config | Sidebar and nav entries are part of the same change; check every `link:` resolves |
| Fixing the README while the doc comments and help text keep the old name | A rename is a whole-repo sweep: markdown, TSDoc, help text, `llms.txt` |
| Editing before the inventory exists | Enumerate every surface in one pass and present it first |
| Assuming the package manager from the README prose | Detect it from the lock file; the prose may be the stale thing |
| Averaging two disagreeing Node versions into one guess | `engines` plus CI are the sources; report the disagreement with both `file:line`s |
| Deleting a duplicate before the guide holds that content | Move it to the guide first, verify the anchor, then replace the copy with a link |
| Writing `llms.txt` from memory of the format | Read llmstxt.org first, including the exact filename it specifies |
| Leaving an example that logs a token or a decoded secret | Rewrite it to use the value without printing it |
| Leaving em-dashes and emoji in rewritten prose | Sweep both before reporting; em-dashes only where they genuinely help |
| Reporting "docs updated" with no per-file list | Emit the two-table report block, changed and needs-a-decision |
