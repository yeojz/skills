---
name: pr-desc
description: Use when a pull request needs a title and body written or rewritten from the diff. Triggers on requests like "write the PR description", "update the PR description", "the PR body is too long", "regenerate the PR body", "PR #NNN description update", "be more succinct in the PR", "add the verification to the PR body", or when the `ship` skill reaches its PR step, pushes a changed diff, or hands over a gate run and needs body text.
---

# pr-desc

## Overview

Writes a pull request title and body from the diff, plus a record of the
commands that actually ran. The body has at most four sections, Summary,
Trade-offs, Follow-ups and Verification, and nothing else. Guarantees that no
test plan, no session narrative, no security-review commentary and no
release-type opinion reaches the PR, that Verification names only commands
that ran in this session with their exit codes, that the title is a
Conventional Commit subject because the repo squash-merges, and that an
existing body is never overwritten without showing the change first.

Template: `template.md`, in the same directory as this SKILL.md. Locate it
through the skill directory this SKILL.md was loaded from. Codex resolves
relative paths in a SKILL.md relative to its directory too, so no
agent-specific path is needed.

## Modes

| User asked | Mode | Runs steps |
|---|---|---|
| "write the PR description", called by `ship` at its PR step | create | 1-6, 8-10 |
| "update the PR description", "regenerate the PR body", "PR #NNN description update", "the PR body is too long", called by `ship` after a push that changed the diff | update | 1-10 |
| Called by `ship` with a new run on the head the body already describes | refresh | 4, 7, 9, 10 |

Update and refresh modes write to a PR that already exists on the remote.
Never upgrade create mode into an edit of a live PR on your own initiative.

Refresh mode changes the Verification section and nothing else. If anything
outside that section would change, the mode is update, with its before and
after and its ask.

## Workflow

### Step 1: Read the diff, not the conversation

The body is written from what the diff shows. Nothing else is a source.

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git fetch origin "$base"
git diff "origin/$base...HEAD" --stat
git diff "origin/$base...HEAD"
git log "origin/$base..HEAD" --format='%s'
```

`base` is the remote's default branch, detected once and reused in every
command below. Never hard-code a branch name here: repos use `main`, `master`,
`develop` and others.

Use the three-dot form. `origin/$base...HEAD` diffs against the merge base, so
it shows only this branch's work. The two-dot form `origin/$base..HEAD` folds
in everything that landed on the default branch since the branch started and
produces a body describing other people's changes.

If the diff is empty, stop and report that there is nothing to describe.

Anything not visible in that diff does not belong in the body. The specific
failure this prevents: chat narrative and security-review commentary from this
session leaking into the PR. A reviewer reads the body next to the diff, not
next to the transcript. If a fact cannot be pointed at in the diff or the commit
subjects, drop it.

Verification is the one section with another source: the output of commands
that ran in this session, with their exit codes, which step 4 covers. That is
still not the conversation. A run is cited from its output, never from the
memory of having run it.

### Step 2: Write the title

A Conventional Commit subject. The repo squash-merges, so this string becomes
the commit on the default branch, and CI rejects a title that does not match the
convention.

```
<type>(<scope>): <imperative subject>
```

- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`,
  `ci`, `build`.
- Scope is the primary package or directory touched, taken from the diff paths.
  Omit the scope when the change spans several unrelated areas.
- Under 72 characters, including type and scope.
- Imperative mood, no trailing period, no emoji, no issue number.

| Diff | Title |
|---|---|
| `packages/auth/**` adds refresh tokens | `feat(auth): add refresh token rotation` |
| `packages/parser/**` fixes empty input crash | `fix(parser): handle empty input without throwing` |
| `.github/workflows/**` only | `ci: run vitest on node 22` |
| Changes across four unrelated packages | `refactor: extract shared http client` |

### Step 3: Write the sections from the diff

Exactly these, in this order, with Verification filled in step 4. Add no
others.

**Summary.** A short paragraph, or a few bullets. What changed and why. It is
not a change log: do not walk the file list, and do not restate what the diff
already shows line by line. A reviewer should be able to read it in fifteen
seconds and know what they are about to look at.

**Trade-offs.** What was chosen over what, and what it costs. One line per
decision.

**Follow-ups.** What was deliberately left out, and where it should land.

**Verification.** The commands that ran, each with its outcome. Step 4.

Trade-offs, Follow-ups and Verification are omitted entirely when there is
nothing real to put under them. An empty heading, `N/A`, or a line of filler
under a heading is worse than no heading. Only Summary is always present.

### Step 4: Fill Verification from real runs

One bullet per command that ran in this session, each with its outcome. The
sources, in order of preference:

| Source | What it gives |
|---|---|
| The `verify` report block the caller hands over | Command, exit code and result per concern, with the label the caller gave it: a head sha when the caller proved the committed tree is the tree it ran on, or `working tree before commit` when it did not |
| The gate `ship` ran on a clean detached checkout | The same, on the pushed head, marked as the detached run |
| A command run earlier in this session whose output is in the transcript | Command, exit code and result, read from that output |

Bullet shape, from the template:

```
- `<command>` on `<short sha>`: exit <code>, <result line from the output>
- `<command>` on `<short sha>`, clean detached checkout: exit <code>, <result line from the output>
- `<command>`, working tree before commit: exit <code>, <result line from the output>
```

Rules:

- Every bullet carries the exit code and names what it ran on. A bullet without
  an exit code is a claim, not a record.
- A sha goes on a bullet only when the run was provably on that commit: a
  detached checkout of it, a rebased or otherwise clean tree that is it, or a
  working-tree run the caller proved was committed unchanged. A run on a
  working tree that was then partly staged, or rewritten by a hook, is
  labelled `working tree before commit` and carries no sha. Never relabel a
  run with the sha that happened to be pushed afterwards.
- The result line is copied from the output: `142 passed`, `All checks
  passed`, the per-file coverage line. Never "passes" or "green".
- A run on an earlier head than the one being described proves another tree.
  When the body is rewritten after a push that changed the diff, bullets from
  the old head are dropped, not carried over.
- CI is not a bullet. Its verdict lives on the PR's checks tab, and a local
  run is never reported as CI passing.
- A non-zero exit is not hidden. The bullet stays with its exit code, and the
  report says the PR is not ready for review until a later run replaces it.
- Nothing ran, nothing to cite: omit the section and say so in the report. Do
  not run the gate from here to fill it. `verify` runs the gate, and `ship`
  calls it before it calls this skill.

### Step 5: Record a time-boxed decision

When the diff contains a deliberate temporary compromise, the body must say so.
This is not optional and it is not a follow-up bullet on its own.

Triggers, all visible in the diff:

| In the diff | What to record |
|---|---|
| An advisory or CVE added to an audit ignore list | Advisory id, what it affects, why it is being ignored now, when to revisit |
| A dependency pinned to an exact older version | The version, what breaks above it, what unpins it |
| A test skipped or a check disabled | What is skipped, why, what re-enables it |
| A `TODO` tied to an external fix or release | What is waited on, and where |

State three things: what was ignored or pinned, why, and when it should be
revisited. Put it in Summary when it is a main point of the PR, otherwise in
Trade-offs. Revisit conditions are concrete: an upstream release, a date, a
version. "Later" is not a revisit condition.

Do not extend this into an opinion about whether the compromise is acceptable to
ship or what release it belongs in.

### Step 6: Strip

Read the drafted body back and remove every one of these before it goes
anywhere.

| Never appears | Why |
|---|---|
| `## Test Plan`, a how-to-test checklist, a Verification bullet with no run behind it | Verification records commands that ran, with exit codes. Instructions for the reviewer and remembered runs are not records |
| Narration of how the change was arrived at, what was tried first, what the session did | The reviewer wants the change, not its history |
| Security-review commentary, threat notes, "no vulnerabilities found" | Belongs in a review, not in the PR body |
| An opinion on release type, version bump, patch/minor/major, "safe to release" | That decision belongs to the repo owner |
| Agent session links, in any form | House rule |
| Model names or any AI identifier, generated-by trailers | House rule |
| Emoji, in the title or the body | House rule |

If the user asked for the body to be shorter, cut Summary to its load-bearing
sentences and drop any Trade-offs or Follow-ups line that does not change what a
reviewer would do. Verification is already one line per run; it is not cut.

### Step 7: Update and refresh modes only, read the current body first

Given a PR number or URL, fetch what is there now before writing anything:

```bash
gh pr view <number> --json number,title,body,headRefName,baseRefName
gh pr diff <number>
```

In update mode, check out or fetch the PR's head branch so step 1's diff
reflects the current state, then regenerate the title and body from that diff.
Do not patch the old text: the approach may have changed since it was written,
and edited-in-place prose keeps stale claims alive.

In refresh mode, keep every line outside `## Verification` byte for byte and
rebuild that section from the runs handed over plus the bullets already there
for the same head. Compare the rest of the body before and after; a difference
anywhere else means this is update mode, so switch to it.

### Step 8: Show before you write

Print the proposed title and body in full.

In update mode, print the existing title and body next to the proposed ones so
the change is visible, and name what is being removed:

```
Before:
  <existing title>
  <existing body>

After:
  <proposed title>
  <proposed body>

Removed: <e.g. the Test Plan section, the release-type paragraph>
```

Then ask and wait for a yes:

> Update the body of PR #<number>?

Editing a PR body is a remote write, visible to everyone watching the PR, and it
destroys the previous text. Never run `gh pr edit` without that confirmation,
even when the user's request was itself "update the PR description": confirm the
content, not the intent.

Refresh mode is the exception. Nothing a reviewer reads changes, only the
record of runs grows, and the go-ahead `ship` is acting on covers it. Print the
bullets being added, skip the before-and-after and the ask, and name the
bullets in the report.

### Step 9: Write it

Write the body to a file rather than passing it inline, so markdown and newlines
survive.

Update and refresh:

```bash
gh pr edit <number> --title "<conventional subject>" --body-file <file>
```

Create, draft unless the user says otherwise:

```bash
gh pr create --draft --title "<conventional subject>" --body-file <file>
```

No `--base` is passed: without it, `gh` targets the repository's default branch,
which is the same branch step 1 detected.

When called by `ship` in create mode, hand the title and body back and let
`ship` run its own PR-creation step. Do not open the PR yourself in that case.
In update and refresh mode, `ship` hands over the runs and this skill edits the
PR.

If `gh` is not authenticated or the command fails, stop and report. Print the
body so the user can paste it, and do not retry more than twice.

### Step 10: Report

State plainly:

- The title, and that it is a Conventional Commit subject under 72 characters
- Which sections the body has, and which were omitted because there was nothing
- The Verification bullets and the head each ran on, or that the section was
  omitted because nothing ran
- Anything stripped, named item by item
- Any time-boxed decision recorded, and its revisit condition
- The PR URL and draft status, or that nothing was written to the remote

## Common Mistakes

| Mistake | Fix |
|---|---|
| Adding a `## Test Plan` or a how-to-test checklist | Summary, Trade-offs, Follow-ups, Verification only. Verification is the record of real runs, not instructions. |
| A Verification bullet from memory, from CI, or without an exit code | Cite the output: command, head, exit code, result line. Nothing ran, omit the section. |
| Putting the pushed sha on a run that happened before staging and commit | The sha belongs to runs proven to be on that commit. Otherwise the label is `working tree before commit`. |
| Carrying a Verification bullet from an earlier head across a push that changed the diff | Drop it. Cite the runs on the current head. |
| Running the test suite from this skill to fill Verification | `verify` runs the gate. This skill records what it was handed. |
| Treating a refresh that also reworded Summary as a refresh | That is update mode. Show before and after, ask, wait. |
| Using `git diff origin/$base..HEAD` (two dots) | Use three dots. Two dots pulls in commits that landed on the default branch and describes other people's work. |
| A title that is not a Conventional Commit subject | Squash-merge makes the title the commit on the default branch, and CI rejects it. `<type>(<scope>): <subject>`, under 72 chars. |
| Saying the change is a patch, minor, or "safe to release" | That is the repo owner's decision. Cut the sentence. |
| Running `gh pr edit` before showing the before and after | Print both, name what is removed, ask, then write. Refresh mode alone skips this. |
| Writing the body from the session transcript | Read the diff and the commit subjects. If it is not in the diff, it is not in the body. |
| Carrying security-review notes from the session into the body | They belong in a review. Strip them. |
| Keeping empty `## Trade-offs`, `## Follow-ups` or `## Verification` headings, or filling them with filler | Omit the section entirely when there is nothing to say. |
| A Summary that lists every changed file | A short paragraph or a few bullets on what changed and why. |
| Leaving an ignored advisory or pinned version unmentioned | Record what was ignored, why, and when to revisit it. |
| Patching the old body when the approach changed | Regenerate from the current diff so stale claims do not survive. |
| Opening the PR ready for review by default | `--draft` unless the user says otherwise. |
| An agent session link, model name, or emoji anywhere in the title or body | House rule. Strip before writing. |
