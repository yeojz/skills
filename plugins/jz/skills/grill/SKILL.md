---
name: grill
description: Use when a plan, design or decision has to be interviewed until nothing is left assumed, before any code is written, or when a new scope needs its glossary, ADRs and standing orders written as the decisions land. Triggers on requests like "grill me", "grill this plan", "stress-test my thinking", "interview me about", "challenge this design", "settle the design first", "kick off the project", "with docs", "write the glossary and ADRs as we go", or when a coordinating session starts a scope that has no CONTEXT.md or design document yet.
---

# grill

## Overview

Interviews the user about a plan one round at a time until every branch of
the design tree is settled. Facts come from subagents, decisions come from
the user as lettered options, and nothing is acted on until the user confirms
a shared understanding. In kickoff mode it also writes the glossary, the ADRs
for one-way doors, the design document, the standing orders and the first
roadmap rows as each decision lands, never in a batch at the end.

The failure this exists to prevent is a phase that stops halfway because a
decision nobody asked about turns out to matter. Every fork that would block
a worker later is asked here, once.

Adapted from the `grilling` and `domain-modeling` skills in
`mattpocock/skills`, MIT, Copyright (c) 2026 Matt Pocock.

## Modes

| Mode | Trigger | Writes |
|---|---|---|
| decision | "grill me", "stress-test this", "challenge this design", one plan or choice | Nothing. The settled tree is in the reply |
| kickoff | "kick off", "start the project", "with docs", a coordinating session opening a new scope | `CONTEXT.md`, `docs/adr/NNNN-<slug>.md`, `docs/design.md`, a standing-orders section in `AGENTS.md`, rows in `docs/roadmap.md` |

Decision mode is the default. Kickoff mode needs one of its triggers or an
explicit ask for docs.

## Workflow

### Step 1: Read what exists before asking anything

```bash
ls CONTEXT.md CONTEXT-MAP.md AGENTS.md CLAUDE.md CONTRIBUTING.md docs/design.md docs/roadmap.md 2>/dev/null
ls docs/adr 2>/dev/null
```

Read every file that exists. The glossary and the ADRs are the terms and
decisions already made; a question that re-opens one of them is asked only
with the ADR named and a reason.

A reference the user names as "not the truth", such as a predecessor
repository, is read for facts and never for decisions. Say which facts came
from it when they shape a question.

Fan out read-only subagents for every fact the environment holds: what the
code does today, which scripts `package.json` declares, what a dependency
exports, what a specification says. Finding facts is this skill's job. The
user is never asked for something a subagent could look up.

### Step 2: Build the design tree and its frontier

Map the plan as a tree: every decision branches into the decisions that hang
off it. The frontier is every decision whose prerequisites are settled, the
questions that can be asked now without guessing at answers not yet heard.

A question whose answer depends on another question still open belongs to a
later round. A question that waits on a subagent's fact belongs to a later
round too; the rest of the frontier is asked now.

### Step 3: Ask the whole frontier in one round

Number each question. Give three or four lettered options, the recommendation
first with one sentence on why, and the trade-off that decides between them.
A question with a single sensible answer is not a question; state the
assumption in the round's preamble instead and let the user object.

```markdown
## Round 2

Settled so far: 1A, 2C, 3A. Waiting on a subagent: what `packages/core` exports today, which gates Q6.

Q4. Where does the session live between requests?
  A. In the signed cookie only. Recommended: no store read per request, and the Store contract stays small.
  B. In the Store, keyed by a session id in the cookie. Revocable at once, costs a read per request.
  C. Both: the cookie carries the id and a short-lived copy of the claims.
  Decides it: whether logout has to revoke immediately.

Q5. What does `Store` call the unit it saves?
  A. Record. Recommended: it is what the glossary already uses for persisted things.
  B. Entry.
  C. Document.
  Decides it: consistency with the glossary, nothing else.
```

Then stop and wait. Do not answer on the user's behalf and do not start a
later round early. Accept answers in the short form the user prefers,
`4A 5A`, as well as prose.

### Step 4: Challenge the words as they arrive

While the user answers, hold the glossary open:

| Signal | Response |
|---|---|
| A term that conflicts with `CONTEXT.md` | Name the conflict at once: the glossary defines X as this, you seem to mean that, which is it |
| A vague or overloaded term ("account", "config", "entry") | Propose one canonical term and list the others as avoided |
| A relationship between concepts | Invent a concrete scenario that probes its edge and ask what happens |
| A claim about how the code works | Check it against the code and surface a contradiction with `file:line` |

A term is resolved when the user has picked it. In kickoff mode it goes into
`CONTEXT.md` in the same turn.

### Step 5: Kickoff mode, write as decisions land

Before the first write, be on a task branch in its own worktree, as the
`pr` skill's Worktree section describes. Never write these files on the default
branch.

| Decision lands | Write |
|---|---|
| First term resolved | `CONTEXT.md` from `template-context.md`, or the context the topic belongs to when `CONTEXT-MAP.md` exists |
| A decision that is hard to reverse, surprising without context, and the result of a real trade-off, all three | `docs/adr/NNNN-<slug>.md` from `template-adr.md`, numbered one above the highest existing |
| Any other decision | A line in `docs/design.md` under Decisions, with the round and the letter chosen |
| A rule every later session must follow (gate commands, draft then ready, rebase never merge, restricted words, invented data only) | A line under a `## Standing orders` heading in `AGENTS.md` |
| A unit of work with a clear boundary | A row in `docs/roadmap.md` |

`CONTEXT.md` is a glossary and nothing else: no implementation detail, no
spec, no scratch notes. An ADR that fails any of the three tests is not
written; the decision is a design-document line instead.

A roadmap row carries, in this order: depends on, owns (the packages or
files), builds, you see (one observable result), done means (the real gate
commands, the behaviour level the `verify` skill reports, and any
conformance or fixture run), acceptance (the list below), and review gate
(whether the owner reviews it before merge). A field the interview has not
settled is written as `not scoped`, and a row with one stays a question for
a later round rather than a phase to start.

```markdown
### 4. Session cookie

Depends on: 3
Owns: `packages/core/src/session.ts`, `packages/core/test/session.test.ts`
Builds: the signed session cookie and its check on every request
You see: a request with a tampered cookie is answered 401
Done means: `pnpm typecheck`, `pnpm test`; behaviour `live-verified` through the Drive section of `VERIFICATION.md`
Acceptance:
- A tampered cookie is refused with 401. `pnpm test -- -t "tampered cookie"`
- A cookie past its TTL is refused and cleared. Drive step L4 of `VERIFICATION.md`
Review gate: owner reviews before merge
```

The Acceptance list is what the phase proves, one criterion per line: a
sentence a reader can judge, then the command that proves it. The command
is part of the criterion. A line with no command is not accepted: ask for
the command, as lettered options drawn from the repo's scripts, test names
or recipe steps when there is a choice, or drop the line and say so. A
criterion whose command drives the running system cites a Drive step of the
nearest `VERIFICATION.md`, and the phase adds that step to the recipe, so
the recipe stays the one place the drive commands live. The behaviour level
under done means says how far the proof goes; the list says what it proves,
and the `coordinate` skill copies it into the brief and checks every line
against the worker's `verify` block.

Files are created lazily, when there is something to put in them, and
updated in place after that. Committing them is the `pr` skill's job, on
the user's word, after the frontier is empty.

### Step 6: Recompute the frontier and repeat

Each round's answers settle decisions, push the frontier outward and unblock
the questions that depended on them. Recompute, write what landed, and ask
the next round. Bound the session at twelve rounds; past that, list what is
still open and ask whether to continue or to park the rest as `not scoped`
rows.

The session is done when the frontier is empty: every branch visited and
nothing left silently assumed. Say so, list the assumptions that were stated
in preambles and not objected to, and ask the user to confirm the shared
understanding. Do not act on the design until they do.

### Step 7: Hand back

In decision mode, the reply ends with the settled tree: each decision and the
letter chosen, grouped by branch, and the assumptions list.

In kickoff mode, the reply ends with:

- The files written, with a one-line summary of each.
- The ADR-tier list: the kinds of decision that a later session must bring
  back to the user as options rather than decide alone. Public API shape,
  data model, a new dependency, a specification interpretation and anything
  that would earn an ADR are the default members.
- The first roadmap row that is fully scoped, with every acceptance
  criterion carrying its command, named as where the coordinating session
  starts.
- Any row still marked `not scoped`, with the question that would scope it.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Asking the user for a fact the repo or a dependency holds | Dispatch a subagent. Facts are the skill's job, decisions are the user's |
| Asking a question whose answer depends on one still open | It belongs to a later round. Recompute the frontier after each round |
| One recommended answer with no alternatives | Three or four lettered options, recommendation first with its reason, and the trade-off that decides |
| Asking a question with one sensible answer | State it as an assumption in the round preamble and let the user object |
| Batching the glossary until the end | Write `CONTEXT.md` the turn a term is resolved |
| An ADR for every decision | All three tests or no ADR. The rest is a design-document line |
| Implementation detail in `CONTEXT.md` | It is a glossary. Detail goes to `docs/design.md` |
| Treating a predecessor repository as the design | Read it for facts, name them, decide fresh |
| Acting on the plan before the user confirms | Say the frontier is empty, list the assumptions, wait |
| Starting a phase whose roadmap row has a `not scoped` field | The field is a question. Ask it, or leave the row for later |
| An acceptance criterion written as a sentence alone | The command is part of the criterion. Ask for it as lettered options from the repo's scripts, tests or recipe steps, or drop the line |
| An acceptance command that drives the system typed into the roadmap | Cite a Drive step of the nearest `VERIFICATION.md` and add the step in the phase; the recipe is the one place drive commands live |
| Writing kickoff files on the default branch | Branch first, as the `pr` skill's Worktree section describes |
| Committing the files inside this skill | Offer `pr` when the frontier is empty |
| Emoji or symbols in the round format | Plain numbered questions and lettered options |
