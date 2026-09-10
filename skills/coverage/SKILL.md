---
name: coverage
description: Use when raising test coverage to a threshold, chasing the last uncovered lines or branches in a file, or explaining a coverage number that looks wrong. Triggers on requests like "bring coverage to 100%", "coverage is not at 100", "why is X still at 93.4%", "raise test coverage", "this file is untested", "coverage report shows 0", or when a package has a coverage threshold that is not met.
---

# coverage

## Overview

Raises coverage to a threshold and proves it with the report from a real run.
It resolves the correct workspace invocation before running anything, reads the
per-file table rather than a headline number, works one file at a time, covers
uncovered branches with real tests instead of ignores or lowered thresholds, and
ends by pasting the table with the target files visible in it.

Two failures this exists to prevent: a coverage number reported that was never
measured, and a zero-coverage report treated as an absence of tests when it is
almost always the wrong filter or project.

## Workflow

### Step 1: Resolve the invocation before running anything

Never run a guessed coverage command. Derive it from the files first.

```bash
cat package.json | jq -r '.scripts | to_entries[] | "\(.key)\t\(.value)"'
cat pnpm-workspace.yaml
cat packages/<pkg>/package.json | jq -r '.scripts'
ls vitest.config.* vitest.workspace.* vite.config.* 2>/dev/null
cat vitest.config.ts
```

Three things must be known before the first run:

| Question | Where the answer lives |
|---|---|
| Which script runs coverage | `test:ci`, `test:cov`, `coverage` in `package.json` scripts |
| Which package to filter | The path of the target file, matched to a workspace entry |
| Which vitest project to select | `test.projects` or `test.workspace` in the vitest config |

The house shape in a pnpm workspace needs both a filter and a project:

```bash
pnpm --filter <pkg> test:ci --project <project>
```

Worked examples of the same shape:

```bash
pnpm --filter core test:ci --project packages
pnpm --filter cli test:ci --project cli
```

The filter names the workspace package. The project names the vitest project
inside it. They are different values and both are required; a run missing
either one is the single most common cause of a wrong report.

If the repo has no vitest projects configured, drop `--project` and say so.
If there is no coverage script at all, stop and report that, rather than
inventing `npx vitest run --coverage`.

### Step 2: Treat a zero as a wrong invocation, not as missing tests

A coverage run that reports 0% while test files exist almost always means the
filter or the project is wrong, the run collected no test files, or the config
being applied is not the one that defines coverage. It almost never means the
code is untested.

The first response to a zero is to re-derive the invocation, not to write tests.
Writing tests against a broken invocation produces more tests and still a zero.

Check, in order:

```bash
pnpm --filter <pkg> test:ci --project <project> 2>&1 | head -30
pnpm --filter <pkg> exec vitest --version
ls packages/<pkg>/src/**/*-test.ts packages/<pkg>/src/**/*.test.ts 2>/dev/null | head
```

| Symptom | Cause | Fix |
|---|---|---|
| `No test files found` | Filter or project selects an empty set | Re-read the workspace and vitest project names |
| Tests run, all files 0% | Coverage `include` misses the source, or the run measured built output | Check `coverage.include` and `coverage.provider` in the config |
| Only some files listed | `coverage.all` is off, so untouched files never appear | Enable `all` or name the file explicitly |
| Report empty but exit 0 | Wrong config picked up from a different directory | Run from the package with the filter, confirm the config path in the output |

Bound this at 3 invocation attempts. If a correct-looking invocation still
reports zero after three, stop and report the commands tried, their output, and
what each ruled out. Do not start writing tests to compensate.

### Step 3: Confirm the coverage provider before writing any ignore hint

The house default is the v8 provider, not istanbul.

```bash
grep -rn "provider" vitest.config.* packages/<pkg>/vitest.config.* 2>/dev/null
```

| Provider | Ignore syntax | Notes |
|---|---|---|
| v8 (house default) | `/* v8 ignore next */`, `/* v8 ignore start */` ... `/* v8 ignore stop */` | May need `@preserve` to survive the build |
| istanbul | `/* istanbul ignore next */` | Wrong under v8; silently does nothing |

An istanbul comment under the v8 provider is inert. It will not change the
report, and the number will stay where it was while the reply claims otherwise.

Under v8, a build step can strip comments, so an ignore that works in source
does nothing in the measured output. When that happens the annotation form is:

```ts
/*! @preserve v8 ignore next */
```

Verify a preserved ignore by re-running coverage and reading the table, not by
assuming the comment took effect.

Ignores are a last resort. Step 6 governs when one is allowed at all.

### Step 4: Read the report, do not summarise it

Capture the full run and read the per-file table.

```bash
mkdir -p .coverage-logs
pnpm --filter <pkg> test:ci --project <project> > .coverage-logs/cov.log 2>&1; echo "exit=$?"
cat .coverage-logs/cov.log
```

`.coverage-logs/` is scratch. Never stage it.

From the table, extract for each target file:

- Statement, branch, function and line percentages.
- The uncovered line numbers column, in full.
- Which uncovered entries are branches rather than whole statements.

A headline total is not the report. A repo total of 100% that hides one file at
93.4% is a false reading of the same table.

If a line range is ambiguous, open the file at those lines:

```bash
sed -n '40,72p' packages/<pkg>/src/<file>.ts
```

### Step 5: Check the exclusion list before writing a test for anything

Test helper directories and test file patterns must not appear in the report at
all. If they do, the config exclusions are wrong and that is the fix. Writing
tests for a test helper to raise its coverage is the wrong repair.

Things that belong in `coverage.exclude`, not in the report:

| Pattern | What it is |
|---|---|
| `@internal/test-helpers`, `internal/tests/**` | Shared test helper packages |
| `**/*-test.ts`, `**/*.test.ts` | The test files themselves |
| `**/*.spec.ts` | Spec-suffixed tests |
| `**/dist/**`, `**/*.d.ts` | Build output and type declarations |
| `**/fixtures/**`, `**/__mocks__/**` | Fixtures and mocks |

```bash
grep -rn "exclude" vitest.config.* packages/<pkg>/vitest.config.* 2>/dev/null
```

If `parser-test.ts` or a shared helper shows up as a row, add the pattern to
`coverage.exclude`, re-run, and confirm the row is gone from the table before
touching any source file. Report the config change explicitly, since it changes
the denominator.

This is the one case where changing config is the correct action. It removes
files that were never in scope. It is not the same as excluding a real source
file to raise a number, which Step 6 forbids.

### Step 6: Write real tests, one file at a time

Work in the order the report gives, one file at a time, and finish a file before
starting the next. Interleaving files hides which change moved which number.

For each uncovered line or branch:

1. Read the code at the uncovered lines.
2. Identify the condition that reaches it: an input, an error path, a fallback.
3. Write a test that exercises it through the public API of the module.
4. Re-run coverage for that file and confirm the line left the uncovered column.

Rules for the tests themselves:

| Rule | Detail |
|---|---|
| Public API first | Reach the branch through the exported surface; test an internal only when no exported path reaches it, and say so |
| Readable values | Prefer `'hello'` over `new Uint8Array([104, 101, 108, 108, 111])`; readable inputs make a failure diagnosable |
| One behaviour per test | A test that covers four branches at once tells you nothing when it fails |
| Assert the behaviour | Cover the branch by asserting what it does, not by calling it and asserting nothing |
| No snapshot padding | A snapshot added purely to touch lines is not a test |

Forbidden ways of reaching a number:

| Forbidden | Why |
|---|---|
| Deleting the uncovered branch | Removes behaviour to move a metric |
| Lowering a coverage threshold | Redefines the goal to match the result |
| Adding an ignore comment to a reachable branch | Hides untested behaviour |
| Excluding a real source file from coverage | Same, at file scale |
| Asserting nothing so the line merely executes | Line coverage without behaviour coverage |
| Testing a private internal because it is easier | Couples the test to the implementation |

If a threshold genuinely is wrong, that is a separate change: say so, explain
why, and ask. Do not fold it into a coverage pass.

Bound the work on a single file at 3 attempts. After the third attempt that
fails to move the uncovered lines, stop, paste the file's current row and its
uncovered lines, and report what was tried.

### Step 7: Report genuinely unreachable code, do not force it

Some lines cannot be reached from a test: a defensive branch on an exhaustive
union, a platform guard for a runtime not under test, a rethrow that only fires
on an impossible state.

When a line is genuinely unreachable, report it rather than forcing 100:

```markdown
Unreachable: packages/core/src/adapter-registry.ts:118
The default arm of an exhaustive switch on a string literal union.
No caller can construct the value that reaches it without an unsafe cast.
Options: (a) leave it uncovered and hold the threshold below 100 for this file,
(b) add a v8 ignore with @preserve, (c) delete the arm and rely on the type.
Recommendation: (b), keeping the runtime guard.
```

Requirements for that report: the file, the line, why no test can reach it, and
lettered options with a recommendation. Do not silently ignore it, and do not
claim 100% while it is uncovered.

Only after this is agreed may an ignore comment be added, and it must use the
configured provider's syntax from Step 3.

### Step 8: Re-run and paste the per-file table

The completion gate is the `verify` skill. Defer to it and satisfy its evidence
rule with the coverage-specific form:

```bash
pnpm --filter <pkg> test:ci --project <project> > .coverage-logs/cov-final.log 2>&1; echo "exit=$?"
```

The final reply contains:

- The exact command, including the filter and the project.
- The exit code.
- The per-file coverage table from that run, in a fenced block, with every
  target file visible as a row.

```text
File                    | % Stmts | % Branch | % Funcs | % Lines | Uncovered
------------------------|---------|----------|---------|---------|----------
adapter-registry.ts     |     100 |      100 |     100 |     100 |
utils.ts                |     100 |      100 |     100 |     100 |
```

Never assert a percentage that does not appear in the pasted output. Not a
remembered number, not a projected one, not "should now be at 100". If the
target file is not a visible row in the table, the claim is not supported and
the reply says so instead.

If a threshold is still unmet, the reply says which file, which metric, which
lines, and stops. It does not report the pass.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Reporting a percentage that was not in the output | Paste the per-file table from the run; no table, no claim |
| Treating a zero-coverage report as missing tests | Re-derive the filter and project first; a zero is an invocation bug |
| Lowering a threshold or adding an ignore to reach a number | Write the test that covers the branch, or report it as unreachable and ask |
| Using istanbul ignore syntax under the v8 provider | Check the configured provider; use `v8 ignore`, with `@preserve` if the build strips comments |
| Running without the workspace filter or the vitest project | Use `pnpm --filter <pkg> test:ci --project <project>`; both are required |
| Reading the headline total instead of the per-file rows | One file at 93.4% means the target is not met |
| Writing tests for `@internal/test-helpers` or `*-test.ts` rows | Fix `coverage.exclude` so they never appear in the report |
| Deleting an uncovered branch to raise the number | Cover it; deleting behaviour is not a coverage fix |
| Covering several files at once | One file at a time, in report order, finishing each before the next |
| Using `Uint8Array` literals as test inputs | Prefer readable strings so a failure is diagnosable |
| Testing an internal because the public path is awkward | Reach the branch through the exported API, or state why no exported path reaches it |
| Claiming 100% while an unreachable line is uncovered | Report the file, line and reason, with lettered options and a recommendation |
| Adding a test that calls the code without asserting | Assert the behaviour of the branch, not merely its execution |
| Re-running until the number looks right | Fix the invocation or the test; an unexplained change is not evidence |
