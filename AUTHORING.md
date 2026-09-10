# Authoring guide

Shared reference for everything in this repo. Read this before writing or
editing a skill, rule, agent or template.

---

## Skill format

Every skill is a directory under `skills/` containing `SKILL.md` and
`evals/evals.json`.

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

Rules for the body:

- Numbered steps with real commands in fenced `bash` blocks.
- Use tables for lookup data (lock file to package manager, flag to meaning).
- State what to do when a step does not apply, rather than leaving it open.
- Bound every retry loop with a number and say what to do when it is exhausted.
- No emoji.
- Sparing em-dashes.

## Eval format

`evals/evals.json` matches the shape already used by the `git-commit` skill:

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

### Git and PR conventions

- Branch before editing. Never edit on `main`.
- Do not create a git worktree unless explicitly asked.
- The default branch is `main`, never `master`.
- Conventional Commits for commit subjects, branch names and PR titles.
- Branches are `<type>/<scope>-<description>`.
- PRs squash-merge, so the PR title becomes the commit on `main`.
- PR body is summary, trade-offs, follow-ups. No test plan. No chat narrative.
  No release-type opinions, that decision belongs to the repo owner.
- Open PRs as drafts unless told otherwise.
- Commits list the repo owner as author. Attribution follows settings.json:
  honour `includeCoAuthoredBy` and `attribution`, and add a `Co-Authored-By`
  trailer only when they ask for one. No Claude session links anywhere in
  commit messages or PR bodies.
- Never stage `.claude/`, `docs/plans/`, or `.plans/`.
- Never use `--no-verify`.

### Writing and docs

- READMEs are succinct quickstarts. Link to the guide, do not paste
  implementations.
- No auto-generated CHANGELOG or migration guide unless asked.
- No emoji. Em-dashes only where they genuinely help.
- Never put model names or AI identifiers in code, comments, docs or PR text.
- No secrets, real domains or credentials in examples. Use `example.com`.

### Code style

- No `any`. No `enum`, use string literal unions. Prefer `type` over `interface`.
- Dependency injection over globals. No global variables.
- Braces on `if` statements.
- Comments are minimal and explain why, never what.
- Readable test values, prefer strings over byte arrays.
- No deprecated aliases left behind for compatibility unless the package is
  already published and the change is breaking.
- Do not use non-public APIs from dependencies.
- Prefer no new dependency. If one is needed, check maintenance status, last
  release, and license compatibility with MIT or ISC first.

### Working style

- Fan independent work out to subagents by default.
- Present design and naming decisions as lettered options with a recommendation,
  rather than implementing straight away.
- Plans live in `docs/plans/YYYY-MM-DD-HHMM-<slug>.md` and are not committed.
- Root-cause a failure. Never work around a failing test to make a suite green.
- Never claim done, fixed or passing without pasting the command output that
  proves it.
