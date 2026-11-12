---
name: handoff
description: Use when a session is running out of context and the work has to continue somewhere else. Triggers on requests like "write a handoff", "handoff to another session", "context is getting low", "we are reaching context limits, can we handoff", "prepare a handover prompt", "write me a prompt to continue this in a new session", "pause and hand off", "do a summary, handoff and clear context", or when the user is about to clear and needs the state captured first.
---

# handoff

## Overview

Captures an in-flight session as a handoff document under `docs/plans/` and
a short paste-ready prompt for a fresh session. Every fact comes from git
and files on disk, never from recollection, because the point is to survive
losing the conversation.

In Claude Code, an auto-compaction continues a running flow in the same
session from its folder and ledgers, so a context limit alone is no reason
to hand off there. This skill moves work to a new session or to a person.
When this session wrote a `docs/plans/*/flow.md`, take the flow and its
folder from it, and Remaining's order from that folder's ledgers.

| Request | Produce |
|---|---|
| "write a handoff", "hand off to a new session", "context is low" | The document, then the prompt |
| "write me a prompt to continue", "a handover prompt to copy" | The prompt only, plus where the detail lives |
| "a quick 2-3 instruction summary" | The prompt only, three instructions at most |

Even for a prompt only, gather the state first: it must name a real branch
and a real first command.

## Workflow

### Step 1: Gather state from git

```bash
base="$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\)[[:space:]]*HEAD$|\1|p')"
git branch --show-current; git status -sb; git status --short
git log --oneline "origin/$base..HEAD"
git diff --stat @{upstream} 2>/dev/null || git diff --stat "origin/$base...HEAD"
git rev-list --left-right --count @{upstream}...HEAD 2>/dev/null
gh pr view --json number,url,state,isDraft 2>/dev/null
```

Record the answers verbatim. No upstream means not pushed. On the default
branch, say so plainly: the next session must branch first.

### Step 2: Fill the template

Fill `template.md` from this skill's folder into
`docs/plans/$(date +%Y-%m-%d-%H%M)-handoff-<slug>.md`, without adding or
removing sections.

**Completed**: each row is the item, the command that proves it, and that
command's real result from this session. A commit proves code was written,
not that it works. Something never run goes under Remaining, or stays here
marked `unverified` with the command to run. When the work serves a spec,
cite its criteria by id and status.

**Remaining**, in order, each with: what to do in one sentence, the files,
the decision already made, and the check that means done (a spec
criterion's check when there is one). Mark which items can run in parallel,
and only when their files don't overlap.

**Decisions.** Under `coordinate`, the notes folder's `decisions.tsv` holds
them; read it rather than remembering. It's append-only, so the latest row
for each `unit` and `decision` is the state:

```bash
notes="<notes folder>"
column -t -s $'\t' "$notes/decisions.tsv"
awk -F'\t' -v unit=2 -v decision=4 'NR == FNR { if (FNR > 1) last[$unit FS $decision] = FNR; next } FNR == last[$unit FS $decision]' "$notes/decisions.tsv" "$notes/decisions.tsv" | sort
```

| Latest row | Goes in as |
|---|---|
| `fork` with a letter in `result` | The choice, with its `when` and `evidence` |
| `fork` with `result` empty | An open question |
| `verdict` or `relay` | That PR's state, under Completed or Remaining |
| Anything else with `result` empty | Something the next session must check |

Quote rows; don't paraphrase. Add decisions agreed in this session that
exist nowhere on disk, marked `unlogged`, each with where it should be
recorded for good (an ADR, the spec's Decisions, `AGENTS.md`). With no
`decisions.tsv`, say so and mark every row `unlogged`; never create the
ledger now. Never edit `AGENTS.md` or `CLAUDE.md` here: name the line and
let the owner decide.

**Open questions**: only those the owner still owes, as lettered options
with a recommendation and what each blocks; or "None". Never answer them.

### Step 3: Write the prompt

A fenced block, last in the reply, that works for someone with no memory of
this session:

- the absolute repo path, and the branch and its base
- the handoff file to read first
- the first command to run
- branch before editing; never edit the default branch
- the notes folder and its ledgers, when there are some
- how to split parallel items, when there are some, and which item waits for which

Never "the plan we discussed" or "continue where we left off": name the
file.

```text
Resume in <absolute repo path> on branch feat/auth-refresh-tokens.
Read docs/plans/2026-09-10-2231-handoff-auth-refresh-tokens.md first; it has the
state, the remaining work in order, and the check for each item.
Start with pnpm --filter auth test to confirm the baseline, then do Remaining 1.
Paste output before claiming anything passes.
```

On macOS, offer to copy it (`printf '%s' "<prompt>" | pbcopy`), and do it
without asking if the request said so. Elsewhere, say `pbcopy` isn't there.

### Step 4: Stop

Clearing context is the owner's action. Never commit the handoff; if a
commit happens in the same turn, `git reset -- docs/plans .plans .claude`.
Report the file path, the branch and whether it's pushed, how many
completed items have evidence and how many are `unverified`, how many
remain and which are parallel, and whether the prompt was copied.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing from memory | Run the Step 1 commands first and quote them |
| A completed item with no command | It's Remaining, or `unverified` |
| A commit sha as proof it works | Cite the test or typecheck run |
| "The plan we discussed" in the prompt | Name the file path |
| Decisions from memory when `decisions.tsv` exists | Quote its latest rows |
| Creating `decisions.tsv` at handoff | Say there is none |
| Answering the open questions | Leave them as options |
| Parallel items that share a file | Sequential |
| Committing the handoff or clearing context | Neither is this skill's to do |
