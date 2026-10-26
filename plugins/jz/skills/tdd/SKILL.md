---
name: tdd
description: Use when a change should be driven by a test: a new behaviour with no test yet, a bug that needs a regression test, or a request to write the test first. Triggers on requests like "write the test first", "TDD", "red green refactor", "add a test for", "add a regression test", "make the test pass", "cover this before changing it", "test-drive this", or when a bug report needs reproducing in a test before it is fixed.
---

# tdd

## Overview

Drives a feature or bugfix through red, green, refactor cycles with the repo's
own test script. Each cycle writes one test that names a behaviour, proves it
fails for the right reason with the runner's pasted output, writes the least
code that passes, proves the whole suite is green with pristine output, and
refactors only while green.

The failure this exists to prevent is a test that never failed. Such a test
proves nothing about the code it claims to cover, and a suite full of them is
green for the wrong reason.

## Workflow

### Step 1: Discover the test command

Never invent a test command. Read what the repo declares and run that.

Detect the package manager from the lock file, never from habit:

| Lock file | Command prefix |
|---|---|
| `pnpm-lock.yaml` | `pnpm` |
| `package-lock.json` | `npm run` |
| `yarn.lock` | `yarn` |
| `bun.lockb` or `bun.lock` | `bun run` |

Then read the scripts, as the `verify` skill does:

```bash
cat package.json | jq -r '.scripts | to_entries[] | "\(.key)\t\(.value)"'
cat packages/<pkg>/package.json | jq -r '.scripts'
```

When there is no `package.json`, read the `Makefile` instead and run the target
as `make <target>`:

```bash
grep -E '^[A-Za-z0-9_-]+:' Makefile | cut -d: -f1
```

Look for `test`, `test:ci` or `test:unit`. In a workspace, run the package's
script through a filter, and narrow to one file by passing its path after the
script:

```bash
pnpm --filter <pkg> test -- src/retry.test.ts
```

Do not substitute `npx vitest`, `npx jest` or a bare binary when the repo does
not declare a script. An invented command that passes proves nothing about the
gate the repo actually runs.

If neither file declares a test command, stop and present the choice:

- (a) Add a `test` script that runs the test runner already present in
  `devDependencies`, so the gate exists for everyone.
- (b) Stop and report that no test command is declared, and ask which one the
  repo is meant to use.

Recommendation: (a) when a runner is already installed, since the missing
script is the defect; otherwise (b), because picking a runner is a design
decision the repo owner makes.

### Step 2: Write one test that names the next behaviour

Write one minimal test showing what should happen. The name reads as a
statement of behaviour, the body exercises real code, and the assertion is on
the result.

| Rule | Detail |
|---|---|
| One behaviour | An "and" in the test name means two tests; split it |
| Clear name | The name says what the code does for which input, not `works` or `test1` |
| Real code | Mocks only for a slow or external dependency; Step 7 gates every one |
| Readable values | Prefer `'hello'` over a byte array, and `example.com` for any domain |
| Shows the API | The test calls the code the way a consumer will, so it documents the interface |

A test that names a behaviour and asserts on the result:

```ts
import { expect, test } from 'vitest';
import { retry } from './retry';

test('retries until the third attempt succeeds', async () => {
  let attempts = 0;
  const operation = async () => {
    attempts += 1;
    if (attempts < 3) {
      throw new Error('temporary outage');
    }
    return 'ok';
  };

  const result = await retry(operation);

  expect(result).toBe('ok');
  expect(attempts).toBe(3);
});
```

The same intent written so that it tests the mock instead of the code:

```ts
test('retry works', async () => {
  const operation = vi.fn()
    .mockRejectedValueOnce(new Error('temporary outage'))
    .mockRejectedValueOnce(new Error('temporary outage'))
    .mockResolvedValueOnce('ok');

  await retry(operation);

  expect(operation).toHaveBeenCalledTimes(3);
});
```

The name says nothing, and the only assertion is about the mock. Any `retry`
that calls three times and returns the wrong value, or nothing, passes it.

For a bugfix, the first test reproduces the bug: it asserts the correct
behaviour and fails on the current code. If the cause of the bug is not yet
known, use the `debug` skill to find it first, then return here with the
reproducing test.

If the test is hard to write, the difficulty is information about the design:

| Symptom | Cause | Response |
|---|---|---|
| Do not know how to test it | The API is not yet decided | Write the call the consumer wishes existed, then the assertion, then work backwards |
| The test is complicated | The interface is complicated | Simplify the interface before the implementation |
| Everything must be mocked | The code is coupled to its dependencies | Inject the dependency through a parameter |
| The setup is huge | The design has a problem, not the test | Extract a helper; if it is still huge, simplify the design |

### Step 3: Run it and confirm it fails for the right reason

Run only the new test file, capture the output and the exit code, and paste
both.

```bash
mkdir -p .tdd-logs
pnpm test -- src/retry.test.ts > .tdd-logs/red.log 2>&1; echo "exit=$?"
tail -40 .tdd-logs/red.log
```

`.tdd-logs/` is scratch. Never stage it.

Read the output against this table before writing any implementation:

| Outcome | Meaning | Action |
|---|---|---|
| Fails on the assertion with the expected message | The right reason | Go to Step 4 |
| Passes | The behaviour already exists, or the test asserts nothing | Read the code under test; if the behaviour exists, say so and stop, since there is nothing to implement; if the assertion is weak, strengthen it and re-run |
| Errors before reaching the assertion: missing export, type error, syntax error | The wrong reason | Fix the error and re-run until the failure is on the assertion; for a missing export, add the smallest stub that lets the test reach its assertion |
| Fails on a different assertion than expected | The test or the setup is wrong | Fix the test until it fails where the missing behaviour lives |

The exit code must be non-zero and the pasted tail must show the assertion
that failed. An assertion never seen failing is an assertion whose value is
unknown.

### Step 4: Write the least code that passes

Write the simplest implementation that turns the pasted failure into a pass.
Nothing the test did not ask for: no options object, no optional parameter, no
fallback, no configuration, no refactoring of neighbouring code.

The implementation the Step 2 test asks for:

```ts
export async function retry<T>(operation: () => Promise<T>): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}
```

The same function with `maxAttempts`, a backoff strategy and an `onRetry`
callback is over-engineered: no test asked for any of them, so none of them is
proven to work, and each one is a parameter that no caller needs.

### Step 5: Run the whole suite and confirm it is green with pristine output

Run the full declared script, not only the new file. Capture and paste.

```bash
pnpm test > .tdd-logs/green.log 2>&1; echo "exit=$?"
tail -40 .tdd-logs/green.log
```

All of the following must hold:

- The new test passes.
- Every other test still passes; paste the pass and fail counts line.
- The exit code is 0.
- The output is pristine: no warnings, no stray `console.log`, no unhandled
  rejection, no deprecation notice introduced by the change.

If the new test still fails, fix the code, not the test. None of the following
is a fix:

| Forbidden | Why |
|---|---|
| Changing the expected value to whatever the code produced | Rewrites the specification to match the defect |
| Weakening or deleting the assertion | Hides the behaviour the test was written to prove |
| `.skip`, `.todo`, `it.only`, commenting the test out | Removes the signal |
| Wrapping the call in a `try`/`catch` that swallows | Moves the failure to runtime |
| Loosening a type or casting to `any` | Hides the defect from the compiler |

Change a test only when it is provably wrong, for example when its expected
value contradicts the specification the user gave, and say why in the reply.

If a different test fails, the change broke existing behaviour. Fix it now, in
this cycle, not later. If the cause is not obvious from the failing output, use
the `debug` skill before editing.

If noise appears in the output, remove its source before continuing. Noise
that was there before the change is reported as pre-existing, not silenced
with a filter or a reporter flag.

Bound the fix loop at 3 attempts, counted out loud. After the third failed
attempt, stop editing and report the failing command, its exit code, the tail
of its output, and each hypothesis tried, as the `verify` skill does.

### Step 6: Refactor only while green

With the suite green, improve the code without changing what it does: remove
duplication, improve names, extract a helper that two places now need. After
each refactor re-run the full script and paste the exit code.

```bash
pnpm test > .tdd-logs/refactor.log 2>&1; echo "exit=$?"
tail -20 .tdd-logs/refactor.log
```

Refactoring adds no behaviour. A new behaviour discovered while refactoring is
the next cycle's test, not an edit made here. If the suite goes red during a
refactor, revert that refactor rather than editing a test to accommodate it.

If nothing needs cleaning up, say so and move on. An empty refactor step is
normal.

### Step 7: Check every mock before the cycle repeats

Before keeping any mock, answer the gate question in the reply: am I testing
real component behaviour, or just mock existence? If the answer is mock
existence, delete the assertion or remove the mock.

| Anti-pattern | How it shows | Fix |
|---|---|---|
| Asserting on the mock | `toHaveBeenCalled` is the only assertion, or a test id ending in `-mock` | Assert on the output or the real component; drop the mock if it adds nothing |
| Test-only method in production | A method called from test files and nowhere else | Move it to a test helper; production code carries no test lifecycle |
| Mocking without understanding | The test depends on a side effect the mock removed, so it passes or fails for the wrong reason | Run once against the real dependency, then mock the slow or external operation underneath it, not the method the test needs |
| Incomplete mock | The mock carries only the fields this test touches | Mirror the real response's full shape, read from its docs or a captured example |
| Mock setup longer than the test logic | Warning sign of coupling or a design problem | See the options below |

When mock setup outgrows the test, present the choice rather than adding more
setup:

- (a) Inject the dependency through a parameter so the test passes a small fake.
- (b) Run the test against the real component as an integration test.
- (c) Keep the mock but move it to the lowest slow or external operation.

Recommendation: (a) when the code under test owns the call, since it removes
the coupling for every future test; (b) when the real component is fast and
deterministic; (c) only when neither is possible in this change.

Then take the next behaviour back to Step 2. Coverage numbers are the business
of the `coverage` skill; this skill never adds a test only to touch a line.

### Step 8: Call verify

When the last cycle is green, the completion gate is the `verify` skill. Call
it, run the repo's typecheck, lint, test and build scripts through it, and
paste its report block. The words done, fixed and passing wait for that block.

The reply for the whole task shows, per cycle, the red run's pasted tail and
exit code, then the green run's pasted tail and exit code. A cycle with only
one of the two was not a cycle.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing the implementation, then a test that passes on the first run | Write the test first and paste it failing before any implementation code |
| Treating an immediately passing test as a good sign | It proves the behaviour already exists or the assertion is empty; read the code and decide which |
| Treating an import error or type error as the red step | Add the smallest stub and re-run until the failure is on the assertion |
| Inventing `npx vitest run` when the repo declares `test` | Read `package.json` or the Makefile and run the declared script |
| Running only the new file for the green step | Run the full script; another test may have broken |
| Changing the expected value to match the output | Fix the code; change a test only when it is provably wrong, and say why |
| Marking a failing test `.skip` to reach green | Fix the cause or stop at 3 attempts and report the blocker |
| Adding options or parameters the test did not ask for | Write the least code that passes; the next behaviour gets its own test |
| A test name joined with "and" | Two behaviours, two tests |
| `toHaveBeenCalledTimes` as the only assertion | Assert on the result; the mock's call count is the mock's behaviour, not the code's |
| A mock with only the fields the test happens to touch | Mirror the real response's full shape |
| Adding behaviour during the refactor step | Refactor only while green and add nothing; a new behaviour starts a new cycle |
| Calling a green run pristine while a warning scrolls past | Remove the noise the change introduced, or report it as pre-existing |
| Saying the feature is done without the red and green tails pasted | Paste both per cycle, then call `verify` for the report block |
