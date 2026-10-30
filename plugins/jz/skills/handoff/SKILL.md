---
name: handoff
description: Use when a session is running out of context and the work has to continue somewhere else. Triggers on requests like "write a handoff", "handoff to another session", "context is getting low", "we are reaching context limits, can we handoff", "prepare a handover prompt", "write me a prompt to continue this in a new session", "pause and hand off", "do a summary, handoff and clear context", or when the user is about to clear and needs the state captured first.
---

# handoff

## Overview

Captures the state of an in-flight session as two artefacts: a full handoff
document under `docs/plans/`, and a short paste-ready prompt for a fresh
session. Every fact in both comes from `git` and from files on disk, never from
recollection, because the point of a handoff is to survive the loss of the
conversation that produced it.

## Output shapes

Produce both by default. The short prompt goes last so the user can copy it
without scrolling.

| Shape | Where it goes | When it is the only output |
|---|---|---|
| Full handoff document | `docs/plans/YYYY-MM-DD-HHMM-handoff-<slug>.md` | Never on its own unless the user says "document only" |
| Short paste-ready prompt | Fenced block in the reply, last thing in the message | The user asked for "a prompt", "a handover prompt", or "2-3 instructions" |

Read the wording of the request:

| User asked | Produce |
|---|---|
| "write a handoff", "pause and write a handoff", "do a context handoff" | Document, then short prompt |
| "handoff to a new session", "we are reaching context limits" | Document, then short prompt |
| "write me a prompt to continue this", "prepare a handover prompt to copy" | Short prompt only, plus a one-line note of where the detail lives |
| "quick 2-3 instruction summary, handoff and clear context" | Short prompt only, three instructions maximum |

When only the short prompt is asked for, still run the state-gathering commands
in Step 1. The prompt has to name a real branch and a real next command.

## Workflow

### Step 1: Gather state from the repo

Run all of these before writing a single line. A handoff written from memory is
the exact failure this skill exists to prevent.

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git branch --show-current
git status -sb
git status --short
git log --oneline "$base..HEAD"
git diff --stat @{upstream} 2>/dev/null || git diff --stat "$base...HEAD"
git rev-list --left-right --count @{upstream}...HEAD 2>/dev/null
gh pr view --json number,url,state,isDraft 2>/dev/null
```

`$base` is the default branch read from the remote, so the same commands work
when it is `master`, `develop` or anything else.

Record the answers verbatim. In particular:

| Fact | Command | Goes in |
|---|---|---|
| Current branch | `git branch --show-current` | Repo and branch table, short prompt |
| Pushed or not, ahead/behind counts | `git status -sb`, `git rev-list --left-right --count @{upstream}...HEAD` | Repo and branch table |
| Uncommitted work | `git status --short` | Repo and branch table, Files touched |
| Commits since the branch point | `git log --oneline "$base..HEAD"` | Completed |
| Size and shape of the change | `git diff --stat` against the upstream | Files touched |

If there is no upstream, `@{upstream}` fails. Fall back to
`git diff --stat "$base...HEAD"` and record the branch as not pushed.

If the branch is the repo's default branch, say so plainly in the handoff. The
next session has to branch before editing.

### Step 2: Start from the template

Read `template.md` from this skill's directory, the directory this `SKILL.md`
was loaded from, and fill it in. Do not restructure it and do not add sections
it does not have.

Write to:

```bash
docs/plans/$(date +%Y-%m-%d-%H%M)-handoff-<slug>.md
```

The slug is kebab-case and names the work, for example
`docs/plans/2026-09-10-2231-handoff-auth-refresh-tokens.md`.

### Step 3: Completed work carries evidence

Every row in Completed has three cells: the item, the command that proves it,
and that command's actual result.

| Item | Evidence command | Result |
|---|---|---|
| Token refresh endpoint | `pnpm --filter api test` | `42 passed` |
| Types compile | `pnpm typecheck` | exit 0 |

Rules:

- The result cell holds real output that was seen in this session, not an
  expectation.
- If the command was never run, the item does not belong in Completed. Move it
  to Remaining, or list it under Completed with the status `unverified` and the
  command the next session must run.
- A commit existing is evidence that code was written, not that it works. Cite
  the test or typecheck run, not the sha.

State unverified items explicitly, for example:

```markdown
| Rate limit middleware | `pnpm --filter api test` | unverified, written but never run |
```

Do not silently promote an unverified item to done because it looks finished.

### Step 4: Remaining work in order

An ordered list. Each item carries enough that a fresh session needs nothing
from this one:

1. What to do, in one imperative sentence.
2. The repo-relative file paths it touches.
3. The decision already made, so the next session does not re-litigate it.
4. The acceptance check: the command to run and the result that means done.

Example row:

```markdown
2. Add refresh-token rotation to the session store. Files:
   `packages/auth/src/session-store.ts`, `packages/auth/test/session-store.test.ts`.
   Decision already made: rotate on every use, not on expiry only.
   Proven by `pnpm --filter auth test` showing the rotation suite passing.
```

Mark items that can run in parallel. That drives Step 6.

### Step 5: Carry forward decisions from the trail, not from memory

A session run under `coordinate` has its decisions on disk already:
`decisions.tsv` in the group's notes folder, one row per fork, verdict and
relay, with a pointer to the evidence. Read it before writing a word of this
section; recollection is what the context clear is about to destroy.

```bash
notes="<notes folder the brief or the app named for this group of sessions>"
ls "$notes/decisions.tsv"
column -t -s $'\t' "$notes/decisions.tsv"
```

The ledger is append-only, so a decision can have several rows: the fork as
it was asked, then the answer, written by `coordinate` with the same `unit`
and `decision` text. The latest row for a `unit` and `decision` pair is the
state; the earlier rows are history. Reconcile before classifying anything:

```bash
awk -F'\t' 'NR > 1 { last[$2 FS $4] = $0 } END { for (k in last) print last[k] }' "$notes/decisions.tsv" | sort
```

Carry rows forward by quoting them, never by paraphrase. Classify each
decision by its latest row:

| Latest row | Goes in the handoff as |
|---|---|
| Kind `fork`, `result` carries the letter chosen | The choice made, with the row's `when` and `evidence` so the next session can find it; the fork row it answers is quoted as history, not reopened |
| Kind `fork`, `result` empty, no later row for the pair | An open question in Step 6, options as the row states them |
| Kind `verdict` or `relay` | The state of that PR, quoted into Remaining or Completed |
| Any other kind with `result` empty | A decision whose outcome the next session must still check, named as such |

A fork row with an empty `result` is open only when no later row for the same
`unit` and `decision` carries an answer: the raw listing shows the question,
the reconciled listing shows whether it was settled.

Then add the decisions and constraints the ledger does not carry: the ones
agreed in this session that exist nowhere on disk. For each one, name where
it should be recorded permanently:

| Decision | Source | Where it belongs |
|---|---|---|
| Rotate the refresh token on every use | `decisions.tsv` 2026-10-30T09:12 unit 7 | `docs/adr/0004-token-rotation.md` |
| Coverage runs need both `--filter` and `--project` | unlogged | `CLAUDE.md`, verification section |
| No `enum`, use string literal unions | unlogged | `CLAUDE.md` or `AGENTS.md`, code style |

When there is no `decisions.tsv`, say so in one line in the handoff, fill the
table from the conversation with every row marked `unlogged`, and tell the
next session the list is what this session remembers, not a trail it kept. Do
not create the file during the handoff: a ledger started at handoff reads as
one that was kept all along. If the work continues under `coordinate`, that
session opens it.

Do not write to `CLAUDE.md` or `AGENTS.md` as part of the handoff. Note the
line that should be added and let the user decide.

### Step 6: Open questions

Only questions the user still owes an answer on. Phrase each as a question with
the options already narrowed, and say what is blocked until it is answered.

```markdown
| # | Question | Options | Blocked work |
|---|---|---|---|
| 1 | Where does the refresh token live? | a) httpOnly cookie. b) response body, recommended, the mobile client cannot read cookies. | Remaining item 3 |
```

If there are none, write "None". Do not manufacture questions to fill the
section, and do not answer them unilaterally.

### Step 7: Write the paste-ready prompt

A fenced block, last in the reply. Self-contained: someone pasting it into an
empty session with no memory of this one must be able to start.

It must contain:

| Element | Example |
|---|---|
| Absolute repo path | `<absolute path to the repo>` |
| Branch, and the base it came from | `on branch feat/auth-refresh-tokens, based on <default-branch>` |
| Where the detail lives | `Read docs/plans/2026-09-10-2231-handoff-auth-refresh-tokens.md first` |
| The first command to run | `Start by running: pnpm --filter auth test` |
| The branch-first rule | `Create a branch before editing; never edit on the default branch` |
| The notes folder and its ledgers, when the session had them | `Notes folder: <absolute path>; read units.tsv and decisions.tsv there first` |

It must not contain a reference to something the next session cannot see. No
"the plan we discussed", no "as agreed earlier", no "continue where we left
off". Name the file path instead.

Short form, when the user asked for two or three instructions:

```text
Resume in <absolute path to the repo> on branch feat/auth-refresh-tokens.
Read docs/plans/2026-09-10-2231-handoff-auth-refresh-tokens.md first; it has the
state, the remaining work in order, and the acceptance check for each item.
Start by running pnpm --filter auth test to confirm the baseline, then do
Remaining item 1. Do not claim anything passes without pasting the output.
```

When the remaining work is parallelisable, say so in the prompt and say how to
split it:

```text
Remaining items 2, 3 and 4 are independent: different files, no shared state.
Fan them out to one subagent each and run them concurrently. Item 5 depends on
all three and runs after they land.
```

Only claim parallelism when the items genuinely touch different files. Two items
editing the same file are sequential.

### Step 8: Clipboard, on macOS

A prompt that has to be pasted into another session is worth putting on the
clipboard. Offer it, and run it when the answer is yes:

```bash
pbcopy < /tmp/handoff-prompt.txt
```

Or pipe the prompt text straight in:

```bash
printf '%s' "<prompt text>" | pbcopy
```

If the request already said "copy to clipboard", run it without asking again.
On a non-macOS platform, say `pbcopy` is unavailable rather than substituting a
tool that may not be installed.

### Step 9: Do not clear, do not commit

Clearing context is the user's action. Say the handoff is ready and stop.

Handoffs and plans live under `docs/plans/` and are not committed. If a commit
happens in the same turn, exclude the path:

```bash
git reset -- docs/plans .plans .claude
```

If `docs/plans/` is not in `.gitignore`, mention that once. Do not edit
`.gitignore` unless asked.

### Step 10: Report

State plainly:

- The handoff file path
- The branch, whether it is pushed, and the ahead/behind counts
- How many completed items carry evidence, and how many are flagged unverified
- How many remaining items, and which are parallelisable
- Whether the prompt was copied to the clipboard
- That clearing context is the user's next action

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing the handoff from memory of the session | Run the Step 1 git commands first and quote their output. Recollection is what a context clear destroys. |
| Listing work as done with no evidence command | Every Completed row needs the command and its real result. No command means it is Remaining or `unverified`. |
| Treating a commit sha as proof that something works | A commit proves code was written. Cite the test or typecheck run. |
| A prompt that says "the plan we discussed" | The next session cannot see it. Name the repo-relative file path. |
| Committing the handoff file | Handoffs live in `docs/plans/` and stay uncommitted. Run `git reset -- docs/plans`. |
| Omitting the absolute repo path or branch from the prompt | The prompt must be self-contained. Name both, plus the first command to run. |
| Recording "not pushed" without checking | Read `git status -sb` and the ahead/behind counts before writing that row. |
| Remaining items with no acceptance check | Each item states the command and the result that means done. |
| Losing session-only decisions | Carry them forward in Step 5 and name where they should be recorded permanently. |
| Writing the decisions section from memory when `decisions.tsv` exists | Read the ledger and quote its rows. Memory fills the table only when there is no trail, and then every row says `unlogged`. |
| Reopening a fork the ledger already answers | Reconcile by `unit` and `decision` first. The latest row is the state; an earlier empty `result` under a later answer is history. |
| Creating `decisions.tsv` at handoff to have a trail to point at | A ledger started at handoff is recollection in a file. Say there is none; `coordinate` opens it in the next session. |
| Answering the open questions on the user's behalf | Present lettered options with a recommendation and leave them open. |
| Clearing context after writing the handoff | That is the user's action. Stop after reporting. |
| Claiming parallelism for items that touch the same file | Only fan out items with genuinely disjoint file sets. |
| Producing only the document when the user asked for a prompt | Read the request wording; the short prompt is what gets pasted. |
| Burying the prompt mid-reply | It goes last, in one fenced block, ready to copy. |
