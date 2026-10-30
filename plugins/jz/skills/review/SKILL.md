---
name: review
description: Use when asked to review a change rather than a whole repo, or to deal with review comments on a pull request. Triggers on requests like "review my changes", "review this branch", "code review", "as a principal software engineer review the changes between this branch and main", "do a quick review of the changes", "do a general review without using the skill", "please do a second check", "check the PR comments", "are the comments addressed", "double check if the new PR comment is valid", "CI is red on the PR", "adversarial review", "get a second opinion on this diff", "have another model review it", "interrogate the diff", or when the user pastes a pull request or a `#discussion_r...` URL.
---

# review

## Overview

Diff-scoped review. It resolves what changed, reads the change plus the code
around it, and reports severity-ranked findings that each point at a real
`file:line`. Design and maintainability weigh the same as correctness, and
every new rejecting guard is sampled by deleting it and running the tests. It
also sweeps unresolved pull request review threads, judges whether each
comment is actually correct, classifies a red CI run before any retry,
addresses the valid ones and reports what is left. For a contested change it
runs the same brief through two model families and merges what they found.

Everything is printed in the session. This skill never writes a plan file; that
is `audit`, which is repo-wide and read-only. `review` is change-scoped and may
edit code when the user asks for the comments to be addressed.

Four modes:

| Mode | Trigger | Output |
|---|---|---|
| 1. Review a change | working tree, a branch against the default branch, a PR number or URL | severity table plus per-finding detail, in the session |
| 2. Sweep PR comments | "check the PR comments", "are the comments addressed", "CI is red", a pasted PR or `#discussion_r...` URL | thread ledger, CI classification, replies posted, remaining count |
| 3. Plain review | "do a general review", "without using the skill", "quick look" | prose notes, no personas, no table |
| 4. Adversarial review | "adversarial review", "second opinion", "have another model review it", "interrogate the diff", a coordinator brief that names a contested design | one brief to two or more reviewers on different model families, findings merged into act on, consider, noted and dismissed with an agreement map; nothing applied |

## Workflow

### Step 1: Resolve the scope before reading anything

Pick the scope from the wording. Default rather than ask when the wording is
clear.

| User says | Scope | Command |
|---|---|---|
| "my changes", "what I have so far", nothing committed | working tree | `git diff HEAD` plus `git status --short` |
| "this branch", "against main", "before I push" | branch | `git diff "origin/$base...HEAD"` |
| "the PR", a number, a PR URL | pull request | `gh pr diff <n>` |
| a `#discussion_r...` URL | one review thread, Mode 2 | Step 7 |
| "the comments", "are they addressed", "CI is red" | Mode 2 | Step 7 |
| "adversarial", "second opinion", "another model", "interrogate" | Mode 4, over the scope the rest of the sentence names | Step 10 |
| nothing identifiable, and the tree is dirty | working tree, say which you chose | |
| nothing identifiable, and the tree is clean | branch against the default branch | |

Establish the ground truth first:

```bash
git rev-parse --abbrev-ref HEAD
git status --short
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git fetch origin "$base"
git log --oneline "origin/$base..HEAD"
```

`$base` is the default branch read from the remote, so the same commands work
when it is `master`, `develop` or anything else. Every later command in this
skill reuses it.

### Step 2: Always use the three-dot form for a branch diff

```bash
git diff "origin/$base...HEAD" --stat
git diff "origin/$base...HEAD"
```

Three dots diffs against the merge base, so it shows only what this branch did.
Two dots diffs against the current tip of `origin/$base`, so every unrelated
commit that landed upstream since the branch started shows up as if it were
part of the change. That produces findings about code the author never touched.

Say which form was used and why in the report's scope line. When `origin/$base`
is stale the merge base is wrong, so `git fetch origin "$base"` runs first,
every time.

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
git diff "origin/$base...HEAD" --name-only
grep -rn "<changedSymbol>" --include="*.ts" packages/ apps/ internal/
grep -rn "from ['\"].*<changedModule>" --include="*.ts" .
```

Fan the lenses in Step 4 out to parallel subagents when the diff spans more
than a handful of files. Give each subagent the same scope, the same diff
command, and the grounding rules from Step 5. For a small diff run the lenses
yourself in sequence and say so.

### Step 4: Work the checklist

These are the recurring defects a change-scoped review is for. Walk them all;
do not stop at the first finding. Three lenses, Design, Maintainability and
Guard deletion, must report a line in Step 6 even when they found nothing;
they weigh the same as the correctness lenses, and a review that is silent on
them is incomplete, not clean.

| Lens | Look for |
|---|---|
| Design | the shape of the change: a public surface wider than the change needed, a decision an ADR or `docs/design.md` settled the other way, a seam placed where the next change in this area will have to move it. The Layering and Over-engineering rows feed this line. Must report |
| Maintainability | what the next reader pays: a comment that explains what instead of why, a test coupled to implementation detail, a module nobody can name the owner of. The Duplication, Dead code and Naming rows feed this line. Must report |
| Guard deletion | every new `if` that throws, returns early or rejects input: delete it, run the package tests, restore. A guard whose deletion stays green is a High. The script below does the loop. Must report |
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
git diff "origin/$base...HEAD" -- '**/package.json'
npm view <pkg> time.modified license
pnpm why <pkg>
```

For the guard deletion row, `guard-deletion.py` sits beside this file. It
lists every rejecting guard the diff added, then for each one in turn
neutralises its condition, runs the test command, restores the file byte for
byte and records whether the suite went red. List first, so the count and
the time per run are known before anything is mutated:

```bash
python3 <skill-dir>/guard-deletion.py --list "origin/$base" 'pnpm --filter <pkg> test:ci' packages/<pkg>
python3 <skill-dir>/guard-deletion.py "origin/$base" 'pnpm --filter <pkg> test:ci' packages/<pkg>
git status --short
```

The test command is the package's declared test script, read from its
`package.json` as `verify` Step 2 does, never invented. For a working-tree
review pass `HEAD` as the base ref. Run it once per changed package with that
package's script; when the list is long, pass the changed files instead of
the package directory and name in the report which guards were not sampled.

The script samples the tree it runs in, and its first line prints that
tree's HEAD and the merge base it used. Those must be the reviewed revision
and its real base. A working-tree or branch review on the reviewed branch
runs it in place. A pull request review, or any review where
`git rev-parse HEAD` is not the reviewed head, runs it in a throwaway
worktree detached at that head, installed from the lock file, against the
PR's own base branch; `gh pr diff` alone leaves the local tree on whatever
was checked out, and sampling there reports zero guards for a PR that added
some, or mutates code the PR never touched.

```bash
read -r head base_ref < <(gh pr view <n> --json headRefOid,baseRefName --jq '"\(.headRefOid) \(.baseRefName)"')
git fetch origin "$base_ref"
git fetch origin "refs/pull/<n>/head"
[ "$(git rev-parse FETCH_HEAD)" = "$head" ] || echo "PR head moved since gh pr view"
sample_dir="$(mktemp -d)"
git worktree add --detach "$sample_dir" "$head"
( cd "$sample_dir" && pnpm install --frozen-lockfile && python3 <skill-dir>/guard-deletion.py "origin/$base_ref" 'pnpm --filter <pkg> test:ci' packages/<pkg> )
git worktree remove --force "$sample_dir"
```

The script exits 1 when a mutant survived, and 2 when the baseline is
already red, a file could not be restored, or a guard was not sampled
because its mutant did not parse or its construct cannot be wrapped; on a 2,
stop and report that before anything else, and name every guard the output
lists as not sampled. Each survivor is a High finding that names the guard
by `file:line` and the test that should have failed. The `git status` after
an in-place run must match the one from Step 1.

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

Scope: `git diff "origin/$base...HEAD"` (three-dot, so upstream commits are excluded)

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

Below the detail sections, the three lenses that must report, one line each,
whether or not they produced a finding:

```markdown
### Lenses that must report

- Design: R3, or clean, checked <what: the boundaries, the new surface>
- Maintainability: clean, checked <what: duplicates grepped, names against <sibling>>
- Guard deletion: <n> guards sampled at <sha> with `<test command>`, <k> survived (R1), <j> not sampled and named, or no new rejecting guard in the diff
```

Severity: Critical is exploitable, data-losing or already broken. High is a
real defect, a boundary violation that will cause one, or a surviving guard
deletion. Medium is a smell, a missing negative test, drifted docs. Low is
naming, consistency, tidying. Design and maintainability findings take their
severity from their consequence, like any other; they are never demoted for
being design.

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

#### Classify a red CI run before any retry

A sweep covers the checks as well as the threads. Read every failing check
and classify it before touching the rerun button; a retry on a defect wastes
a run, and a retry on a stale base hides the fix that is needed.

```bash
gh pr checks <n>
gh run view <run-id> --log-failed
git diff "origin/$base...HEAD" --name-only
git fetch origin "$base"
git merge-base --is-ancestor "origin/$base" HEAD && echo "branch has the current base" || echo "branch is behind the base"
gh run list --branch "$base" --workflow "<workflow name from the failing check>" --limit 3
```

| Signal | Class | Do |
|---|---|---|
| The failing test or file is outside the diff's `--name-only` list and imports nothing the diff changed; the branch is behind `origin/$base`; the same check is green on the current `origin/$base` | Stale base | The fix is already on the default branch. Rebase through `ship`'s rebase step and push; the run on the rebased head going green is the proof. Never rerun the old head |
| The failing test or file is outside the diff and imports nothing the diff changed; the same check is red on the current `origin/$base` | Upstream failure | Not this PR's defect and not a rebase: rebasing onto a red base stays red. Report it as pre-existing with the base run's URL, and leave the check red until the default branch is fixed; it earns no rerun here |
| The failing test or file is in the diff, or imports something the diff changed | Defect | A finding with an R id, into the work set like a valid comment; a fix round, then `verify` |
| A timeout, a connection reset, a port already in use, a 429 or 5xx from a registry, a runner lost, and the same test passes locally on the same head | Suspected flake | One fresh run, once per failing check per head: `gh run rerun <run-id> --failed`. Then classify again |
| The second run fails on the same test with the same message | Not flake | It is a defect. No third run; the job is open until a fix lands and the run on the new head is green |
| CI runs a script the local gate skipped | Gap | Run that script locally first, then classify its failure by the rows above |

The rerun budget is one per failing check per head, ever. An identical
second failure is evidence, not bad luck. A check that is still red at the
end of the sweep is listed in the closing report with its class, next to the
remaining thread count.

In the desktop app, bind the PR once and turn its monitor on instead of
polling the checks or the app's PR status: the monitor wakes the session on a
CI failure, a merge conflict and a new review comment, and each wake is a
sweep through this step from scratch. Under another agent, re-fetch when the
user asks or a fix was pushed, never on a timer. Merging stays the owner's.

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

### Step 10: Mode 4, adversarial review

Two or more reviewers on different model families read the same brief and
never see each other's findings; this session verifies and merges what comes
back and applies nothing. It replaces the ad hoc "get another model to look
at it" session, and it is the second opinion `rules/models.md` asks for on a
contested design.

1. Resolve the scope through Steps 1 and 2 and record the head sha. Every
   reviewer reads the same revision.
2. Write one brief and save it to a file, in the group's notes folder when
   the session has one and in a temporary directory otherwise. It carries:
   the scope line and the exact diff command with the sha; the lens table
   from Step 4 with the three lenses that must report; the grounding rules
   from Step 5; the table shape from Step 6 with R ids, severity, `file:line`
   and quoted evidence; and the sentence "read only: edit nothing, run no
   formatter, post nothing". The brief is written once and sent verbatim to
   each reviewer; a brief that differs between reviewers makes the agreement
   map meaningless.
3. Start the reviewers in one batch, each fresh, none a fork of this session:
   - one on the review tier from `rules/models.md`, never below it;
   - one through Codex when its plugin is present, told read only. When the
     plugin is absent, say so and run the second reviewer as another fresh
     session on the review tier; two reviews from one family are weaker than
     two families, and the report says which it got.
   Label them A, B and so on, and record each label's family and tier. A
   reviewer that fails or returns nothing gets one fresh start; after that
   the report carries the reviewers that answered and names the gap.
4. Verify every finding yourself against the cited lines, as Step 5 requires,
   before it is bucketed. Agreement raises priority; it never stands in for
   verification, because two reviewers can agree on the same wrong claim.
5. Merge findings that point at the same defect, within a few lines of the
   same file, under one R id, and build the agreement map: one row per merged
   finding, one column per reviewer, each cell `raised <severity>`,
   `not raised` or `contradicted`.
6. Bucket on the evidence:

| Bucket | Means |
|---|---|
| Act on | Verified at the line and High or above, or raised by two or more reviewers and verified. A fix is expected before merge |
| Consider | Verified at the line, Medium or Low, or a judgment call the repo's docs do not settle. Named for the owner to decide |
| Noted | True, but outside this change or settled the other way by a documented decision. Recorded so it is not re-raised |
| Dismissed | Refuted by the cited code, the dependency source or the specification text, or not grounded in a line. Each one says which reviewer raised it and quotes what refutes it |

7. Print in the session:

```markdown
## Adversarial review: <branch or PR> at <sha>, <n> reviewers

Brief: <path>, identical for every reviewer
Reviewers: A = <family>, review tier; B = Codex through its plugin, <its reported tier>
Agreement: <k> of <m> merged findings raised by every reviewer; A only <p>; B only <q>

| ID | Location | A | B | Bucket |
|----|----------|---|---|--------|
| R1 | `packages/core/src/verify.ts:42` | raised High | raised Medium | act on |
| R2 | `packages/cli/src/run.ts:88` | raised Medium | not raised | consider |
| R3 | `packages/core/src/index.ts:7` | not raised | raised Low | dismissed |

### Act on
### Consider
### Noted
### Dismissed
```

Each section carries the Step 6 detail per finding plus a "Raised by" line.
Nothing is applied: no edit, no commit, no reply on a thread and no posted
review. When the user asks for the act-on list to be worked, that is
`execute-plan`; when a coordinator asked for the review, the buckets go back
to it as the verdict's evidence.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using a two-dot `git diff "origin/$base..HEAD"` for a branch review | Use the three-dot form. Two dots pulls in unrelated upstream commits and produces findings about code the author never touched. |
| Diffing without fetching first | `git fetch origin "$base"` before every branch diff, or the merge base is stale and the scope is wrong. |
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
| A report with no Design, Maintainability or Guard deletion line | The three lenses report every time, clean or not, with what was checked. Silence is an incomplete review, not a clean one. |
| Demoting a design finding because "it works" | Design and maintainability weigh the same as correctness; severity comes from the consequence. |
| Calling guard-deletion sampling done from reading the tests | Run `guard-deletion.py` with the package's declared test script and paste its table. A survivor is a High. |
| Running the guard-deletion script on a red baseline, or leaving a mutant behind | The script exits 2 on both; stop and report. The `git status` after the run matches the one before. |
| Pressing rerun on a red check before reading its log | Classify first: stale base rebases, a defect becomes a finding, a suspected flake earns one fresh run. |
| A second rerun because the first came back red again | An identical second failure is a defect, not a flake. The budget is one per failing check per head. |
| Rerunning a failure in code the diff never touched | Read the base first. Behind the base and green there is a stale base: rebase and push. Red on the base too is an upstream failure that no rebase fixes. Neither earns a rerun. |
| Prescribing a rebase because the same check is red on the default branch | That is an upstream failure, not a stale base. A rebase onto a red base stays red; report it as pre-existing with the base run's URL. |
| Running `guard-deletion.py` in whatever tree happens to be checked out | It samples the tree it runs in. For a PR, or when HEAD is not the reviewed head, run it in a worktree detached at the PR head against the PR's base, and check its first line names that head. |
| Polling the PR's checks or status in a loop | In the desktop app, bind the PR and turn the monitor on once; let the wake run the sweep. |
| Sending each adversarial reviewer its own wording of the brief | One brief, written once, sent verbatim to every reviewer; otherwise the agreement map compares different questions. |
| Letting the adversarial reviewers see each other's findings | Each reviewer is fresh and independent. Merging happens here, after both return. |
| Bucketing an adversarial finding on the vote count | Verify it at the line first. Two reviewers agreeing on a wrong claim is still dismissed, with the refuting line quoted. |
| Applying the act-on bucket from an adversarial review | Mode 4 applies nothing. Working the list is `execute-plan`, and only when asked. |
