# <Target> audit, <date>

<!--
File: docs/plans/YYYY-MM-DD-HHMM-<slug>.md. Never committed. The `implement`
skill writes status back into it item by item.
-->

Branch: <branch> at <short sha>
Target: <repo, package or path>

## Scope

<The question this plan answers, and each exclusion the user asked for with
its reason.>

Personas: <which lenses ran, in parallel or in sequence and why, and any
dropped with the reason>.

Read: <paths and commit ranges read>. Not read: <paths>. Nothing not read is
the basis of a finding.

## Findings

Ids are `A1`, `A2` and never renumbered. Critical first. Every row starts at
`not started`.

| ID | Severity | Location | Finding | Suggested fix | Verify with | Status |
|---|---|---|---|---|---|---|
| A1 | High | `<path>:<line>` | <one sentence> | <one sentence> | `<script from package.json>` | not started |

### A1: <title>

- Evidence: <the cited lines, quoted>
- Why it matters: <the consequence in this codebase>
- Blast radius: <what else it touches>

## Remediation order

One entry per subagent-sized task, by severity then dependency.

1. A1: <what to change>. Files: `<path>`. Depends on: none.

Parallel: <entries with no shared file>. Serial: <entries that must run in
order, and why>.

## Unverified

<Claims a persona made that couldn't be grounded in a line, labelled; or
"None".>
