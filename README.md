# skills

Portable coding-agent setup: skills, always-on rules, review personas and
hooks, packaged as one plugin, `jz`, in a marketplace that Claude Code and
Codex both read. Add the marketplace on any machine and the agents behave the
same.

A skill loads when you type its command, `/jz:verify` or `/jz:pr`, or when
the brief that starts a session names it. A plain request such as "commit"
does not load one on its own, which is why a hook denies a commit, push or
PR create until `pr` is loaded. The rules, the personas and the hooks load
with the plugin.

---

## Install

Requirements: `bash`, `git` and `python3` on the machine that runs the hooks,
and an authenticated `gh` for the skills that push, open or review pull
requests.

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
or turn auto-update on for the marketplace under
`/plugin`.

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

## Use it

### A first session

Open a session in a project. The house rules arrive at session start as a
block headed "House rules from the jz plugin", with the project's own
`CLAUDE.md`, `AGENTS.md` and `CONTRIBUTING.md` surfaced beside them. Then:

1. Settle what to build. `/jz:grill` interviews the plan until nothing is
   assumed and, in spec mode, writes a spec of requirements and steps.
   `/jz:criteria` then writes acceptance criteria for each requirement, seen failing before
   anything is built. `/jz:review` in audit mode reads the repo without editing it and
   writes a plan file under `docs/plans/`, which is never committed.
2. Build it. `/jz:implement` builds a spec step or a plan item, running its
   criteria before, during and after, writing tests first.
   `/jz:debug` takes a bug cause first.
3. Prove it. `/jz:verify` runs the repo's own scripts and ends in a
   Verification block with a `behaviour` row. Without that block nothing is
   done.
4. Ship it. `/jz:pr`, with the mode in the request: "commit" stops at the
   commit, "commit and push" at the push, "commit, push and open a draft PR"
   at the draft, and "... and mark ready" runs through to ready. The body is
   written from the diff. A commit or push typed before the skill is loaded
   is denied, with the call that unblocks it.
5. Review it. `/jz:review` on a branch or a PR number; "check the PR comments"
   sweeps the unresolved threads.
6. After the merge, "PR 12 merged, clean up" runs the `pr` cleanup: the tip
   checks, the branch and worktree removal, and the main checkout brought
   level with the remote.

A spec's steps run through `/jz:coordinate` from a session in the target
repository. It starts one worker session per step and one reviewer per PR,
reports one line per PR at merge-ready, and leaves the merge to you.

### Set up a project

The skills read these from the project. Each one is optional, and the skill
says what it does without it.

| In the project | Read by | Without it |
|---|---|---|
| `.claude/` in `.gitignore` | `pr` Worktree section | `pr` offers to add it to `.git/info/exclude` before creating a worktree; the hook refuses to stage `.claude/` or `docs/plans/` either way |
| `AGENTS.md` with a `## Standing orders` section | `coordinate`, pasted verbatim into every brief | the phase template's default block stands in, and adding the section is part of the first phase |
| `AGENTS.md` with a `## Restricted words` list | `no-restricted-words.sh` | only the house list applies |
| `AGENTS.md` with an `## Enforcement` table | `improve` | the first project-side `improve` run creates it |
| `VERIFICATION.md` at the root, or one per package | `verify`, for the `behaviour` row | the row reads what the test runs support, `unit-only` at most, unless another pasted run drove the feature |
| `docs/specs/<slug>.md`, `CONTEXT.md`, `docs/adr/` | written by `grill` in spec mode, criteria added by `criteria`, read by `implement` and `coordinate` | `implement` and `coordinate` refuse a spec whose criteria are not signed off and offer `criteria` |
| Scripts named `format`, `lint`, `typecheck`, `test` and `build` in `package.json`, or the same targets in a `Makefile` | `verify` | the concern is reported as "no script"; nothing is invented in its place |

---

## What is in here

```
.claude-plugin/marketplace.json   the marketplace, for Claude Code
.agents/plugins/marketplace.json  the same marketplace, for Codex
plugins/jz/                       the agent-agnostic plugin
  skills/      loaded on demand when a request matches the description;
               a skill that fills in a template carries it as template.md
  rules/       always on, injected at session start by a hook
  agents/      four read-only review personas the review skill's audit mode fans out to
  hooks/       the hook scripts and the hooks.json that wires them up
```

### Skills

Twelve skills, in three groups. The workflow runs in this order:

```
grill  ->  criteria  ->  implement  ->  verify  ->  pr  ->  review
what and    how we'll     build it        prove it     ship it  second
steps       know it's     against them                          opinion
            done
```

`grill` settles what to build and writes a spec of requirements and steps.
`criteria` writes how each requirement will be proven, and sees each check
fail before anything is built. `implement` builds a step at a time against
those criteria, `verify` gates every done claim, `pr` ships it as a draft
PR structured by requirement, and `review` gives an independent read.
`coordinate` drives a spec's steps through that loop with one fresh session
per step and per review, and `handoff` carries the state when context runs
out.

#### Workflow

| Skill | Use it for |
|---|---|
| `grill` | Interview a plan until nothing is assumed; in spec mode write the spec (requirements, decisions, vertical-slice steps), the glossary, ADRs and standing orders as decisions land |
| `criteria` | Write acceptance criteria per requirement (scenario, what counts as passing, and a test, command, drive or inspection check), run each once to see it fail, and get the owner's sign-off |
| `implement` | Build a spec step or plan item: see its criteria fail, write tests first, build the least change, record each criterion's status, checkpoint per item |
| `verify` | The completion gate: runs the repo's own scripts cheapest first, pastes output and exit codes, reports one row per concern and per criterion and the behaviour level reached, and raises coverage to a threshold with the per-file table |
| `pr` | Verify, commit, push and open a draft PR with a body written from the diff, structured by requirement when there is a spec; ready only when asked; rebase when the default branch moves; clean up after the merge |
| `review` | Change review with design, maintainability, guard-deletion and criteria lenses that always report; audit mode for a whole repo or a plan, fanned out to personas into a plan file; the PR comment and red-CI sweep; an adversarial mode across two model families |
| `coordinate` | Drive a spec's steps to merge-ready: one fresh worker per step with the step's criteria and behaviour target as Done means, one fresh reviewer per PR, bounded fix rounds, the units and decisions ledgers, one line per PR |
| `handoff` | Write a resumable handoff before context runs out, with decisions read from the `coordinate` ledger rather than from memory |

#### Task

| Skill | Use it for |
|---|---|
| `debug` | Reproduce, instrument, trace to the root cause, a failing test first, one fix at a time |
| `guard-deps` | Advisories, action pinning, supply-chain settings, vetting a new dependency |
| `sync-docs` | Bring READMEs, guides and doc comments back in line with the code |

#### Self-improvement

| Skill | Use it for |
|---|---|
| `improve` | Corrections that came back, from the session transcript, review threads and reverts: proposed as edits to a skill or rule in this plugin behind an approval by number, or fixed in the project at the highest level that holds, with the check proven red on the past mistake and an enforcement row |

`verify` is the one the others depend on. It is what stops "done" from meaning
"probably done".

`review`'s audit mode fans out to the four personas under `agents/`, which install as the
subagent types `jz:principal-engineer`, `jz:security-engineer`,
`jz:test-engineer` and `jz:technical-writer`.

### Rules

Always-on and deliberately short, because they cost tokens in every session.
A plugin cannot ship rule files directly, so the `load-house-rules.sh` hook
injects them at session start.

| File | Covers |
|---|---|
| `house-style.md` | TypeScript and general code style |
| `prose.md` | Numbered writing rules, so a steer can cite "prose rule 4": plain facts, no narrative of earlier runs, no mannered phrasing, sentence-case headings, straight quotes, no emoji or model names |
| `git-workflow.md` | Branching, worktrees, commits, PR bodies, what never gets staged |
| `verification.md` | Evidence before assertions, root cause over workaround |
| `ui-conventions.md` | Icons, primitives, type scale, the checks before a layout is done |
| `parallelism.md` | Fan independent work out to subagents by default; wait for the owner only at a lettered design fork, a remote write that asks, or an action the brief marks as theirs |
| `models.md` | Host-neutral model tiers mapped to Claude and Codex: grilling, coordination, implementation, review on the other family first, fix escalation and scans |

### Hooks

Some rules are enforcement problems, and a rule can be ignored while a hook
cannot. `hooks.json` wires these up with `${CLAUDE_PLUGIN_ROOT}`, which Codex
also sets.

| Hook | Event | Effect |
|---|---|---|
| `no-claude-artifacts.sh` | PreToolUse on Bash | Blocks any staging or commit that would include `.claude/`, `docs/plans/` or `.plans/` |
| `require-pr-skill.sh` | PreToolUse on Bash | Denies `git commit`, `git push` and `gh pr create` until the session's transcript shows the `pr` skill loaded, by a Skill call whose result reported no error or a typed `/jz:pr`; a payload without a transcript path passes, so the gate holds on Claude Code only |
| `confirm-remote-writes.sh` | PreToolUse on Bash | Asks before a `gh pr create` without `--draft`, `gh pr ready` and any force push not pinned to a sha, including a bare `--force-with-lease`, `-f` clusters and a `+refspec`; a branch push, a draft PR and a `--force-with-lease=<branch>:<sha>` push pass without a prompt |
| `protect-default-branches.sh` | PreToolUse on Bash | Blocks a push that would update or delete `main`, `master`, `develop`, `trunk` or the branch `origin/HEAD` names, resolved from the repository's own configuration and tracking refs, and blocks merging a pull request: `gh pr merge` including `--auto`, and the REST and GraphQL merge calls through `gh api`. The owner merges on GitHub |
| `scan-secrets-before-push.sh` | PreToolUse on Bash | Scans the commits a `git push` would publish, with betterleaks or gitleaks when one is on PATH and a builtin set of token shapes otherwise, and asks before the push when something looks like a secret; nothing is installed |
| `rebase-not-merge.sh` | PreToolUse on Bash | Blocks merging the default branch into a feature branch, or pulling it without `--rebase`; rebase instead. A checkout on the default branch may fast-forward itself |
| `no-restricted-words.sh` | PreToolUse on Bash | Blocks a commit message, PR body, review or comment that carries an emoji, an agent attribution trailer, a session link, a model version slug, or a word listed under a `## Restricted words` heading in the repo's `AGENTS.md` or `CLAUDE.md` |
| `load-house-rules.sh` | SessionStart | Injects the rule files as context, since a plugin cannot ship always-on instructions |
| `load-project-rules.sh` | SessionStart | Surfaces `CLAUDE.md`, `AGENTS.md` and `CONTRIBUTING.md` at session start |

The hooks that read a command line share one parser, `command_lines.py`, so a
line continuation, a quoted separator, a trailing comment, a `timeout 30`
wrapper or a `bash -c` script is read the way the shell will read it. The
hooks that judge a push share `git_push.py`, which reads the push options the
way git does and works out from the repository's configuration and tracking
refs which refs the push would update. It never contacts the remote and never
runs anything the command names, since a hook runs before the owner approves
the call. The
hooks that judge a `gh` call share `gh_options.py`, which finds the subcommand
past `-R o/r` and reads each flag's final value the way gh does.

The hooks have their own regression suite, which builds a throwaway repo and
feeds each hook the payloads it will see. Exit 2 denies a tool call, exit 0
allows it, and an ask decision is read from the output.

```bash
make test
```

`make validate` runs the hook suite, along with checks over the marketplace
and plugin manifests, every skill, rule, agent and template, `bash -n` and
`shellcheck` over every script, `claude plugin validate` over the marketplace
and the plugin when the Claude Code CLI is installed, a 300-line limit on
every skill, and a check that every skill is listed in this README. Run it before
committing a change here.

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
