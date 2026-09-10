# agent-config

Portable coding-agent setup: skills, always-on rules, review agents and hooks.
Clone it on any machine, run `./install.sh`, and they all behave the same.

Everything is symlinked into `~/.claude`, so `git pull` here updates every
machine without reinstalling.

The hooks target Claude Code, which owns the hook contract. Skills are written
in the `SKILL.md` format that both Claude Code and Codex load. The rules, agent
personas and templates are plain markdown, so any agent that reads an
instruction file can use them. See Using this with Codex below.

---

## Install

Requirements: `bash`, `git` and `python3`. `shellcheck` is optional;
`validate.sh` uses it when present.

```bash
git clone <repository url> ~/code/agent-config
cd ~/code/agent-config
./install.sh
```

Then start a new Claude Code session so the rules and hooks load.

| Command | Effect |
|---|---|
| `./install.sh` | Install or refresh every symlink and merge the settings entries |
| `./install.sh --dry-run` | Print what would change, touch nothing |
| `./install.sh --uninstall` | Remove this repo's symlinks and settings entries |

The installer never overwrites a file it did not create. An existing file, or a
symlink that points somewhere else, is skipped and reported; only a dangling
link is replaced. `settings.json` is backed up to `~/.claude/.install-backup/`
before any merge that changes it, and only this repo's own hook and permission entries are
added or removed.

Set `CLAUDE_CONFIG_DIR` to install somewhere other than `~/.claude`. When
`~/.codex` exists (or `CODEX_HOME` points at one), skills and agents are linked
there too, aliased back to the same files in this repo.

---

## What is in here

```
skills/      loaded on demand when a request matches the description;
             a skill that fills in a template carries it as template.md
rules/       always on, injected into every session
agents/      four read-only review personas the audit skill fans out to
hooks/       shell scripts plus the settings.json fragment that wires them up
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
| `design-critique` | Judging, redesigning or fixing a UI visually; needs a browser automation tool |
| `docs-sync` | Bring READMEs, guides and doc comments back in line with the code |
| `handoff` | Write a resumable handoff before context runs out |
| `coverage` | Raise coverage to threshold and prove it with the report |
| `naming` | Lettered naming options with trade-offs, then rename everywhere |
| `pr-desc` | Regenerate a PR body from the diff alone |
| `release` | Version PR, changeset, label gate, publish |

`verify` is the one the others depend on. It is what stops "done" from meaning
"probably done".

`audit` fans out to the four personas under `agents/`: `principal-engineer`,
`security-engineer`, `test-engineer` and `technical-writer`.

### Rules

Always-on and deliberately short, because they cost tokens in every session.

| File | Covers |
|---|---|
| `house-style.md` | TypeScript and general code style |
| `git-workflow.md` | Branching, commits, PR bodies, what never gets staged |
| `verification.md` | Evidence before assertions, root cause over workaround |
| `ui-conventions.md` | Icons, primitives, type scale, the checks before a layout is done |
| `parallelism.md` | Fan independent work out to subagents by default |

### Hooks

Some rules are enforcement problems, and a rule can be ignored while a hook
cannot.

| Hook | Event | Effect |
|---|---|---|
| `no-claude-artifacts.sh` | PreToolUse on Bash | Blocks any staging or commit that would include `.claude/`, `docs/plans/` or `.plans/` |
| `load-project-rules.sh` | SessionStart | Surfaces `CLAUDE.md`, `AGENTS.md` and `CONTRIBUTING.md` at session start |

The installer also adds `gh pr create`, `gh pr merge` and force-push to the
`permissions.ask` list, so remote writes need a confirmation. The force-push
entries cover `--force`, `--force-with-lease` and `-f`, both directly after
`git push` and after a remote (`git push <remote> --force`), plus a `+refspec`.

The hooks have their own regression suite, which builds a throwaway repo and
checks the exit code for each case. Exit 2 denies the tool call, exit 0 allows
it.

```bash
./hooks/test-hooks.sh
```

`./validate.sh` runs it, along with format checks over every skill, rule, agent
and template, `bash -n` and `shellcheck` over every script, and a check that
every skill is listed in this README. Run it before committing a change here.

---

## Using this with Codex

Skills need no extra step. When `./install.sh` detects a Codex directory it
mirrors the Claude side there, linking `skills/*` into `~/.codex/skills` and
`agents/*.md` into `~/.codex/agents`; when it does not, it says so. Both are
symlinks back into this repo, so the two runtimes read one source of truth and
a `git pull` updates both.

Codex loads `~/.codex/skills/<name>/SKILL.md` with the same `name` and
`description` frontmatter, so the same files serve both. It has no documented
agents directory, so those links are there to make a persona file resolvable on
disk when a skill reads one directly, not because Codex loads them itself.

Rules are always-on in Claude Code through `~/.claude/rules`. Codex reads an
instruction file in the repository instead, so write the rules into one:

```bash
./make-agents-md.sh ~/code/some-project
./make-agents-md.sh --dry-run ~/code/some-project
./make-agents-md.sh --help
```

That writes every file in `rules/` into `AGENTS.md` in the target repo, between
delimiter comments. Re-running replaces only the generated block, so anything
you wrote by hand around it survives. Edit the rules here and re-run to update.

Hooks and the settings fragment are Claude Code only for now. Codex's hook wire
format matches (PreToolUse, SessionStart, `hookSpecificOutput`, exit 2 denies),
so wiring them in is a follow-up rather than a rewrite.

The agent personas under `agents/` are ordinary prompts, and the templates are
ordinary markdown, so pointing another agent at one works by hand.

---

## Working on this repo

Read [AUTHORING.md](AUTHORING.md) before adding or editing anything. It defines
the skill, rule, agent and template formats and the house facts every skill
assumes. [CONTRIBUTING.md](CONTRIBUTING.md) has the pull request checklist.

Each skill carries `evals/evals.json`, a transcript-review checklist of prompts
and observable expectations. `validate.sh` enforces its structure, so behaviour
changes can be checked rather than guessed at.

---

## License

MIT. See [LICENSE](LICENSE).
