# Authoring guide

Shared reference for everything in this repo. Read this before writing or
editing a skill, rule, agent or template.

---

## Skill format

Every skill is a directory under `skills/` containing `SKILL.md` and
`evals/evals.json`. A skill that fills in a document also carries its
`template.md` in the same directory.

`SKILL.md` starts with YAML frontmatter, exactly two keys:

```markdown
---
name: <kebab-case, matches the directory name>
description: Use when <situation>. Triggers on requests like "<phrase>", "<phrase>", or when <condition>.
---
```

The `description` is the only thing the model sees before deciding to load the
skill, so it must name concrete trigger phrases drawn from real usage.

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
- Use tables for lookup data (lock file to package manager, flag to meaning).
- State what to do when a step does not apply, rather than leaving it open.
- Bound every retry loop with a number and say what to do when it is exhausted.
- No emoji.
- Sparing em-dashes.

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

## Rule format

A rule file is plain markdown under `rules/`: one H1, a flat list of
imperative lines, no frontmatter, under 80 lines. Rules are always on and cost
tokens in every session, so a line that a skill already enforces belongs in the
skill, not here.

## Agent format

An agent is a markdown file under `agents/` with frontmatter carrying `name`,
`description` and `tools`. Agents are read-only reviewers, so `tools` must not
include `Edit` or `Write`. Findings use an id prefix per persona, such as `PE`,
`SEC` or `TE`, so a plan can trace each item back to the lens that raised it.

## Template format

A template is plain markdown with no frontmatter, saved as `template.md` inside
the skill directory that fills it in. There is no top-level `templates/`.

---

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
