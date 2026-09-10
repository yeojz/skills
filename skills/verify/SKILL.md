---
name: verify
description: Use when about to claim work is done, fixed, passing or complete, before any commit or PR, and whenever the user challenges whether it really is. Triggers on requests like "is it done", "are you sure", "did the tests pass", "verify", "check it works", "still errors out", "why is coverage still", or when another skill calls this as its completion gate.
---

# verify

## Overview

The completion gate for every other skill in this repo. It discovers the repo's
real commands from `package.json`, runs them cheapest first, pastes the actual
output and exit code for each, root-causes any failure instead of routing around
it, and blocks the words done, fixed and passing until an evidence block exists.

The failure this exists to prevent is work reported as complete that was not.
A summary sentence is not evidence. Command output is evidence.

## Workflow

### Step 1: Fix the scope before running anything

| Scope | How to run |
|---|---|
| Whole repo | `pnpm <script>` at the workspace root |
| One package | `pnpm --filter <pkg> <script>` |
| One vitest project | `pnpm --filter <pkg> test:ci --project <project>` |
| Coverage in a workspace | Needs both the filter and the project |
| After rebase, merge or squash | Step 7 first, then this whole workflow |

Default to whole repo. Narrow to a filter only when the change is confined to one
package and the user asked for that package, or when isolating a failure in
Step 5. A narrowed run is reported as narrowed, never as "the repo passes".

### Step 2: Discover the real commands

Never invent a command. Read the scripts that exist.

```bash
cat package.json
cat package.json | jq -r '.scripts | to_entries[] | "\(.key)\t\(.value)"'
```

In a monorepo, read the workspace root's `package.json` and the target package's
`package.json`. Root scripts usually fan out; package scripts are what a filter
targets.

```bash
cat pnpm-workspace.yaml
cat packages/<pkg>/package.json | jq -r '.scripts'
```

Detect the package manager from the lock file, never from habit:

| Lock file | Command prefix |
|---|---|
| `pnpm-lock.yaml` | `pnpm` |
| `package-lock.json` | `npm run` |
| `yarn.lock` | `yarn` |
| `bun.lockb` or `bun.lock` | `bun run` |

Then build the coverage table, mapping each concern to a discovered script:

| Concern | Script names to look for |
|---|---|
| format | `format`, `format:check`, `biome:format`, `prettier:check` |
| lint | `lint`, `lint:ci`, `biome:check`, `eslint` |
| typecheck | `typecheck`, `type-check`, `tsc`, `check-types` |
| test | `test`, `test:ci`, `test:cov`, `coverage` |
| build | `build`, `build:ci` |
| cross-runtime | `test:bun`, `test:deno`, `test:platform-*`, `test:dist-*` |

If a concern has no script, write "no script" in that row and move on. Do not
substitute an invented equivalent such as a bare `tsc --noEmit` or `npx biome`
when the repo does not define one. An invented command that passes proves
nothing about the repo's own gate.

### Step 3: Run cheapest to most expensive

Fast failures must surface first, so run in this order:

1. `typecheck`
2. `lint`, then `format:check`
3. `test`
4. `build`
5. cross-runtime: `test:bun`, `test:deno`, `test:platform-*`, `test:dist-*`

The first non-zero exit stops the sequence. Go to Step 5. Do not run the
expensive tail on a tree that is already broken, and do not report the concerns
that were never reached as passing; they are "not run".

Capture output and the exit code exactly:

```bash
mkdir -p .verify-logs
pnpm typecheck > .verify-logs/typecheck.log 2>&1; echo "exit=$?"
tail -40 .verify-logs/typecheck.log
```

Use `$?` on the line immediately after the command. A pipeline into `tail` hides
the real exit code, which is how a failing command gets reported as green.

`.verify-logs/` is scratch. Never stage it.

### Step 4: Paste the evidence, not a description of it

For every command run, the reply contains three things:

- The exact command, including any filter and project flags.
- The exit code.
- The last 20 to 40 lines of real output, in a fenced block.

Extra rules for the places where a summary most often diverges from the output:

- Coverage claims paste the per-file coverage table, not a headline percentage.
  A repo-level "100%" that hides one file at 93.4% is a false report.
- A test claim pastes the pass and fail counts line, not "all tests pass".
- If output is very long, paste the tail plus every failure line, never a
  paraphrase of the middle.

### Step 5: On failure, root-cause it

The workaround reflex is forbidden. None of the following counts as a fix, and
none of them may be used to reach green:

| Forbidden | Why |
|---|---|
| Weakening or deleting an assertion | Hides the defect the test caught |
| `.skip`, `.todo`, `it.only`, commenting a test out | Removes the signal |
| Adding a fallback or a swallowing `try`/`catch` | Moves the failure to runtime |
| `any`, `as unknown as`, `@ts-ignore`, `@ts-expect-error` | Loosens the type instead of fixing it |
| Disabling a lint rule or adding an ignore comment | Silences the rule |
| Lowering a coverage threshold | Redefines the goal to match the result |
| `--no-verify`, `--passWithNoTests`, `--bail` to hide failures | Bypasses the gate |
| Re-running until it passes and calling it flaky | Unproven claim |

If a rule, threshold or assertion genuinely is wrong, that is a separate change:
say so, explain why, and ask. Do not fold it into a fix silently.

The procedure:

1. Read the actual error text and the file and line it names.
2. Isolate with the smallest command that still reproduces it.
3. Form one hypothesis about the cause, stated in the reply.
4. Fix the cause.
5. Re-run the same smallest command, then re-run the full command from Step 3.

Isolation commands:

```bash
pnpm --filter <pkg> test:ci --project <project> -- <path/to/file.test.ts>
pnpm --filter <pkg> test:ci -- -t "<test name>"
pnpm --filter <pkg> exec tsc --noEmit -p tsconfig.json
```

If the cause is not obvious after reading the error, report the smallest
reproducing command and its output rather than guessing at a change.

### Step 6: Bound the fix loop at 3 attempts

Count attempts out loud: attempt 1 of 3, attempt 2 of 3, attempt 3 of 3. An
attempt is one hypothesis plus one fix plus one re-run.

After the third failed attempt, stop editing and report:

- The failing command and its exit code.
- The smallest reproducing command.
- The tail of the failing output.
- Each hypothesis tried and what ruled it out.
- What is blocking, and the one question that would unblock it.

Do not commit. Do not open a PR. Do not claim done, fixed or passing.

### Step 7: Verify git state after any rebase, merge or squash

A rebase that reports success and leaves conflicts behind is the same failure in
another costume. After any history operation, prove the state:

```bash
git status
git log --oneline -10
git log --oneline origin/main..HEAD
git diff origin/main...HEAD --stat
git diff --check
```

Check for an operation that stalled rather than finished:

```bash
ls .git/rebase-merge .git/rebase-apply 2>/dev/null
grep -rn '^<<<<<<< ' --exclude-dir=.git . || echo "no conflict markers"
```

All of the following must hold before the operation is called complete:

| Assertion | How it shows |
|---|---|
| No rebase in progress | `.git/rebase-merge` and `.git/rebase-apply` absent |
| No unresolved paths | `git status` shows no `UU` or `both modified` |
| No conflict markers left in files | `git diff --check` clean, grep finds none |
| Branch sits on top of upstream | `git log --oneline origin/main..HEAD` lists only your commits |
| The diff is the intended change | `git diff origin/main...HEAD --stat` matches what was worked on |

Fetch first if `origin/main` may be stale: `git fetch origin main`.

Then run Steps 2 through 4 on the rebased tree. A rebase is not complete until
the test commands pass on the rebased tree. Clean `git status` alone proves
nothing about whether the code still works.

### Step 8: Emit the final report block

Every completion claim ends with this block, filled from real runs:

```markdown
## Verification

Scope: <whole repo | pnpm --filter @scope/pkg | --project <project>>
Commands read from: <path/to/package.json>

| Concern | Command | Exit | Result |
|---|---|---|---|
| typecheck | pnpm typecheck | 0 | pass |
| lint | pnpm lint | 0 | pass |
| test | pnpm test | 0 | pass |
| build | pnpm build | 0 | pass |
| test:deno | pnpm test:deno | 0 | pass |
| format | (no script) | - | not covered |
```

Rules for the block:

- One row per concern from the Step 2 table. No concern is omitted.
- `Result` is `pass`, `fail`, `not covered` or `not run`. Nothing else.
- Any `fail` row means the reply says blocked and pastes the failing output.
- The words done, fixed, passing, complete, working and green may not appear in
  the reply unless this block is present and no row says `fail`.
- If the scope was narrowed, the scope line says so. A filtered run never
  supports a claim about the whole repo.

## Common Mistakes

| Mistake | Fix |
|---|---|
| "All tests pass" with no output pasted | Paste the command, the exit code and the output tail |
| Inventing `npx tsc --noEmit` when the repo has no typecheck script | Read `package.json`; record "no script" instead |
| Piping into `tail` and reading `$?` from the pipeline | Redirect to a log file, read `$?`, then `tail` the file |
| Reporting coverage from a headline number | Paste the per-file table; one file below target means not met |
| Running only `pnpm test` and calling the repo verified | Run typecheck, lint, build and the cross-runtime scripts too |
| Skipping cross-runtime scripts because Node passed | `test:bun`, `test:deno`, `test:dist-*` are separate rows in the block |
| Adding `@ts-ignore` or `any` to clear a typecheck failure | Root-cause the type; a loosened type is not a fix |
| Marking a test `.skip` to get a green suite | Fix the cause or report the blocker |
| Using `--no-verify` to get past a hook | Never. Fix what the hook caught |
| Looping on fixes indefinitely | Stop at 3 attempts and report the blocker |
| Calling a rebase done because `git status` is clean | Prove upstream position, then run the tests on the rebased tree |
| Reporting a `--filter` run as whole-repo verification | State the narrowed scope in the report block |
| Claiming a fix for a command the user says still errors | Re-run that exact command and paste its output |
