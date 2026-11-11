#!/usr/bin/env bash
# Regression suite for the factory's gate and job scripts. Builds throwaway
# repositories with a local bare repository as origin and a stub gh on PATH
# that records its arguments, so nothing here needs a network. The stub's
# `pr merge` merges the named commit into the bare repository, which lets a
# later job be cut from an integration branch that really moved.
set -uo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JOB="$SCRIPTS/job"
GATE="$SCRIPTS/gate"
T="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$T"' EXIT
pass=0
fail=0
OUT=""

# The suite's commits must not depend on the machine's git identity or config.
export GIT_CONFIG_GLOBAL="$T/gitconfig" GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=dev GIT_AUTHOR_EMAIL=dev@example.com
export GIT_COMMITTER_NAME=dev GIT_COMMITTER_EMAIL=dev@example.com
: > "$T/gitconfig"

mkdir -p "$T/bin"
cat > "$T/bin/gh" <<'STUB'
#!/usr/bin/env bash
# Records every call. `pr view` answers from a file the suite writes, and
# `pr merge` merges the commit it was pinned to into the base branch on origin.
T="$(cd "$(dirname "$0")/.." && pwd)"
printf '%s\n' "$*" >> "$T/gh.log"
case "$1 $2" in
  "pr view") cat "$T/gh-view.json" ;;
  "pr merge")
    [ -f "$T/gh-merge-fails" ] && { echo "merge refused by the stub" >&2; exit 1; }
    sha="${!#}"
    scratch="$T/merger.$$"
    git clone -q "$(cat "$T/gh-origin")" "$scratch" 2>/dev/null
    git -C "$scratch" checkout -q "$(cat "$T/gh-base")"
    git -C "$scratch" merge -q --no-ff -m "merge pull request $3" "$sha" || exit 1
    git -C "$scratch" push -q origin HEAD
    rm -rf "$scratch" ;;
  "pr create") echo "https://example.com/pull/57" ;;
esac
STUB
cat > "$T/bin/pnpm" <<'STUB'
#!/bin/sh
# Stands in for the package manager: the script named test fails with 3.
[ "$2" = test ] && exit 3
exit 0
STUB
chmod +x "$T/bin/gh" "$T/bin/pnpm"
export PATH="$T/bin:$PATH"

t() {
  # t <label> <expected exit> <command...>; the output is left in $OUT
  local label="$1" want="$2" got
  shift 2
  OUT="$("$@" 2>&1)"
  got=$?
  printf '  %-68s' "$label"
  if [ "$got" = "$want" ]; then
    echo "PASS"; pass=$((pass + 1))
  else
    echo "FAIL, exit $got, expected $want: $(printf '%s' "$OUT" | tail -1)"; fail=$((fail + 1))
  fi
}

has() {
  # has <label> <fixed text expected in $OUT>
  printf '  %-68s' "$1"
  if printf '%s\n' "$OUT" | grep -qF -- "$2"; then
    echo "PASS"; pass=$((pass + 1))
  else
    echo "FAIL, not in: $(printf '%s' "$OUT" | head -3 | tr '\n' ' ')"; fail=$((fail + 1))
  fi
}

lacks() {
  printf '  %-68s' "$1"
  if printf '%s\n' "$OUT" | grep -qF -- "$2"; then
    echo "FAIL, found: $2"; fail=$((fail + 1))
  else
    echo "PASS"; pass=$((pass + 1))
  fi
}

same() {
  # same <label> <got> <expected>
  printf '  %-68s' "$1"
  if [ "$2" = "$3" ]; then
    echo "PASS"; pass=$((pass + 1))
  else
    echo "FAIL, got '$2', expected '$3'"; fail=$((fail + 1))
  fi
}

spec_many() {
  # A spec with eligible, ineligible and blocked steps. <status line>
  cat <<SPEC
# Demo parsers

Status: ${1}

## Requirements

- **R1 Alpha.** Alpha is seen.
- **R2 Beta.** Beta is seen.
- **R3 Gamma.** Gamma is seen.
- **R4 Delta.** Delta is seen.
- **R5 Epsilon.** Epsilon reads well.
- **R6 Zeta.** Zeta is seen.
- **R7 Theta.** Theta is seen.

## Criteria

| ID | Req | Scenario | Passes when | Check | Status |
|---|---|---|---|---|---|
| C1.1 | R1 | Alpha is built | The file exists | command: \`test -f src/alpha/ok.txt\` | fail |
| C2.1 | R2 | Beta is built | The file exists | test: \`test -f src/beta/ok.txt\` | not written |
| C2.2 | R2 | Beta runs | It answers | drive: Drive step L1 of \`VERIFICATION.md\` | not written |
| C3.1 | R3 | Gamma is built | The pipe matches | command: \`echo gamma \\| grep -q gamma\` | fail |
| C4.1 | R4 | Delta is built | True | command: \`true\` | fail |
| C5.1 | R5 | Epsilon reads well | A reader agrees | inspection: read the page against the style guide | not met |
| C7.1 | R7 | Theta is built | The pipe matches | command: \`echo theta | grep -q theta\` | fail |

## Steps

### Step 1: Alpha

- Status: not started
- Serves: R1
- Blocked by: none
- Owns: \`src/alpha/\`, \`requirements.txt\`, the alpha tests
- You see: alpha
- ADRs: none
- Review gate: none
- Risk: low
- Surfaces: none

### Step 2: Beta

- Status: not started
- Serves: R2
- Blocked by: Step 1
- Owns: \`src/beta/\`
- You see: beta
- ADRs: none
- Review gate: none
- Risk: medium
- Surfaces: none

### Step 3: Gamma

- Status: not started
- Serves: R3
- Blocked by: none
- Owns: \`src/gamma/\`
- You see: gamma
- ADRs: none
- Review gate: none
- Risk: high
- Surfaces: security

### Step 4: Delta

- Status: not started
- Serves: R4
- Blocked by: none
- Owns: \`src/delta/\`
- You see: delta
- ADRs: none
- Review gate: owner reviews before merge
- Risk: low
- Surfaces: none

### Step 5: Epsilon

- Status: not started
- Serves: R5
- Blocked by: none
- Owns: \`src/epsilon/\`
- You see: epsilon
- ADRs: none
- Review gate: none
- Risk: low
- Surfaces: none

### Step 6: Zeta

- Status: not started
- Serves: R6
- Blocked by: none
- Owns: \`src/zeta/\`
- You see: zeta
- ADRs: none
- Review gate: none
- Risk: low
- Surfaces: none

### Step 7: Eta

- Status: not started
- Serves: R7
- Blocked by: Step 4
- Owns: \`src/eta/\`
- You see: eta
- ADRs: none
- Review gate: none
- Risk: low
- Surfaces: none

### Step 8: Theta

- Status: not started
- Serves: R7
- Blocked by: none
- Owns: \`src/theta/\`
- You see: theta
- ADRs: none
- Review gate: none
- Risk: low
- Surfaces: none

### Step 9: Iota

- Status: not started
- Serves: R7
- Blocked by: none
- Owns: \`src/iota/\`
- You see: iota
- ADRs: none
- Review gate: none
- Risk: low
- Surfaces: none

### Step 10: Kappa

- Status: not started
- Serves: R7
- Blocked by: none
- Owns: the kappa module
- You see: kappa
- ADRs: none
- Review gate: none
- Risk: low
- Surfaces: none
SPEC
}

spec_one() {
  # A spec with one eligible step, which runs in direct mode. <status line>
  cat <<SPEC
# Fix the parser

Status: ${1}

## Requirements

- **R1 Fixed.** The parser accepts the input.

## Criteria

| ID | Req | Scenario | Passes when | Check | Status |
|---|---|---|---|---|---|
| C1.1 | R1 | The input is parsed | The file exists | command: \`test -f src/fix/ok.txt\` | fail |

## Steps

### Step 1: Fix the parser

- Status: not started
- Serves: R1
- Blocked by: none
- Owns: \`src/fix/\`
- You see: the fix
- ADRs: none
- Review gate: none
- Risk: low
- Surfaces: none
SPEC
}

make_repo() {
  # make_repo <name> <spec function> <status line>: a checkout at $T/<name> with origin at $T/<name>.git
  local repo="$T/$1"
  git init -q --bare -b main "$repo.git"
  git init -q -b main "$repo"
  mkdir -p "$repo/docs/specs" "$repo/src/alpha"
  "$2" "$3" > "$repo/docs/specs/demo.md"
  printf 'test:\n\t@test ! -f src/alpha/FAIL_TESTS\n' > "$repo/Makefile"
  printf '.claude/\ndocs/plans/\n' > "$repo/.gitignore"
  echo "def test_old(): pass" > "$repo/src/alpha/test_old.py"
  # The two protected lists name only extras: the defaults must survive them.
  echo '{"concurrency": 2, "max_rounds": 2, "protected_branches": ["release"], "protected_paths": ["custom/*"]}' > "$repo/factory.json"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m "chore: fixture"
  git -C "$repo" remote add origin "$repo.git"
  git -C "$repo" push -q -u origin main
  git -C "$repo" remote set-head origin main
}

printf '\ngate\n'
make_repo g spec_many "criteria signed off 2026-01-01"
G="$T/g"
branch() {
  # branch <name> [start]: a new branch in the gate fixture, checked out
  git -C "$G" checkout -q -b "$1" "${2:-main}"
}
commit() {
  git -C "$G" add -A
  git -C "$G" commit -q -m "feat: $1"
}
gate1() { "$GATE" --spec "$G/docs/specs/demo.md" --step 1 --base main --worktree "$G" "$@"; }

branch ok
echo ok > "$G/src/alpha/ok.txt"; commit ok
t "a branch inside Owns that meets its criterion passes" 0 gate1
has "the last line reads GATE: PASS" "GATE: PASS $(git -C "$G" rev-parse HEAD) escalate: none"
has "a concern with no script is reported, not failed" "| lint | no script | not run |"
has "the declared test target is run" '| test | `make test` | 0 |'
t "with --out the gate prints one line" 0 gate1 --out "$T/out-ok"
same "and that line is the verdict" "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')" 1
same "checks.md line 1 is the verdict" "$(sed -n 1p "$T/out-ok/checks.md")" "GATE: PASS"
same "checks.md line 2 is the commit" "$(sed -n 2p "$T/out-ok/checks.md")" "COMMIT: $(git -C "$G" rev-parse HEAD)"
same "checks.md line 3 is the escalation" "$(sed -n 3p "$T/out-ok/checks.md")" "ESCALATE: none"
same "checks.md opens its body with a summary" "$(sed -n 5p "$T/out-ok/checks.md")" "## Summary"
t "the full log sits beside the report" 0 grep -q 'exit=0' "$T/out-ok/checks.log"
sed 's/"diff_line_cap": 800/"diff_line_cap": 0/' "$SCRIPTS/../config.json" > "$T/cap.json"
t "the diff cap escalates without failing" 0 gate1 --config "$T/cap.json"
has "the cap is named on the last line" "escalate: diff over the cap of 0 changed lines"

branch protected ok
echo "edited" >> "$G/docs/specs/demo.md"; commit protected
t "an edit to a protected path fails" 1 gate1
has "the protected path is named" "GATE: FAIL protected path edited: docs/specs/demo.md"

branch cheat
sed 's|test -f src/alpha/ok.txt|true|' "$G/docs/specs/demo.md" > "$T/spec.tmp" && cp "$T/spec.tmp" "$G/docs/specs/demo.md"
echo other > "$G/src/alpha/other.txt"; commit cheat
t "a branch that rewrites its criterion still fails it" 1 gate1
has "the criterion ran as the base wrote it" "criterion C1.1 failed"
t "the report is written on a failure too" 1 gate1 --out "$T/out-cheat" --base main
OUT="$(cat "$T/out-cheat/checks.md" 2>/dev/null)"
has "the base's command is in the criteria table" 'test -f src/alpha/ok.txt'

branch added-protected ok
mkdir -p "$G/.github/workflows" "$G/custom"; echo "on: push" > "$G/.github/workflows/x.yml"; echo x > "$G/custom/c.txt"
commit added-protected
t "an added protected path fails" 1 gate1
has "the added path is named" "protected path added: .github/workflows/x.yml"
has "a repository's own protected path is added to the defaults" "protected path added: custom/c.txt"

branch outside ok
mkdir -p "$G/src/other"; echo x > "$G/src/other/x.txt"; commit outside
t "a file outside Owns fails" 1 gate1
has "the file is named" "outside Owns: src/other/x.txt"

branch failing-check ok
echo x > "$G/src/alpha/FAIL_TESTS"; commit failing-check
t "a failing declared check fails" 1 gate1
has "the check is named" "check test failed (exit 2)"

branch no-criterion
echo x > "$G/src/alpha/other.txt"; commit no-criterion
t "a failing criterion command fails" 1 gate1
has "the criterion is named" "criterion C1.1 failed (exit 1)"

branch lock ok
echo "requests" > "$G/requirements.txt"; commit lock
t "a dependency manifest change escalates without failing" 0 gate1
has "the manifest is named" "escalate: escalate path changed: requirements.txt"

branch deleted ok
git -C "$G" rm -q src/alpha/test_old.py; commit deleted
t "a deleted test file escalates" 0 gate1
has "the test file is named" "test file deleted: src/alpha/test_old.py"

branch skip ok
echo 'it.skip("parses", () => {})' > "$G/src/alpha/a.test.js"; commit skip
t "an added skip marker escalates" 0 gate1
has "the file with the marker is named" "skip marker added: src/alpha/a.test.js"

branch hidden ok
printf '* binary\n' > "$G/.gitattributes"
echo 'it.skip("parses", () => {})' > "$G/src/alpha/b.test.js"
echo 'it.only("parses", () => {})' > "$G/src/alpha/$(printf 'caf\303\251').test.js"
echo 'xit("parses", () => {})' > "$G/src/alpha/q\"q.test.js"
commit hidden
t "a binary attribute and a quoted file name fail only on Owns" 1 gate1 --config "$T/cap.json" --out "$T/out-hidden"
OUT="$(sed -n 3p "$T/out-hidden/checks.md")"
has "a marker in a file marked binary is still seen" "skip marker added: src/alpha/b.test.js"
has "a marker in a file with a non-ASCII name is still seen" "skip marker added: src/alpha/$(printf 'caf\303\251').test.js"
has "a marker in a file whose name git quotes is still seen" "skip marker added: src/alpha/q"
has "lines of files marked binary still count toward the cap" "diff over the cap of 0 changed lines"

branch gamma
mkdir -p "$G/src/gamma"; echo x > "$G/src/gamma/g.txt"; commit gamma
t "a high risk step with a security surface passes its gate" 0 \
  "$GATE" --spec "$G/docs/specs/demo.md" --step 3 --base main --worktree "$G"
has "and escalates on both" "escalate: risk is high; security surface"

branch beta
mkdir -p "$G/src/beta"; echo x > "$G/src/beta/ok.txt"; commit beta
t "a drive criterion is listed, not run" 0 \
  "$GATE" --spec "$G/docs/specs/demo.md" --step 2 --base main --worktree "$G" --out "$T/out-beta"
OUT="$(cat "$T/out-beta/checks.md")"
has "the drive row reads not run" "| C2.2 | R2 | drive |  | not run |"

branch kappa
mkdir -p "$G/src/anywhere"; echo x > "$G/src/anywhere/i.txt"; commit kappa
t "by hand, an Owns line with no backticked path skips the Owns check" 0 \
  "$GATE" --spec "$G/docs/specs/demo.md" --step 10 --base main --worktree "$G"
has "and the report says so" "the Owns check was skipped"

branch integration-tip
mkdir -p "$G/src/merged"; echo x > "$G/src/merged/m.txt"; commit "another step"
branch on-integration integration-tip
echo ok > "$G/src/alpha/ok.txt"; commit on-integration
t "measured against the run's base, another step's file is outside Owns" 1 gate1
t "measured against the integration branch, only this step counts" 0 \
  "$GATE" --spec docs/specs/demo.md --step 1 --base integration-tip --spec-ref main --worktree "$G"

branch pkg ok
echo '{"scripts": {"lint": "true", "test": "false"}}' > "$G/package.json"; : > "$G/pnpm-lock.yaml"; commit pkg
t "package.json scripts run through the lock file's package manager" 1 gate1 --out "$T/out-pkg"
has "the failing script is named with its exit code" "check test failed (exit 3)"
OUT="$(cat "$T/out-pkg/checks.md")"
has "the passing script ran too" '| lint | `pnpm run lint` | 0 |'
branch nolock ok
echo '{"scripts": {"test": "true"}}' > "$G/package.json"; commit nolock
t "package.json without a lock file fails, never guesses" 1 gate1
has "the reason says so" "no lock file names the package manager"

git -C "$G" checkout -q ok
t "an unknown step is a missing input" 2 "$GATE" --spec "$G/docs/specs/demo.md" --step 99 --base main --worktree "$G"
t "an unknown base is a missing input" 2 "$GATE" --spec "$G/docs/specs/demo.md" --step 1 --base nowhere --worktree "$G"
t "a missing flag is a usage error" 2 "$GATE" --spec "$G/docs/specs/demo.md" --base main

# The job suite: evidence files are written by hand, since the job script
# reads only their header lines.
dir() { echo "$R/docs/plans/factory-demo/jobs/$1"; }
tree() { echo "$R/.claude/worktrees/$1"; }
head_of() { git -C "$(tree "$1")" rev-parse HEAD; }
field() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$(dir "$1")/job.json" "$2"; }
work() {
  # work <job> <path>: one pushed commit in the job's worktree
  mkdir -p "$(dirname "$(tree "$1")/$2")"
  echo "$1" >> "$(tree "$1")/$2"
  git -C "$(tree "$1")" add -A
  git -C "$(tree "$1")" commit -q -m "feat: $1"
  git -C "$(tree "$1")" push -q origin "HEAD:refs/heads/$(field "$1" branch)" 2>/dev/null
}
build_md() { printf 'STATUS: %s\nCOMMIT: %s\nQUESTION: %s\n\n## Summary\n\n- built\n' "$2" "${3:-$(head_of "$1")}" "${4:-none}" > "$(dir "$1")/build.md"; }
checks_md() {
  # checks_md <job> <PASS|FAIL> [sha] [escalate]
  mkdir -p "$(dir "$1")/round-$(field "$1" round)"
  printf 'GATE: %s\nCOMMIT: %s\nESCALATE: %s\n\n## Summary\n' "$2" "${3:-$(head_of "$1")}" "${4:-none}" \
    > "$(dir "$1")/round-$(field "$1" round)/checks.md"
}
review_md() {
  # review_md <job> <reviewer> <PASS|CHANGES> [sha]
  mkdir -p "$(dir "$1")/round-$(field "$1" round)"
  printf 'VERDICT: %s\nCOMMIT: %s\n\n## Summary\n' "$3" "${4:-$(head_of "$1")}" \
    > "$(dir "$1")/round-$(field "$1" round)/review-$2.md"
}
decision_md() { printf '%s\nCOMMIT: %s\nQUESTION: %s\n\n## Summary\n' "$2" "${3:-$(head_of "$1")}" "${4:-none}" > "$(dir "$1")/decision.md"; }
pr_view() { printf '{"baseRefName":"%s","headRefOid":"%s"}\n' "$1" "$2" > "$T/gh-view.json"; echo "$1" > "$T/gh-base"; }
advance() { "$JOB" advance "$(dir "$1")" "${@:2}"; }
say() { printf '%s' "$1" | "$JOB" "$2" "$(dir "$3")"; }
reviewed() {
  # reviewed <job>: PASS files from every routed reviewer, then the move to approve
  local name
  for name in $(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["reviewers"]))' "$(dir "$1")/job.json"); do
    review_md "$1" "$name" PASS
  done
  advance "$1" approve
}
to_merged() {
  # to_merged <job> <path> <pr>: the whole path of a job with nothing to escalate
  advance "$1" build && work "$1" "$2" && build_md "$1" READY && advance "$1" gate --pr "$3" \
    && checks_md "$1" PASS && advance "$1" review && reviewed "$1" \
    && decision_md "$1" APPROVE && advance "$1" merging \
    && pr_view factory/demo "$(head_of "$1")" && "$JOB" merge "$(dir "$1")"
}

printf '\njob plan\n'
make_repo j spec_many "draft"
R="$T/j"
echo "$R.git" > "$T/gh-origin"
cd "$R" || exit 1
SPEC=docs/specs/demo.md
t "a draft spec is refused" 1 "$JOB" plan "$SPEC"
has "the refusal names the status" "refused: spec status is \`draft\`, not \`criteria signed off\`"
spec_many "criteria signed off 2026-01-01" > "$SPEC"
t "a spec that differs from its committed copy is refused" 1 "$JOB" plan "$SPEC"
git add -A && git commit -q -m "docs: sign off" && git push -q origin main
t "a signed-off spec is planned" 0 "$JOB" plan "$SPEC"
PLAN="$OUT"
has "an eligible step gets a job" "job 01-alpha step 1 integration factory-job/demo/01-alpha"
has "a step with a review gate is listed with the reason" "ineligible step 4 review gate: owner reviews before merge"
has "a step with an inspection criterion is listed" "ineligible step 5 criterion C5.1 of R5 is an inspection"
has "a step whose requirement has no criterion is listed" "ineligible step 6 requirement R6 has no criterion"
has "a step whose Owns names no path is listed" "ineligible step 10 Owns names no path in backticks"
lacks "an ineligible step gets no job" "job 04-delta"
same "more than one eligible step runs in integration mode" \
  "$(python3 -c 'import json; r=json.load(open("docs/plans/factory-demo/run.json")); print(r["mode"], r["integration_branch"], r["spec"])')" \
  "integration factory/demo docs/specs/demo.md"
same "the integration branch is pushed from the base sha" \
  "$(git -C "$R.git" rev-parse refs/heads/factory/demo)" "$(git rev-parse main)"
same "reviewers are the union of the risk and surface routes" \
  "$(field 03-gamma reviewers)" "['principal-engineer', 'test-engineer', 'security-engineer']"
same "the job records the base ref and sha" "$(field 01-alpha base)" "{'ref': 'main', 'sha': '$(git rev-parse main)'}"
same "the job records the gate base" "$(field 01-alpha gate_base)" "origin/factory/demo"
same "a job behind an ineligible step is blocked from the start" "$(field 07-eta stage)" "blocked"
t "planning the same spec again changes nothing" 0 "$JOB" plan "$SPEC"
same "and prints the same lines" "$OUT" "$PLAN"

printf '\njob next and the start of a job\n'
t "next lists every job" 0 "$JOB" next "$SPEC"
has "an unblocked job starts" "start 01-alpha planned"
has "a job behind an unmerged step holds" "hold 02-beta planned blocked by 01-alpha (planned)"
has "the second slot starts another job" "start 03-gamma planned"
has "a third job holds on concurrency" "hold 08-theta planned concurrency 2 is in use"
has "a blocked job is done" "done 07-eta blocked blocked by Step 4, which the factory does not run"
t "a move the table does not have is refused" 1 advance 01-alpha review
has "the refusal names both stages" "refused: no move from planned to review"
t "a job behind an unmerged step cannot start" 1 advance 02-beta build
t "planned to build creates the worktree and branch" 0 advance 01-alpha build
same "the worktree is on the job branch" "$(git -C "$(tree 01-alpha)" rev-parse --abbrev-ref HEAD)" "factory-job/demo/01-alpha"
t "a second job starts" 0 advance 03-gamma build
t "a third start is refused on concurrency" 1 advance 08-theta build
has "the refusal names the limit" "refused: concurrency 2 is in use"

printf '\nbuild to gate\n'
t "a missing build.md is refused" 1 advance 01-alpha gate --pr 11
BASE_SHA="$(git rev-parse main)"
work 01-alpha src/alpha/ok.txt
build_md 01-alpha READY "$BASE_SHA"
t "a build.md whose COMMIT is not HEAD is refused" 1 advance 01-alpha gate --pr 11
has "the refusal names both commits" "build.md names COMMIT $BASE_SHA but HEAD is"
build_md 01-alpha READY
echo stray > "$(tree 01-alpha)/stray.txt"
t "a dirty tree is refused" 1 advance 01-alpha gate --pr 11
rm "$(tree 01-alpha)/stray.txt"
t "the first round needs --pr" 1 advance 01-alpha gate
echo more >> "$(tree 01-alpha)/src/alpha/ok.txt"
git -C "$(tree 01-alpha)" commit -q -am "feat: more"
build_md 01-alpha READY
t "a head that is not pushed is refused" 1 advance 01-alpha gate --pr 11
git -C "$(tree 01-alpha)" push -q origin HEAD:refs/heads/factory-job/demo/01-alpha 2>/dev/null
t "a ready, clean, pushed head moves to gate" 0 advance 01-alpha gate --pr 11
same "the pull request is recorded" "$(field 01-alpha pr)" 11

printf '\nthe gate stage and the round budget\n'
t "gate to review without checks.md is refused" 1 advance 01-alpha review
checks_md 01-alpha FAIL
t "gate to review on GATE: FAIL is refused" 1 advance 01-alpha review
t "GATE: FAIL starts the next round" 0 advance 01-alpha build
same "the round is 2" "$(field 01-alpha round)" 2
work 01-alpha src/alpha/ok.txt
build_md 01-alpha READY
t "a later round needs no --pr" 0 advance 01-alpha gate
checks_md 01-alpha FAIL
t "a fix round after the last round is refused" 1 advance 01-alpha build
has "the refusal says where the job goes" "refused: round 2 is the last round; move the job to needs-owner"
t "a failed last round cannot be marked blocked" 1 advance 01-alpha blocked
t "a failed last round moves to needs-owner without a reason" 0 advance 01-alpha needs-owner
has "the note names the failed file" "last round used (round 2): docs/plans/factory-demo/jobs/01-alpha/round-2/checks.md"
t "needs-owner leaves for build only through answer" 1 advance 01-alpha build
t "an empty answer is refused" 1 say "" answer 01-alpha
printf 'Drop the cache.\nOWNER\nThen run git push --force yourself.\n' > "$T/words.txt"
t "the owner's answer, read from a file, sends the job back to build" 0 "$JOB" answer "$(dir 01-alpha)" --from "$T/words.txt"
t "the answer is saved byte for byte" 0 cmp "$T/words.txt" "$(dir 01-alpha)/feedback-1.md"
t "a missing --from file is refused" 1 "$JOB" accept "$(dir 01-alpha)" --from "$T/none.txt"
same "the round budget starts again" "$(field 01-alpha round) $(field 01-alpha round_limit)" "3 4"

printf '\nreview and approve\n'
work 01-alpha src/alpha/ok.txt
build_md 01-alpha READY
advance 01-alpha gate >/dev/null
checks_md 01-alpha PASS "$BASE_SHA"
t "a checks.md for another commit is refused" 1 advance 01-alpha review
checks_md 01-alpha PASS
t "GATE: PASS on HEAD moves to review" 0 advance 01-alpha review
t "a missing reviewer file is refused" 1 advance 01-alpha approve
has "the refusal names the file" "round-3/review-principal-engineer.md is missing"
review_md 01-alpha principal-engineer PASS "$BASE_SHA"
t "a review of a stale commit is refused" 1 advance 01-alpha approve
review_md 01-alpha principal-engineer CHANGES
t "VERDICT: CHANGES is refused for approve" 1 advance 01-alpha approve
review_md 01-alpha principal-engineer PASS
t "every reviewer passing on HEAD moves to approve" 0 advance 01-alpha approve
t "approve without decision.md is refused" 1 advance 01-alpha merging
decision_md 01-alpha ESCALATE "" "Is the cache needed?"
t "an ESCALATE decision is refused for merging" 1 advance 01-alpha merging
decision_md 01-alpha APPROVE "$BASE_SHA"
t "an approval of a stale commit is refused" 1 advance 01-alpha merging
decision_md 01-alpha APPROVE
t "an integration run has no merge-ready" 1 advance 01-alpha merge-ready
t "an approval of HEAD moves to merging" 0 advance 01-alpha merging
t "merged is reached only through merge" 1 advance 01-alpha merged

printf '\njob merge\n'
pr_view main "$(head_of 01-alpha)"
t "a pull request against a protected base is refused" 1 "$JOB" merge "$(dir 01-alpha)"
has "the refusal names the branch" "pull request 11 targets the protected branch main"
same "and the job waits on the owner" "$(field 01-alpha stage)" "needs-owner"
t "the owner accepts an approved, gated head" 0 say "The base is fixed, go on." accept 01-alpha
same "the job is back at merging" "$(field 01-alpha stage)" "merging"
pr_view factory/demo "$(head_of 01-alpha)"
t "a gated, approved job merges" 0 "$JOB" merge "$(dir 01-alpha)"
has "one line names the pull request" "merged 01-alpha merged pull request 11 merged at"
OUT="$(cat "$T/gh.log")"
has "gh merged with a merge commit pinned to the head" "pr merge 11 --merge --match-head-commit $(head_of 01-alpha)"
same "the gate ran again before the merge" "$(sed -n 1p "$(dir 01-alpha)/round-3/merge-checks.md")" "GATE: PASS"

printf '\nhard escalation\n'
work 03-gamma src/gamma/g.txt
build_md 03-gamma READY
advance 03-gamma gate --pr 13 >/dev/null
checks_md 03-gamma PASS "" "risk is high"
t "an escalated gate still moves to review" 0 advance 03-gamma review
t "and on to approve" 0 reviewed 03-gamma
decision_md 03-gamma APPROVE
t "approve to merging is refused while ESCALATE is not none" 1 advance 03-gamma merging
has "the refusal carries the reasons" "refused: ESCALATE is not none (risk is high); 03-gamma is now at needs-owner"
same "the refusal itself parks the job" "$(field 03-gamma stage)" "needs-owner"
t "a following move to needs-owner changes nothing" 0 advance 03-gamma needs-owner
t "next marks the job as waiting" 0 "$JOB" next "$SPEC"
has "with the reasons as the question" "wait 03-gamma needs-owner hard escalation: risk is high"
has "the job behind the merged step now starts" "start 02-beta planned"
t "needs-owner leaves for merging only through accept" 1 advance 03-gamma merging
t "the owner accepts the escalation" 0 say "High risk is expected here." accept 03-gamma
same "the acceptance is saved word for word" "$(cat "$(dir 03-gamma)/acceptance-1.md")" "High risk is expected here."
pr_view factory/demo "$(head_of 03-gamma)"
OLD="$(head_of 03-gamma)"
t "a reason the owner did not accept stops the merge" 1 "$JOB" merge "$(dir 03-gamma)"
has "the unaccepted reason is named" "escalates what the owner has not accepted: security surface"
same "the worktree is back at the pushed head" "$(head_of 03-gamma)" "$OLD"
checks_md 03-gamma PASS "" "risk is high; security surface"
t "the owner accepts both reasons" 0 say "Both are expected." accept 03-gamma
t "the accepted job syncs and merges" 0 "$JOB" merge "$(dir 03-gamma)"
NEW="$(head_of 03-gamma)"
t "the branch was rebased onto the integration branch" 0 git merge-base --is-ancestor "$(head_of 01-alpha)" "$NEW"
same "the rebased head was pushed over the old one" "$(git -C "$R.git" rev-parse refs/heads/factory-job/demo/03-gamma)" "$NEW"
OUT="$(cat "$T/gh.log")"
has "gh was pinned to the rebased head" "pr merge 13 --merge --match-head-commit $NEW"

printf '\nthe circuit breaker\n'
advance 02-beta build >/dev/null
advance 08-theta build >/dev/null
t "the next job is cut from the merged integration branch" 0 test -f "$(tree 02-beta)/src/alpha/ok.txt"
build_md 08-theta BLOCKED "" "Which fixture holds the theta input?"
t "STATUS: BLOCKED moves a job to blocked" 0 advance 08-theta blocked
build_md 02-beta FORK "" "Keep the old format?"
t "STATUS: FORK without a fork file is refused" 1 advance 02-beta needs-owner
printf 'FORK\nCOMMIT: %s\nQUESTION: Keep the old format or replace it?\n\n## Summary\n' "$(head_of 02-beta)" > "$(dir 02-beta)/fork-1.md"
t "STATUS: FORK moves a job to needs-owner" 0 advance 02-beta needs-owner
t "next after two stopped jobs in a row" 0 "$JOB" next "$SPEC"
has "stop is the first line and names both jobs" "$(printf '%s\n' "$OUT" | sed -n 1p | grep -F 'stop circuit breaker: the last 2 finished jobs ended at needs-owner or blocked (08-theta blocked, 02-beta needs-owner)')"
has "the fork's question is the note of the wait line" "wait 02-beta needs-owner Keep the old format or replace it? (docs/plans/factory-demo/jobs/02-beta/fork-1.md)"
has "a planned job holds while the breaker is open" "hold 09-iota planned the circuit breaker is open"
t "a start is refused while the breaker is open" 1 advance 09-iota build
t "status prints the table" 0 "$JOB" status "$SPEC"
has "with a header row" "job       stage        round  pull request  gate  reviews"
has "and the question of a waiting job" "Keep the old format or replace it?"
t "status --json prints the run and its jobs" 0 "$JOB" status "$SPEC" --json
has "with each job's stage" '"stage": "needs-owner"'
has "and its history of moves" '"history": ['
t "the JSON parses" 0 sh -c "\"$JOB\" status \"$SPEC\" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d[\"run\"][\"mode\"] and d[\"jobs\"]'"
t "dashboard prints the page's path" 0 "$JOB" dashboard "$SPEC"
has "inside the run folder" "dashboard docs/plans/factory-demo/dashboard.html"
BOARD="$(dirname "$(dirname "$(dir 02-beta)")")/dashboard.html"
t "the page exists and carries the waiting job's question" 0 grep -c "Keep the old format or replace it?" "$BOARD"
t "a note cannot close the page's data element" 1 grep -c '</script><' "$BOARD"
STAMP="$(cksum < "$BOARD")"
t "the owner's answer closes the breaker" 0 say "Replace it." answer 02-beta
t "the page is rewritten when a job moves" 1 test "$STAMP" = "$(cksum < "$BOARD")"
t "and shows the job's new stage" 0 python3 -c "import json,re,sys; d=json.loads(re.search(r'<script id=\"data\" type=\"application/json\">(.*?)</script>', open(sys.argv[1]).read(), re.S).group(1)); assert [j for j in d['jobs'] if j['id']=='02-beta'][0]['stage']=='build'" "$BOARD"
t "a builder's blocked job is answered the same way" 0 say "Use fixtures/theta.txt." answer 08-theta
t "next in a new process reports each job at its recorded stage" 0 "$JOB" next "$SPEC"
lacks "the breaker is closed" "stop "
has "a merged job is done" "done 01-alpha merged"
has "an answered job resumes at build" "resume 02-beta build round 2"
has "and so does the other" "resume 08-theta build round 2"
has "the last job holds on concurrency" "hold 09-iota planned concurrency 2 is in use"

printf '\njob final\n'
t "final is refused while a job is not merged" 1 "$JOB" final "$SPEC"
has "the refusal names the open jobs" "refused: not every job is merged: 02-beta build"
work 02-beta src/beta/ok.txt; build_md 02-beta READY; advance 02-beta gate --pr 12 >/dev/null
checks_md 02-beta PASS; advance 02-beta review >/dev/null; reviewed 02-beta >/dev/null
decision_md 02-beta APPROVE; advance 02-beta merging >/dev/null; pr_view factory/demo "$(head_of 02-beta)"
t "the answered job merges" 0 "$JOB" merge "$(dir 02-beta)"
work 08-theta src/theta/t.txt; build_md 08-theta READY; advance 08-theta gate --pr 18 >/dev/null
checks_md 08-theta PASS; advance 08-theta review >/dev/null; reviewed 08-theta >/dev/null
decision_md 08-theta APPROVE; advance 08-theta merging >/dev/null; pr_view factory/demo "$(head_of 08-theta)"
touch "$T/gh-merge-fails"
t "a merge gh refuses moves the job to needs-owner" 1 "$JOB" merge "$(dir 08-theta)"
has "with gh's reason" "merge refused by the stub; 08-theta is now at needs-owner"
rm "$T/gh-merge-fails"
say "Try again." accept 08-theta >/dev/null
pr_view factory/demo "$(head_of 08-theta)"
t "and merges once accepted" 0 "$JOB" merge "$(dir 08-theta)"
t "the last job runs start to merge" 0 to_merged 09-iota src/iota/i.txt 19
t "final gates the integration branch and opens the pull request" 0 "$JOB" final "$SPEC"
has "one line with the pull request" "final https://example.com/pull/57 PASS"
same "the final gate ran the criteria of every finished requirement" \
  "$(grep -c '^| C[0-9.]* .* | 0 | [0-9.]* |$' docs/plans/factory-demo/final-checks.md)" 3
OUT="$(cat docs/plans/factory-demo/final-checks.md)"
has "a requirement an unmerged step serves is listed, not run" '| C7.1 | R7 | command | `echo theta \| grep -q theta` | not run |'
OUT="$(cat "$T/gh.log")"
has "the final pull request is a draft against the default branch" "pr create --draft --base main --head factory/demo --title feat: demo parsers"
has "its body lists each job" "| 03-gamma | #13 | PASS | principal-engineer PASS, security-engineer PASS, test-engineer PASS | merged |"
t "final a second time opens nothing new" 0 "$JOB" final "$SPEC"
same "gh pr create ran once" "$(grep -c '^pr create' "$T/gh.log")" 1

printf '\ndirect mode\n'
make_repo d spec_one "criteria signed off 2026-01-01"
R="$T/d"
echo "$R.git" > "$T/gh-origin"
cd "$R" || exit 1
t "a spec with one eligible step is planned" 0 "$JOB" plan "$SPEC"
has "in direct mode" "job 01-fix-the-parser step 1 direct factory-job/demo/01-fix-the-parser"
t "no integration branch is created" 1 git rev-parse --verify --quiet refs/heads/factory/demo
same "the gate base is the run's base sha" "$(field 01-fix-the-parser gate_base)" "$(git rev-parse main)"
J=01-fix-the-parser
advance "$J" build >/dev/null; work "$J" src/fix/other.txt; build_md "$J" READY; advance "$J" gate --pr 21 >/dev/null
checks_md "$J" PASS; advance "$J" review >/dev/null; reviewed "$J" >/dev/null; decision_md "$J" APPROVE
t "a direct run has no merging" 1 advance "$J" merging
t "a forged GATE: PASS does not reach merge-ready" 1 advance "$J" merge-ready
has "the gate ran again and failed the criterion" "refused: the gate before merge-ready failed: criterion C1.1 failed (exit 1)"
same "the job stays at approve" "$(field "$J" stage)" "approve"
advance "$J" needs-owner --reason "The criterion fails." >/dev/null; say "Add the file." answer "$J" >/dev/null
work "$J" src/fix/ok.txt
echo 'it.skip("parses", () => {})' > "$(tree "$J")/src/fix/a.test.js"; work "$J" src/fix/ok.txt
build_md "$J" READY; advance "$J" gate >/dev/null
t "the gate by hand takes the gate base and the spec ref" 0 "$GATE" --spec "$SPEC" --step 1 \
  --base "$(field "$J" gate_base)" --spec-ref "$(git rev-parse main)" --worktree "$(tree "$J")" --out "$T/out-direct"
checks_md "$J" PASS; advance "$J" review >/dev/null; reviewed "$J" >/dev/null; decision_md "$J" APPROVE
t "a forged ESCALATE: none does not reach merge-ready" 1 advance "$J" merge-ready
has "the escalation comes from the gate run again" "refused: ESCALATE is not none (skip marker added: src/fix/a.test.js)"
same "and the job waits on the owner" "$(field "$J" stage)" "needs-owner"
t "the owner's acceptance gates once more and ends at merge-ready" 0 say "The skip is wanted." accept "$J"
same "a direct job ends at merge-ready" "$(field "$J" stage)" "merge-ready"
same "the gate before merge-ready is on file" "$(sed -n 1p "$(dir "$J")/round-2/merge-checks.md")" "GATE: PASS"
t "next reports it done" 0 "$JOB" next "$SPEC"
has "at merge-ready" "done 01-fix-the-parser merge-ready"
t "a direct run has no merge" 1 "$JOB" merge "$(dir "$J")"
t "a direct run has no final pull request" 1 "$JOB" final "$SPEC"
t "a spec with no run is refused by next" 1 "$JOB" next docs/specs/none.md

printf '\nthe integration branch and the run folder as inputs\n'
make_repo s spec_many "criteria signed off 2026-01-01"
R="$T/s"
echo "$R.git" > "$T/gh-origin"
cd "$R" || exit 1
"$JOB" plan "$SPEC" >/dev/null
RUN=docs/plans/factory-demo/run.json
same "the run records the integration tip" \
  "$(python3 -c 'import json; print(json.load(open("docs/plans/factory-demo/run.json"))["integration_tip"])')" "$(git rev-parse main)"
advance 01-alpha build >/dev/null; work 01-alpha src/alpha/ok.txt; build_md 01-alpha READY
advance 01-alpha gate --pr 31 >/dev/null; checks_md 01-alpha PASS; advance 01-alpha review >/dev/null
reviewed 01-alpha >/dev/null; decision_md 01-alpha APPROVE; advance 01-alpha merging >/dev/null
pr_view develop "$(head_of 01-alpha)"
t "a default protected branch survives a repository's own list" 1 "$JOB" merge "$(dir 01-alpha)"
has "the refusal names it" "pull request 31 targets the protected branch develop"
say "Go on." accept 01-alpha >/dev/null
cp "$RUN" "$T/run.json"
sed 's|"integration_branch": "factory/demo"|"integration_branch": "release-2"|' "$T/run.json" > "$RUN"
pr_view release-2 "$(head_of 01-alpha)"
t "a run.json that names another branch cannot aim the merge" 1 "$JOB" merge "$(dir 01-alpha)"
has "the refusal names the branch the run owns" "run.json names the integration branch release-2, not factory/demo"
OUT="$(cat "$T/gh.log")"
lacks "and gh was never asked to merge it" "pr merge 31"
cp "$T/run.json" "$RUN"
say "Go on." accept 01-alpha >/dev/null
TIP="$(git rev-parse main)"
git clone -q "$R.git" "$T/rogue" 2>/dev/null
git -C "$T/rogue" checkout -q factory/demo
mkdir -p "$T/rogue/src/unowned"; echo x > "$T/rogue/src/unowned/x.txt"
git -C "$T/rogue" add -A; git -C "$T/rogue" commit -q -m "feat: unowned"; git -C "$T/rogue" push -q origin factory/demo
ROGUE="$(git -C "$T/rogue" rev-parse HEAD)"
pr_view factory/demo "$(head_of 01-alpha)"
t "a commit pushed straight to the integration branch stops the merge" 1 "$JOB" merge "$(dir 01-alpha)"
has "the refusal names both commits" "origin/factory/demo is at $ROGUE, not at $TIP where this run's last merge left it"
t "and stops the start of the next job" 1 advance 03-gamma build
has "with the same refusal" "origin/factory/demo is at $ROGUE, not at $TIP"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
