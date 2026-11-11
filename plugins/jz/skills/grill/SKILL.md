---
name: grill
description: Use when a plan, design or decision has to be interviewed until nothing is left assumed, before any code is written, or when a new scope needs a spec, glossary and ADRs written as the decisions land. Triggers on requests like "grill me", "grill this plan", "stress-test my thinking", "interview me about", "challenge this design", "settle the design first", "kick off the project", "write a spec", "with docs", "write the glossary and ADRs as we go", or when a coordinating session starts a scope that has no spec yet.
---

# grill

## Overview

Interviews the owner one round at a time until every branch of the design
tree is settled. Facts come from subagents, decisions come from the owner as
lettered options, and nothing is acted on until the owner confirms a shared
understanding. In spec mode it also writes the glossary, the ADRs and a spec
of requirements and steps as each decision lands. How each requirement will
be proven is the `criteria` skill's job, next.

Adapted from the `grilling` and `domain-modeling` skills in
`mattpocock/skills`, MIT, Copyright (c) 2026 Matt Pocock.

## Modes

| Mode | Trigger | Writes |
|---|---|---|
| decision | "grill me", "stress-test this", "challenge this design" | Nothing. The settled tree is in the reply |
| spec | "kick off", "write a spec", "with docs", a coordinating session opening a scope | `docs/specs/<slug>.md`, `CONTEXT.md`, `docs/adr/NNNN-<slug>.md`, a `## Standing orders` section in `AGENTS.md` |

Decision mode is the default.

## Workflow

### Step 1: Read what exists before asking anything

```bash
ls CONTEXT.md CONTEXT-MAP.md AGENTS.md CLAUDE.md docs/specs docs/adr 2>/dev/null
```

Read every file that exists. A question that re-opens a glossary term or an
ADR names it and gives a reason. A reference the owner calls "not the truth",
such as a predecessor repository, is read for facts, never for decisions.

Fan out read-only subagents for every fact the environment holds: what the
code does, which scripts exist, what a dependency exports. The owner is never
asked for something a subagent could look up.

### Step 2: Ask the frontier, one round at a time

Map the plan as a tree of decisions. The frontier is every decision whose
prerequisites are settled. A question that depends on another open question,
or on a subagent still running, waits for a later round.

Number each question. Give three or four lettered options, the
recommendation first with one sentence on why, and the trade-off that decides.
Mark every question `Tier: ADR` or `Tier: below`: ADR when the answer would
earn an ADR by the three tests in Step 4 or is on the ADR-tier list in
Step 6, below otherwise.
A question with one sensible answer is an assumption: state it in the round's
preamble, numbered `A1`, `A2`, and let the owner object.

```markdown
## Round 2

Settled: 1A, 2C, 3A. Waiting on a subagent: what `packages/core` exports, which gates Q6.

Q4. Where does the session live between requests?
  A. In the signed cookie only. Recommended: no store read per request.
  B. In the Store, keyed by an id in the cookie. Revocable at once, one read per request.
  C. Both: the cookie carries the id and a short-lived copy of the claims.
  Decides it: whether logout has to revoke immediately.
  Tier: ADR
```

Then stop and wait. Accept short answers such as `4A 5B`.

### Step 3: Challenge the words as they arrive

| Signal | Response |
|---|---|
| A term that conflicts with `CONTEXT.md` | Name the conflict and ask which meaning is right |
| A vague or overloaded term | Propose one canonical term and list the others as avoided |
| A relationship between concepts | Invent a scenario that probes its edge and ask what happens |
| A claim about the code | Check it and surface a contradiction with `file:line` |

### Step 4: Spec mode, write as decisions land

Be on a task branch in its own worktree first, as the `pr` skill's Worktree
section describes. Write each file the turn its content is settled, never in
a batch at the end.

| Lands | Write |
|---|---|
| A term is resolved | `CONTEXT.md` from `template-context.md`: vocabulary only, no implementation |
| A decision that is hard to reverse, surprising without context, and a real trade-off, all three | `docs/adr/NNNN-<slug>.md` from `template-adr.md`, one paragraph, numbered one above the highest |
| Any decision | One line under the spec's Decisions, with the round and letter, linking its ADR if it has one |
| A rule every later session must follow | A line under `## Standing orders` in `AGENTS.md` |
| An outcome the owner wants | A requirement in the spec |
| A unit of work | A step in the spec |

The spec comes from `template-spec.md`. Its rules:

- **A requirement is an observable outcome**: what someone can see happen,
  not how it's built. "Make it cleaner" is not one; ask what would be
  different, or drop it and say so. Requirements are numbered `R1`, `R2`,
  and numbers never move.
- **A step is a vertical slice**: it can be demoed or checked on its own and
  fits in one fresh session. Prefactoring comes first. Each step lists the
  requirements it serves, the steps that block it, what it owns, the one
  result you'll see, its ADRs, whether the owner reviews it before merge,
  its Risk and its Surfaces.
- **Risk and Surfaces are asked, never assumed.** Put both in the round that
  settles the step, as questions with a recommendation.

  | Line | Value | When |
  |---|---|---|
  | Risk | low | Contained and easy to verify |
  | Risk | medium | Several files or behaviours, or shared code |
  | Risk | high | Data, money, auth, migrations, concurrency, or anything hard to undo |
  | Surfaces | ui | Someone sees the change on a screen |
  | Surfaces | security | Auth, permissions, input reaching a query, shell or HTML, secrets, payments |
  | Surfaces | none | Neither. A step with both reads `ui, security` |

- **Leave the Criteria section empty.** `criteria` fills it, next.

### Step 5: Recompute and repeat

Recompute the frontier after each round, write what landed, and ask the next
round. After twelve rounds, list what's still open and ask whether to go on
or park it under Out of scope.

The session is done when the frontier is empty. Say so, list the assumptions
nobody objected to, and ask the owner to confirm the shared understanding.
Don't act on the design until they do.

### Step 6: Hand back

Decision mode ends with the settled tree, grouped by branch, and the
assumptions list.

Spec mode ends with:

- the files written, one line each
- the ADR-tier list: kinds of decision a later session must bring back as
  options rather than decide alone (public API shape, data model, a new
  dependency, a specification reading, and anything that would earn an ADR)
- "Next: run `criteria` on `docs/specs/<slug>.md`"

Committing the files is the `pr` skill's job, on the owner's word.

### When the owner is handsfree

A brief that says the owner is `handsfree` names a run folder. Everything
above holds, with these differences:

- Write each round to two files in that folder instead of the reply, then
  stop and reply "round <N> written". `round-<N>-questions.md` holds the
  assumptions, the numbered questions, their lettered options in no order
  of preference, the facts each one rests on with `file:line`, the
  trade-off and the `Tier:` mark. It holds no recommendation and no hint of
  one. `round-<N>-recommendations.md` holds one line per question: the
  letter and one sentence.
- Started again with `round-<N>-answers.md`, apply it and continue from the
  spec written so far; never ask a settled question again. `Q4: B` is the
  answer. `Q4: owner` is still open: go on with what doesn't depend on it.
  `A1: object` turns that assumption into a question in the next round. A
  line such as `D3: B` overturns that decision: rewrite the requirements,
  steps and ADR it affects, and name the changed requirements in the reply.
- Number the spec's Decisions as the folder's `decisions.tsv` numbers them,
  ADR-tier ones first, each with the options, every pick and the chosen one:

```markdown
- **D3, ADR tier.** Where the session lives. A cookie only, B the Store, C both. Recommendation B, handsfree B, second opinion B. Chosen: B. ADR-0002.
- **D1.** Name of the claims helper. A `readClaims`, B `parseClaims`. Recommendation B, handsfree A, second opinion A. Chosen: A.
```

- An ADR from one of these decisions takes the model sign-off line of
  `template-adr.md`. The frontier being empty ends the run with the Step 6
  hand-back; the confirmation in Step 5 is the owner's and is not asked of
  the brief's sender.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Asking the owner for a fact the repo holds | Dispatch a subagent |
| A question whose answer depends on one still open | Later round |
| One recommended answer with no alternatives | Three or four lettered options and the trade-off |
| Batching the glossary or spec to the end | Write the turn it's settled |
| An ADR for every decision | All three tests, or it's a Decisions line only |
| A requirement nobody could observe | Ask what would be different, or drop it |
| Writing criteria or acceptance commands in the spec | That's the `criteria` skill's job |
| A step that only builds one layer | Slice vertically, so the step can be checked on its own |
| Acting before the owner confirms | Say the frontier is empty, list the assumptions, wait |
| A step with no Risk or Surfaces line, or one filled in without asking | Ask both in the round that settles the step |
| A recommendation, or the favoured option listed first, in a handsfree questions file | Recommendations go in their own file only |
