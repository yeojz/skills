<!--
Filled by the intake skill for one request, or one batch, and shown to the
owner as a single screen. Copy requirements, criteria, options and output
from the files as written; reword nothing. Leave out the bug section for a
request that is not a bug, and the batch section for a single request.
Delete this comment before showing it.
-->

# Approval: <spec title>

Spec: `docs/specs/<slug>.md`. Status: <the spec's own status line, read with grep; it must read draft here>, waiting for your approval.
Request: <typed text, a failing command, or issue <n>>, saved in `<notes folder>/request.md`.
Outcome: Accept. <Why, in one line.>

## Problem

<Who has the problem and what it costs them, as the spec states it.>

## Cause and reproduction

Cause: `<file>:<line>`. <What is wrong there, and where the bad value first appears.>

Reproduced on `<sha>`, <k> of 3 runs failed:

```bash
<the failing command>
```

```text
<the failing lines, pasted from the log, with the exit code>
```

## Requirements

- **R1 <Name>.** <As the spec has it. For a bug it names the cause and says the fix removes it there.>

## Criteria

| ID | Req | Scenario | Passes when | Check | Seen failing |
|---|---|---|---|---|---|
| C1.1 | R1 | <scenario> | <pass condition> | <test, command, drive or inspection, with its command> | <fail, not met or not written, as `criteria` recorded it> |

## Steps

| Step | Serves | Blocked by | Owns | Risk | Surfaces | Review gate | Factory-eligible |
|---|---|---|---|---|---|---|---|
| 1: <title> | R1 | none | <the paths the step may edit, in backticks; a step that names none is not eligible> | <low, medium or high> | <none, ui, security> | <none, or owner reviews before merge> | <yes, or no with the reason> |

## Requests in this batch

| Request | Outcome | Step |
|---|---|---|
| 1: <the request in a few words> | Accept | Step 1 |
| 2: <the request in a few words> | Reject: <reason and evidence> | none |

## Out of scope

- <What the spec leaves out, and why.>

## Decisions made for you

ADR-tier decisions come first. Each shows the options, every pick and the
letter that was chosen.

### D1 (ADR-tier): <the question>

- A. <option>
- B. <option>
- C. <option>
- Picks: recommendation <letter>, handsfree <letter>, second opinion <letter>
- Chosen: <letter>. <The reason, in one sentence.>
- Rests on it: <the requirements, criteria and steps that change if you overturn it>

### D2: <the question>

- A. <option>
- B. <option>
- Picks: recommendation <letter>, handsfree <letter>, second opinion <letter, or not asked>
- Chosen: <letter>. <The reason, in one sentence.>
- Rests on it: <the requirements, criteria and steps that change if you overturn it>

## Needs the owner

<None, or each open decision by number with its options and each pick, and no recommendation. The spec cannot be approved while one is listed here.>

## Your reply

Nothing is built and the status stays `draft` until you answer. Reply with
one of:

- `ok` to approve the spec as shown. The status becomes `criteria signed off <date>`.
- `D3: B` to overturn a decision by its number and letter. Several fit in one reply: `D1: C, D3: B`. The affected requirements, criteria and steps are rewritten and this screen is shown again.
- `drop` to stop here. The spec stays a draft and nothing is built.
- An edit in your own words, for anything the letters do not cover.

For a batch, answer per request: `1 ok, 2 ok, 3 drop`.
