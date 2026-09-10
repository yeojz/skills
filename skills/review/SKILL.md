---
name: review
description: Use when asked to review a change rather than a whole repo, or to deal with review comments on a pull request. Triggers on requests like "review my changes", "review this branch", "code review", "as a principal software engineer review the changes between this branch and main", "do a quick review of the changes", "do a general review without using the skill", "please do a second check", "check the PR comments", "are the comments addressed", "double check if the new PR comment is valid", or when the user pastes a pull request or a `#discussion_r...` URL.
---

# review

## Overview

Diff-scoped review. It resolves what changed, reads the change plus the code
around it, and reports severity-ranked findings that each point at a real
`file:line`. It also sweeps unresolved pull request review threads, judges
whether each comment is actually correct, addresses the valid ones and reports
what is left.

Everything is printed in the session. This skill never writes a plan file; that
is `audit`, which is repo-wide and read-only. `review` is change-scoped and may
edit code when the user asks for the comments to be addressed.

Three modes:

| Mode | Trigger | Output |
|---|---|---|
| 1. Review a change | working tree, a branch against `main`, a PR number or URL | severity table plus per-finding detail, in the session |
| 2. Sweep PR comments | "check the PR comments", "are the comments addressed", a pasted PR or `#discussion_r...` URL | thread ledger, replies posted, remaining count |
| 3. Plain review | "do a general review", "without using the skill", "quick look" | prose notes, no personas, no table |

## Workflow

### Step 1: Resolve the scope before reading anything

Pick the scope from the wording. Default rather than ask when the wording is
clear.

| User says | Scope | Command |
|---|---|---|
| "my changes", "what I have so far", nothing committed | working tree | `git diff HEAD` plus `git status --short` |
| "this branch", "against main", "before I push" | branch | `git diff origin/main...HEAD` |
| "the PR", a number, a PR URL | pull request | `gh pr diff <n>` |
| a `#discussion_r...` URL | one review thread, Mode 2 | Step 6 |
| "the comments", "are they addressed" | Mode 2 | Step 6 |
| nothing identifiable, and the tree is dirty | working tree, say which you chose | |
| nothing identifiable, and the tree is clean | branch against `main` | |

Establish the ground truth first:

```bash
git rev-parse --abbrev-ref HEAD
git status --short
git fetch origin main
git log --oneline origin/main..HEAD
```

### Step 2: Always use the three-dot form for a branch diff

```bash
git diff origin/main...HEAD --stat
git diff origin/main...HEAD
```

Three dots diffs against the merge base, so it shows only what this branch did.
Two dots diffs against the current tip of `origin/main`, so every unrelated
commit that landed upstream since the branch started shows up as if it were
part of the change. That produces findings about code the author never touched.

Say which form was used and why in the report's scope line. When `origin/main`
is stale the merge base is wrong, so `git fetch origin main` runs first, every
time.

For a pull request:

```bash
gh pr view <n> --json number,title,headRefName,baseRefName,files,additions,deletions
gh pr diff <n>
```

If `gh` is not authenticated, stop and say so rather than falling back to
reading the web page.

### Step 3: Read past the diff

A diff hides its callers. Reviewing hunks alone is how a missing argument
pass-through or a now-dead export gets missed. For every changed file:

1. Read the whole file, not the hunk.
2. Find the callers of every changed signature.
3. Read the sibling package that does the same job, to judge consistency.
4. Read the repo's own instruction files first if present: `CLAUDE.md`,
   `AGENTS.md`, `CONTRIBUTING.md`. A finding that contradicts a documented,
   deliberate decision is not a finding.

```bash
git diff origin/main...HEAD --name-only
grep -rn "<changedSymbol>" --include="*.ts" packages/ apps/ internal/
grep -rn "from ['\"].*<changedModule>" --include="*.ts" .
```

Fan the lenses in Step 4 out to parallel subagents when the diff spans more
than a handful of files. Give each subagent the same scope, the same diff
command, and the grounding rules from Step 5. For a small diff run the lenses
yourself in sequence and say so.

### Step 4: Work the checklist

These are the recurring defects a change-scoped review is for. Walk them all;
do not stop at the first finding.

| Lens | Look for |
|---|---|
| Duplication | logic reimplemented when a function already exists in this workspace. Grep for the behaviour before accepting a new helper |
| Pass-through | a new parameter, option or context added at one layer and dropped at the next call site |
| Assertions | non-null assertions `!`, `as unknown as`, `any`, `@ts-ignore` introduced by the change |
| Redundancy | a check the caller already made, or new state that duplicates a field already on an existing object |
| Over-engineering | an abstraction with one implementation, a factory for a single value, an option nobody passes, indirection added ahead of a second use |
| Fallbacks | a default or `??` that hides a real error, a `try`/`catch` that swallows, a silent retry |
| Dead code | code the change orphaned, an export nobody imports any more, a deprecated alias kept with no reason |
| Layering | a pure package importing from core, platform specifics landing in shared code, a provider importing another provider, a boundary crossed the wrong way |
| Dependency API | use of a dependency's non-public API, a deep import past its `exports` map |
| New dependency | any addition to `package.json`. It needs a justification, a maintenance and last-release check, and MIT or ISC compatible licensing |
| Naming | a name that disagrees with the sibling packages that do the same thing |
| Security | secrets logged or put in an error message, secret comparison that is not constant time, a shell command built from an external value, path traversal, a branch that rejects input with no negative test covering it |
| Spec conformance | when the change claims to implement a specification, check it against the specification text |

For the new dependency row:

```bash
git diff origin/main...HEAD -- '**/package.json'
npm view <pkg> time.modified license
pnpm why <pkg>
```

### Step 5: Ground every finding in a line

A finding that cannot be pointed at a line gets dropped. No exceptions, and the
same rule applies to anything a subagent returns.

1. Every finding cites a path and a line number that exists on the reviewed
   revision. Read the cited lines before writing the finding down.
2. Never assert what a library does. Read it in `node_modules/<pkg>` or in the
   published source and cite the file.
3. Never assert what a specification says from memory. Quote the specification
   text and cite the section.
4. If the claim depends on a command's behaviour, run the command and use the
   real output.

```bash
sed -n '<start>,<end>p' <path>
cat node_modules/<pkg>/package.json
sed -n '1,80p' node_modules/<pkg>/dist/index.d.ts
```

A review that reports a plausible problem that is not in this change is worse
than a review that reports nothing. Anything that cannot be verified either
gets dropped or goes in a clearly labelled "Unverified" list at the end.

### Step 6: Report in the session

Print this. Do not write a file.

```markdown
## Review: <branch or PR>, <n> files, +<add>/-<del>

Scope: `git diff origin/main...HEAD` (three-dot, so upstream commits are excluded)

| ID | Severity | Location | Finding |
|----|----------|----------|---------|
| R1 | High | `packages/core/src/verify.ts:42` | Secret compared with `===` |
| R2 | Medium | `packages/cli/src/run.ts:88` | `timeout` option accepted but not passed to `exec` |

### R1: <title>

**Severity:** High
**Location:** `packages/core/src/verify.ts:42`

Evidence: the cited lines, quoted.

Why it matters: the concrete consequence in this codebase, not a principle.

Suggested fix: what to change, and the `package.json` script that proves it.
```

Severity: Critical is exploitable, data-losing or already broken. High is a
real defect or a boundary violation that will cause one. Medium is a smell, a
missing negative test, drifted docs. Low is naming, consistency, tidying.

Ids are `R1`, `R2`, `R3` and stay stable once printed. If the review finds
nothing, say that plainly and name what was checked; do not manufacture a Low.

Do not offer to start fixing. If the user asks for the findings to be worked,
that is `execute-plan`, and only then.

### Step 7: Mode 2, sweep the PR review comments

Use the API. Never scrape the pull request page: the HTML hides collapsed and
outdated threads, so a scrape reports fewer comments than exist. A sweep is not
finished until the remaining unresolved and non-outdated count has been
re-fetched from the API and reported.

Enumerate every thread with its resolved and outdated state:

```bash
gh pr view <n> --json url,headRefName,baseRefName

gh api graphql -f query='
query($owner:String!, $repo:String!, $pr:Int!) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$pr) {
      reviewThreads(first:100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first:50) { nodes { databaseId author { login } body } }
        }
      }
    }
  }
}' -F owner=<owner> -F repo=<repo> -F pr=<n>
```

For a pasted `#discussion_r<id>` URL, resolve that one comment directly:

```bash
gh api repos/<owner>/<repo>/pulls/comments/<id>
```

Build the ledger before touching any code:

| Thread | Path:line | Resolved | Outdated | Action |
|---|---|---|---|---|

The work set is threads where `isResolved` is false and `isOutdated` is false.
Resolved or outdated threads are listed for completeness and not acted on.

For each thread in the work set, in this order:

1. **Judge it first.** Read the code the comment points at on the current head.
   Decide: valid, already addressed, or wrong. A review comment is an opinion,
   including one from a bot. Acting on a wrong comment makes the code worse.
2. If valid, make the change.
3. If already addressed, note the commit or the line that addresses it.
4. If wrong, do not change the code. Say why, cite the `file:line` or the
   dependency source that settles it, and push back on the thread.
5. Reply on the thread either way:

```bash
gh api repos/<owner>/<repo>/pulls/<n>/comments \
  -f body='<what changed, or why this is not a change>' \
  -F in_reply_to=<databaseId>
```

Never resolve a thread you disagreed with; leave the author to close it.

After the work set is done, call the `verify` skill and paste its report block.
No fix made during a review is complete until `verify` has passed on it.

Then re-fetch and report:

```bash
gh api graphql -f query='...same query...' -F owner=<owner> -F repo=<repo> -F pr=<n>
```

The closing report states: total threads, how many were unresolved and not
outdated at the start, what was changed, what was pushed back on, and the
remaining unresolved and non-outdated count after the push. Every thread left
unaddressed is listed by name with the reason. "All comments addressed" without
that count is not an acceptable answer.

If the user asks for a second sweep or "can you check for more comments", run
the same query again from scratch rather than reusing the earlier result; new
comments arrive between passes.

### Step 8: Mode 3, plain review

When the user asks for a general or quick review, or explicitly says to do it
without the skill's ceremony, drop the machinery: no personas, no severity
table, no ids.

Keep only these, because they are what make a review true rather than
decorative:

- The three-dot diff for a branch, from Step 2.
- Reading past the diff, from Step 3.
- A `file:line` behind every point raised, from Step 5.

Report as short prose grouped by file, longest concern first, and say plainly
if nothing needs changing. Do not escalate back into the full format unless the
user asks.

### Step 9: Second-pass review

"Please do a second check" means re-review the current state, not re-print the
last report.

1. Re-run the scope commands from Step 1. The diff has moved.
2. For each finding from the previous pass, state one of: fixed, and cite the
   line that fixes it; not fixed, and cite the line that still shows it; or no
   longer applicable, and say why.
3. Review the new hunks as a fresh change through Step 4. Fixes introduce
   defects of their own, so the second pass is not a checklist tick.
4. Call `verify` before saying any of the previous findings are resolved.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using a two-dot `git diff origin/main..HEAD` for a branch review | Use the three-dot form. Two dots pulls in unrelated upstream commits and produces findings about code the author never touched. |
| Diffing without fetching first | `git fetch origin main` before every branch diff, or the merge base is stale and the scope is wrong. |
| Reporting a finding without a line reference | Cite `path:line` or drop the finding. |
| Acting on a review comment without checking it is correct | Judge the comment against the code first. Wrong comments get a reasoned push-back on the thread, not a change. |
| Scraping the pull request page for comments | Use `gh api` and the `reviewThreads` GraphQL query. The page hides collapsed and outdated threads. |
| Writing a plan file at the end of a review | Reviews print in the session. Plan files are `audit`'s output. |
| Reviewing only the diff hunks | Read the whole changed file and its callers. A diff hides missing pass-through and orphaned exports. |
| Saying "all comments addressed" without a count | Re-fetch the threads and report the remaining unresolved and non-outdated count. |
| Resolving a thread you argued against | Reply with the reasoning and leave it open for the author. |
| Claiming what a library or a specification does from memory | Read `node_modules/<pkg>` or quote the specification section. |
| Claiming a fix from a review is done without running anything | Call `verify` and paste its report block first. |
| Running the full ceremony when asked for a general review | Mode 3: prose, no table, no personas. Keep the three-dot diff and the line citations. |
| Re-printing the first report as the second check | Re-run the diff and classify each old finding as fixed, not fixed, or no longer applicable, with a line. |
| Offering to fix everything at the end of a review | Report and stop. Fixing findings is `execute-plan`, and only if the user asks. |
| Padding a clean review with Low-severity filler | Say nothing needs changing and name what was checked. |
