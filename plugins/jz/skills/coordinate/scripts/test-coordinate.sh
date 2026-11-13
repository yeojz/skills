#!/usr/bin/env bash
# Regression suite for the coordinate skill's unit script. Builds a throwaway
# repository with a local bare repository as origin and a stub gh on PATH that
# answers `pr view` from a file the suite writes, so nothing here needs a
# network. Each refusal the script can make has a case that reaches it.
set -uo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT="$SCRIPTS/unit"
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
# Records every call and answers `pr view` from the file the suite writes.
T="$(cd "$(dirname "$0")/.." && pwd)"
printf '%s\n' "$*" >> "$T/gh.log"
[ -f "$T/gh-fails" ] && { echo "HTTP 502: stub outage" >&2; exit 1; }
case "$1 $2" in "pr view") cat "$T/gh-view.json" ;; esac
STUB
chmod +x "$T/bin/gh"
export PATH="$T/bin:$PATH"

t() {
  # t <label> <expected exit> <unit arguments...>; the output is left in $OUT
  local label="$1" want="$2" got
  shift 2
  OUT="$(cd "$R" && "$UNIT" "$@" 2>&1)"
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

R="$T/repo"
N="$R/docs/plans/coordinate-demo"
git init -q --bare "$T/origin.git"
git init -q -b main "$R"
git -C "$R" remote add origin "$T/origin.git"
git -C "$R" commit -q --allow-empty -m "chore: start"
git -C "$R" push -q origin main
git -C "$R" switch -q -c feat/x-step

push_commit() {
  # A new commit on the step's branch, pushed; prints its sha.
  git -C "$R" commit -q --allow-empty -m "feat: $1"
  git -C "$R" push -q origin feat/x-step
  git -C "$R" rev-parse HEAD
}
pr_view() { printf '{"state":"%s","headRefOid":"%s","isDraft":%s}\n' "$1" "$2" "${3:-false}" > "$T/gh-view.json"; }
at_move() {
  # at_move <file> <id>: give the file the very second its row last moved
  python3 -c 'import calendar,os,sys,time; t=calendar.timegm(time.strptime(sys.argv[2],"%Y-%m-%dT%H:%M:%SZ")); os.utime(sys.argv[1],(t,t))' "$1" "$(cell "$2" moved)"
}
aged() { python3 -c 'import os,sys,time; t=time.time()-120; os.utime(sys.argv[1],(t,t))' "$1"; }
cell() { awk -F'\t' -v id="$1" -v col="$2" 'NR == 1 { for (i = 1; i <= NF; i++) if ($i == col) n = i } $1 == id { print $n }' "$N/units.tsv"; }

brief() {
  # brief <id> [behaviour target]
  cat > "$N/phase-$1.md" <<BRIEF
# Phase $1: a step

## Done means

Behaviour target: ${2:-unit-only}

- C1.1 empty input is refused: passes when the parser returns an error. Check: \`make test\`
- C1.2 a pipe survives: passes when the row is read whole. Check: \`cat x | wc -l\`
- C1.10 a tenth criterion: passes when it holds. Check: \`make test\`

<!-- a comment the repository's own standing orders carry -->
BRIEF
}

report() {
  # report <id> <status> <commit> <C1.2 result> [behaviour]
  cat > "$N/report-$1.md" <<REPORT
STATUS: $2
COMMIT: $3
QUESTION: ${6:-none}

| Concern | Command | Exit | Result |
|---|---|---|---|
| test | make test | 0 | pass |
| format | (no script) | - | not covered |
| C1.1 empty input is refused | make test | 0 | pass |
| C1.2 a pipe survives | \`cat x | wc -l\` | 0 | $4 |
| C1.10 a tenth criterion | make test | 0 | pass |
| behaviour | make test | 0 | ${5:-unit-only} |

## Findings answered

| ID | Commit | What changed |
|---|---|---|
| F1 | abc1234 | failing guard restored |
| F2 | def5678 | - |

## Forks decided

| Fork | Options | Chosen | Why |
|---|---|---|---|
| helper name | parseClaims, readClaims | readClaims | fails the glossary otherwise |
REPORT
}

review() {
  # review <pr> <verdict> <commit> [findings] [C1.2 result on the reviewer's checkout]
  cat > "$N/review-pr$1.md" <<REVIEW
VERDICT: $2
COMMIT: $3
FINDINGS: ${4:-0 P1, 0 P2, 0 P3, 0 not fixed}

## Criteria

| Criterion | Check | Result here | Worker's row | Finding |
|---|---|---|---|---|
| C1.1 empty input is refused | \`make test\` | pass, exit 0 | pass, exit 0 | none |
| C1.2 a pipe survives | \`cat x | wc -l\` | ${5:-pass, exit 0} | pass, exit 0 | none |
| C1.10 a tenth criterion | \`make test\` | pass, exit 0 | pass, exit 0 | none |
REVIEW
}

printf '\nopen and add\n'
t "a step is refused before the ledgers exist" 1 add "$N" 01 "first step"
has "and the refusal names the command" "run \`unit open\` first"
t "open creates the ledgers" 0 open "$N"
same "units.tsv has its header" "$(head -1 "$N/units.tsv" | cut -f1,9,10)" "$(printf 'id\tstate\tmoved')"
same "decisions.tsv has its header" "$(head -1 "$N/decisions.tsv" | cut -f1-3)" "$(printf 'when\tunit\tkind')"
t "add writes a row at scoped" 0 add "$N" 01 "first	step"
same "the title is one cell" "$(cell 01 title)" "first step"
t "a second step is added" 0 add "$N" 02 "second step"
t "a third step is added" 0 add "$N" 03 "third step"
t "an id already in the ledger is refused" 1 add "$N" 01 "again"
t "an id that could leave the folder is refused" 1 add "$N" "../x" "escape"
t "open again leaves the run as it is" 0 open "$N"
has "and counts its steps" "3 steps"

printf '\nscoped to running\n'
t "next asks for a brief that is not written" 0 next "$N"
has "with the file it wants" "brief 01 phase-01.md is not written yet"
t "running is refused without the brief" 1 move "$N" 01 running --branch feat/x-step
has "naming the brief" "phase-01.md is not written yet"
brief 01
printf '<!-- Paste the ## Standing orders section of AGENTS.md here verbatim, then delete this comment. -->\n' >> "$N/phase-01.md"
t "running is refused while the brief holds a template comment" 1 move "$N" 01 running --branch feat/x-step
brief 01
t "next says to start a step whose brief is written" 0 next "$N"
has "naming the brief to send" "start 01 phase-01.md"
t "running is refused without a branch" 1 move "$N" 01 running
has "naming the flag" "needs --branch"
t "a state the row cannot reach from here is refused" 1 move "$N" 01 merged
has "with the states it can reach" "01 is at scoped, which leaves only for: running, parked, blocked"
t "running records the branch and the session" 0 move "$N" 01 running --branch feat/x-step --session s-1 --base main
has "and prints one line" "running 01 branch=feat/x-step"
same "the session is in the row" "$(cell 01 session)" "s-1"

printf '\nthe worker'"'"'s report\n'
H1="$(push_commit one)"
pr_view OPEN "$H1"
t "next waits while there is no report" 0 next "$N"
has "on the running step" "wait 01 running"
t "ready is refused without a pull request" 1 move "$N" 01 ready
has "naming the flag" "--pr"
t "ready is refused before the report is written" 1 move "$N" 01 ready --pr 42
has "naming the report" "report-01.md is not written yet"
report 01 BLOCKED "$H1" pass unit-only "the fixture server will not start"
at_move "$N/report-01.md" 01
t "next shows a report written in the second its row moved" 0 next "$N"
has "as one line" "report 01 BLOCKED the fixture server will not start"
t "a report that is not READY is refused" 1 move "$N" 01 ready --pr 42
has "with its status and question" "reads STATUS: BLOCKED: the fixture server will not start"
printf 'STATUS: READY\nHEAD: %s\nQUESTION: none\n' "$H1" > "$N/report-01.md"
t "a report whose second line is not COMMIT is refused" 1 move "$N" 01 ready --pr 42
has "naming the line" "report-01.md line 2 must read \`COMMIT: ...\`"
report 01 READY "$H1" fail
t "a failing criterion is refused" 1 move "$N" 01 ready --pr 42
has "naming the row" "C1.2 a pipe survives\` reads fail"
report 01 READY "$H1" "not covered"
t "a criterion that neither passes nor is met is refused" 1 move "$N" 01 ready --pr 42
has "quoting its result" "report-01.md: C1.2 reads not covered"
report 01 READY "$H1" pass
grep -v '^| C1.1' "$N/report-01.md" > "$N/report.tmp" && mv "$N/report.tmp" "$N/report-01.md"
t "a criterion with no row is refused" 1 move "$N" 01 ready --pr 42
has "naming the criterion" "report-01.md has no row for C1.1"
report 01 READY "$H1" pass type-check-only
t "a behaviour row below the brief's target is refused" 1 move "$N" 01 ready --pr 42
has "naming both levels" "behaviour reads type-check-only, below the brief's unit-only"
report 01 READY "$H1" pass
printf '# Phase 01\n\nBehaviour target: none: the criteria alone decide\n' > "$N/phase-01.md"
t "a brief that lists no criterion is refused" 1 move "$N" 01 ready --pr 42
has "naming the brief" "phase-01.md lists no criterion"
brief 01
pr_view OPEN "0000000000000000000000000000000000000000"
t "a report for a commit the pull request is not at is refused" 1 move "$N" 01 ready --pr 42
has "naming both commits" "report-01.md reports $H1, and pull request 42 is at 0000000000"
git -C "$R" commit -q --allow-empty -m "feat: unpushed"
H_LOCAL="$(git -C "$R" rev-parse HEAD)"
report 01 READY "$H_LOCAL" pass
pr_view OPEN "$H_LOCAL"
t "a head origin does not hold is refused" 1 move "$N" 01 ready --pr 42
has "naming the branch" "origin/feat/x-step is at ${H1:0:10}"
git -C "$R" reset -q --hard "$H1"
report 01 READY "$H1" pass
sed 's/^| C1.10 \(.*\)| pass |$/| C1.10 \1| not covered |/' "$N/report-01.md" > "$N/report.tmp" && mv "$N/report.tmp" "$N/report-01.md"
pr_view OPEN "$H1"
t "a two-digit criterion is read as itself" 1 move "$N" 01 ready --pr 42
has "and named whole" "report-01.md: C1.10 reads not covered"
report 01 READY "$H1" pass
sed 's/^Behaviour target: .*/Behaviour target: unit-only, which the owner set below live-verified/' "$N/phase-01.md" > "$N/phase.tmp" && mv "$N/phase.tmp" "$N/phase-01.md"
pr_view OPEN "$H1" true
t "a pull request still in draft is refused" 1 move "$N" 01 ready --pr 42
has "saying so" "pull request 42 is still a draft"
pr_view OPEN "$H1"
printf 'STATUS: DONE\nCOMMIT: %s\nQUESTION: none\n' "$H1" > "$N/report.keep"; cp "$N/report-01.md" "$N/report.good"; cp "$N/report.keep" "$N/report-01.md"
t "next flags a status the report cannot carry" 0 next "$N"
has "as a line to check" "check 01 running: report-01.md reads STATUS: DONE"
cp "$N/report.good" "$N/report-01.md"
t "a report that matches the brief and the pull request moves the row" 0 move "$N" 01 ready --pr 42
has "and prints the pull request and the head" "ready 01 pr=42 head=${H1:0:10}"
same "the head is in the row" "$(cell 01 head)" "$H1"
same "the row is at ready" "$(cell 01 state)" "ready"

printf '\nthe review\n'
t "next says to start the reviewer" 0 next "$N"
has "with the pull request and head" "review 01 pr=42 head=${H1:0:10}"
t "a fix round with no verdict is refused while the pull request has not moved" 1 move "$N" 01 fixing --reason "owner pushed"
has "naming both heads" "pull request 42 is at ${H1:0:10} and the step's head is ${H1:0:10}"
pr_view OPEN "0000000000000000000000000000000000000000"
t "and refused without a reason when it has" 1 move "$N" 01 fixing
t "a pull request that moved under a waiting step frees it for a fix round" 0 move "$N" 01 fixing --reason "owner pushed a typo fix"
has "naming the new head" "fixing 01 pr=42 moved to 0000000000"
same "which uses no fix round" "$(grep -c "$(printf '\tverdict\t')" "$N/decisions.tsv")" "0"
pr_view OPEN "$H1"
# Back to ready for the cases below: the suite stands in for the report a real new head would bring.
python3 -c 'import sys; p=sys.argv[1]; text=open(p).read().replace("\tfixing\t","\tready\t"); open(p,"w").write(text)' "$N/units.tsv"
t "the row moves to in-review" 0 move "$N" 01 in-review
t "next waits while there is no review" 0 next "$N"
has "on the step in review" "wait 01 in-review"
t "a verdict is refused before the review is written" 1 move "$N" 01 merge-ready
has "naming the review file" "review-pr42.md is not written yet"
review 42 "after fixes" "0000000" "0 P1, 2 P2, 1 P3, 0 not fixed"
t "next flags a review of another commit" 0 next "$N"
has "as stale" "stale 01 review-pr42.md is of 0000000, and the step's head is ${H1:0:10}"
t "a review of another commit is refused" 1 move "$N" 01 fixing
has "naming both commits" "review-pr42.md reviewed 0000000, and the step's head is ${H1:0:10}"
review 42 "after fixes" "$H1" "0 P1, 2 P2, 1 P3, 0 not fixed"
t "next shows the verdict and the counts" 0 next "$N"
has "as one line" "verdict 01 after fixes; 0 P1, 2 P2, 1 P3, 0 not fixed"
t "merge-ready is refused on a verdict of after fixes" 1 move "$N" 01 merge-ready
has "quoting the verdict" "review-pr42.md reads VERDICT: after fixes"
review 42 "looks fine" "$H1"
t "a verdict the skill does not name starts no fix round" 1 move "$N" 01 fixing
review 42 "after fixes" "$H1" "0 P1, 2 P2, 1 P3, 0 not fixed"
t "a verdict of after fixes starts a fix round" 0 move "$N" 01 fixing
has "and prints the review file, the round and the counts" "fixing 01 pr=42 head=${H1:0:10} review=review-pr42.md round=1 findings=0 P1, 2 P2, 1 P3, 0 not fixed"
same "the verdict is logged" "$(tail -1 "$N/decisions.tsv" | cut -f2,3,5,6)" "$(printf '01\tverdict\treview-pr42.md\tafter fixes')"
aged "$N/report-01.md"
t "next waits on a fix round whose report is the old one" 0 next "$N"
has "on the step being fixed" "wait 01 fixing"
t "ready is refused on the commit already reviewed" 1 move "$N" 01 ready
has "naming the commit" "still reports ${H1:0:10}"

fix_round() {
  # fix_round <label>: a new head, its report, the move to ready and to in-review; the sha is left in $H
  H="$(push_commit "$1")"
  report 01 READY "$H" pass
  pr_view OPEN "$H"
  (cd "$R" && "$UNIT" move "$N" 01 ready >/dev/null 2>&1 && "$UNIT" move "$N" 01 in-review >/dev/null 2>&1)
}
fix_round two
same "a fix round's new head reaches review" "$(cell 01 state) $(cell 01 head)" "in-review $H"
review 42 rework "$H"
t "a verdict of rework starts the second round" 0 move "$N" 01 fixing
has "counted as round 2" "round=2"
fix_round three
review 42 "after fixes" "$H"
t "the third round starts" 0 move "$N" 01 fixing
fix_round four
review 42 "after fixes" "$H"
t "a fourth fix round is refused" 1 move "$N" 01 fixing
has "naming the limit and the way out" "01 has used 3 fix rounds; move it to blocked"
t "the step is blocked with the open findings" 0 move "$N" 01 blocked --reason "F2 still open after three rounds"
t "a blocked step leaves only for the state it came from" 1 move "$N" 01 fixing --reason "owner: one more round"
has "naming that state" "01 is at blocked, which leaves only for: in-review"
t "the owner's word returns it to review" 0 move "$N" 01 in-review --reason "owner: one more round"
t "and allows a further fix round" 0 move "$N" 01 fixing
has "counted from one again" "round=1"
fix_round five
review 42 "merge as is" "$H" "" "fail, exit 1"
t "merge as is is refused when a criterion failed for the reviewer" 1 move "$N" 01 merge-ready
has "naming the criterion" "review-pr42.md: C1.2 reads fail, exit 1 on the reviewer's checkout"
printf 'VERDICT: merge as is\nCOMMIT: %s\nFINDINGS: none\n' "$H" > "$N/review-pr42.md"
t "merge as is is refused when the review ran no criterion" 1 move "$N" 01 merge-ready
has "naming the first one" "review-pr42.md: C1.1 reads nothing on the reviewer's checkout"
review 42 "merge as is" "$H"
pr_view OPEN "$H1"
t "merge-ready is refused when the pull request moved after the review" 1 move "$N" 01 merge-ready
has "naming both heads" "pull request 42 moved to ${H1:0:10} after the review of ${H:0:10}"
pr_view OPEN "$H"
t "a verdict of merge as is on the reviewed head moves the row" 0 move "$N" 01 merge-ready
has "and prints the line for the owner" "merge-ready 01 pr=42 head=${H:0:10} review=review-pr42.md findings=0 P1, 0 P2, 0 P3, 0 not fixed"
same "the verdict is in the row" "$(cell 01 verdict)" "merge as is"

printf '\nthe merge\n'
t "leaving merge-ready for a fix round is refused without a reason" 1 move "$N" 01 fixing
has "naming the flag" "leaving merge-ready for fixing needs --reason"
t "next waits on an open pull request" 0 next "$N"
has "at merge-ready" "wait 01 merge-ready pr=42"
pr_view OPEN "$H1"
t "next flags a pull request that moved after the verdict" 0 next "$N"
has "as stale" "stale 01 pr=42 moved to ${H1:0:10} after the verdict"
t "merged is refused while the pull request is open" 1 move "$N" 01 merged
has "quoting its state" "pull request 42 reads OPEN, not MERGED"
touch "$T/gh-fails"
t "a gh that fails is a refusal, not a move" 1 move "$N" 01 merged
has "with gh's own last line" "gh pr view 42 failed: HTTP 502: stub outage"
t "next still prints a line for every step when gh fails" 0 next "$N"
has "and says which step to check" "check 01 merge-ready: gh pr view 42 failed"
rm "$T/gh-fails"
printf 'not json\n' > "$T/gh-view.json"
t "an answer from gh that is not JSON is a refusal" 1 move "$N" 01 merged
has "saying so" "gh pr view 42 did not answer in JSON"
pr_view CLOSED "$H"
t "next flags a pull request closed without merging" 0 next "$N"
has "as a line to check" "check 01 merge-ready: pull request 42 was closed without merging"
pr_view MERGED "$H"
t "next reports the merge" 0 next "$N"
has "with the pull request" "merged 01 pr=42"
t "merged is refused while origin still holds the branch" 1 move "$N" 01 merged
has "naming the cleanup" "origin still holds feat/x-step; run the pr skill's Cleanup first"
git -C "$R" push -q origin --delete feat/x-step
t "merged is recorded once the branch is gone" 0 move "$N" 01 merged
t "next reads a merged step as done" 0 next "$N"
has "with its state" "done 01 merged"
t "a merged step moves nowhere" 1 move "$N" 01 fixing --reason "owner asked"

printf '\nparked and blocked\n'
t "parked is refused without the question" 1 move "$N" 02 parked
has "naming the flag" "needs --reason"
t "parked records the question" 0 move "$N" 02 parked --reason "cookie or store for the session token?"
t "next shows what the owner owes" 0 next "$N"
has "with the question" "owner 02 cookie or store for the session token?"
t "status prints the table" 0 status "$N"
has "with its header" "id  title"
has "with a merged row's short head" "${H:0:10}  merge as is  merged"
has "and what the owner owes" "owed by the owner, 02: cookie or store for the session token?"
t "leaving parked is refused without the answer" 1 move "$N" 02 scoped
t "a parked step leaves only for the state it was parked from" 1 move "$N" 02 running --reason "owner: B" --branch feat/y
has "naming that state" "02 is at parked, which leaves only for: scoped"
t "leaving parked records the answer" 0 move "$N" 02 scoped --reason "owner: B, the store"
same "the answer is logged with the move" "$(tail -1 "$N/decisions.tsv" | cut -f2,3,4,6)" "$(printf '02\tnote\towner: B, the store\tparked to scoped')"
t "a move to the state a row is at is refused" 1 move "$N" 02 scoped
t "a record of a new base takes no other flag" 1 move "$N" 02 scoped --base main --reason "x"
t "unless it records a new base" 0 move "$N" 02 scoped --base "feat/x-step@abc1234"
has "and says nothing moved" "kept 02 scoped base=feat/x-step@abc1234 session=-"
same "the base is in the row" "$(cell 02 base)" "feat/x-step@abc1234"
t "blocked is refused without what blocks the step" 1 move "$N" 03 blocked
t "blocked records what blocks the step" 0 move "$N" 03 blocked --reason "no machine can run the gate"
t "next reads a blocked step as done" 0 next "$N"
has "with the reason" "done 03 blocked: no machine can run the gate"
t "leaving blocked is refused without a reason" 1 move "$N" 03 scoped
t "leaving blocked records who asked" 0 move "$N" 03 scoped --reason "owner: run the gate on the CI host"

printf '\nlog\n'
t "log appends a decision" 0 log "$N" 02 fork "helper name: readClaims" --evidence "CONTEXT.md" --result A
same "as one row of six cells" "$(tail -1 "$N/decisions.tsv" | awk -F'\t' '{ print NF }')" "6"
t "a line break in a decision stays in its cell" 0 log "$N" - note "$(printf 'first line\nsecond\tcell')"
same "and the row is still one line of six cells" "$(tail -1 "$N/decisions.tsv" | awk -F'\t' '{ print NF, $4 }')" "6 first line second cell"
t "a decision for a step the ledger does not hold is refused" 1 log "$N" 09 fork "x"
t "a kind the ledger does not know is a usage error" 2 log "$N" 02 rumour "x"
t "a verdict row is not for log to write" 2 log "$N" 02 verdict "second reviewer" --result "after fixes"

printf '\na ledger from before the script\n'
O="$R/docs/plans/coordinate-old"
mkdir -p "$O"
printf 'id\ttitle\tsession\tbranch\tbase\tpr\thead\tverdict\tstate\n07\told step\t\tfeat/x\t\t\t\t\tparked\n' > "$O/units.tsv"
printf 'when\tunit\tkind\tdecision\tevidence\tresult\n' > "$O/decisions.tsv"
t "its nine columns are read" 0 status "$O"
has "with its row" "old step"
t "a held step with no row to say where it came from is refused" 1 move "$O" 07 running --reason "owner: A"
has "with the command that repairs it" "unit log <notes> 07 park"
t "the repair is one log row" 0 log "$O" 07 park "cookie or store?" --result running
t "after which the step leaves for that state" 0 move "$O" 07 running --reason "owner: A"
printf 'id\ttitle\tstate\n07\told\tscoped\n' > "$O/units.tsv"
t "a header the script did not write is refused" 1 next "$O"
has "naming the header" "does not start with the header this script writes"
printf '%s\n07\told\t\t\t\t\t\t\thalf-done\t\n' "$(head -1 "$N/units.tsv")" > "$O/units.tsv"
t "a state the script does not know is refused" 1 next "$O"
has "naming it" "holds step 07 at \`half-done\`"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
