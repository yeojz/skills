# skills

Portable coding-agent setup: skills, always-on rules, review personas and
hooks, packaged as one plugin, `jz`, in a marketplace that Claude Code and
Codex both read. Add the marketplace on any machine and the agents behave the
same.

Every skill is invoked as `/jz:<name>`, for example `/jz:verify` or
`/jz:ship`. The rules, the personas and the hooks load with the plugin.

---

## Install

Requirements: `bash`, `git` and `python3` on the machine that runs the hooks.

### Claude Code

In a session:

```text
/plugin marketplace add yeojz/skills
/plugin install jz@yeojz-skills
```

Or from a shell:

```bash
claude plugin marketplace add yeojz/skills
```

```bash
claude plugin install jz@yeojz-skills
```

Start a new session so the rules and hooks load. Claude Code leaves
auto-update off for third-party marketplaces, so to pick up new commits run
`claude plugin marketplace update yeojz-skills` and then `claude plugin update jz@yeojz-skills`,
or turn auto-update on for the marketplace under `/plugin`.

### Codex

```bash
codex plugin marketplace add yeojz/skills
```

```bash
codex plugin add jz@yeojz-skills
```

Then start a new session. `codex plugin marketplace upgrade` refreshes the
snapshot after new commits. On Codex CLI 0.164.0 the skills load as
`jz:<name>`. Codex runs a plugin's hooks only after you trust them once, from
`/hooks` in an interactive session; until then the rules do not arrive at
session start, and `make-agents-md.sh` below writes them into the
repository's `AGENTS.md` instead.

### Upgrading from the symlink installer

Earlier versions of this repo installed by symlinking into `~/.claude` and
`~/.codex` with `install.sh`. Remove those links before installing the plugin,
or every skill appears twice. The uninstaller only removes links that point
into its own checkout, so run it from the checkout that created them, with the
working tree clean, on the last commit that still has the old layout:

```bash
git checkout 3adb7f1
```

```bash
./install.sh --uninstall claude codex
```

```bash
git checkout main
```

The first command puts the whole old layout back at the same path, the second
removes the links and the settings entries, and the third returns to the
current revision. If the links were created from a different clone, run the
same three commands there.

---

## What is in here

```
.claude-plugin/marketplace.json   the marketplace, for Claude Code
.agents/plugins/marketplace.json  the same marketplace, for Codex
plugins/jz/                       the plugin
  skills/      loaded on demand when a request matches the description;
               a skill that fills in a template carries it as template.md
  rules/       always on, injected at session start by a hook
  agents/      four read-only review personas the audit skill fans out to
  hooks/       the hook scripts and the hooks.json that wires them up
```

### Skills

A change usually runs through the skills in this order. `grill` or `audit`
settles what to build and leaves a plan. `coordinate` drives a roadmap of
phases through the rest of the loop, one fresh session per phase and one per
review. `execute-plan` works the plan item by item, reaching for `tdd`,
`debug`, `coverage`, `design-critique`, `docs-sync` or `deps-guard` as the
item demands. `verify` gates every done claim. `ship`
commits, pushes and opens the draft PR, `pr-desc` writes its body, `review`
handles the comments, and `release` follows a merge. `handoff` carries the
state when context runs out.

#### Settle the work

| Skill | Use it for |
|---|---|
| `grill` | Interview a plan until nothing is assumed; in kickoff mode write the glossary, ADRs, design doc, standing orders and roadmap rows as decisions land |
| `coordinate` | Drive a roadmap to merge-ready: fill the phase and review briefs from their templates, one fresh worker session per phase and one fresh reviewer per PR, keep the units and decisions ledgers, report one line per PR |
| `audit` | Read-only repo assessment that writes a prioritised plan file |
| `naming` | Lettered naming options with trade-offs, then rename everywhere |

#### Build

| Skill | Use it for |
|---|---|
| `execute-plan` | Work a plan item by item with honest status and commit checkpoints |
| `tdd` | Failing test first, simplest code to pass, refactor while green |
| `debug` | Reproduce, instrument, trace to the root cause, one fix at a time |
| `coverage` | Raise coverage to threshold and prove it with the report |
| `deps-guard` | Advisories, action pinning, supply-chain settings, vetting a new dependency |
| `design-critique` | Judging, redesigning or fixing a UI visually; needs a browser automation tool |
| `docs-sync` | Bring READMEs, guides and doc comments back in line with the code |

#### Prove it

| Skill | Use it for |
|---|---|
| `verify` | The completion gate. Runs the repo's own scripts and pastes real output before any done claim |

#### Ship and review

| Skill | Use it for |
|---|---|
| `ship` | Branch, format, lint, verify, conventional commit; on one go-ahead push, draft PR, gate the pushed head on a clean detached checkout and mark ready; rebase when the default branch moves; clean up after the merge |
| `pr-desc` | Write or refresh a PR title and body from the diff, with a Verification section listing the commands that actually ran |
| `review` | Diff-scoped or PR-scoped review, plus the unresolved-comment sweep |
| `release` | Version PR, changeset, label gate, publish |

#### Hand over

| Skill | Use it for |
|---|---|
| `handoff` | Write a resumable handoff before context runs out |

`verify` is the one the others depend on. It is what stops "done" from meaning
"probably done".

`audit` fans out to the four personas under `agents/`, which install as the
subagent types `jz:principal-engineer`, `jz:security-engineer`,
`jz:test-engineer` and `jz:technical-writer`.

### Rules

Always-on and deliberately short, because they cost tokens in every session.
A plugin cannot ship rule files directly, so the `load-house-rules.sh` hook
injects them at session start.

| File | Covers |
|---|---|
| `house-style.md` | TypeScript and general code style |
| `git-workflow.md` | Branching, worktrees, commits, PR bodies, what never gets staged |
| `verification.md` | Evidence before assertions, root cause over workaround |
| `ui-conventions.md` | Icons, primitives, type scale, the checks before a layout is done |
| `parallelism.md` | Fan independent work out to subagents by default |
| `models.md` | Which model tier does coordination, review, scoped implementation and scans |

### Hooks

Some rules are enforcement problems, and a rule can be ignored while a hook
cannot. `hooks.json` wires these up with `${CLAUDE_PLUGIN_ROOT}`, which Codex
also sets.

| Hook | Event | Effect |
|---|---|---|
| `no-claude-artifacts.sh` | PreToolUse on Bash | Blocks any staging or commit that would include `.claude/`, `docs/plans/` or `.plans/` |
| `confirm-remote-writes.sh` | PreToolUse on Bash | Asks before a `gh pr create` without `--draft`, `gh pr ready`, `gh pr merge` and any force push, including `--force-with-lease`, `-f` clusters and a `+refspec`; a branch push and a draft PR pass without a prompt |
| `scan-secrets-before-push.sh` | PreToolUse on Bash | Scans the commits a `git push` would publish, with betterleaks or gitleaks when one is on PATH and a builtin set of token shapes otherwise, and asks before the push when something looks like a secret; nothing is installed |
| `rebase-not-merge.sh` | PreToolUse on Bash | Blocks merging the default branch into a feature branch, or pulling it without `--rebase`; rebase instead |
| `no-restricted-words.sh` | PreToolUse on Bash | Blocks a commit message, PR body, review or comment that carries an emoji, an agent attribution trailer, a session link, a model version slug, or a word listed under a `## Restricted words` heading in the repo's `AGENTS.md` or `CLAUDE.md` |
| `load-house-rules.sh` | SessionStart | Injects the rule files as context, since a plugin cannot ship always-on instructions |
| `load-project-rules.sh` | SessionStart | Surfaces `CLAUDE.md`, `AGENTS.md` and `CONTRIBUTING.md` at session start |

The hooks that read a command line share one parser, `command_lines.py`, so a
line continuation, a quoted separator, a trailing comment, a `timeout 30`
wrapper or a `bash -c` script is read the way the shell will read it.

The hooks have their own regression suite, which builds a throwaway repo and
feeds each hook the payloads it will see. Exit 2 denies a tool call, exit 0
allows it, and an ask decision is read from the output.

```bash
make test
```

`make validate` runs it, along with checks over the four manifests, every
skill, rule, agent and template, `bash -n` and `shellcheck` over every script,
`claude plugin validate` when the Claude Code CLI is installed, and a check
that every skill is listed in this README. Run it before committing a change
here.

---

## Rules as an AGENTS.md block

An agent that reads an instruction file in the repository rather than loading
plugins can still get the rules:

```bash
./make-agents-md.sh ~/code/some-project
./make-agents-md.sh --dry-run ~/code/some-project
./make-agents-md.sh --help
```

That writes every file in `plugins/jz/rules/` except `models.md` into `AGENTS.md` in the target
repo, between delimiter comments. Re-running replaces only the generated block,
so anything you wrote by hand around it survives. Edit the rules here and
re-run to update.

The agent personas under `agents/` are ordinary prompts, and the templates are
ordinary markdown, so pointing another agent at one works by hand.

---

## Working on this repo

Read [AUTHORING.md](AUTHORING.md) before adding or editing anything. It defines
the layout, the skill, rule, agent and template formats and the house facts
every skill assumes. [CONTRIBUTING.md](CONTRIBUTING.md) has the pull request
checklist.

Each skill carries `evals/evals.json`, a transcript-review checklist of prompts
and observable expectations. `validate.sh` enforces its structure, so behaviour
changes can be checked rather than guessed at.

---

## License

MIT. See [LICENSE](LICENSE).
