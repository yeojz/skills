---
name: debug
description: Use when a bug, failing test, build failure or unexpected behaviour needs its cause found before anything is changed. Triggers on requests like "this test is failing", "why does this break", "it works locally but not in CI", "the build is red", "flaky test", "fix this error", "something is creating a .git in the source tree", a pasted stack trace, or when a previous fix did not hold.
---

# debug

## Overview

Finds the cause of a failure before changing any code, and proves the fix with
a test that failed first. It reads the whole error, reproduces the failure with
the repo's own commands, narrows the cause by instrumenting and tracing rather
than guessing, changes one thing per hypothesis, and stops after three failed
fixes to report what those failures revealed.

The failure this exists to prevent is a patch applied where the error surfaced
rather than where the bad value came from. That hides the defect until it
returns somewhere else.

## Workflow

### Step 1: Read the whole error before touching anything

Capture the complete output to a file and read all of it: the first error, the
full stack trace, every file path, line number and error code. The bottom of a
stack trace is where the failure surfaced; the cause is usually higher up.

```bash
mkdir -p .debug-logs
pnpm test > .debug-logs/test.log 2>&1; echo "exit=$?"
grep -n -E 'Error|FAIL|at .*:[0-9]+' .debug-logs/test.log | head -60
```

Warnings printed before the error are part of the error. Note them.

`.debug-logs/` is scratch. Never stage it.

### Step 2: Reproduce it with the repo's own command

Read `package.json` for the declared scripts and run the smallest one that
still fails. Never invent a command.

```bash
jq -r '.scripts | to_entries[] | "\(.key)\t\(.value)"' package.json
pnpm --filter <pkg> test:ci -- <path/to/file.test.ts>
pnpm --filter <pkg> test:ci -- -t "<test name>"
```

Run it three times. A failure that appears every time is a bug. One that
appears some of the time is a race or shared state, and it is also a bug.

```bash
for run in 1 2 3; do
  pnpm --filter <pkg> test:ci -- <path/to/file.test.ts> > ".debug-logs/run-$run.log" 2>&1
  echo "run=$run exit=$?"
done
```

If it cannot be reproduced, gather more data instead of guessing: the exact
steps, the environment it failed in, the CI log, the input that was used.
Report what was tried and what is still missing. Do not propose a fix for a
failure that has not been seen.

### Step 3: Check what changed

Most failures follow a change. Find the change before reading the code.

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git status
git log --oneline -15
git diff "origin/$base...HEAD" --stat
git diff "origin/$base...HEAD" -- package.json pnpm-lock.yaml
git diff "origin/$base...HEAD" -- '*.config.*' '.github/workflows/*'
```

| Changed | Where to look |
|---|---|
| A dependency version | The lock file diff, then that dependency's release notes |
| A config file | The diff, then the tool's docs for the changed key |
| Nothing in the repo | Node version, environment variables, OS, the CI runner image |

For "works locally, fails in CI", compare the two environments directly:

```bash
node --version && pnpm --version
env | sort > .debug-logs/env-local.txt
```

then read the setup steps of the CI log for the same values.

### Step 4: Instrument each boundary and run once

When the failure crosses layers (CI workflow to build script to application,
or request handler to service to database), do not reason about which layer is
wrong. Log what enters and leaves each layer, run once, and read the result.

```bash
# Layer 1: the workflow
echo "BASE_URL: ${BASE_URL:+set}${BASE_URL:-unset}"

# Layer 2: the build script
env | grep '^BASE_URL=' || echo "BASE_URL not in build environment"

# Layer 3: the application
node -e 'console.error("config:", process.env.BASE_URL)'
```

The first layer where the value is missing or wrong is the layer to
investigate. Log before the dangerous operation, not after it fails; a log
line placed after the failure never runs.

Instrumentation is removed before the fix is committed.

### Step 5: Trace the bad value back to where it originates

An error deep in the call stack means a wrong value arrived from somewhere
above. Walk the chain upward until the value is first wrong.

1. Name the immediate cause: the line that threw, or the operation that
   misbehaved.
2. Ask what called it and with which arguments.
3. Repeat until the arguments are first wrong. That is the origin, and the
   only place a fix belongs.

When the chain cannot be read from the stack trace, capture it at the
dangerous operation:

```typescript
console.error("before git init", {
  directory,
  cwd: process.cwd(),
  stack: new Error().stack,
});
```

Use `console.error` inside tests; a logger may be silenced there.

```bash
pnpm --filter <pkg> test:ci > .debug-logs/trace.log 2>&1; echo "exit=$?"
grep -n -A 20 'before git init' .debug-logs/trace.log
```

A file or directory appearing during the suite with no owning test is shared
state leaking between tests. `find-polluter.sh` sits beside this file. It runs
the test files one at a time with the repo's own script and stops at the first
one that leaves the path behind:

```bash
bash <skill-dir>/find-polluter.sh .git src '*.test.ts' 'pnpm test:ci --'
```

### Step 6: Compare against a working example

Find code in the same repo that does the same thing and works. Read all of it,
then list every difference from the broken code, however small. Do not skip a
difference on the grounds that it cannot matter; the one that matters usually
looks like that.

```bash
grep -rn '<function or pattern>' src/ packages/ --include='*.ts' | head -40
```

List what the working example depends on: config, environment, setup code,
ordering. The broken code is missing one of them or has one wrong.

### Step 7: State one hypothesis and change one thing

Write the hypothesis in the reply in this form: "X is the cause because Y; if
so, changing Z alone will make the reproduction pass."

Make only Z. Re-run the Step 2 command and paste the result.

- It passes: go to Step 8.
- It does not pass: revert Z, count the attempt, form a new hypothesis. Never
  leave a failed change in place while trying the next one.

If no hypothesis can be stated, say which part is not understood and return to
Step 4 or Step 5 with more instrumentation. Do not change code to see what
happens.

### Step 8: Write the failing test before the fix

Write the smallest test that reproduces the bug, run it, and paste the failing
output. Use the `tdd` skill for the shape of the test. A one-off script is
acceptable only when the repo has no test runner.

```bash
pnpm --filter <pkg> test:ci -- <path/to/new.test.ts> > .debug-logs/red.log 2>&1; echo "exit=$?"
tail -30 .debug-logs/red.log
```

The exit code must be non-zero here. A new test that passes before the fix
does not reproduce the bug.

### Step 9: Fix the root cause only

Change the origin found in Step 5, not the place the error surfaced. One
change, with no refactoring bundled in and no improvements made in passing.
Remove the Step 4 and Step 5 instrumentation.

Two fix shapes come up often enough to name.

A guessed delay in a test. Replace `sleep` and fixed `setTimeout` waits with a
poll on the condition the test cares about:

| Rule | Why |
|---|---|
| Poll the condition; do not sleep for a guessed duration | Passes on a slow CI runner as well as on a fast laptop |
| Always set a timeout and fail with a message naming the condition | A loop with no timeout hangs the suite instead of failing it |
| Re-read the value inside the loop | A value captured before the loop never changes |
| Poll every 10ms or so, not every 1ms | Tighter polling burns CPU and slows the rest of the run |
| Keep a fixed delay only for timed behaviour, with a comment saying why | Debounce and throttle tests need real time to pass |

A bad value that reached a dangerous operation. After fixing the origin,
reject the value at each layer it passed through, so the same bug cannot
return by a different path:

| Layer | What it rejects |
|---|---|
| Entry point | Input that is empty, missing or the wrong shape |
| Business logic | Input that is well formed but wrong for this operation |
| Environment guard | The operation itself where it is dangerous, such as `git init` outside a temp dir under test |
| Instrumentation | Nothing; it records the call site so the next investigation starts with evidence |

Add these guards as a separate change so the root-cause fix stays reviewable
on its own.

### Step 10: Verify with the repo's own gate

Call the `verify` skill. It re-runs the new test, then the full typecheck,
lint, test and build sequence, and pastes the output. The bug is fixed when the
new test passes, the full suite passes, and the Step 2 reproduction no longer
fails. None of those is reported without the pasted output.

Never weaken an assertion, skip a test, or add a fallback or a swallowing
`try/catch` to reach green. Those hide the defect; they do not fix it.

### Step 11: Stop at three failed fixes and report

Count attempts out loud: attempt 1 of 3, attempt 2 of 3, attempt 3 of 3. An
attempt is one hypothesis, one change, one re-run.

After the third failure, stop editing. Three failures where each fix uncovered
new shared state or coupling somewhere else are not three wrong guesses; they
are the signal that the structure is wrong, and a fourth patch will move the
failure again rather than remove it.

Report:

- The reproduction command and its output.
- Each hypothesis, the change made, and what ruled it out.
- What each attempt revealed about coupling between components.

Then present the choice as lettered options:

- A: Refactor the coupling the attempts exposed, as its own change.
- B: Revert to the last known good commit and start again from Step 1.
- C: Treat the failure as environmental and add a documented retry or
  timeout.

Recommend A when each fix exposed new coupling, B when the last known good
commit is recent and small, and C only when Steps 1 to 6 found nothing in the
repo. Wait for the choice.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Reading only the last line of the error | Capture the whole output to a file and read the full trace |
| Proposing a fix before the failure has been reproduced | Run the repo's own command until it fails; if it will not, gather data |
| Running the reproduction once and calling it deterministic | Run it three times; an intermittent failure is a race or shared state |
| Skipping `git diff` because the code looks unrelated | Most failures follow a change; check the lock file and config too |
| Reasoning about which layer is wrong instead of instrumenting | Log at each boundary, run once, read where the value first goes wrong |
| Logging after the operation that fails | Log before it; the line after never runs |
| Fixing where the error surfaced | Trace the value upward to its origin and fix there |
| Adding a delay to make a flaky test pass | Poll the condition with a timeout and re-read inside the loop |
| Changing several things at once | One hypothesis, one change, one re-run |
| Leaving a failed change in place while trying the next | Revert it first, then form the next hypothesis |
| Writing the test after the fix | Write it first and paste its failing output before editing the code |
| Bundling a refactor into the fix | Fix the root cause only; propose the refactor as a separate change |
| Weakening an assertion or skipping a test to reach green | Root-cause it; a silenced test is not a fix |
| Adding a fallback or swallowing `try/catch` | The failure moves to runtime; fix the cause instead |
| A fourth fix attempt after three failures | Stop, report what each attempt revealed, and offer lettered options |
| Claiming fixed without pasted output | Call `verify` and let its report block carry the claim |
