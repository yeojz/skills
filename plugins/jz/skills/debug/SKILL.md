---
name: debug
description: Use when a bug, failing test, build failure or unexpected behaviour needs its cause found before anything is changed. Triggers on requests like "this test is failing", "why does this break", "it works locally but not in CI", "the build is red", "flaky test", "fix this error", "something is creating a .git in the source tree", a pasted stack trace, or when a previous fix did not hold.
---

# debug

## Overview

Finds the cause of a failure before changing code, and proves the fix with a
test that failed first. It reads the whole error, reproduces it with the
repo's own command, narrows the cause by instrumenting and tracing rather
than guessing, changes one thing per hypothesis, and stops after three
failed fixes. A patch where the error surfaced, rather than where the bad
value came from, only moves the bug.

## Workflow

### Step 1: Read the whole error

```bash
mkdir -p .debug-logs
pnpm test > .debug-logs/test.log 2>&1; echo "exit=$?"
grep -n -E 'Error|FAIL|at .*:[0-9]+' .debug-logs/test.log | head -60
```

Read all of it: the first error, the full trace, every path, line and code,
and the warnings before it. The bottom of a trace is where it surfaced; the
cause is usually higher. Never stage `.debug-logs/`.

### Step 2: Reproduce it, three times

Run the smallest declared script that still fails (read `package.json`;
never invent a command), three times:

```bash
for run in 1 2 3; do
  pnpm --filter <pkg> test -- <path/to/file.test.ts> > ".debug-logs/run-$run.log" 2>&1; echo "run=$run exit=$?"
done
```

Every time is a bug; some of the time is a race or shared state, also a bug.
If it won't reproduce, gather the steps, environment, CI log and input, and
report what's missing. Never propose a fix for a failure not yet seen.

### Step 3: Check what changed

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git log --oneline -15
git diff "origin/$base...HEAD" --stat
git diff "origin/$base...HEAD" -- package.json pnpm-lock.yaml '*.config.*' '.github/workflows/*'
```

A dependency bump means the lock diff, then its release notes; a config
change means that key's docs; nothing in the repo means the Node version,
environment, OS or runner image. For "works locally, fails in CI", compare
`node --version`, `pnpm --version` and the environment with the CI log's
setup steps.

### Step 4: Instrument each boundary, run once

When the failure crosses layers (workflow, build script, application; or
handler, service, database), log what enters and leaves each layer and run
once, instead of reasoning about which is wrong. Print only whether a
secret is set, never its value, and never with `${VAR:-...}`, which expands
to the value when it is set:

```bash
if [ -n "${TOKEN:-}" ]; then echo "TOKEN: set"; else echo "TOKEN: unset or empty"; fi
``` The first layer where the
value is missing or wrong is where to look. Log before the dangerous
operation, not after it fails. Remove the instrumentation before the fix is
committed.

### Step 5: Trace the bad value to its origin

Name the line that misbehaved, then what called it with which arguments, and
repeat until the arguments are first wrong. That origin is the only place a
fix belongs. When the trace doesn't show the chain, capture it at the
dangerous operation:

```typescript
console.error("before git init", { directory, cwd: process.cwd(), stack: new Error().stack });
```

Use `console.error` in tests; a logger may be silenced. A file appearing
during the suite with no owning test is shared state leaking:
`find-polluter.sh`, beside this file, runs the test files one at a time and
stops at the first that leaves it behind.

```bash
bash <skill-dir>/find-polluter.sh .git src '*.test.ts' 'pnpm test:ci --'
```

### Step 6: Compare with a working example

Find code in the repo that does the same thing and works, read all of it,
and list every difference, however small, plus what it depends on (config,
environment, setup, ordering). The broken one lacks one of them.

### Step 7: One hypothesis, one change

Write it as: "X is the cause because Y; if so, changing Z alone makes the
reproduction pass." Change only Z and re-run Step 2's command. If it fails,
revert Z before the next hypothesis. With no hypothesis, go back to Step 4
or 5; never change code to see what happens.

### Step 8: A failing test first

Write the smallest test that reproduces the bug, as the `implement` skill
describes for a test check, and paste it failing (non-zero exit) before
touching the code. A test that already passes doesn't reproduce the bug. A
one-off script is only for a repo with no test runner.

### Step 9: Fix the origin only

Change the origin from Step 5, nothing else: no refactor, no improvements in
passing, instrumentation removed.

| A guessed delay in a test | Do instead |
|---|---|
| `sleep` or a fixed `setTimeout` | Poll the condition about every 10ms |
| A loop with no limit | A timeout that fails naming the condition |
| A value read once before the loop | Re-read it inside the loop |
| Timed behaviour (debounce, throttle) | Keep the real delay, with a comment why |

When a bad value reached something dangerous, after fixing the origin add a
guard at each layer it passed through (entry point, business logic, an
environment guard around the dangerous call), as a separate change so the
fix stays reviewable on its own.

### Step 10: Verify

Run the `verify` skill: the new test passes, the full suite passes, and the
Step 2 reproduction no longer fails, each with output pasted. Never weaken
an assertion, skip a test, or add a fallback or swallowing `try`/`catch`.

### Step 11: Stop after three failed fixes

Count attempts out loud. After the third, stop editing: three fixes that
each exposed new coupling mean the structure is wrong. Report the
reproduction, each hypothesis and what ruled it out, and what each attempt
revealed, then offer:

- A: refactor the coupling, as its own change (when each fix exposed more)
- B: revert to the last good commit and restart (when it's recent and small)
- C: treat it as environmental with a documented retry or timeout (only when
  Steps 1 to 6 found nothing in the repo)

Recommend one and wait.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Reading only the last line | Capture the whole output and read the trace |
| A fix before a reproduction | Reproduce with the repo's command, or gather data |
| One run called deterministic | Three runs |
| Guessing which layer is wrong | Instrument each boundary and run once |
| Fixing where it surfaced | Trace to the origin |
| A sleep to calm a flaky test | Poll with a timeout |
| Several changes at once | One hypothesis, one change |
| The test after the fix | Paste it failing first |
| A fourth attempt | Stop and offer options |
