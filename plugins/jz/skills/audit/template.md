# <Target> audit, <date>

<!--
Filename: docs/plans/YYYY-MM-DD-HHMM-<slug>.md
Plans are working documents and are not committed. Never stage `docs/plans/`,
`.plans/` or `.claude/`. Editing this file during a run is expected: the
`execute` skill writes status back into it item by item.
-->

Date: <YYYY-MM-DD HH:MM>
Branch: <branch at time of writing> at <short commit sha>
Target: <repo, package or path this plan covers>
Owner: <who decides scope questions>

## Scope and what was read

<One or two sentences naming the question this plan answers, and the exclusions
the user asked for, with the reason given for each.>

Personas: <which lenses ran, whether they ran as parallel subagents or in
sequence in the main session, and any persona dropped with the reason>.

Read:

- `<path/to/file.ts>` - <why it was read>
- `<packages/<pkg>>` - <what was covered>
- `<diff or commit range, e.g. git log --oneline -20>` - <what it showed>

Not read: `<path>`, `<path>`. Anything not read is out of scope and must not be
the basis of a finding.

## Findings

Ids are stable, sequential and prefixed `A`: `A1`, `A2`, `A3`. Once assigned
they are never renumbered, because remediation entries and status records
reference them by name. Rows are sorted Critical first. Every row starts at
`not started`; `execute` updates the status column.

| ID | Severity | Location | Finding | Suggested fix | Status |
|---|---|---|---|---|---|
| A1 | Critical | `<path/to/file.ts>:<line>` | <one-sentence finding> | <one-sentence fix> | not started |
| A2 | High | `<path/to/file.ts>:<line>` | <one-sentence finding> | <one-sentence fix> | not started |
| A3 | Medium | `<path/to/other.ts>:<line>` | <one-sentence finding> | <one-sentence fix> | not started |

## Detail

<One subsection per finding, repeating the block below. Keep the id and title
identical to the findings table row.>

### <id>: <finding title>

- Severity: `<Critical | High | Medium | Low>`
- Location: `<path/to/file.ts>:<line>`
- Evidence: <the cited lines, quoted verbatim>
- What is wrong: <the concrete defect at those lines>
- Why it matters: <the consequence in this codebase, not a general principle>
- Suggested fix: <what to change, in one or two sentences>
- Verify with: `<script from package.json, for example pnpm --filter <pkg> test:ci --project <project>>`
- Risk and blast radius: <what else this touches, what could break, who depends
  on it>

## Remediation order

Each entry is sized to be exactly one subagent task: one concern, one area,
independent enough to hand to one agent, and small enough to finish and verify
in one pass. Split anything larger. Group ids only when they touch the same file
and must move together. Order by severity first, then by dependency: a fix that
unblocks another comes first.

1. `<id>[, <id>]` - <what to change>
   - Files: `<path/to/file.ts>`, `<path/to/file.test.ts>`
   - Evidence: `pnpm --filter <pkg> test:ci --project <project>`
   - Depends on: none. Independent, can be fanned out in parallel.
2. `<id>` - <what to change>
   - Files: `<path/to/file.ts>`
   - Evidence: `pnpm --filter <pkg> <script>`
   - Depends on: none. Independent, can be fanned out in parallel.
3. `<id>` - <what to change>
   - Files: `<path/to/file.ts>`
   - Evidence: `pnpm --filter <pkg> test:ci --project <project>`
   - Depends on: entry 2. Conflicts with it, they share `<path/to/file.ts>`, so
     run in order.

Parallel set: <entry numbers with no shared file and no producer-consumer link>.
Serial set: <entry numbers that must run in order, and the reason for each>.
When a conflict is uncertain, serialise.

## Status vocabulary

| Status | Meaning | Required record |
|---|---|---|
| `not started` | Not attempted yet, or out of scope for this run | Nothing beyond the status |
| `done` | Implemented, or already mitigated, and verified | The evidence command and its result, for example `pnpm --filter <pkg> test:ci --project <project>` -> `<N> passed` |
| `skipped` | Deliberately not done, or no longer applies | The reason, and who decided, with the date |
| `blocked` | Attempted and verification failed, or a prerequisite is missing | The failing command, its output, and what is blocking |

A status of `done` without an evidence command is not done.

## Unverified

Anything a persona returned that could not be grounded in a `file:line` that
was read, labelled as not confirmed. Write "None" when the list is empty.

- <claim>, from <persona>. Not confirmed because <reason>.

## Follow-ups

- <adjacent problem spotted during the run, left unfixed, with `<path>:<line>`>
