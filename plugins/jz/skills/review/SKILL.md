---
name: review
description: Use when a change, a pull request, a whole repo or a plan needs reviewing, or when a PR's review comments or red CI need dealing with. Triggers on requests like "review my changes", "review this branch", "code review", "review the changes between this branch and main", "audit the repo", "assess the codebase", "code smells", "any risks", "write a plan if you find issues", "critique this plan", "check the PR comments", "are the comments addressed", "CI is red on the PR", "please do a second check", "do a quick review", "adversarial review", "get a second opinion on this diff", or when the user pastes a pull request or a `#discussion_r...` URL.
---

# review

## Overview

An independent judgement of someone's work, grounded in real lines. It
reviews a change or a pull request, audits a whole repo or a plan into a
plan file, sweeps a PR's comments and red checks, or runs one brief past two
model families. Every finding points at a `file:line` that was read.

## Modes

| Mode | Trigger | Output |
|---|---|---|
| change | "review my changes", "this branch", a PR number or URL | findings in the session |
| audit | "audit", "assess the repo", "code smells", "critique this plan" | one plan file in `docs/plans/`; no edits |
| comments | "check the PR comments", "CI is red", a `#discussion_r...` URL | thread ledger, CI classes, replies, remaining count |
| adversarial | "adversarial review", "second opinion", "another model" | merged findings in buckets; nothing applied |
| quick | "quick look", "general review", "without the skill" | short prose |

## Rules for every mode

**Scope.** Fetch, then diff with three dots, so only this branch's work
shows:

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git fetch origin "$base"
git diff "origin/$base...HEAD" --stat
```

The working tree is `git diff HEAD`; a pull request is `gh pr diff <n>`. With
no clear scope, a dirty tree means the working tree, a clean one the branch.
Say which was used.

**Read past the diff.** Read each changed file whole, the callers of each
changed signature, and the sibling that does the same job. Read `AGENTS.md`,
`CLAUDE.md`, the spec and the ADRs first: a finding that contradicts a
documented decision is not a finding.

**Ground every finding.** Each one cites a path and line that exists on the
reviewed revision, read before writing it down. What a library does is read
in `node_modules/<pkg>`; what a specification says is quoted. What can't be
grounded is dropped or listed under Unverified.

**Severity.** Critical is exploitable, data-losing or already broken. High is
a real defect or a boundary violation that will cause one. Medium is a smell,
a missing negative test, drifted docs. Low is naming and tidying. Design
findings take severity from their consequence, never demoted for being
design. A clean review says so and names what was checked; no filler Lows.

## Mode: change

Walk every lens. Four always report a line, clean or not:

| Lens | Look for |
|---|---|
| Design (always) | a surface wider than needed, a decision a spec or ADR settled the other way, a seam the next change will have to move |
| Maintainability (always) | comments that say what instead of why, tests coupled to implementation, duplication, dead code, names that disagree with siblings |
| Guard deletion (always) | new rejecting branches, sampled below |
| Criteria (always, when the change serves a spec or brief) | each criterion's check run on the reviewed revision |
| Correctness | a dropped pass-through, a fallback that hides an error, `!`, `any`, `@ts-ignore`, a redundant check |
| Dependencies | a new dependency without justification, maintenance and MIT or ISC licence; a deep import past `exports` |
| Security | secrets logged, non-constant-time comparison, a shell command from external input, path traversal, a rejection with no negative test |

Fan the lenses out to subagents when the diff spans many files; give each
the same scope and these rules.

**Guard deletion.** List the new `if` branches that reject (throw, return
early, answer 4xx) from the chosen diff. Sample security boundaries,
data-loss guards and the rejection the change was asked for first. For each:

```bash
snapshot="$(mktemp)" && cp -p <path> "$snapshot"
# neutralise the one condition: if (cond) becomes if (false && (cond))
pnpm --filter <pkg> test
cp -p "$snapshot" <path> && cmp "$snapshot" <path> && echo restored
```

The suite is green before the first guard. A red run kills the mutant; a
green run is a High naming the guard and the test that should have failed.
A compiler refusing the mutant is "covered by the compiler", not a kill.
Restore from the snapshot, never `git checkout`, which discards work under
review. Sample in the reviewed revision. For a PR that isn't checked out,
use a worktree detached at its head, kept until the last restore and the
last criterion's check:

```bash
head="$(gh pr view <n> --json headRefOid --jq .headRefOid)"
git fetch origin "refs/pull/<n>/head"
sample_dir="$(mktemp -d)" && git worktree add --detach "$sample_dir" "$head"
( cd "$sample_dir" && pnpm install --frozen-lockfile )
# sample each guard and run each criterion's check inside "$sample_dir"
git worktree remove --force "$sample_dir" && git worktree prune
```

Name each unsampled guard with its reason.

**Criteria.** Run each criterion's check as written, on the reviewed
revision; judge an inspection criterion against its written standard. A
check that fails, has no row in the author's `verify` block, or reads
`not run` there is a High naming the criterion.

Report in the session, ids `R1`, `R2` stable once printed:

```markdown
## Review: <branch or PR>, <n> files, +<add>/-<del>

Scope: `git diff "origin/$base...HEAD"` at <sha>

| ID | Severity | Location | Finding |
|----|----------|----------|---------|
| R1 | High | `packages/core/src/verify.ts:42` | Secret compared with `===` |

### R1: <title>
Evidence: <quoted lines>. Why it matters: <the consequence here>. Fix: <what, and the script that proves it>.

### Lenses that always report
- Design: <R ids, or clean, and what was checked>
- Maintainability: <...>
- Guard deletion: <n> guards, <k> sampled at <sha> with `<command>`, <s> survived, unsampled: <guard, reason>
- Criteria: <n> run at <sha>, <p> pass, <f> fail or missing
```

**Second check.** Re-run the scope, mark each earlier finding fixed, not
fixed or no longer applicable with a line, and review the new hunks fresh.

Don't offer to fix. Working findings is `implement`, when asked.

## Mode: audit

Read-only for the whole run: no edits, no branches, no staging, no installs.
The one file written is the plan. "Just fix it" means leaving audit mode;
confirm first.

1. **Scope.** The repo, a package, a layer, or a plan file. Honour every
   exclusion the user names and record it with its reason. Skip
   `node_modules/`, `dist/` and lock files unless supply chain is in scope.
2. **Fan out** in one message to the persona subagents, each with the same
   scope, exclusions and grounding rules: `jz:principal-engineer`,
   `jz:security-engineer`, `jz:test-engineer`, `jz:technical-writer`. Drop
   one only when it has nothing to read, and say so. Each prompt ends:
   "Return findings only. Edit nothing. For each: severity, file:line,
   finding, quoted evidence, suggested fix. No line, no finding." Without
   subagents, or for a single small file, run the persona files one at a
   time in full and record that.
3. **Verify and merge.** Read every returned line yourself. One defect found
   by two lenses is one finding.
4. **Write** `docs/plans/YYYY-MM-DD-HHMM-<slug>.md` from `template.md`:
   ids `A1`, `A2` never renumbered, every row `not started`, every fix naming
   its verification script from `package.json`, remediation sized to one
   subagent task each. Never stage it.
5. **Reply** with the path, the count by severity and the two or three
   findings that matter.

**Plan critique.** For a plan or spec file: check every claim it makes
against the code, judge each stated concern (valid, already mitigated, not
real) with the line that settles it, name the risks it misses (data shape,
compatibility, error paths, a half-finished migration), and check each step
is verifiable. Write `docs/plans/...-critique.md` with a verdict table, end
with lettered options and a recommendation, and never edit the plan itself.

## Mode: comments

Use the API; the PR page hides collapsed and outdated threads. For a
pasted `#discussion_r<id>` URL, fetch that one comment with
`gh api repos/<o>/<r>/pulls/comments/<id>`.

```bash
gh api graphql -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved isOutdated path line comments(first:50){nodes{databaseId author{login} body}}}}}}}' -F o=<owner> -F r=<repo> -F n=<n>
```

The work set is threads neither resolved nor outdated. For each: judge it
against the code first (valid, already addressed, or wrong); change the code
only if valid; reply either way with what changed or the line that refutes
it (`gh api repos/<o>/<r>/pulls/<n>/comments -f body=... -F in_reply_to=<id>`).
Never resolve a thread you disagreed with. Run `verify` on any fix, then
re-fetch and report the remaining unresolved, non-outdated count, each
thread left open with its reason, and each check still red with its class.
"All addressed" without that count is not an answer.

**Red CI.** Read the failing log before any rerun:

```bash
gh pr checks <n>; gh run view <run-id> --log-failed
git merge-base --is-ancestor "origin/$base" HEAD || echo "behind the base"
```

| Signal | Class | Do |
|---|---|---|
| Failure outside the diff, branch behind the base, base green | Stale base | Rebase through the `pr` skill's Rebase section; never rerun |
| Failure outside the diff, base red too | Upstream | Report it with the base run's URL; no rerun, no rebase |
| Failure in or reached by the diff | Defect | A finding, fixed, then `verify` |
| Timeout, reset, 429 or 5xx, passes locally | Suspected flake | One rerun per check per head (`gh run rerun <run-id> --failed`), then classify again |
| The same failure twice | Defect | No third run |

In the desktop app, bind the PR and turn its monitor on instead of polling.

## Mode: adversarial

1. Fix the scope and head sha. Write one brief to a file: the diff command
   at that sha, the lens table, the grounding rules, the report table, and
   "read only: edit nothing, post nothing".
2. Start two fresh reviewers on different model families in one batch: one
   on the review tier from `rules/models.md`, one through Codex when its
   plugin is present (otherwise a second fresh session, and say so). Label
   them A and B with each one's family and tier. Same brief, verbatim;
   neither sees the other.
3. Verify every finding at its line yourself; agreement never replaces that.
   Merge findings on the same defect, and build the agreement map: one row
   per finding, one column per reviewer (`raised <severity>`, `not raised`
   or `contradicted`), with the count raised by both.
4. Bucket: **act on** (verified and High+, or raised by both and verified),
   **consider** (verified, Medium or Low, or a judgement call), **noted**
   (true but out of scope or settled), **dismissed** (refuted, with the
   refuting line quoted). Print it; apply nothing.

## Mode: quick

No table, no ids, no personas. Keep the three-dot diff, read past it, and a
`file:line` behind every point. Short prose by file, biggest concern first.

## Common Mistakes

| Mistake | Fix |
|---|---|
| A two-dot diff, or no fetch first | Fetch, then three dots |
| A finding with no line | Cite it or drop it |
| What a library or spec does, from memory | Read the source; quote the spec |
| No Design, Maintainability, Guard deletion or Criteria line | They always report, clean or not |
| Judging guard coverage by reading tests | Neutralise, run, restore; a survivor is a High |
| Restoring a sampled file with `git checkout` | Copy the snapshot back and `cmp` |
| Taking the author's criteria rows on trust | Run each check on the reviewed revision |
| Editing anything during an audit | The plan is the only file written |
| One general pass instead of personas | Fan out one subagent per lens |
| Acting on a review comment without judging it | Judge first; a wrong one gets a reasoned reply |
| A second rerun after an identical failure | It's a defect |
| Applying the adversarial act-on list | Nothing is applied; that's `implement`, when asked |
