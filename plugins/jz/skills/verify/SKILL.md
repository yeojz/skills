---
name: verify
description: Use when about to claim work is done, fixed, passing or complete, before any commit or PR, and whenever the user challenges whether it really is. Triggers on requests like "is it done", "are you sure", "did the tests pass", "verify", "check it works", "still errors out", "why is coverage still", or when another skill calls this as its completion gate.
---

# verify

## Overview

The completion gate for every other skill in this repo. It discovers the repo's
real commands from `package.json` or its Makefile, runs them cheapest first,
pastes the actual output and exit code for each, root-causes any failure instead
of routing around it, names the behaviour level those runs support, and blocks
the words done, fixed and passing until an evidence block exists.

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

When there is no `package.json`, read the `Makefile` instead. A repo with no
JavaScript keeps its entry points there. List its targets:

```bash
grep -E '^[A-Za-z0-9_-]+:' Makefile | cut -d: -f1
```

The command prefix is then `make`, and a target runs as `make <target>`. If
neither file exists, every row of the coverage table is "no script", and the
report says so rather than inventing commands.

Then build the coverage table, mapping each concern to a discovered script or
Makefile target. The same names apply to both:

| Concern | Script names to look for |
|---|---|
| format | `format`, `format:check`, `biome:format`, `prettier:check` |
| lint | `lint`, `lint:ci`, `biome:check`, `eslint` |
| typecheck | `typecheck`, `type-check`, `tsc`, `check-types` |
| test | `test`, `test:ci`, `test:cov`, `coverage` |
| build | `build`, `build:ci` |
| cross-runtime | `test:bun`, `test:deno`, `test:platform-*`, `test:dist-*` |
| validate | `validate`, `check` (a single repo-wide gate, common in a Makefile) |
| behaviour | the nearest `VERIFICATION.md`, found as described below; "no recipe" when there is none |

The `behaviour` concern has a different source: a repository that can be driven
end to end keeps the recipe in `VERIFICATION.md`, a plain file next to
`AGENTS.md` with Launch, Doctor, Drive, Evidence and Cleanup sections and a map
from each acceptance to the drive step that proves it. Find it the way agents
find `AGENTS.md`: resolve each changed path against the repository root, walk
up from its directory and take the first `VERIFICATION.md` on the way, stopping
at the root, so a monorepo may keep one per package and one at the root and the
package one wins for a change under it. The walk never leaves the repository: a
path outside it, or a repository with no recipe at any level, is "no recipe",
never a file from a parent workspace or another project. Its Drive section is
the command the `behaviour` row cites when it reads `live-verified`. It is never under `.claude/`, which
stays out of git, and it is not a skill: Codex and a person run it the same way.
When there is none, the row can still reach `live-verified` from another pasted
run that drove the feature, a browser, a real request, a conformance tier, but
not from this skill inventing one.

```bash
root="$(git rev-parse --show-toplevel)"
dir="$(python3 - "$root" "<changed path>" <<'PY'
import os, sys
root, changed = sys.argv[1], sys.argv[2]
wanted = os.path.normpath(os.path.join(root, os.path.dirname(changed)))
kept = wanted
while not os.path.isdir(kept) and os.path.dirname(kept) != kept:
    kept = os.path.dirname(kept)
print(os.path.normpath(os.path.join(os.path.realpath(kept), os.path.relpath(wanted, kept))))
PY
)"
recipe="no recipe"
while case "$dir" in "$root"|"$root"/*) true ;; *) false ;; esac; do
  if [ -f "$dir/VERIFICATION.md" ]; then recipe="$dir/VERIFICATION.md"; break; fi
  [ "$dir" = "$root" ] && break
  dir="$(dirname "$dir")"
done
echo "$recipe"
```

The loop prints exactly one line. The directory is resolved without being
entered: a deleted file whose directory went with it is still a changed path in
`git diff --name-only`, so the path is normalised against the root as text and
canonicalised through its nearest surviving ancestor, which also resolves a
symlinked prefix the way `pwd -P` would. The `case` keeps the walk inside the
repository, the root test ends it after the root has been checked once, and the
first match ends it early, so a package recipe is never joined by the root one.

If a concern has no script, write "no script" in that row and move on. Do not
substitute an invented equivalent such as a bare `tsc --noEmit` or `npx biome`
when the repo does not define one. An invented command that passes proves
nothing about the repo's own gate.

### Step 3: Run cheapest to most expensive

Fast failures must surface first, so run in this order:

1. `typecheck`
2. `lint`, then `format:check`
3. `test`, or `validate` when the repo exposes a single repo-wide gate
4. `build`
5. cross-runtime: `test:bun`, `test:deno`, `test:platform-*`, `test:dist-*`

The first non-zero exit stops the sequence. Go to Step 5. Do not run the
expensive tail on a tree that is already broken, and do not report the concerns
that were never reached as passing; they are "not run".

Capture output and the exit code exactly:

```bash
mkdir -p .verify-logs
pnpm typecheck > .verify-logs/typecheck.log 2>&1; echo "exit=$?"
make validate > .verify-logs/validate.log 2>&1; echo "exit=$?"
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
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git status
git log --oneline -10
git log --oneline "origin/$base..HEAD"
git diff "origin/$base...HEAD" --stat
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
| Branch sits on top of the default branch | `git log --oneline "origin/$base..HEAD"` lists only your commits |
| The diff is the intended change | `git diff "origin/$base...HEAD" --stat` matches what was worked on |

`$base` is the default branch read from the remote, so the same commands work
when it is `master`, `develop` or anything else. Fetch first if `origin/$base`
may be stale: `git fetch origin "$base"`.

Then run Steps 2 through 4 on the rebased tree. A rebase is not complete until
the test commands pass on the rebased tree. Clean `git status` alone proves
nothing about whether the code still works.

### Step 8: Emit the final report block

Every completion claim ends with this block, filled from real runs:

```markdown
## Verification

Scope: <whole repo | pnpm --filter @scope/pkg | --project <project>>
Commands read from: <path/to/package.json or Makefile>

| Concern | Command | Exit | Result |
|---|---|---|---|
| typecheck | pnpm typecheck | 0 | pass |
| lint | pnpm lint | 0 | pass |
| test | pnpm test | 0 | pass |
| build | pnpm build | 0 | pass |
| test:deno | pnpm test:deno | 0 | pass |
| format | (no script) | - | not covered |
| behaviour | pnpm test:conformance -- fixtures/journal.ledger | 0 | live-verified |
```

Rules for the block:

- One row per concern from the Step 2 table. No concern is omitted.
- `Result` is `pass`, `fail`, `not covered` or `not run`. Nothing else, except
  on the `behaviour` row.
- The `behaviour` row is always present and last. Its `Result` is the highest
  level the pasted runs support, never the one intended, and its `Command` is
  the run that supports it:

| Value | Holds when |
|---|---|
| `live-verified` | The changed behaviour was driven end to end on the real system started locally, against mocks or fixtures where it has external dependencies, and the run is pasted: the Drive section of the nearest `VERIFICATION.md`, a browser against the dev server, a real request to a local process, the built CLI on a fixture, a conformance tier. A live or shared environment is never required for this level and is never touched unless the owner asked for that run |
| `unit-only` | The test script passed and a test in it exercises the changed behaviour; nothing drove the feature itself |
| `type-check-only` | Only typecheck, lint or format ran green over the change; no test exercises it |
| `not run` | Nothing above ran, or the sequence stopped at a failure before reaching it |

- A green suite with no test on the changed behaviour is `type-check-only`,
  not `unit-only`. Scripts passing says nothing about the feature having been
  exercised, which is what this row exists to separate.
- A brief or roadmap row that names a level under Done means is met only when
  this row reads that level or higher; a lower value is reported as not met,
  with what was not driven and why.
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
| Reporting "no script" for every concern on a repo with no `package.json` | Read the `Makefile`. Its targets are the repo's declared commands. |
| Writing `live-verified` because the test suite is green | Green scripts are `unit-only` at most. `live-verified` needs a pasted run that drove the feature on a running system |
| Inventing a live run when the repository has a `VERIFICATION.md` | Walk up from the changed paths, read the nearest one, run its Launch, Doctor, Drive and Cleanup as written, and cite its Drive step |
| Reading `VERIFICATION.md` and writing `live-verified` without running it | The recipe is the command; the row carries its pasted exit code and result, or the row stays at what did run |
| Deploying to, logging in to or writing to a cloud account, a preview, staging or production to verify | Verification runs the real system locally against mocks or fixtures. A live environment is the owner's step, taken only when they asked for that run |
| Leaving the `behaviour` row out, or filling it from the level the brief asked for | The row is always present, filled from what ran; a brief's level is a target the row is compared against, not a value to copy |
