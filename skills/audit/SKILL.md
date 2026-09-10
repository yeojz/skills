---
name: audit
description: Use when asked for a read-only assessment of a repo, package or plan document that ends in a written plan rather than in edits. Triggers on requests like "audit", "assess the repo", "code smell", "review the codebase", "any risks", "write a plan if you detect issues", "critique this plan", or when the user says to identify problems but not to change any code yet.
---

# audit

## Overview

A strictly read-only assessment. It reads the target, fans the work out to
parallel subagent personas, grounds every finding in a real `file:line`, and
writes exactly one artefact: a severity-ranked plan at
`docs/plans/YYYY-MM-DD-HHMM-<slug>.md`. It never edits code.

Two modes:

| Mode | Target | Output |
|---|---|---|
| Repo audit | a repo, an app, a package, a directory | scope, findings table, per-finding detail, remediation order |
| Plan critique | an existing plan or spec document | a critique section judging merit, hidden risk, and whether the stated concerns are actually valid |

This skill is not `review`. `review` is diff-scoped and reports on a branch or
PR. `audit` is target-scoped, read-only, and always ends in a plan file.

## Workflow

### Step 1: Enter the read-only gate before anything else

Nothing in this skill edits code. Before reading a single file, hold these
rules for the whole run:

| Not allowed | Allowed |
|---|---|
| `Edit` on any file | `Read`, `Grep`, `Glob` |
| `Write` to any source, test, config or doc file | `Write` to the one plan file in `docs/plans/` |
| `git add`, `git commit`, `git checkout -b`, `git stash`, `git restore`, `git rebase`, `git push` | `git log`, `git status`, `git diff`, `git show`, `git blame` |
| `pnpm add`, `pnpm up`, any install or codemod | `pnpm ls`, `pnpm why`, `cat package.json` |
| Creating a branch or a worktree | Staying on the current branch, untouched |

The single file this skill may create is the plan document. If a finding is
trivial and the fix is one line, it still goes in the plan and not into the
file. If the user says "just fix it while you are there", stop and confirm they
want to leave audit mode, because that is a different job.

Subagents inherit this gate. Every persona prompt must state that the persona
is read-only and returns findings as text.

### Step 2: Settle the scope

Resolve the target before reading. Default rather than ask where the wording is
clear:

| User says | Scope |
|---|---|
| "the repo", "the codebase", "everything" | whole repo, all workspaces |
| "this package", "`packages/<x>`", "the CLI" | that directory plus its direct dependents |
| "the providers", "the auth layer" | the modules that implement it, plus their call sites |
| a plan or spec file path | plan critique mode, Step 8 |
| nothing identifiable | ask once, with two or three concrete options |

Honour exclusions literally. When the user names a path to leave out, for
instance a docs directory whose specs they say may be out of date, exclude that
path from every persona prompt and record the exclusion, and the reason given
for it, in the plan's scope section.
Default exclusions are `node_modules/`, `dist/`, build output, and lock files
except when supply chain is in scope.

Map the target before fanning out:

```bash
git -C . rev-parse --abbrev-ref HEAD
git -C . status --short
ls pnpm-workspace.yaml pnpm-lock.yaml package.json 2>/dev/null
cat package.json
find packages apps internal -maxdepth 2 -name package.json 2>/dev/null
git -C . log --oneline -20
```

Read the repo's own instruction files first if they exist: `CLAUDE.md`,
`AGENTS.md`, `CONTRIBUTING.md`. A finding that contradicts
a documented, deliberate decision is not a finding.

### Step 3: Fan out to parallel personas

Fan-out is the default, not an optimisation. Launch all applicable personas in
a single message so they run concurrently. Give each one the same scope, the
same exclusions, and the same grounding rules from Step 4.

| Persona | Looks for |
|---|---|
| Principal engineer | layering violations, module boundaries, duplication, dead code, over-engineering, abstractions with one implementation, dependency injection done as a global or a singleton, provider implementations bleeding into each other or into core, missing argument pass-through, non-null assertions, `any`, `enum`, deprecated aliases kept for no reason |
| Security engineer | input validation and parsing, secret handling and logging, comparison of secrets that is not constant time, injection vectors including shell, SQL, path traversal and prototype pollution, unsafe deserialisation, supply chain: new or unmaintained dependencies, transitive risk, unpinned GitHub Actions, install scripts |
| Test engineer | uncovered branches, tests that assert nothing or only assert a mock was called, a rejecting branch with no negative test, tests that pass because of a workaround, shared mutable fixture state, skipped or `.only` tests |
| Technical writer | README and guide drift against real exports, code examples that call something that is not exported, CLI examples that disagree with real `--help` output, dead links, stale version numbers, secrets or real domains in examples |

Drop a persona only when it has nothing to read, for example the test engineer
in a repo with no test directory, and say so in the plan's scope section.

Add a persona when the target demands one, for example a performance or a
release-process lens. Keep each persona to one lens; do not merge them.

Each persona prompt must end with the return contract:

```text
Return findings only. Do not edit any file. For each finding give:
severity, file:line, one-sentence finding, evidence quote, suggested fix.
If you cannot cite a file and line, do not report it.
```

When the target is small enough that fan-out costs more than it saves, for
example a single file under a few hundred lines, run the lenses yourself in
sequence and say in the plan that you did.

### Step 4: Ground every finding

A finding without a `file:line` is not a finding. Apply these rules to your own
work and to everything a persona returns:

1. Every finding cites a path and a line number that exists. Verify each one by
   reading the cited lines before writing the plan.
2. Nothing is reported from memory or from what a library "usually" does. If a
   claim depends on a dependency's behaviour, read that behaviour in
   `node_modules/<pkg>` or in the published source and cite it.
3. If a claim depends on a specification, quote the specification text and cite
   the section. Do not paraphrase a spec from recollection.
4. If a claim depends on a command's behaviour, run the read-only command and
   use the real output.

```bash
grep -rn "<symbol>" --include="*.ts" packages/ | head -20
sed -n '<start>,<end>p' <path>
cat node_modules/<pkg>/package.json
pnpm why <pkg>
pnpm <script> --help
```

Drop anything that survives none of the above. An audit that reports a
plausible problem that does not exist in this codebase is worse than an audit
that reports nothing. When a persona returns something you cannot verify,
either drop it or move it to an "Unverified, needs a look" list at the end of
the plan, clearly labelled as not confirmed.

Deduplicate across personas: the same line found by two lenses is one finding
with both rationales, not two.

### Step 5: Rank by severity

| Severity | Meaning |
|---|---|
| Critical | exploitable, data-losing, or already broken in production paths |
| High | a real defect or a boundary violation that will cause a defect or block a change |
| Medium | a code smell, a coverage gap on a rejecting branch, drifted docs |
| Low | consistency, naming, minor duplication, tidying |

Rank within a severity by blast radius. Preference violations from the house
rules are Medium at most unless they cause a defect.

### Step 6: Write the plan file

One file, at:

```bash
mkdir -p docs/plans
date +%Y-%m-%d-%H%M
# docs/plans/2026-09-10-1432-provider-boundaries-audit.md
```

The slug is kebab-case and names the target, for example
`repo-audit`, `provider-di-boundaries`, `cli-package-audit`.

Plans are working documents and are not committed. Never `git add` the file,
and never stage `docs/plans/` or `.plans/`.

Structure, in this order:

```markdown
# <Target> audit, <date>

## Scope

What was audited, which paths were excluded and why, which personas ran,
the branch and commit audited, and what was read. Name the exclusions the
user asked for.

## Findings

| ID | Severity | Location | Finding | Suggested fix |
|----|----------|----------|---------|---------------|
| A1 | Critical | `packages/core/src/verify.ts:42` | Secret compared with `===` | Use `timingSafeEqual` on equal-length buffers |
| A2 | High | `packages/aws/src/client.ts:17` | Provider imports the GCP provider's config type | Move the shared type to `internal/types` |

## Detail

### A1: <finding title>

**Severity:** Critical
**Location:** `packages/core/src/verify.ts:42`

Evidence: the cited lines, quoted.

Why it matters: the concrete consequence, not a general principle.

Suggested fix: what to change, and what to run to prove it.

### A2: ...

## Remediation order

1. A1, A4 - <one subagent task, one sitting>
2. A2 - ...

## Unverified

Anything that could not be grounded, labelled as not confirmed.
```

Rules for the plan body:

- IDs are stable, sequential, and prefixed `A`: `A1`, `A2`, `A3`. Never renumber
  them after writing, because `execute-plan` references them.
- Each remediation item is sized to one subagent task: one concern, one area,
  independently verifiable. Split anything larger. Group items only when they
  touch the same file and must move together.
- Order remediation by severity first, then by dependency: a fix that unblocks
  another comes first.
- Every suggested fix names the verification command from the repo's own
  `package.json` scripts. Never invent a command.
- No emoji. Sparing em-dashes. No model names or AI identifiers.

### Step 7: Report back

In the chat reply give the plan path, the count by severity, and the two or
three findings that actually matter. Do not paste the whole plan. Do not offer
to start fixing unless the user asks; if they do, that is the `execute-plan`
skill and it starts with a branch.

### Step 8: Plan critique mode

When the target is an existing plan or spec document rather than code, the job
is to judge it before anyone writes code. Same read-only gate, same grounding
rules.

1. Read the document in full.
2. Check every claim it makes about the codebase against the codebase. A plan
   that proposes fixing something that is already handled, or that describes a
   module that does not exist, fails here. Say so plainly.
3. For each stated concern, decide: valid, already mitigated, or not a real
   problem. Cite the `file:line` that settles it.
4. Assess merit: does the change buy what it claims, is it the smallest thing
   that works, does it add an abstraction with one implementation, does it add
   a dependency that is not needed.
5. Name the hidden risks the plan does not mention: migration and data shape,
   backwards compatibility on a published package, error paths, concurrency,
   what happens to existing tests, what is left half-migrated if it stops
   midway.
6. Check the plan is executable: are steps ordered, is each one verifiable, is
   there a stated way to prove each one is done.

Write the critique as a section in a new plan file at the same
`docs/plans/YYYY-MM-DD-HHMM-<slug>-critique.md` path. Do not edit the plan
being critiqued. Use the same `A1`, `A2` ids for the issues raised with the
plan. Include a verdict table:

| Stated concern | Verdict | Evidence |
|---|---|---|
| "Tokens are not validated" | Already mitigated | `packages/core/src/token.ts:31` validates before use |
| "Provider config leaks across providers" | Valid | `packages/aws/src/client.ts:17` imports from `packages/gcp` |

End with a recommendation in lettered options, for example "A: proceed as
written, B: proceed with items 3 and 5 dropped, C: rescope", with one named as
the recommendation.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Editing code during an audit, even a one-line obvious fix | Audits never edit. The only file created is the plan. Record the one-liner as a finding with a suggested fix and stop. |
| Running `git checkout -b`, `git stash`, `git add` or `git commit` during an audit | The working tree and the branch end exactly as they started. Read-only git commands only. |
| Committing the plan file | Plans are not committed. Never stage `docs/plans/` or `.plans/`. |
| Reporting a finding with no line number | Cite `path:line` or drop the finding. |
| Reporting what a library or a spec "usually" does | Read the dependency source or quote the specification text and cite the section. |
| Reporting a problem that is not in this codebase | Verify the symbol exists with `grep -rn` before writing it down. Unverifiable items go under "Unverified", labelled. |
| Running one general-purpose pass instead of parallel personas | Fan out one subagent per lens in a single message. Fan-out is the default. |
| Merging the security and test lenses into one persona | One lens per persona. Merged lenses drop findings from both. |
| Auditing paths the user told you to ignore | Exclude them from every persona prompt and record the exclusion in the plan's scope. |
| Renumbering findings between drafts | IDs are stable once written. `execute-plan` references `A1`, `A2` by name. |
| A remediation item too big for one subagent | Split until each item is one concern in one area, independently verifiable. |
| Inventing a verification command | Read `package.json` scripts and cite those. Workspace coverage usually needs `pnpm --filter <pkg> test:ci --project <project>`. |
| Flagging a documented, deliberate decision as a defect | Read `CLAUDE.md`, `AGENTS.md` and `CONTRIBUTING.md` first. |
| Offering to fix everything at the end of the audit | Report and stop. Fixing is `execute-plan`, and it starts with a branch. |
| Treating a diff or a PR as an audit target | That is `review`. `audit` is target-scoped and always writes a plan file. |
