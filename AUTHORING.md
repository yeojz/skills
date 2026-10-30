# Authoring guide

Shared reference for everything in this repo. Read this before writing or
editing a skill, rule, agent or template.

---

## Layout

The repository is a plugin marketplace. Everything an agent loads lives in
the one plugin under `plugins/jz/`: `skills/`, `rules/`, `agents/` and
`hooks/`. The marketplace manifests sit at the repository root,
`.claude-plugin/marketplace.json` for Claude Code and
`.agents/plugins/marketplace.json` for Codex, and both point at that
directory. For Claude Code the marketplace entry is the plugin's manifest, so
there is no `plugins/jz/.claude-plugin/plugin.json`; Codex reads the portable
`plugins/jz/plugin.json`. Neither pins a version, so an install tracks
commits.

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
instruction (`verify`, `execute-plan`), and keep it short.

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
| Rebase onto the default branch, never merge it in | `rebase-not-merge.sh`, PreToolUse |
| No secret, token or credential reaches a remote | `scan-secrets-before-push.sh`, PreToolUse, through betterleaks or gitleaks when installed |
| No emoji, attribution trailer, session link or model slug in commit or PR text | `no-restricted-words.sh`, PreToolUse |
| A repository's own restricted words stay out of its PR text | `no-restricted-words.sh`, reading `## Restricted words` in `AGENTS.md` or `CLAUDE.md` |
| Rules are read in every session | `load-house-rules.sh`, SessionStart |
| Project instruction files are read at session start | `load-project-rules.sh`, SessionStart |
| Skills, rules, agents, templates and manifests are well formed | `validate.sh`, in CI |
| Open as draft, mark ready only after the gate is green | `ship` steps 11 and 12: the pushed head is gated on a clean detached checkout, and ready is flipped only when a go-ahead or brief named it; no hook yet |
| Model tier matches the job | nothing; `models.md` describes it |

A repository lists its restricted words as bullets under a `## Restricted
words` heading in `AGENTS.md` or `CLAUDE.md`, one word per bullet.

## House facts

The defaults this setup assumes. Skills must take these as given rather than
asking about them each time.

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
