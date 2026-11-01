# Authoring guide

Shared reference for everything in this repo. Read this before writing or
editing a skill, rule, agent or template.

---

## Layout

The repository is a plugin marketplace with two plugins. Everything both
agents load lives in `plugins/jz/`: `skills/`, `rules/`, `agents/` and
`hooks/`. The marketplace manifests sit at the repository root,
`.claude-plugin/marketplace.json` for Claude Code and
`.agents/plugins/marketplace.json` for Codex, and both point at that
directory. For Claude Code the marketplace entry is the plugin's manifest, so
there is no `plugins/jz/.claude-plugin/plugin.json`; Codex reads the portable
`plugins/jz/plugin.json`. Neither pins a version, so an install tracks
commits.

`plugins/jzc/` holds what exists only for Claude Code: mods written against
its function hooks API (see Mod format below). Its manifest is
`plugins/jzc/.claude-plugin/plugin.json`, and only the Claude Code marketplace
lists it. Codex does not run Claude Code mods, so `jzc` stays out of
`.agents/plugins/marketplace.json`, and `validate.sh` fails if it appears
there. Anything that an agent other than Claude Code could use belongs in
`jz`; `jzc` never holds a skill, a rule or an agent.

A plugin cannot ship always-on instruction files or permission entries. The
rules reach a session through the `load-house-rules.sh` SessionStart hook,
and the confirmations for remote writes come from the
`confirm-remote-writes.sh` PreToolUse hook. Anything that must hold on every
run belongs in a hook, not in prose.

## Skill format

Every skill is a directory under `plugins/jz/skills/` containing `SKILL.md` and
`evals/evals.json`. A skill that fills in a document also carries its
`template.md` in the same directory; one that fills more than one kind of
document names them `template-<kind>.md`.

Write a skill for a judgment call. Anything `validate.sh` or a hook can check
mechanically belongs there instead: a check never skips a step and costs no
context. Installed as a plugin, a skill is invoked as `/jz:<name>`.

`SKILL.md` starts with YAML frontmatter, exactly two keys:

```markdown
---
name: <kebab-case, matches the directory name>
description: Use when <situation>. Triggers on requests like "<phrase>", "<phrase>", or when <condition>.
---
```

Name the skill for the action it performs, verb first where that reads as an
instruction (`verify`, `execute`), and keep it short.

The `description` is the only thing the model sees before deciding to load the
skill, so it must name concrete trigger phrases drawn from real usage: the
requests, symptoms and error strings a user actually types, plus their
synonyms. It says when to use the skill, never what the skill does. A
description that summarises the workflow becomes a shortcut: the model follows
the summary instead of loading the body. A skill whose body called for two
reviews got one, because its description said "code review between tasks".

Keep the whole frontmatter under 1024 characters and aim the description near
500. `validate.sh` does not check this, so measure it yourself:

```bash
awk 'NR==1{next} /^---$/{exit} {print}' skills/<name>/SKILL.md | wc -c
```

The body follows this shape:

```markdown
# <name>

## Overview

One or two sentences. What the skill does and what it guarantees.

## Workflow

### Step 1: <imperative>
### Step 2: <imperative>
...

## Common Mistakes

| Mistake | Fix |
|---------|-----|
```

A skill with more than one way of running may add `## Modes` between Overview
and Workflow, with a table naming each mode and one section per mode after it.

Rules for the body:

- Numbered steps with real commands in fenced `bash` blocks.
- A diagram only for a decision the steps do not make obvious. Linear flow is
  a numbered list.
- One complete example in the language the repo uses, not one per language.
- Use tables for lookup data (lock file to package manager, flag to meaning).
- State what to do when a step does not apply, rather than leaving it open.
- Bound every retry loop with a number and say what to do when it is exhausted.
- No emoji.
- Sparing em-dashes.

A supporting file sits beside `SKILL.md` when it is a reusable script or
reference material over about 100 lines; a pattern under about 50 lines stays
inline. Point to it from `SKILL.md` by relative path, for example
`see reference.md`. Never use an `@path` reference: it force-loads the file
into every session that loads the skill.

## Eval format

`evals/evals.json` is a transcript-review checklist: prompts a user would type,
paired with behaviour that can be checked by reading the transcript.
`validate.sh` enforces the structure.

```json
{
  "skill_name": "<name>",
  "evals": [
    {
      "id": 1,
      "prompt": "<what a user would type>",
      "expected_output": "<prose description of correct behaviour>",
      "files": [],
      "expectations": [
        "<one observable behaviour per line>"
      ]
    }
  ]
}
```

Three to five evals per skill. Each `expectations` entry must be checkable by
reading a transcript.

Evals are the test, so write them before the skill. Run each prompt without the
skill and note where the model went wrong; each `expectations` line then
asserts the observable behaviour that corrects one of those failures. An
expectation that would also pass without the skill proves nothing.

## Rule format

A rule file is plain markdown under `plugins/jz/rules/`: one H1, a flat list of
imperative lines, no frontmatter, under 80 lines. Rules are always on and cost
tokens in every session, so a line that a skill already enforces belongs in the
skill, not here. `models.md` is the one rule that names models; it reaches a
session through the hook only and `make-agents-md.sh` never writes it into a
repository.

## Agent format

An agent is a markdown file under `plugins/jz/agents/` with frontmatter carrying `name`,
`description` and `tools`. Agents are read-only reviewers, so `tools` must not
include `Edit` or `Write`. Installed as a plugin, an agent is the
subagent type `jz:<name>`. Findings use an id prefix per persona, such as `PE`,
`SEC` or `TE`, so a plan can trace each item back to the lens that raised it.

## Mod format

A mod is a change to Claude Code's own interface or behaviour: a pane, a
band, a slash command, a hook on an event the classic hooks do not see. It is
a TypeScript module on the function hooks API, loaded by the `jzc` plugin.
The `plugin-authoring` skill that ships with Claude Code carries the API, the
types and the test kit; read it before writing one.

A plugin loads one hooks module, so `plugins/jzc/hooks/hooks.json` names
`./register.tsx` and nothing else, and that file only imports each mod's
`register` from `hooks/mods/<mod>.tsx` and calls it. Adding a mod is one new
file under `hooks/mods/`, its test beside it as `hooks/mods/<mod>.test.tsx`,
and one import line in `register.tsx`.

Rules for a mod:

- Strict TypeScript: no `any`, no `enum`, `type` over `interface`.
  `validate.sh` greps for all three. The one `interface` allowed is
  `PluginState` in the contract, which the API merges by declaration.
- Every `$.state` value is declared in `plugins/jzc/types/index.d.ts` under
  the plugin's name, `jzc`, with the key prefixed by the mod's name
  (`'skills-used.uses'`), so two mods never share a key. The atom reads
  `atom({ plugin: 'jzc', key: '<mod>.<name>' } as const, ...)`. Give it a
  `shape` tag and change the tag when the value's fields change: a reload
  keeps what the earlier code stored.
- A slash command carries the `jzc-` prefix in its registered name
  (`jzc-skills-used`). The engine namespaces a plugin's skills and agents as
  `jzc:<name>` but registers a command under the bare name it is given, so a
  bare `skills-used` would collide with any other plugin's.
- A pane's `requestId` is the mod's name.
- Never name a model in a mod or its docs.
- One test file per mod, driving the plugin through `claude-code/testing`
  on every surface (`terminal`, `desktop`, `vscode`, `mobile`), with a case
  that seeds a value an earlier version stored so the `shape` guard is
  proven.

Checks, all of which `make validate` runs when the tool is present:

```bash
claude plugin validate plugins/jzc
```

```bash
claude plugin test plugins/jzc
```

```bash
tsc -p plugins/jzc
```

The type check reads the API declarations the engine lays beside the plugin
at `plugins/jzc/.claude-plugin/types/`, which is gitignored and written only
when an interactive session loads the plugin from this folder:

```bash
CLAUDE_CODE_PLUGIN_DIRS="$PWD/plugins/jzc" claude
```

Until that folder exists `validate.sh` notes the type check as skipped, so CI
runs the validator and the tests but not `tsc`. The headless check that a
command is served is:

```bash
claude -p --plugin-dir "$PWD/plugins/jzc" '/jzc-skills-used'
```

## Template format

A template is plain markdown with no frontmatter, saved as `template.md`, or
`template-<kind>.md` when there are several, inside the skill directory that
fills it in. There is no top-level `templates/`.

---

## Enforcement

A rule that nothing enforces is a correction waiting to recur. This table
pairs each rule that has recurred with what now enforces it. A row whose
enforcement is "nothing" and whose correction comes back is the next hook,
lint or check to write, at the highest level that holds: structure, then a
check that fails, then a test, with prose last.

| Rule | Enforced by |
|---|---|
| Never stage `.claude/`, `docs/plans/` or `.plans/` | `no-claude-artifacts.sh`, PreToolUse |
| Ask before a `gh pr create` without `--draft`, `gh pr ready`, `gh pr merge` and any force push | `confirm-remote-writes.sh`, PreToolUse |
| Commit, push and open PRs through the `pr` skill | `require-pr-skill.sh`, PreToolUse, from the transcript the payload names; a host whose payload carries no transcript path is not gated |
| Rebase onto the default branch, never merge it in; the default branch's own checkout may fast-forward | `rebase-not-merge.sh`, PreToolUse |
| No secret, token or credential reaches a remote | `scan-secrets-before-push.sh`, PreToolUse, through betterleaks or gitleaks when installed |
| No emoji, attribution trailer, session link or model slug in commit or PR text | `no-restricted-words.sh`, PreToolUse |
| A repository's own restricted words stay out of its PR text | `no-restricted-words.sh`, reading `## Restricted words` in `AGENTS.md` or `CLAUDE.md` |
| Rules are read in every session | `load-house-rules.sh`, SessionStart |
| Project instruction files are read at session start | `load-project-rules.sh`, SessionStart |
| Skills, rules, agents, templates and manifests are well formed | `validate.sh`, in CI |
| A mod plugin is listed for Claude Code only, its hooks module exists, its sources carry no `any`, `enum` or `interface`, its tests pass and it type-checks | `validate.sh`: manifests, the grep, `claude plugin test` and `tsc` when present |
| Open as draft, mark ready only after the gate is green | `pr` Ready section: ready is flipped only when a go-ahead or brief named it, `verify` passed on the pushed head and no check has failed; no hook yet |
| Model tier matches the job | nothing; `models.md` describes it |
| Done means a behaviour level, not only a green script | nothing; the `behaviour` row in `verify` Step 8 names the level the runs support, and `coordinate` Step 5 checks it against the level Done means named |
| A throwaway worktree is removed only after the last step that runs in it | `validate.sh`: a skill or template that names the directory variable after its `git worktree remove` fails |
| Every requirement has an eval whose check proves it, seen failing before the build, and every eval has a row in the verify block | nothing; `eval` Step 3 asks for the check or sends the requirement back to `grill`, `eval` Step 4 runs each check before sign-off, `execute` stops a step whose requirement has no eval, `coordinate` Step 3 treats a row without a list as not scoped and Step 5 sends a missing row back, `verify` Step 8 reads `not run` for a criterion without a run, and the review brief re-runs each command |
| Wait for the owner only at a lettered fork, a remote write that asks, or the owner's action; everything else proceeds and is reported | `confirm-remote-writes.sh` for the remote writes; nothing for the rest, `parallelism.md` states it |
| Prose rules 7 and 8, no emoji or model name in commit or PR text | `no-restricted-words.sh`, PreToolUse; `validate.sh` for emoji in this repo's files |
| Prose rules 1 to 6 and 9 to 14 | nothing; `prose.md` numbers them so a steer cites one, and `reflect` turns a repeated steer into the next check |

A repository lists its restricted words as bullets under a `## Restricted
words` heading in `AGENTS.md` or `CLAUDE.md`, one word per bullet.

## House facts

The defaults this setup assumes. Skills must take these as given rather than
asking about them each time.

### Verification recipes

A repository that can be driven end to end keeps the recipe in a
`VERIFICATION.md` next to its `AGENTS.md`, or next to a package's manifest in a
monorepo: Launch, Doctor, Drive, Evidence, Cleanup, and a map from each
acceptance to the drive step that proves it. `verify` reads the nearest one
upward from the changed paths and cites its Drive section on the `behaviour`
row. An eval whose check drives the system cites one of its Drive steps, and
the step that adds the eval adds the Drive step, so the recipe stays the one place the drive commands live. It is a
plain file a person or Codex runs the same way, never a skill
under `.claude/`, which the `no-claude-artifacts.sh` hook keeps out of git. A
recipe drives the system locally, against mocks or fixtures for anything
external, and carries no step that deploys to, logs in to or writes to a live
or shared environment; such a step is the owner's, taken when they ask.

### Stack

| Concern | Default |
|---|---|
| Language | TypeScript, strict, ESM first |
| Package manager | pnpm, detected from the lock file, never assumed |
| Monorepo | pnpm workspaces, `packages/`, `apps/`, `internal/` |
| Build | tsup |
| Test | Vitest, v8 coverage provider, not istanbul |
| Lint and format | Biome in newer repos, ESLint plus Prettier in older ones |
| CI | GitHub Actions |
| Runtimes tested | Node, plus Bun and Deno where the repo has those scripts |
| Docs site | VitePress |

Never invent a command. Read `package.json` scripts and run those. Coverage in a
workspace usually needs both a filter and a project, for example
`pnpm --filter <pkg> test:ci --project <project>`.

### Conventions

The git, PR, writing, code-style and working-style conventions live in
`rules/` and nowhere else; read those files rather than a restatement here.
Two facts no rule file carries:

- READMEs are succinct quickstarts. Link to the guide, do not paste
  implementations.
- Plans live in `docs/plans/YYYY-MM-DD-HHMM-<slug>.md` and are not committed.
