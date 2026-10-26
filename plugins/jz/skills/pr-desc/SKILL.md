---
name: pr-desc
description: Use when a pull request needs a title and body written or rewritten from the diff. Triggers on requests like "write the PR description", "update the PR description", "the PR body is too long", "regenerate the PR body", "PR #NNN description update", "be more succinct in the PR", or when the `ship` skill reaches its PR step and needs body text.
---

# pr-desc

## Overview

Writes a pull request title and body from the diff alone. The body has exactly
three sections, Summary, Trade-offs and Follow-ups, and nothing else.
Guarantees that no test plan, no session narrative, no security-review
commentary and no release-type opinion reaches the PR, that the title is a
Conventional Commit subject because the repo squash-merges, and that an existing
body is never overwritten without showing the change first.

Template: `template.md`, in the same directory as this SKILL.md. Locate it
through the skill directory this SKILL.md was loaded from. Codex resolves
relative paths in a SKILL.md relative to its directory too, so no
agent-specific path is needed.

## Modes

| User asked | Mode | Runs steps |
|---|---|---|
| "write the PR description", called by `ship` | create | 1-5, 7-9 |
| "update the PR description", "regenerate the PR body", "PR #NNN description update", "the PR body is too long" | update | 1-9 |

Update mode writes to a PR that already exists on the remote. Never upgrade
create mode into an edit of a live PR on your own initiative.

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

### Step 3: Write the three sections

Exactly these, in this order. Add no others.

**Summary.** A short paragraph, or a few bullets. What changed and why. It is
not a change log: do not walk the file list, and do not restate what the diff
already shows line by line. A reviewer should be able to read it in fifteen
seconds and know what they are about to look at.

**Trade-offs.** What was chosen over what, and what it costs. One line per
decision.

**Follow-ups.** What was deliberately left out, and where it should land.

Trade-offs and Follow-ups are omitted entirely when there are none. An empty
heading, `N/A`, or a line of filler under a heading is worse than no heading.
Only Summary is always present.

### Step 4: Record a time-boxed decision

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

### Step 5: Strip

Read the drafted body back and remove every one of these before it goes
anywhere.

| Never appears | Why |
|---|---|
| `## Test Plan`, `## Verification`, a checklist of how it was checked | Verification happens in the `verify` skill and in CI, not in prose here |
| Narration of how the change was arrived at, what was tried first, what the session did | The reviewer wants the change, not its history |
| Security-review commentary, threat notes, "no vulnerabilities found" | Belongs in a review, not in the PR body |
| An opinion on release type, version bump, patch/minor/major, "safe to release" | That decision belongs to the repo owner |
| Agent session links, in any form | House rule |
| Model names or any AI identifier, generated-by trailers | House rule |
| Emoji, in the title or the body | House rule |

If the user asked for the body to be shorter, cut Summary to its load-bearing
sentences and drop any Trade-offs or Follow-ups line that does not change what a
reviewer would do.

### Step 6: Update mode only, read the current body first

Given a PR number or URL, fetch what is there now before writing anything:

```bash
gh pr view <number> --json number,title,body,headRefName,baseRefName
gh pr diff <number>
```

Check out or fetch the PR's head branch so step 1's diff reflects the current
state, then regenerate the title and body from that diff. Do not patch the old
text: the approach may have changed since it was written, and edited-in-place
prose keeps stale claims alive.

### Step 7: Show before you write

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

### Step 8: Write it

Write the body to a file rather than passing it inline, so markdown and newlines
survive.

Update:

```bash
gh pr edit <number> --title "<conventional subject>" --body-file <file>
```

Create, draft unless the user says otherwise:

```bash
gh pr create --draft --title "<conventional subject>" --body-file <file>
```

No `--base` is passed: without it, `gh` targets the repository's default branch,
which is the same branch step 1 detected.

When called by `ship`, hand the title and body back and let `ship` run its own
PR-creation confirmation. Do not open the PR yourself in that case.

If `gh` is not authenticated or the command fails, stop and report. Print the
body so the user can paste it, and do not retry more than twice.

### Step 9: Report

State plainly:

- The title, and that it is a Conventional Commit subject under 72 characters
- Which sections the body has, and which were omitted because there was nothing
- Anything stripped, named item by item
- Any time-boxed decision recorded, and its revisit condition
- The PR URL and draft status, or that nothing was written to the remote

## Common Mistakes

| Mistake | Fix |
|---|---|
| Adding a `## Test Plan` or verification checklist | Summary, Trade-offs, Follow-ups only. Verification lives in CI and the `verify` skill. |
| Using `git diff origin/$base..HEAD` (two dots) | Use three dots. Two dots pulls in commits that landed on the default branch and describes other people's work. |
| A title that is not a Conventional Commit subject | Squash-merge makes the title the commit on the default branch, and CI rejects it. `<type>(<scope>): <subject>`, under 72 chars. |
| Saying the change is a patch, minor, or "safe to release" | That is the repo owner's decision. Cut the sentence. |
| Running `gh pr edit` before showing the before and after | Print both, name what is removed, ask, then write. |
| Writing the body from the session transcript | Read the diff and the commit subjects. If it is not in the diff, it is not in the body. |
| Carrying security-review notes from the session into the body | They belong in a review. Strip them. |
| Keeping empty `## Trade-offs` / `## Follow-ups` headings, or filling them with filler | Omit the section entirely when there is nothing to say. |
| A Summary that lists every changed file | A short paragraph or a few bullets on what changed and why. |
| Leaving an ignored advisory or pinned version unmentioned | Record what was ignored, why, and when to revisit it. |
| Patching the old body when the approach changed | Regenerate from the current diff so stale claims do not survive. |
| Opening the PR ready for review by default | `--draft` unless the user says otherwise. |
| An agent session link, model name, or emoji anywhere in the title or body | House rule. Strip before writing. |
