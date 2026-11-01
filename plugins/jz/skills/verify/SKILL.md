---
name: verify
description: Use when about to claim work is done, fixed, passing or complete, before any commit or PR, whenever the user challenges whether it really is, or when coverage has to reach a threshold. Triggers on requests like "is it done", "are you sure", "did the tests pass", "verify", "check it works", "still errors out", "bring coverage to 100%", "why is X still at 93.4%", "coverage report shows 0", "this file is untested", or when another skill calls this as its completion gate.
---

# verify

## Overview

The completion gate. It runs the repo's own commands and a spec's criteria,
pastes the real output and exit code of each, root-causes any failure
instead of routing around it, and says how far the proof went. The words
done, fixed and passing wait for its report block.

## Workflow

### Step 1: Fix the scope

Default to the whole repo. Narrow to `pnpm --filter <pkg>` (and
`--project <project>` for one vitest project) only when the change is
confined to one package and the user asked for it, or to isolate a failure.
A narrowed run is reported as narrowed, never as "the repo passes". After a
rebase, merge or squash, do Step 6 first.

### Step 2: Discover the real commands

Never invent a command. The lock file decides the package manager:

| Lock file | Prefix |
|---|---|
| `pnpm-lock.yaml` | `pnpm` |
| `package-lock.json` | `npm run` |
| `yarn.lock` | `yarn` |
| `bun.lockb`, `bun.lock` | `bun run` |

```bash
jq -r '.scripts | to_entries[] | "\(.key)\t\(.value)"' package.json
grep -E '^[A-Za-z0-9_-]+:' Makefile 2>/dev/null | cut -d: -f1
```

In a workspace, read the root and the target package's `package.json`. With
no `package.json`, the Makefile's targets are the commands, run as
`make <target>`. Map each concern to a script; a concern with none is
"no script", never an invented `npx tsc` or `npx biome`.

| Concern | Script names |
|---|---|
| typecheck | `typecheck`, `type-check`, `tsc`, `check-types` |
| lint | `lint`, `lint:ci`, `biome:check`, `eslint` |
| format | `format:check`, `biome:format`, `prettier:check` |
| test | `test`, `test:ci`, `validate`, `check` |
| coverage | `test:cov`, `coverage`, or the test script with coverage on; only when a threshold applies |
| build | `build`, `build:ci` |
| cross-runtime | `test:bun`, `test:deno`, `test:platform-*`, `test:dist-*` |
| criteria | the criteria of the requirements a spec step serves, or a brief's acceptance list; each check run as written |
| behaviour | the nearest `VERIFICATION.md` |

The nearest `VERIFICATION.md` is found like `AGENTS.md`: walk up from each
changed path's directory to the repo root and take the first one; never look
outside the repo. Its Drive section is what a `live-verified` behaviour row
cites.

```bash
root="$(git rev-parse --show-toplevel 2>/dev/null)"; p="<changed path>"
recipe="no recipe"
if [ -n "$root" ]; then
  root="$(cd -P "$root" && pwd)"
  case "$p" in /*) dir="$(dirname "$p")" ;; *) dir="$root/$(dirname "$p")" ;; esac
  while [ ! -d "$dir" ]; do dir="$(dirname "$dir")"; done
  dir="$(cd -P "$dir" && pwd)"
  while case "$dir" in "$root"|"$root"/*) true ;; *) false ;; esac; do
    [ -f "$dir/VERIFICATION.md" ] && { recipe="$dir/VERIFICATION.md"; break; }
    [ "$dir" = "$root" ] && break; dir="$(dirname "$dir")"
  done
fi
echo "$recipe"
```

The nearest existing directory is resolved with `cd -P` before the
containment check, so a `..` segment or a symlink that leads outside the
repo, or no git repo at all, is "no recipe".

### Step 3: Run cheapest first

Order: typecheck, lint, format, test, coverage, build, cross-runtime, then
each criterion's check. A Drive step runs inside the recipe's Launch and
Cleanup. The first failure stops the run: go to Step 5. Concerns never
reached are `not run`, not passing.

```bash
mkdir -p .verify-logs
pnpm typecheck > .verify-logs/typecheck.log 2>&1; echo "exit=$?"
tail -40 .verify-logs/typecheck.log
```

Read `$?` on the line right after the command; a pipe into `tail` hides it.
Never stage `.verify-logs/`.

### Step 4: Paste the evidence

For each command: the exact command, the exit code, and the last 20 to 40
lines of output. A test claim pastes the pass and fail counts. A coverage
claim pastes the per-file table: one file at 93.4% under a 100% headline
means not met.

**Coverage that looks wrong.** A zero, or a missing file, is almost always
the invocation, not missing tests. In a workspace the run needs both
`--filter <pkg>` and `--project <project>`. Re-derive them from
`pnpm-workspace.yaml` and the vitest config; after 3 invocations, report
each command and what it ruled out:

| Symptom | Cause |
|---|---|
| `No test files found` | The filter or project selects nothing; re-read the workspace and vitest project names |
| Tests run, every file 0% | `coverage.include` misses the source, or the run measured built output |
| Files missing from the table | `coverage.all` is off |
| Helpers or test files in the table | `coverage.exclude` is wrong; fix the config, don't test them |

**Raising coverage.** One file at a time, in report order. Reach each
uncovered branch through the public API, assert what it does, and re-run.
Before writing an ignore hint, check the provider: `/* v8 ignore next */`
under v8 (the house default), with `@preserve` if the build strips
comments, never the istanbul syntax. A branch that truly
can't be reached is reported with its `file:line` and lettered options, not
ignored.

### Step 5: On failure, root-cause it

None of these is a fix, and none may be used to reach green:

| Forbidden | Why |
|---|---|
| Weakening, deleting or `.skip`-ing a test | Hides the defect |
| A swallowing `try`/`catch` or a fallback | Moves the failure to runtime |
| `any`, `as unknown as`, `@ts-ignore` | Loosens the type |
| Disabling a lint rule | Silences it |
| Lowering a coverage threshold, or ignoring a reachable branch | Redefines the goal |
| `--no-verify`, `--passWithNoTests` | Bypasses the gate |
| Re-running until it passes | Unproven |

If a rule, threshold or assertion really is wrong, say so and ask; don't
fold the change into a fix.

Read the error and the line it names, reproduce it with the smallest command
(`pnpm --filter <pkg> test -- -t "<name>"`), state one hypothesis, fix the
cause, re-run the small command, then the full sequence. Count attempts:
after 3, stop and report the failing command, the smallest reproduction,
each hypothesis and what ruled it out, and the question that would unblock
it. Don't commit or claim done.

### Step 6: After a rebase, merge or squash

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git status; git diff --check
ls .git/rebase-merge .git/rebase-apply 2>/dev/null
git log --oneline "origin/$base..HEAD"
```

No rebase in progress, no unresolved paths, no conflict markers, only this
branch's commits on top of `origin/$base`. Then run Steps 2 to 4 on the
rebased tree: a clean status proves nothing about whether the code works.

### Step 7: The report block

Every completion claim ends with this, filled from real runs:

```markdown
## Verification

Scope: <whole repo | pnpm --filter @scope/pkg>
Commands read from: <package.json | Makefile>

| Concern | Command | Exit | Result |
|---|---|---|---|
| typecheck | pnpm typecheck | 0 | pass |
| test | pnpm test | 0 | pass |
| coverage | pnpm test:cov | 0 | pass: every file at 100% (table above) |
| format | (no script) | - | not covered |
| C2.1 tampered cookie refused | pnpm test -- -t "tampered cookie" | 0 | pass |
| C3.1 quickstart runs as written | inspection: ran each README command in a fresh clone | - | met |
| behaviour | Drive step D3 of VERIFICATION.md | 0 | live-verified |
```

- One row per concern; none omitted. Results are `pass`, `fail`,
  `not covered` or `not run`; an inspection criterion is `met` or `not met`.
- One row per criterion, before `behaviour`, run as the criterion names it.
  One with no check reads `(no check)` and `not run`. With no criteria, one
  row reads `criteria | (none) | - | not covered`.
- The `behaviour` row is last and says how far the proof went, from what
  actually ran, never raised because criteria pass:

| Value | Holds when |
|---|---|
| `live-verified` | The changed behaviour was driven end to end on the real system started locally, against mocks or fixtures, with the run pasted: a Drive step, a browser on the dev server, a real request, the built CLI on a fixture |
| `unit-only` | A passing test exercises the changed behaviour; nothing drove the feature |
| `type-check-only` | Only typecheck, lint or format covers the change |
| `not run` | Nothing above ran, or the run stopped first |

- Any `fail`, `not met` or `not run` row, or a behaviour row below the level
  the spec or brief asks for, means the reply says blocked or not met and
  names each one.
- Done, fixed, passing, complete and green appear only with this block,
  every criterion reading `pass` or `met`, no `fail` row, and the behaviour
  level at or above the target.
- Never deploy to, log in to or write to a live or shared environment to
  verify; that is the owner's step.

## Common Mistakes

| Mistake | Fix |
|---|---|
| "All tests pass" with nothing pasted | Command, exit code, output tail |
| An invented command | Read `package.json` or the Makefile; else "no script" |
| `$?` read after a pipe | Redirect to a log, read `$?`, then `tail` |
| A headline coverage number | Paste the per-file table |
| A zero coverage report treated as no tests | Fix the filter, project or config first |
| An istanbul ignore under v8 | Check the provider; `v8 ignore` |
| Lowering a threshold to meet it | Test the branch, or report it unreachable with options |
| `live-verified` from a green suite | That's `unit-only` at most; drive the feature |
| Leaving out a criterion that didn't run | Its row reads `not run` |
| A narrowed run reported as the whole repo | Say the scope |
| A rebase called done on a clean status | Run the tests on the rebased tree |
