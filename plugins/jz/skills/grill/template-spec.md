# <Scope name>

Status: draft
<!-- `criteria` changes this to "criteria signed off <date>"; `implement` reads it before starting. -->

Glossary: `CONTEXT.md`. ADRs: `docs/adr/`.

## Problem

<Who has the problem and what it costs them, in two or three sentences.>

## Requirements

- **R1 <Name>.** <An outcome someone can observe: what they do, and what they see happen.>
- **R2 <Name>.** <...>

## Out of scope

- <What this spec deliberately does not do, and why.>

## Decisions

- <Decision> (round <n>, <letter>). ADR-<NNNN> when it has one.

## Criteria

<Written by the `criteria` skill. Leave empty in `grill`.>

## Steps

### Step 1: <Vertical slice, named for what it delivers>

- Serves: R1
- Blocked by: none
- Owns: <packages, directories or files>
- You see: <one observable result>
- ADRs: <ADR-NNNN, or none>
- Review gate: <owner reviews before merge, or none>

<!--
Rules:
- Requirements are numbered R1, R2 and never renumbered; a dropped one stays with "(dropped: <reason>)".
- A step can be demoed or checked on its own and fits in one fresh session. Prefactoring goes first.
- No file paths or code in Requirements; they describe outcomes, and code changes.
Delete this comment before saving.
-->
