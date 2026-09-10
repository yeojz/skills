# <plan title>

<!--
Filename: docs/plans/YYYY-MM-DD-HHMM-<slug>.md
Plans are working documents and are not committed. Never stage `docs/plans/`,
`.plans/` or `.claude/`. Editing this file during a run is expected.
-->

Date: <YYYY-MM-DD HH:MM>
Branch: <branch at time of writing>
Target: <repo, package or path this plan covers>
Owner: <who decides scope questions>

## Scope and what was read

<One or two sentences naming the question this plan answers, and the exclusions
the user asked for.>

Read:

- `<path/to/file.ts>` - <why it was read>
- `<packages/<pkg>>` - <what was covered>
- `<diff or commit range, e.g. git log --oneline -20>` - <what it showed>

Not read: `<path>`, `<path>`. Anything not read is out of scope and must not be
the basis of a finding.

## Findings

Ids are stable and alphanumeric. Once assigned they are never renumbered,
because remediation entries and status records reference them by name. Rows are
sorted Critical first.

| id | severity | file:line | finding | status |
|---|---|---|---|---|
| A1 | Critical | `<path/to/file.ts>:<line>` | <one-sentence finding> | not started |
| A2 | High | `<path/to/file.ts>:<line>` | <one-sentence finding> | not started |
| B1 | Medium | `<path/to/other.ts>:<line>` | <one-sentence finding> | not started |

## Detail

<One subsection per finding, repeating the block below. Keep the id and title
identical to the findings table row.>

### <id> <finding title>

- Severity: `<Critical | High | Medium | Low>`
- Evidence: `<path/to/file.ts>:<line>` - <the cited lines, quoted verbatim>
- What is wrong: <the concrete defect at those lines>
- Why it matters: <the consequence in this codebase, not a general principle>
- Suggested fix: <what to change, in one or two sentences>
- Risk and blast radius: <what else this touches, what could break, who depends
  on it>

## Remediation order

Each entry is sized to be exactly one subagent task: independent enough to hand
to one agent, and small enough to finish and verify in one pass. Split anything
larger.

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

## Follow-ups

- <adjacent problem spotted during the run, left unfixed, with `<path>:<line>`>
