---
name: handsfree
description: Use when the owner wants a skill run without stopping for its design questions, or overturns a decision that was made for them. Triggers on requests like "handsfree grill", "handsfree criteria docs/specs/x.md", "handsfree coordinate docs/specs/x.md", "handsfree factory docs/specs/x.md", "run it handsfree", "go handsfree on", "decide the forks without me", "answer for me", "D3: B", or when intake runs grill and criteria on a request the owner named.
---

# handsfree

## Overview

Wraps the command the owner names and answers that skill's design questions
in the owner's place, as a second assessor: it forms its own pick on every
question before it reads the recommendation, asks a second opinion where the
rules call for one, and logs every decision with a number the owner can
overturn. It never answers a question this session framed, and it never
answers a sign-off, a merge or a remote write that asks.

## Workflow

### Step 1: Open the run folder

The command is everything after the word `handsfree`. The slug is the spec
file's basename without `.md`, or a slug of the request when no spec exists
yet. The folder is never committed.

```bash
run="docs/plans/handsfree-<slug>"; mkdir -p "$run" || echo "cannot create $run"
[ -f "$run/decisions.tsv" ] || printf 'number\tround\tquestion\ttier\trecommendation\town pick\tsecond opinion\tdecision\treason\n' > "$run/decisions.tsv"
ls "$run"; tail -5 "$run/decisions.tsv"
```

A folder that already holds rounds is a run to continue: the next round is
one above the highest answers file, and the next decision is one above the
last `D<n>`. If the folder can't be created, start nothing.

Overwrite `$run/next.md` with the file-write tool when the run starts and
after each round, never appending: `flow: handsfree`; `state:` `running`,
`waiting-owner` while Step 6 holds questions, or `done` after Step 9; `cwd:`
this session's absolute working directory; `step: round <N>`; `next:` one
sentence; `resume: ls <run>; tail -5 <run>/decisions.tsv` with the folder
written out; `updated:`. Only this session writes it, never the asking
skill's subagent.

### Step 2: Start the asking skill

| Wrapped skill | Who asks | How a round reaches this session |
|---|---|---|
| `grill`, `criteria`, any other skill that interviews | A subagent running that skill, at the tier `rules/models.md` gives the job | It writes the two round files and stops |
| `coordinate` | The workers; this session also loads `coordinate` and runs it | An ADR-tier fork arrives as the two round files |
| `factory` | The builders; this session also loads `factory` and runs it | A job whose build ends in a fork, with its fork file |

Put these lines in the subagent's brief, and in every phase brief under
`coordinate`:

```text
Your owner is handsfree. Write each round of questions to
<absolute run folder>/round-<N>-questions.md, with no recommendation in it,
and your recommendations to round-<N>-recommendations.md, then stop and
reply "round <N> written". You are started again with round-<N>-answers.md.
A sign-off is never asked here: report "ready for sign-off" and stop.
```

A worker that stops on a fork keeps building what doesn't depend on it.
Forks that arrive together share one round. Under `factory`, have a light
tier subagent copy the job's fork file into the two round files, the
builder's recommendation and its reasons into the recommendations file only,
so this session reads the question before any recommendation.

A fork below the ADR tier under `coordinate` or `factory` follows that
skill's own rule. A design question that comes up in this session itself is
not answered here: start a subagent at the strong tier to frame it as a
round with options, facts and a recommendation, then treat it like any
other round.

### Step 3: Write your own pick first

Read `round-<N>-questions.md` and nothing else from the round. Work from the
facts it gives. Below the ADR tier, do no research of your own; a missing
fact is a line in the answers file asking the skill for it. Write
`round-<N>-picks.md` before opening the recommendations file:

```markdown
Q4: B. Logout has to revoke at once, and R3 already reads the store per request.
Q5: owner. Adds a queue service the repository does not use yet.
Q6: A. Tier raised to ADR: the response shape is public.
A1: stands.
A2: object. The spec's R2 names two tenants, so one schema per tenant is not the only reading.
```

- Check each `Tier:` mark. Raise `below` to `ADR` when the answer would earn
  an ADR or is on the spec's ADR-tier list. Never lower one.
- Mark a question `owner` when it is one of the three kinds in Step 6.
- An assumption gets no pick and no second opinion. Let it stand, or object
  with the reason; an objection goes back in the answers file and the skill
  asks it as a question in a later round.

Then read `round-<N>-recommendations.md`.

### Step 4: Apply the decision rules

| Tier | The picks | Outcome |
|---|---|---|
| below | Your pick matches the recommendation | Decided |
| below | They differ | A second opinion; the option two of the three chose is decided, and the dissent is logged in the reason |
| below | Three different picks | The owner |
| ADR | Any | A second opinion, always |
| ADR | The recommendation, your pick and the second opinion all match | Decided |
| ADR | Any one differs | The owner |

A pick that matches the recommendation is still yours: the picks file holds
your reason, written before you read theirs.

### Step 5: Ask the second opinions, once per round

Collect every question in the round that needs one, then send at most two
requests, one per row, both in one batch. Never send one request per
question.

| Questions | Goes to | Research |
|---|---|---|
| Below the ADR tier, picks differ | The assessor thread: one per run, standard tier, the other family where present | No. It reads the spec, the glossary and the ADRs once, then works from the facts in the questions file |
| ADR tier | A fresh session per round, top tier, the other family where present | Yes, its own |

Fill `template-second-opinion.md` for each. The brief carries the questions
file and the question numbers, never a recommendation, your pick, or who
disagreed with whom. Each appends its picks to `round-<N>-second.md` and
replies with one line per question.

After the round is decided, send the assessor thread the decisions alone,
such as `D7: B`, so its later picks stay consistent. When it reports half
its context used, retire it and start a new one whose first read is
`decisions.tsv`. With no other family present, both run on this family at
the same tiers.

### Step 6: Collect what is the owner's

Three kinds of question are never decided here:

- one whose chosen option would add a package, service or tool the
  repository does not use yet
- one only the owner can answer: intent the repository cannot reveal
- an ADR-tier question whose three picks do not all match, or any question
  the rules in Step 4 leave unsettled

Append each to `owner-questions.md` with its lettered options and every pick
in one line each, with no recommendation of your own added. Write
`Q5: owner` in the answers file and go on: the asking skill continues with
everything that does not depend on the answer. Ask the owner once, with the
whole file, when nothing else can proceed or the skill reaches its end. Log
the owner's answer as a decision with `owner` in the reason, and pass it on
in their words.

### Step 7: Write the answers, log, start the skill again

```markdown
Q4: B
Q5: owner
Q6: A
A2: object. R2 names two tenants.
```

Save that as `round-<N>-answers.md`. Append one row per decided question to
`decisions.tsv`: the next `D<n>`, the round, the question with its lettered
options, the tier, the three picks with `none` where no second opinion was
asked, the decision, and the reason. The file is append-only.

Start the asking skill again with the answers file: a fresh subagent that
reads the spec written so far and the run folder, since the state is in the
files. Under `coordinate`, relay the answers to the worker and name each one
in the next report to the owner. Under `factory`, pass the answer back
through the job script's `answer` command; a hard escalation condition or a
blocked job still goes to the owner.

An ADR written from one of these decisions carries the model sign-off line
from grill's `template-adr.md`: `(C)` the session running handsfree, `(W)`
the asking skill's session, `(R)` the second opinion.

### Step 8: Leave the owner's actions to the owner

Never answer, on any skill's behalf: a sign-off, a merge, marking a pull
request ready, a force push, or any other remote write that asks. The guards
ask the owner for ready and force pushes and deny merges outright, and a
sign-off is the owner's own reply; nothing else answers any of them.
`criteria` ends at "ready for sign-off": show the owner its table and wait.
On their yes, start `criteria` again with their words so it sets the status
line. Under `intake`, the owner's approval of the intake spec is that yes.

### Step 9: Report, and take an overturn

Report every decision to the owner, one line each, ADR-tier ones first:

```text
D7 (ADR tier) span format: B, line and column. Recommendation B, handsfree B, second opinion B.
D8 helper name: A, readClaims. Recommendation B, handsfree A, second opinion A; dissent: B matches the older module.
```

A spec written through handsfree lists the same decisions under its
Decisions heading, with the options, every pick and the chosen one. The
owner overturns one by number and letter:

```text
D7: A
```

Append a row for `D7` with the new decision and `overturned by the owner`
as the reason. Write the line and the owner's words to the next answers
file and start `grill` again with it, then `criteria` for each requirement
that changed. Ask for approval or sign-off again only after the affected
requirements, criteria and steps are rewritten. Never edit the spec from
this session.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Opening the recommendations file to "save time" before the picks file exists | Picks first, from the questions file alone |
| Deciding an ADR-tier question because your pick matched the recommendation | Three matching picks, or the owner |
| One second opinion request per question | One request per round to the assessor thread, one to a fresh top tier session |
| Pasting the recommendation, or "the skill and I disagree", into the second opinion brief | Questions, options, facts and constraints only |
| Answering a question this session framed | A subagent frames it, then the round runs as usual |
| Deciding a question whose chosen option adds a dependency | `owner-questions.md`, whatever the picks say |
| Asking the owner each question as it comes up | Collect them; ask once; keep the rest moving |
| Saying yes to a sign-off, a ready or a merge for the owner | Stop and show the owner; hooks ask for remote writes |
| Rewriting the spec after an overturn | Start the asking skill again with the answer |
