---
name: improve
description: Use when a correction keeps coming back and should become a lasting change, either an edit to a skill or rule in this plugin or a check the project runs, instead of a steer typed again. Triggers on requests like "/improve", "/reflect", "/correct", "reflect on this session", "what did I have to correct", "turn that into a rule", "update the skill so this does not happen again", "phase done, what did we learn", "agents keep doing X", "this is the second time", "I keep having to tell you", "make it impossible to", "add a check so this cannot recur".
---

# improve

## Overview

Turns repeated corrections into lasting changes. It gathers what the owner
had to correct, sorts each correction by where the fix belongs, and either
proposes an edit to a skill or rule in this plugin, or builds a check the
project runs on every push. Every change is grounded in the owner's own
words, and nothing in the plugin changes without an approval by number.

| Path | Fixes | Fix looks like |
|---|---|---|
| Plugin | how a skill or rule here behaves | a rule line, a skill step, an eval expectation |
| Project | the project's code, scripts, CI, tests, formatter | a check that fails on the mistake: architecture, types, lint or CI, a test, or a line in `AGENTS.md` as the floor |

## Workflow

### Step 1: Gather the corrections

Read every source before sorting anything.

**This session.** The conversation in context, and the transcript file,
because compaction drops the start. Find the file by session identity,
never by modification time, since two chats on one checkout share a folder:

| Host | Transcript | User turns |
|---|---|---|
| Claude Code | `~/.claude/projects/<cwd with / and . as ->/<session-id>.jsonl` | `type == "user"`, the string content or its `text` blocks; `tool_result` blocks are not turns |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<id>.jsonl` | `type == "response_item"`, `payload.type == "message"`, `payload.role == "user"` |

```bash
transcript="$HOME/.claude/projects/$(pwd | tr '/.' '--')/${CLAUDE_CODE_SESSION_ID:?}.jsonl"
jq -r 'select(.type=="user") | .message.content | if type=="string" then . else (map(select(.type=="text") | .text) | join("\n")) end | select(length>0)' "$transcript"
```

Without a session id (Codex, or an unset variable), find the one transcript
for this `cwd` that contains a phrase the owner typed in this conversation;
zero or several matches is a stop, so ask which.

**The project's history**, for the project path:

```bash
base="$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\)[[:space:]]*HEAD$|\1|p')"
git fetch origin "$base"
git log --oneline --since='60 days ago' "origin/$base" | grep -iE 'revert|^[0-9a-f]+ fix' | head -40
gh pr list --state merged --limit 15 --json number,title
grep -n -A 30 '^## Enforcement' AGENTS.md CLAUDE.md 2>/dev/null
```

Read the review threads of those PRs (the `review` skill's comments-mode
query), since that's where the owner typed most corrections.

**Signals**, each recorded with its turn or source:

| Signal | Looks like |
|---|---|
| A negation or repeat | "no", "not that", "again", "I said", "second time" |
| A restated rule | the owner types a line a rule file already has |
| An undo or revert | the next turn or commit reverts what was just done |
| A hook denial, then a rephrase | exit 2, then the same intent in other words |
| A workaround | a retried command with `--no-verify`, `--force` or a skipped step |
| An over-ask | "just do it" to a question that shouldn't have been asked |

One occurrence is a candidate; two of the same kind, or one the owner
marked as repeated, is a target. A candidate with no quote behind it is
dropped.

### Step 2: Sort by where the fix belongs

| Correction is about | Path, home |
|---|---|
| wording, tone, headings | Plugin: `rules/prose.md`, by rule number; when the owner cites a rule that already exists, also the skill that wrote the prose |
| branching, commits, PR body, staging | Plugin: `rules/git-workflow.md` or the `pr` skill |
| a done claim without output, a weakened test | Plugin: `rules/verification.md` or `verify` |
| fan-out, waiting, options without a recommendation | Plugin: `rules/parallelism.md` |
| the model a session ran on | Plugin: `rules/models.md` |
| a step a skill took or skipped | Plugin: that skill's `SKILL.md`, the step by name |
| the project's code, scripts, CI, tests, formatter, hooks | Project |

Run the plugin path for plugin targets and the project path for project
targets; one run may do both, plugin first.

### Step 3, plugin path: propose and wait

One proposal per target: the file, the edit as a diff, the quoted evidence
with its turn, and the eval expectation that would have caught it.

```markdown
### P1: pr asks before a branch push

File: `plugins/jz/skills/pr/SKILL.md`, Push section
Evidence: turn 14, "push it, you do not need to ask"; turn 22, "again, just push"

    -Ask before pushing the branch.
    +A branch push needs no confirmation question; the request decides whether it runs.

Eval: `pr/evals/evals.json`, eval 2, add "Pushes the branch without asking"
```

A rule line is one imperative line and keeps its file under 80 lines (say
which line it replaces if it wouldn't); rule numbers never move. Never
propose deleting a rule the owner restated: restated means not followed.
When prose was already there and ignored, propose a hook, as its own PR.

Print the numbered list, the project targets, and what was dropped, then
stop. Apply only the numbers the owner names (`1 3`, or "all"); "looks
good" names none.

Apply in a working checkout of the plugin repository, never under
`~/.claude/plugins/`, which the next update overwrites:

```bash
jq -r '.["yeojz-skills"].source.repo' ~/.claude/plugins/known_marketplaces.json
```

Use this session's checkout if it is that repo; otherwise ask for one or
clone it. Branch as the `pr` skill's Worktree section describes, apply only
the accepted proposals, run `make validate`, and hand the commit and PR to
`pr`.

### Step 3, project path: build the check

**Ledger.** One row per class, with its count, sources and what enforces it
today. Take the highest count; on a tie, the one that reached a remote. A
class something already enforces is reported as covered. Fix one class per
run.

**Ladder.** Take the first level that holds, meaning it runs without anyone
remembering and the usual path can't step around it:

| Level | The mistake becomes | Example: tests waiting on real time |
|---|---|---|
| Architecture | impossible to write | inject a clock |
| Types | a compile error | a branded `Duration` a literal can't satisfy |
| Lint or CI | a red check | a CI grep for `setTimeout` under `test/` |
| Tests | a failing test | a regression test for the reverted behaviour |
| Docs (floor) | a line in `AGENTS.md` | "tests never wait on real time" |

When two levels hold, offer both as lettered options and wait. A docs fix
records `nothing` as its enforcement, so the class stays a target.

**Fix** in the task's worktree, as the `pr` skill's Worktree section
describes, as one commit that does only this (`refactor`, `ci`, `test` or
`docs` by level).

**Prove it red, then green.** The fix is uncommitted, so never rebuild the
mistake in the task worktree: carry the fix into a throwaway worktree and
rebuild it there.

```bash
git status --short --untracked-files=all; git hash-object <fixed-path>
red_dir="$(mktemp -d)" && git worktree add --detach "$red_dir" HEAD
git -c core.quotepath=false ls-files -z --modified --others --exclude-standard | sort -zu | while IFS= read -r -d '' f; do
  if [ -e "$f" ]; then mkdir -p "$red_dir/$(dirname "$f")" && cp -p "$f" "$red_dir/$f" || exit 1; else rm -f "${red_dir:?}/${f:?}"; fi
done; echo "copy exit=$?"
diff <(git status --short --untracked-files=all) <(git -C "$red_dir" status --short --untracked-files=all) && echo "fix carried over"
( cd "$red_dir" && pnpm install --frozen-lockfile )   # or the lock file's equivalent, when the check needs dependencies
# rebuild the mistake inside "$red_dir": git -C "$red_dir" show <sha>:<path> > "$red_dir/<path>", or revert --no-commit <sha>
( cd "$red_dir" && pnpm lint ); echo "exit=$?"
git worktree remove --force "$red_dir" && git worktree prune
pnpm lint; echo "exit=$?"
git status --short --untracked-files=all; git hash-object <fixed-path>
```

The red run must exit non-zero and the green one zero, and the status and
hash before and after must match, which proves the task worktree was never
touched; a copy error or a status diff is a stop. If it can't be made red, the level doesn't hold:
drop one, at most three times, then report the class as unfixed.

**Record** the rule and what enforces it (the file and the script that
runs it) in the `## Enforcement` table of `AGENTS.md` or `CLAUDE.md`,
creating it if needed, in the same commit. Then `verify`, and hand the
commit and PR to `pr`.

### Step 4: Report

```markdown
## improve: <session or step>

Plugin: P1 applied, P2 skipped by the owner. Files: <paths>, with each changed rule file's line count. `make validate` exit 0.
Project: <class>, at lint or CI because <why not higher>. Red: `<cmd>` exit 1 on <sha>:<path>. Green: exit 0. Enforcement row added.
Still targets: <class> (<n>), <class> (<n>).
Handoff line: <one line for the next session>
```

Every sha, exit code and result line comes from output in this session.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Applying a proposal because it's obviously right | Apply only the numbers the owner names |
| Mining only the conversation in context | Read the transcript file, by session id |
| A change with no quote behind it | Drop it |
| Editing the installed plugin copy | Edit a checkout of the repo |
| A skill change with no eval expectation | Add the one that would have caught it |
| Choosing docs because it's quickest | Walk the ladder from the top |
| A check that was never red | Rebuild the past mistake in a throwaway worktree; paste both exits |
| Two classes in one commit | One class per run |
| Fixing the triggering occurrence and calling the class fixed | The class is fixed when a check fails on it |
