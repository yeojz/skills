# agent-config

Portable coding-agent setup: skills, always-on rules, review agents, hooks and
templates. Clone it on any machine, run `./install.sh`, and they all behave the
same.

Everything is symlinked into `~/.claude`, so `git pull` here updates every
machine without reinstalling.

The skills and hooks target Claude Code, which owns the `SKILL.md` format and
the hook contract. The rules, agent personas and templates are plain markdown
with nothing Claude-specific in them, so they carry over to any agent that
reads an instruction file, Codex included. See Using this with Codex below.

---

## Install

```bash
git clone <this repo> ~/code/agent-config
cd ~/code/agent-config
./install.sh
```

Then start a new Claude Code session so the rules and hooks load.

| Command | Effect |
|---|---|
| `./install.sh` | Install or refresh every symlink and merge the settings entries |
| `./install.sh --dry-run` | Print what would change, touch nothing |
| `./install.sh --uninstall` | Remove this repo's symlinks and settings entries |

The installer never overwrites a file it did not create. `settings.json` is
backed up to `~/.claude/.install-backup/` before every merge, and only this
repo's own hook and permission entries are added or removed.

Set `CLAUDE_CONFIG_DIR` to install somewhere other than `~/.claude`.

---

## What is in here

```
skills/      loaded on demand when a request matches the description
rules/       always on, injected into every session
agents/      read-only review personas the audit skill fans out to
hooks/       shell scripts plus the settings.json fragment that wires them up
templates/   plan, handoff and PR body shapes
```

### Skills

| Skill | Use it for |
|---|---|
| `verify` | The completion gate. Runs the repo's own scripts and pastes real output before any done claim |
| `ship` | Branch, format, lint, verify, conventional commit, push, draft PR |
| `audit` | Read-only repo assessment that writes a prioritised plan file |
| `execute-plan` | Work a plan item by item with honest status and commit checkpoints |
| `deps-guard` | Advisories, action pinning, supply-chain settings, vetting a new dependency |
| `review` | Diff-scoped or PR-scoped review, plus the unresolved-comment sweep |
| `docs-sync` | Bring READMEs, guides and doc comments back in line with the code |
| `handoff` | Write a resumable handoff before context runs out |
| `coverage` | Raise coverage to threshold and prove it with the report |
| `naming` | Lettered naming options with trade-offs, then rename everywhere |
| `pr-desc` | Regenerate a PR body from the diff alone |
| `release` | Version PR, changeset, label gate, publish |

`verify` is the one the others depend on. It is what stops "done" from meaning
"probably done".

### Rules

Always-on and deliberately short, because they cost tokens in every session.

| File | Covers |
|---|---|
| `house-style.md` | TypeScript and general code style |
| `git-workflow.md` | Branching, commits, PR bodies, what never gets staged |
| `verification.md` | Evidence before assertions, root cause over workaround |
| `ui-conventions.md` | Icons, primitives, type scale, avoiding the generic AI look |
| `parallelism.md` | Fan independent work out to subagents by default |

### Hooks

Some rules are enforcement problems, and a rule can be ignored while a hook
cannot.

| Hook | Event | Effect |
|---|---|---|
| `no-claude-artifacts.sh` | PreToolUse on Bash | Blocks any staging or commit that would include `.claude/`, `docs/plans/` or `.plans/` |
| `load-project-rules.sh` | SessionStart | Surfaces `CLAUDE.md`, `AGENTS.md` and `CONTRIBUTING.md` at session start |

The installer also adds `gh pr create`, `gh pr merge` and force-push to the
`permissions.ask` list, so remote writes need a confirmation.

The hooks have their own regression suite, which builds a throwaway repo and
checks the exit code for each case. Exit 2 denies the tool call, exit 0 allows
it.

```bash
./hooks/test-hooks.sh
```

`./validate.sh` runs it, along with format checks over every skill, rule, agent
and template. Run it before committing a change here.

---

## Using this with Codex

Claude Code reads `~/.claude/rules` on its own. Codex and most other agents read
an instruction file in the repository instead, so the rules have to be written
into one.

```bash
./make-agents-md.sh ~/code/some-project
```

That writes the five rule files into `AGENTS.md` in the target repo, between
delimiter comments. Re-running replaces only the generated block, so anything
you wrote by hand around it survives. Edit the rules here and re-run to update.

The rest of the repo carries over by hand. The agent personas under `agents/`
are ordinary prompts, and the templates are ordinary markdown. A `SKILL.md` body
is a readable procedure, so pointing another agent at one works even though only
Claude Code loads them automatically.

---

## Working on this repo

Read [AUTHORING.md](AUTHORING.md) before adding or editing anything. It defines
the skill and eval formats and the house facts every skill assumes.

Each skill carries `evals/evals.json` in the shape `claude plugin eval` expects,
so behaviour changes can be checked rather than guessed at.
