# Handoff: <task>

Date: <YYYY-MM-DD HH:MM>

## Situation

One paragraph only: what the work is, why it was started, and where it stopped. No chat narrative.

<Paragraph. The work is <what>. It was started because <reason>. It stopped at <point> because <cause>.>

## Repo and branch

| Field | Value |
|---|---|
| Repo | <org/name or absolute path> |
| Branch | <type/scope-description> |
| Base branch | <default branch, as reported by `git ls-remote --symref origin HEAD`> |
| Pushed | <pushed to `<remote>` / not pushed> |
| Open PR | <#<number> or URL / none> |
| Working tree | <clean / dirty, <n> files> |

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git status --short
git branch --show-current
git log --oneline "$base..HEAD"
git status -sb
gh pr view --json number,url,state,isDraft
```

## Completed

An item with no evidence command is not complete. Move it to Remaining.

| Item | Evidence command | Result |
|---|---|---|
| <what was finished> | `<command that proves it>` | <actual output, for example `42 passed`> |
| <what was finished> | `<command that proves it>` | <actual output> |

## Remaining

In the order it should be done.

1. <task>. Files: `<repo-relative path>`, `<repo-relative path>`. Proven by `<command>` showing <expected result>.
2. <task>. Files: `<repo-relative path>`. Proven by `<command>` showing <expected result>.
3. <task>. Files: `<repo-relative path>`. Proven by `<command>` showing <expected result>.

## Files touched

- `<repo-relative path>`: <what changed in one line>
- `<repo-relative path>`: <what changed in one line>

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git diff --stat "$base...HEAD"
git status --short
```

## Verification

Read `package.json` scripts and run those. Never invent a command.

```bash
ls pnpm-lock.yaml package-lock.json yarn.lock bun.lockb 2>/dev/null
pnpm lint
pnpm typecheck
pnpm test
pnpm --filter <pkg> test:ci --project <project>
```

## Open questions and decisions owed

Present each of these as lettered options with a recommendation. Do not decide them unilaterally.

| # | Question | Options | Blocked work |
|---|---|---|---|
| 1 | <question> | a) <option>. b) <option>, recommended because <reason>. | <what cannot proceed until this is answered> |
| 2 | <question> | a) <option>. b) <option>, recommended because <reason>. | <what cannot proceed until this is answered> |

## Next session prompt

```text
Resume work in <absolute repo path> on branch <type/scope-description>, based on <default-branch>.

Rules: create a branch before editing and never edit on the default branch. If <type/scope-description>
does not exist locally, create it from <default-branch>. Do not create a git worktree.

Read the handoff at <repo-relative path to this file> before anything else. It holds
the current state, the completed items with the command output that proves each one,
the remaining work in order, and the open decisions.

Immediate next task: <first item from Remaining>, touching <repo-relative paths>.

Verification: read the scripts in package.json and run those; do not invent a command.
Do not claim anything is done, fixed or passing without pasting the output of the
command that proves it.

Open decisions are listed in the handoff. Present them as lettered options with a
recommendation and wait for an answer rather than deciding them yourself.
```
