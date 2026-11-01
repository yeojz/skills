---
name: criteria
description: Use when a spec's requirements need acceptance criteria, scenarios and checks written before any building starts, or when a requirement changed and its criteria must follow. Triggers on requests like "write the criteria", "write acceptance criteria for this spec", "how will we know it works", "define done", "what are the pass conditions", "add criteria for R3", "R2 changed, update its criteria", "write the evals", or when grill hands back a spec with an empty Criteria section, or implement stops on a requirement with no criterion.
---

# criteria

## Overview

Turns each requirement in a spec into acceptance criteria. Each criterion is
a scenario, what counts as passing, and the check that decides it. Every criterion is checked once before building
starts, so nothing is recorded as a proof that couldn't have failed. The
owner signs the criteria off once; `implement` then builds against them.

## Workflow

### Step 1: Read the spec and what the repo can check

```bash
ls docs/specs/ CONTEXT.md docs/adr VERIFICATION.md 2>/dev/null
cat package.json 2>/dev/null | jq -r '.scripts // {} | keys[]'
grep -E '^[A-Za-z0-9_-]+:' Makefile 2>/dev/null | cut -d: -f1
```

Read the spec in full, the glossary and the ADRs it links. The scripts,
the Makefile and the nearest `VERIFICATION.md` say which check types this
repo supports. Never invent a command it doesn't declare.

### Step 2: Pick the seam

For each requirement, find where its outcome can be observed: the highest
existing seam (a public function, a CLI, an HTTP route, a rendered page)
rather than an internal one. Prefer seams the repo already tests through,
and as few seams across the spec as possible. Say which seam each
requirement uses.

### Step 3: Write the criteria

One or more per requirement, numbered `C<r>.<n>`, in the spec's Criteria table:

| ID | Req | Scenario | Passes when | Check | Status |
|---|---|---|---|---|---|
| C2.1 | R2 | Given a signed cookie, when one byte is changed and the request sent | 401, and the cookie is cleared | test: `pnpm test -- -t "tampered cookie"` | not written |
| C2.2 | R2 | A cookie past its TTL | 401 | drive: Drive step L4 of `VERIFICATION.md` (added by the step) | not written |
| C3.1 | R3 | The README quickstart | A new user can run every command as written | inspection: run each command in a fresh clone; all exit 0 | not met |

Choose the check by what the repo supports, strongest first:

| Check | Use when | The cell holds |
|---|---|---|
| test | The repo has a test runner | The exact test command and the test's name; `implement` writes the test |
| command | No test fits, but a script, lint, build or grep can fail | The exact command and the output that means pass |
| drive | The outcome only shows in the running system | A Drive step of the nearest `VERIFICATION.md`; adding the step is part of the work |
| inspection | Nothing can run it | What to read or do, and the written standard a reviewer judges against |

The check is part of the criterion. Without one it is only a wish: offer checks as lettered options from the repo's scripts, tests or
recipe steps, or say the requirement can't be evaluated yet.

A requirement with no observable outcome can't get a criterion. Send it back to
`grill` with the question that would settle it; don't invent a criterion.

### Step 4: Check each one before building

Run every check that can run now and record the result:

| Result | Status |
|---|---|
| The check runs and fails | `fail` |
| An inspection shows the outcome is absent | `not met` |
| A test check whose test doesn't exist yet, or a drive check whose Drive step isn't in `VERIFICATION.md` yet | `not written` |
| The check already passes | Stop. Either the requirement is already met, or the criterion can't tell the difference; rewrite it or tell the owner |

```bash
pnpm test -- -t "tampered cookie"; echo "exit=$?"
```

### Step 5: Sign-off

Show the table and the seam per requirement, and wait for the owner's yes.
On a yes, set the spec's status line to `criteria signed off <YYYY-MM-DD>`.

### When a requirement changes

Re-enter at Step 2 for that requirement only. Rewrite its rows and keep
their IDs; mark a removed row `(dropped: <reason>)` rather than renumbering.
Get the owner's yes on the changed rows.

## Common Mistakes

| Mistake | Fix |
|---|---|
| A criterion with no check | The command is part of the criterion; offer options or say it can't be evaluated yet |
| An invented test command | Use the repo's scripts, tests and recipe steps only |
| Testing an internal function when a public seam exists | Use the highest existing seam |
| A criterion that already passes before the build | It can't fail, so it proves nothing; rewrite it |
| Inventing a criterion for a vague requirement | Send it back to `grill` |
| Writing the test code here | `criteria` names the test; `implement` writes it and watches it fail |
| Renumbering after a change | IDs never move; drop with a reason |
