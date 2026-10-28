# Phase <unit id>: <title from the roadmap row>

<!--
Filled by the coordinate skill from one docs/roadmap.md row. Every field is
filled; a blank one is where the worker stalls. The Standing orders section
is pasted verbatim from the repo's AGENTS.md, never paraphrased.
Delete this comment before sending.
-->

Model tier: <the tier rules/models.md names for a scoped unit with named files and a done condition; one tier up when the row is subtle or security-sensitive>
Repo: <absolute path to the main checkout>
Branch: `<type>/<scope>-<description>` in its own worktree under `.claude/worktrees/`, based on `<default branch, or the unmerged dependency's branch>`
Notes folder: <absolute path>; write the hand-over note there as `unit-<id>.md`

## Read first, in this order

1. `AGENTS.md`, the Standing orders section in particular
2. `CONTEXT.md`, the glossary; use its terms and no others
3. `docs/adr/<NNNN>-<slug>.md` for each ADR that touches this row: <list them>
4. `docs/roadmap.md`, the row for unit <id> only
5. `<notes folder>/unit-<previous id>.md`, the previous unit's hand-over note, or "none" for the first unit

## Decisions already made

Do not reopen these. A question that would reopen one is an ADR-tier fork: send it to the coordinator with lettered options and keep working on what does not depend on it.

- <decision>, from `docs/adr/<NNNN>-<slug>.md` or `docs/design.md` round <n> option <letter>
- <decision>
- Based on `<branch>` because PR <number> is not merged yet; rebase onto the default branch once it is

## Scope

Build: <the row's builds field, in one or two sentences>

You see when it works: <the row's you see field, one observable result>

Owns, and may edit nothing outside it:

- `<absolute path>`
- `<absolute path>`

## Not asked for now

- <the neighbouring row's work, named so the worker stops at the boundary>
- <a tempting refactor that belongs to a later row>

## Done means

Behaviour level: <live-verified | unit-only | type-check-only, as the verify skill reports it>

Gate, read from `package.json` scripts or the Makefile, run through the `verify` skill, output and exit codes pasted:

```bash
<real gate command>
<real gate command>
```

<conformance or fixture run the row names, or "no conformance run for this row">

## Ship

Use the `ship` skill in ship-to-ready mode. This brief is the go-ahead for push, draft PR, the gate on a clean detached checkout, and marking the PR ready once that gate is green; ask for none of them again. The PR body comes from `pr-desc`, with the detached gate run in its Verification section. The PR stays draft until that gate passes on the pushed head.

## Forbidden

- Editing any file outside Owns
- Merging the default branch in; rebase instead
- `--no-verify`, a weakened, skipped or deleted test, a loosened type, a swallowing catch
- `gh pr merge`, auto-merge, or a force push without `--force-with-lease=<branch>:<old sha>`
- Committing `docs/plans/`, `.claude/` or `.plans/`
- Deciding an ADR-tier fork alone: public API shape, data model, a new dependency, a specification interpretation

## Report

Message the coordinator when the PR is ready, and again if blocked, with:

- Branch, PR URL, head SHA
- The gate on the clean detached checkout: command, exit code, the counts line
- Behaviour level reached, and what was not verified and why
- Forks decided below the ADR tier, each with the choice made
- Forks parked for the coordinator, as lettered options
- The hand-over note path

## Standing orders

<!-- Paste the ## Standing orders section of AGENTS.md here verbatim. When the repo has none, the block below stands in, and adding the section to AGENTS.md is part of this unit's scope. -->

- Work only on this branch in this worktree; never on the default branch.
- Rebase onto the default branch; never merge it in.
- Open the PR as a draft; mark it ready only after the gate is green on a clean detached checkout of the pushed head.
- Run the gate named under Done means and paste its output with exit codes; never say done, fixed or passing without it.
- Never weaken, skip or delete a test to reach green; root-cause the failure.
- Never commit `docs/plans/`, `.claude/` or `.plans/`.
- No emoji, model names, AI identifiers or session links in commits, PR text, reviews or comments; the repo's restricted words stay out too.
- Invented data only in fixtures and examples, with `example.com` for every domain.
- Do not wait on an unmerged PR; base on its branch and say so.
- An ADR-tier fork is a question to the coordinator with lettered options, not a decision; park it and continue what does not depend on it.
- Report with head SHA, gate counts and what was not verified.
