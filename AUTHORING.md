# Authoring guide

Shared reference for everything in this repo. Read this before writing or
editing a skill, rule, agent or template.

---

## Layout

The repository is a plugin marketplace with one plugin. Everything both
agents load lives in `plugins/jz/`: `skills/`, `rules/`, `agents/` and
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
`confirm-remote-writes` guard. Anything that must hold on every
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
instruction (`verify`, `implement`), and keep it short.

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

- Under 300 lines; `validate.sh` fails a longer one. Aim near 150: the
  whole file is read every time the skill loads, so every line is paid for
  on every use.
- Numbered steps with real commands in fenced `bash` blocks.
- No `$ARGUMENTS` and no `$` followed by digits, such as awk's `$2` or `$0`:
  Claude Code replaces them with the skill's arguments on load, counting
  from `$0`. Use `${2}` in shell and a `-v` variable or a regex in awk;
  `validate.sh` fails the file. A backslash escape is no fix, since Codex
  reads the file as written.
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
| Never stage `.claude/`, `docs/plans/` or `.plans/` | `no-claude-artifacts` guard, PreToolUse: an add or commit is denied while one is unignored, modified or staged |
| Ask before a `gh pr create` without `--draft`, `gh pr ready` and any force push not pinned with `--force-with-lease=<branch>:<sha>` | `confirm-remote-writes` guard, PreToolUse |
| Never push to a default branch and never merge a pull request; the owner merges on GitHub | `protect-default-branches` guard, PreToolUse |
| Commit, push and open PRs through the `pr` skill | `require-pr-skill` guard, PreToolUse, from the transcript the payload names; a host whose payload carries no transcript path is not gated |
| Rebase, never merge a branch in; a checkout may fast-forward with `--ff-only` | `rebase-not-merge` guard, PreToolUse |
| No secret, token or credential reaches a remote | `scan-secrets-before-push` guard, PreToolUse, through betterleaks or gitleaks when installed |
| Rules are read in every session | `load-house-rules.sh`, SessionStart |
| Project instruction files are read at session start | `load-project-rules.sh`, SessionStart |
| Skills, rules, agents, templates and manifests are well formed | `validate.sh`, in CI |
| A SKILL.md stays under 300 lines | `validate.sh`, in CI |
| Open as draft, mark ready only after the gate is green | `pr` Ready section: ready is flipped only when a go-ahead or brief named it, `verify` passed on the pushed head and no check has failed; no hook yet |
| A factory job moves only on evidence, and never by a session's word | `skills/factory/scripts/job`: the only writer of `job.json`, which refuses a stage move its header lines and head commit do not support |
| A branch cannot edit the checks, the criteria or the spec it is judged by, or files outside its step's Owns | `skills/factory/scripts/gate`: reads the spec and `factory.json` from the base ref and fails a protected path edit or a file outside Owns |
| The factory never merges into a default branch | `skills/factory/scripts/job merge` refuses a protected base; the `protect-default-branches` guard denies a merge an agent types |
| The factory scripts keep doing the above | `skills/factory/scripts/test-factory.sh`, run by `make test` |
| `handsfree` forms its own pick before reading a recommendation, and never answers a sign-off, a merge or a new dependency | nothing; the `handsfree` skill states it, and the decision log records every pick |
| Model tier matches the job | nothing; `models.md` describes it |
| Done means a behaviour level, not only a green script | nothing; the `behaviour` row in `verify` Step 7 names the level the runs support, and `coordinate` Step 5 checks it against the behaviour target in the brief |
| A throwaway worktree is removed only after the last step that runs in it | `validate.sh`: a skill or template that names the directory variable after its `git worktree remove` fails |
| A skill or template carries no `$ARGUMENTS` or `$<digits>` placeholder that Claude Code would fill with the skill's arguments | `validate.sh`: a SKILL.md or template with one fails, naming the line |
| Every requirement has an acceptance criterion whose check proves it, seen failing before the build, and every criterion has a row in the verify block | nothing; `criteria` Step 3 asks for the check or sends the requirement back to `grill`, `criteria` Step 4 runs each check before sign-off, `implement` stops a step whose requirement has no criterion, `coordinate` Step 3 holds back a step whose requirement has no criterion and Step 5 sends a missing row back, `verify` Step 7 reads `not run` for a criterion without a run, and the review brief re-runs each command |
| Wait for the owner only at a lettered fork, a remote write that asks, or the owner's action; everything else proceeds and is reported | `confirm-remote-writes` guard for the remote writes; nothing for the rest, `parallelism.md` states it |
| Prose rules 7 and 8, no emoji or model name in commit or PR text | nothing in a hook; `validate.sh` for emoji in this repo's files |
| Prose rules 1 to 6 and 9 to 14 | nothing; `prose.md` numbers them so a steer cites one, and `improve` turns a repeated steer into the next check |

A repository lists its restricted words as bullets under a `## Restricted
words` heading in `AGENTS.md` or `CLAUDE.md`, one word per bullet.

## House facts

The defaults this setup assumes. Skills must take these as given rather than
asking about them each time.

### The workflow

`grill` writes a spec in `docs/specs/<slug>.md`: requirements (observable
outcomes, `R1`, `R2`), decisions, and vertical-slice steps. `criteria` adds a
Criteria section, one or more checks per requirement (`C1.1`), each a test,
command, drive or inspection, run once to see it fail, then signed off by
the owner. `implement` builds a step at a time against them, `verify`
reports them, `pr` structures the PR body by requirement, and `review`
re-runs them. `coordinate` drives the steps across sessions with the owner
merging each pull request. `factory` drives the eligible steps unattended
into `factory/<slug>` and leaves one final pull request to the owner.
`handsfree` wraps any of these and answers the design questions in the
owner's place, and `intake` uses it to turn a named bug or request into a
spec for one approval. A skill that reads a spec reads its status line
first: work starts only once it says `criteria signed off`.

A step also carries `Risk` and `Surfaces` lines, which route the factory's
reviewers. The factory's state lives under `docs/plans/factory-<slug>/` and
is written only by its `job` script, which also redraws
`dashboard.html` there after every command; `handsfree` keeps its rounds and its
decision log under `docs/plans/handsfree-<slug>/`. Neither is committed.

### Verification recipes

A repository that can be driven end to end keeps the recipe in a
`VERIFICATION.md` next to its `AGENTS.md`, or next to a package's manifest in a
monorepo: Launch, Doctor, Drive, Evidence, Cleanup, and a map from each
criterion to the drive step that proves it. `verify` reads the nearest one
upward from the changed paths and cites its Drive section on the `behaviour`
row. A criterion whose check drives the system cites one of its Drive steps,
and the step that adds the criterion adds the Drive step, so the recipe stays the one place the drive commands live. It is a
plain file a person or Codex runs the same way, never a skill
under `.claude/`, which the `no-claude-artifacts` guard keeps out of git. A
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
