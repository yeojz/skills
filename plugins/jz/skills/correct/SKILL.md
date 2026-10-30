---
name: correct
description: Use when the same correction has come back a second time in a project and needs a check that makes it stop, rather than another steer. Triggers on requests like "agents keep doing X", "/correct", "this is the second time", "I keep having to tell you", "stop doing X every time", "why does this keep happening", "make it impossible to", "add a check so this cannot recur", "what keeps getting reverted", or when a review thread, a revert or a steer repeats one already seen in this project.
---

# correct

## Overview

Turns a correction that recurs in a project into a check the project runs on
its own. It reads the project's recent corrections, reverts and review
threads, groups them into classes, fixes the most frequent class at the
highest level that holds, architecture first and docs last, in its own
commit, proves the new check fails on the past mistake and passes on the
fix, and adds or updates the row in the project's enforcement table.

The failure this exists to prevent is the steer typed for the third time. A
rule can be ignored while a check cannot, so the correction is spent once on
the check and never again on the symptom.

`correct` changes the project: its lint, CI, tests, hooks, scripts and
`AGENTS.md`. A correction about how a skill or a rule in the plugin behaves
is the `reflect` skill's job and is listed for it, not fixed here.

## Workflow

### Step 1: Gather the corrections

Read every source before grouping anything. A class counted from one source
is a guess.

```bash
base="$(git ls-remote --symref origin HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2 }')"
git fetch origin "$base"
git log --oneline --since='60 days ago' "origin/$base" | grep -iE 'revert|^[0-9a-f]+ fix' | head -40
git log --format='%h %s' --since='60 days ago' "origin/$base" -- .github/ package.json biome.json .eslintrc* | head -20
gh pr list --state merged --limit 15 --json number,title --jq '.[] | "\(.number)\t\(.title)"'
```

For each of the recent pull requests, read the review threads, since that is
where the owner typed the correction:

```bash
gh api graphql -f query='
query($owner:String!, $repo:String!, $pr:Int!) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$pr) {
      reviewThreads(first:100) {
        nodes { path line comments(first:10) { nodes { author { login } body } } }
      }
    }
  }
}' -F owner=<owner> -F repo=<repo> -F pr=<n> --jq '.data.repository.pullRequest.reviewThreads.nodes[] | "\(.path):\(.line)\t\(.comments.nodes[0].body)"'
```

Then the session's own steers: every message in this conversation where the
user negated, repeated or restated something ("no", "again", "I said",
"stop", "as before"), and every hook denial the transcript shows. When the
conversation has been compacted, read the transcript file; the `reflect`
skill's Step 1 names where each host keeps it.

Last, the project's enforcement table, if it has one:

```bash
grep -n -A 30 '^## Enforcement' AGENTS.md CLAUDE.md 2>/dev/null
```

A row whose "Enforced by" says `nothing` and whose rule appears in the
corrections is a target before anything else is.

### Step 2: Group into classes and count

Write the ledger before choosing anything. One row per class, not per
occurrence; two occurrences of the same class make it a target, one is a
steer and stays in the ledger for next time.

```markdown
| Class | Seen | Sources | Enforced by today |
|---|---|---|---|
| Wall-clock timing bound in a test | 3 | PR 23 thread, PR 27 revert, steer in this session | nothing |
| `.claude/` tripping `format:check` | 2 | two `--no-verify` commits in the log | nothing |
| Merging the default branch in | 1 | PR 19 thread | `rebase-not-merge.sh` |
```

Pick the class with the highest count. Break a tie by cost: the class that
reached a remote or the default branch outranks one caught in the working
tree. A class the plugin already enforces, as the third row above, is
reported as covered and the next class is taken; a class that is a plugin
skill or rule misbehaving goes on the list for `reflect` in Step 7.

Fix one class per run. A second class is a second run and a second commit.

### Step 3: Pick the highest level that holds

Walk the ladder from the top and stop at the first level that holds. A level
holds when the check runs without anyone remembering to run it, and the
usual path cannot step around it.

| Level | The mistake becomes | Holds when | Example for the timing-bound class |
|---|---|---|---|
| Architecture | unrepresentable: the API, file or value that made it possible is gone | the code still compiles without the thing being removed | inject a clock into the module under test, so a test never waits on real time |
| Types | a compile error | the compiler runs in CI and the type cannot be cast around in the usual path | a branded `Duration` that a literal number cannot satisfy |
| Lint or CI | a red check | the linter or the workflow runs on every push | a lint rule or CI grep that fails on `setTimeout` or `Date.now` under `test/` |
| Tests | a failing test | the suite runs in CI and the test cannot pass by accident | a regression test that pins the behaviour the revert restored |
| Docs | a line in `AGENTS.md` | nothing else holds | a line saying tests must not wait on real time |

Docs is the floor, not a choice. A docs-level fix is reported as "nothing
enforces this yet" in the enforcement row, so the class stays a target.

When two levels both hold, present them as lettered options with the
recommendation first and the trade-off that decides, and wait; the
parallelism rule applies here as anywhere. When one level holds, say which
and why the ones above it do not, and proceed.

### Step 4: Branch, then write the fix in its own commit

Work in the task's worktree as the `ship` skill's Step 1 describes, never on
the default branch. The fix is one commit that does nothing else: no
unrelated tidying, no second class, no symptom fix for the occurrence that
triggered the run. If the triggering occurrence still needs its own fix,
that is a separate commit after this one.

The commit type follows the level: `refactor` for architecture and types,
`ci` or `chore` for lint, CI and hooks, `test` for a regression test,
`docs` for the floor. The scope names the class.

### Step 5: Prove the check fails on the past mistake

A check that has never been red proves nothing. Reconstruct the mistake from
its real occurrence, run the check, and paste the non-zero exit; then run it
on the fixed tree and paste the zero.

The fix from Step 4 is still uncommitted, so the red run never happens in
the task worktree: reconstructing the mistake there overwrites the fixed
file, and `git checkout -- <path>` afterwards restores the index version
and discards the fix while `git status --short` reads clean. Build a
throwaway worktree detached at `HEAD`, carry the uncommitted fix into it by
name, and reconstruct the mistake there:

```bash
git status --short
git hash-object <fixed-path>
red_dir="$(mktemp -d)"
git worktree add --detach "$red_dir" HEAD
for f in <every path git status --short listed>; do
  if [ -e "$f" ]; then mkdir -p "$red_dir/$(dirname "$f")" && cp -p "$f" "$red_dir/$f"; else rm -f "${red_dir:?}/${f:?}"; fi
done
```

When the check needs dependencies, install them inside `$red_dir` from the
lock file, with `pnpm install --frozen-lockfile` or the equivalent the lock
file names. Then reconstruct the mistake inside `$red_dir`, never outside
it:

| Fix is | Reconstruct the mistake, inside `$red_dir`, by |
|---|---|
| A lint rule or CI grep | `git -C "$red_dir" show <offending-sha>:<path> > "$red_dir/<path>"` |
| A test | `git -C "$red_dir" revert --no-commit <revert-sha>` |
| A hook | feeding it the payload the transcript shows, as `test-hooks.sh` in the plugin does |
| A type or an architecture change | `git -C "$red_dir" apply <offending-hunk.patch>` and reading the compiler's refusal |
| A formatter or ignore change | recreating the file that tripped the gate under `$red_dir`, running the gate there |

```bash
( cd "$red_dir" && pnpm lint ); echo "exit=$?"
git worktree remove --force "$red_dir"
git worktree prune
pnpm lint; echo "exit=$?"
git status --short
git hash-object <fixed-path>
```

Use `$?` on the line after the command, never through a pipe. Both exit
codes go in the report, with the `git status --short` and the hash of the
fixed file before and after, which must match: the task worktree was never
touched, and the matching hash is the proof. If the check cannot be made
red on the past mistake, the level does not hold: drop one level and
repeat. Bound this at three levels; past that, report the class as unfixed
with what was tried.

### Step 6: Add or update the enforcement row

The project's `AGENTS.md`, or `CLAUDE.md` when that is the instruction file
it has, carries a `## Enforcement` table in the same shape as the plugin's
`AUTHORING.md`: rule, then what enforces it. Create the table when the
project has none; update the row when the class already has one.

```markdown
## Enforcement

| Rule | Enforced by |
|---|---|
| Tests never wait on real time | `no-wall-clock.test.ts`, in `pnpm test:ci` |
| `.claude/` is never formatted or linted | `biome.json` ignore, in `pnpm format:check` |
```

The "Enforced by" cell names the file and the script or workflow that runs
it, so the next reader can run it. A docs-level fix writes `nothing` there
and the line it added.

The row lands in the same commit as the fix, since the row is the record of
the fix.

### Step 7: Verify, commit and report

Run the `verify` skill over the fixed tree and paste its report block. Then
commit and hand the push and the PR to `ship`, in whatever mode the user
asked for.

The report carries:

```markdown
## correct: <class>

Level: lint or CI, because architecture would mean <reason> and types do not hold since <reason>.
Red on the past mistake: `pnpm lint` on <sha>:<path>, exit 1, <result line>
Green on the fix: `pnpm lint` on the working tree, exit 0, <result line>
Enforcement row: added, `AGENTS.md`
Commit: <sha> <subject>

Remaining classes, by count: <class> (<n>), <class> (<n>)
For reflect: <class>, since it is the <skill or rule> misbehaving, not the project
```

The remaining classes are the next run's Step 2. Nothing in the report is
written from memory: every sha, exit code and result line comes from output
in this session.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Fixing the occurrence that triggered the run and calling the class fixed | The occurrence is a symptom. The class is fixed when a check fails on it |
| Counting from the session alone | Read the review threads, the reverts and the enforcement table too; the owner typed most corrections in a thread |
| Choosing docs because it is quickest | Docs is the floor. Walk the ladder from architecture and stop at the first level that holds |
| A check that was never red | Reconstruct the past mistake, run the check, paste the non-zero exit, then the zero on the fix |
| Two classes in one commit | One class, one commit. The second class is the next run |
| Fixing a plugin skill or rule here | That is `reflect`. List it under "For reflect" and leave it |
| Reconstructing the mistake in the task worktree | The fix is uncommitted there; `git checkout --` restores the index version and discards it. Red runs happen in a throwaway worktree with the fixed paths copied in, and the fixed file's hash matches before and after |
| An enforcement row that names no runnable thing | Name the file and the script or workflow that runs it |
| Weakening the check so the current tree passes | Root-cause the current red; the verification rule forbids the shortcut |
| Writing the fix on the default branch | Branch first, as `ship` Step 1 describes |
