---
name: reflect
description: Use at the end of a phase, or when a session's corrections and workarounds should become an edit to a skill or rule in the plugin instead of a steer typed again next time. Triggers on requests like "/reflect", "reflect on this session", "what did I have to correct", "what should the skill have said", "turn that into a rule", "update the skill so this does not happen again", "phase done, what did we learn", "before you hand off, reflect", "which prose rule was that", or when a coordinating session closes a phase or a handoff is about to be written.
---

# reflect

## Overview

Mines this session's transcript for the corrections the user typed and the
workarounds the agent took, attributes each to the skill or rule that should
have prevented it, and proposes the exact edit: a rule line, a skill step, a
row in a Common Mistakes table, an eval expectation. Every proposal waits
for approval. Nothing is applied on the agent's own initiative, and an
approval covers only the proposals it names.

The failure this exists to prevent is the correction that lives in one
session's memory and is typed again in the next. The last reflection in
this setup was a one-off that produced a proposal document; this makes it a
step at the end of every phase.

`reflect` changes the plugin repository: its skills, rules and evals. A
correction about the project itself, its scripts, CI, tests or formatter, is
the `correct` skill's job and is listed for it, not proposed here.

| Skill | Changes | Fix looks like |
|---|---|---|
| `reflect` | the plugin: `plugins/jz/skills/`, `plugins/jz/rules/` | a numbered prose rule, a skill step, an eval expectation |
| `correct` | the project: its lint, CI, tests, hooks, `AGENTS.md` | a check the project runs on every push |

## Workflow

### Step 1: Mine the transcript

The conversation in context is the first source. Compaction drops the start
of a long session, so read the transcript file as well; it holds every turn.

| Host | Transcript | User turns |
|---|---|---|
| Claude Code | `~/.claude/projects/<cwd with / replaced by ->/<session-id>.jsonl` | `type == "user"`; `message.content` is a string, or an array whose `text` blocks are the turn and whose `tool_result` blocks are tool output, not a turn |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<id>.jsonl` | `type == "response_item"` with `payload.type == "message"` and `payload.role == "user"` |

```bash
project_dir="$HOME/.claude/projects/$(pwd | tr '/' '-')"
transcript="$(ls -t "$project_dir"/*.jsonl | head -1)"
jq -r 'select(.type=="user") | .message.content | if type=="string" then . else (map(select(.type=="text") | .text) | join("\n")) end | select(length>0)' "$transcript"
```

```bash
jq -r 'select(.type=="response_item" and .payload.type=="message" and .payload.role=="user") | .payload.content[].text' ~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-<id>.jsonl
```

Read every user turn and the agent turn before it. Record a candidate for
each of these signals, with the turn it came from:

| Signal | Looks like | Candidate |
|---|---|---|
| A negation or a repeat | "no", "not that", "again", "I said", "as I said", "stop", "second time" | a correction |
| A restated house rule | the user types a line a rule file already carries | the rule was loaded and not followed, or the rule is too vague |
| A cited prose rule | "prose rule 4", "that is rule 2 again" | the rule holds; the skill that wrote the prose missed it |
| An undo | the next turn reverts or deletes what the agent just did | a correction |
| A hook denial followed by a rephrase | exit 2 in the transcript, then the same intent in other words | a workaround, or a hook that is too wide |
| A retried command with different flags | the same script run twice, the second with `--no-verify`, `--force` or a skipped step | a workaround |
| A step done twice | a skill step repeated because the first pass missed something the step named | the step is unclear |
| "just do it" | the user answers a question the skill should not have asked | an over-ask |

One occurrence is a candidate. Two of the same kind in one session, or one
that the user marked as repeated, is a proposal.

### Step 2: Attribute each candidate

Each candidate belongs to the skill or rule that was loaded when it
happened, or whose scope it falls in when none was loaded:

| Candidate is about | Home |
|---|---|
| wording, tone, headings, quotes, narrative of earlier runs | `rules/prose.md`, cited by number |
| branching, commits, PR body, what gets staged, asking before a push | `rules/git-workflow.md` or the `ship` skill |
| a done claim without output, a weakened test | `rules/verification.md` or the `verify` skill |
| fan-out, waiting on the user, options without a recommendation | `rules/parallelism.md` |
| the model a session or brief ran on | `rules/models.md` |
| a step a skill took or skipped | that skill's `SKILL.md`, the step by number |
| the project's scripts, CI, formatter, tests, hooks | `correct`, not this skill |

A candidate with no home is a proposal for a new rule line, and the report
says which file it would join. A candidate that is the project's own
problem goes under "For correct" and is not proposed here.

### Step 3: Draft one proposal per item

Each proposal names the file, shows the edit as a diff, quotes the evidence
and says what level it lands at. The evidence is the user's words from the
transcript, quoted, with the turn; a proposal with no quote is dropped.

```markdown
### P1: ship asks before a branch push

File: `plugins/jz/skills/ship/SKILL.md`, Step 9
Evidence: turn 14, "push it, you do not need to ask, a branch push can be withdrawn"; turn 22, "again, just push"
Level: skill step, plus an eval expectation

    -Ask before pushing the branch.
    +A branch push needs no confirmation question; the request decides whether it runs.

Eval: `evals/evals.json`, eval 2, add "Pushes the branch without asking a confirmation question"
```

Rules for the edit:

- A rule line is imperative, one line, and keeps the file under 80 lines.
  Count before proposing, and when the line would push it over, propose
  which existing line it replaces.
- A prose change cites the rule number it sharpens, or takes the next free
  number; numbers never move.
- A change to a skill's behaviour comes with the eval expectation that
  would have caught it, since evals are the test in this repository.
- A change that only a hook can hold, because prose was already there and
  was not followed, is proposed as a hook and marked as its own pull
  request; this skill does not write hooks.
- Never propose deleting a rule the user restated. Restating means it was
  not followed, not that it was wrong.

### Step 4: Present and wait

Print the proposals as a numbered list, each with its file, level and
evidence, followed by the items handed to `correct` and the candidates
dropped for lack of a quote. Then stop.

```markdown
## reflect: <phase or session>

Proposals, accept by number:
1. P1 ship asks before a branch push, `ship/SKILL.md` Step 9 plus eval 2
2. P2 prose rule 2 missed twice, `rules/prose.md`, sharpen the line
3. P3 new parallelism line: an unmerged dependency is a branch to base on

For correct: tests with wall-clock bounds, seen twice, the project's suite
Dropped: one "hm" at turn 9 with no correction behind it
```

Accept the answer in the short form, `1 3`, as well as prose. An answer that
names none applies none. Never apply a proposal the user did not name, and
never apply one on the strength of "looks good" without a number or "all".

### Step 5: Apply the accepted proposals in the plugin repository

The installed plugin is a copy that the next marketplace update overwrites,
and so is the marketplace's own clone under the plugin cache, so the edit
goes into a working checkout of the plugin repository. The marketplace
record names the repository:

```bash
jq -r '.["yeojz-skills"].source.repo' ~/.claude/plugins/known_marketplaces.json
git -C "$HOME/.claude/plugins/marketplaces/yeojz-skills" remote get-url origin
```

When this session already runs in that repository, use it. Otherwise ask
for the path of a checkout, or clone one with `gh repo clone <repo>` into a
directory of its own; never edit under `~/.claude/plugins/`. Then branch in
that repository as the `ship` skill's Step 1 describes, apply only the
accepted proposals, and run its gate:

```bash
make validate; echo "exit=$?"
```

Hand the commit and the pull request to `ship` in the mode the user asked
for. The commit covers the accepted proposals and nothing else.

### Step 6: Report

```markdown
## reflect: applied

Accepted: P1, P3. Skipped: P2.
Files: `plugins/jz/skills/ship/SKILL.md`, `plugins/jz/skills/ship/evals/evals.json`, `plugins/jz/rules/parallelism.md` (now 41 lines)
Gate: `make validate`, exit 0, All checks passed
For correct: tests with wall-clock bounds, seen twice
Handoff line: reflect ran over phase 12; P1 and P3 applied on <branch>, P2 skipped by the owner
```

The handoff line is for the `handoff` skill or the coordinating session's
notes, so the next phase starts knowing what changed.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Applying a proposal because it is obviously right | Every proposal waits. Approval names numbers |
| Reading only the conversation in context | Compaction dropped the start. Read the transcript file |
| A proposal with no quote from the transcript | Drop it. Evidence is the user's words and the turn |
| Proposing a fix to the project's scripts or CI | That is `correct`. List it under For correct |
| Editing the installed plugin copy | The next update overwrites it. Edit a checkout of the repository and ship from there |
| A rule line that pushes the file past 80 lines | Count first; propose the line it replaces |
| Renumbering prose rules to fit a new one | Numbers never move. Take the next free number |
| A skill change with no eval expectation | Add the expectation that would have caught it |
| Deleting a rule the user restated | Restated means not followed. Sharpen it or propose a hook |
| Running at the end of a phase without being asked, then applying | Running unasked is fine; applying without a named approval never is |
