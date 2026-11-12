# Phase <unit id>: <title from the spec step>

<!--
Filled by the coordinate skill from one step of a spec in docs/specs/. Every field is
filled; a blank one is where the worker stalls. The Standing orders section
is pasted verbatim from the repo's AGENTS.md, never paraphrased.
Delete this comment before sending.
-->

Model tier: <the coordinating tier from rules/models.md, not the model the coordinator runs on, and the host's model and reasoning effort for it; one tier up when the step is subtle or security-sensitive; for a fix round after a failed one, one tier above the last round's>
Repo: <absolute path to the main checkout>
Branch: `<type>/<scope>-<description>` in its own worktree under `.claude/worktrees/`, based on `<default branch, or the unmerged dependency's branch>`
Notes folder: <absolute path>; write the report there as `report-<id>.md` and the hand-over note as `unit-<id>.md`

## Read first, in this order

1. `AGENTS.md`, the Standing orders section in particular
2. `CONTEXT.md`, the glossary; use its terms and no others
3. `docs/adr/<NNNN>-<slug>.md` for each ADR the step lists: <list them>
4. `docs/specs/<slug>.md`: the Requirements and Criteria this step serves, and the step itself
5. `<notes folder>/unit-<previous id>.md`, the previous unit's hand-over note, or "none" for the first unit

## Decisions already made

Do not reopen these. A question that would reopen one is an ADR-tier fork: send it to the coordinator with lettered options and keep working on what does not depend on it.

- <decision>, from `docs/adr/<NNNN>-<slug>.md` or the spec's Decisions, round <n> option <letter>
- <decision>
- Based on `<parent branch>@<parent tip sha>` because PR <number> is not merged yet; once it merges, rebase with `git rebase --onto <default branch> <parent tip sha>`, never with a plain rebase, since the repo squash-merges

## Scope

Build: <the step's title and what it delivers, in one or two sentences>

You see when it works: <the step's You see field>

Owns, and may edit nothing outside it:

- In `docs/specs/<slug>.md`, only this step's status line under its heading and the Status cells of its rows in the Criteria table, where `implement` records progress
- `<absolute path>`
- `<absolute path>`

## Not asked for now

- <the neighbouring step's work, named so the worker stops at the boundary>
- <a tempting refactor that belongs to a later step>

## Done means

Behaviour target: <the highest level the checks below can reach: live-verified when any is a drive check, unit-only when any is a test check, otherwise "none: the criteria alone decide"; the owner can set it otherwise. The verify report's behaviour row must reach it, filled from what ran>

Criteria, copied as written from the spec's Criteria section for every requirement this step serves. Before building, see each one fail, as the `implement` skill describes. Each gets its own row in the verify report, run as written, reading pass, fail, met, not met or not run; none is left out. A drive criterion whose Drive step isn't in `VERIFICATION.md` yet means this step adds it, and the recipe is listed under Owns:

- C<r>.<n> <scenario>: passes when <...>. Check: `<command>`
- C<r>.<n> <scenario>: passes when <...>. Check: Drive step <id> of `<path to VERIFICATION.md>`
- C<r>.<n> <scenario>: passes when <...>. Check: inspection, <what to read and the standard>

Gate, read from `package.json` scripts or the Makefile, run through the `verify` skill, output and exit codes pasted:

```bash
<real gate command>
<real gate command>
```

<conformance or fixture run the step needs, or "none">

## Ship

Use the `pr` skill through to Ready. This brief is the go-ahead for push, draft PR, and marking the PR ready once `verify` passes on the pushed head and no check has failed; ask for none of them again. The PR stays draft until then. Build with the `implement` skill without pausing at its checkpoints, committing each item through `pr`.

## Forbidden

- Editing any file outside Owns
- Merging the default branch in; rebase instead
- `--no-verify`, a weakened, skipped or deleted test, a loosened type, a swallowing catch
- `gh pr merge`, auto-merge, or a force push without `--force-with-lease=<branch>:<old sha>`
- Committing `docs/plans/`, `.claude/` or `.plans/`
- Deciding an ADR-tier fork alone: public API shape, data model, a new dependency, a specification interpretation

## Report

Write `report-<unit id>.md` in the notes folder after the push, replacing any earlier one, when the PR is ready and again if blocked. A script reads its first three lines and its verify table, so they are exact:

```markdown
STATUS: READY
COMMIT: <pushed head sha, equal to the worktree's HEAD>
QUESTION: none
```

Line 1 is `STATUS: READY`, `STATUS: BLOCKED` or `STATUS: FORK`. `BLOCKED` puts the one thing that would unblock the work on line 3, and `FORK` the one decision needed. `READY` is only for a head on which the gate and every criterion pass. Below those lines:

- Branch and PR URL
- The `verify` report on the pushed head as its table, `| Concern | Command | Exit | Result |`: the gate rows, then one row per criterion whose first cell starts with its id, then the `behaviour` row; the spec's Criteria table updated to match
- What was not driven and why, when the behaviour row is below the target
- Forks decided below the ADR tier, each with the choice made
- Forks parked for the coordinator, as lettered options
- The hand-over note path

Then message the coordinator with the three lines and the report's path, and nothing else.

## Standing orders

<!-- Paste the ## Standing orders section of AGENTS.md here verbatim. When the repo has none, the block below stands in, and adding the section to AGENTS.md is part of this unit's scope. -->

- Work only on this branch in this worktree; never on the default branch.
- Rebase onto the default branch; never merge it in.
- Open the PR as a draft; mark it ready only after `verify` passes on the pushed head and no check has failed.
- Run the gate and every criterion under Done means and paste their output with exit codes; never say done, fixed or passing until every criterion reads pass or met.
- Never weaken, skip or delete a test to reach green; root-cause the failure.
- Never commit `docs/plans/`, `.claude/` or `.plans/`.
- No emoji, model names, AI identifiers or session links in commits, PR text, reviews or comments, except an ADR's Sign-off line, the PR Decisions line that repeats it and a co-author trailer the harness supplies on a commit; the repo's restricted words stay out too.
- Invented data only in fixtures and examples, with `example.com` for every domain.
- Do not wait on an unmerged PR; base on its branch and say so.
- An ADR-tier fork is a question to the coordinator with lettered options, not a decision; park it and continue what does not depend on it.
- Report with head SHA, gate counts and what was not verified.
