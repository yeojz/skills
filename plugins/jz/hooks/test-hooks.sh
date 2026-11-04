#!/usr/bin/env bash
# Regression suite for the hook scripts. Builds a throwaway repo, feeds each
# hook the PreToolUse payload shape it will see in real use, and checks the
# exit code. Exit 0 allows the tool call, exit 2 denies it.
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HOOK_DIR
FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

git init -q "$FIXTURE"
mkdir -p "$FIXTURE/docs/plans" "$FIXTURE/.claude" "$FIXTURE/src"
echo plan > "$FIXTURE/docs/plans/x.md"
echo settings > "$FIXTURE/.claude/settings.json"
echo readme > "$FIXTURE/README.md"
echo code > "$FIXTURE/src/a.ts"
echo "not a claude directory" > "$FIXTURE/src/.claudette"

fail=0

check() {
  # check <json-quoted command> <label> <expected exit>
  printf '  %-52s' "$2"
  printf '{"tool_name":"Bash","tool_input":{"command":%s},"cwd":"%s"}' "$1" "$FIXTURE" \
    | "$HOOK_DIR/no-claude-artifacts.sh" >/dev/null 2>&1
  local got=$?
  if [ "$got" = "$3" ]; then
    echo "exit=$got PASS"
  else
    echo "exit=$got FAIL, expected $3"
    fail=1
  fi
}

printf '\nno-claude-artifacts.sh\n'

# The artifacts start untracked and unignored, the state an agent finds them in.
check '"ls -la"'                               "benign command"                0
check '"echo hello"'                           "benign echo"                   0
check '"git status"'                           "git status is read-only"       0
check '"git add -A"'                           "add -A sweeps a plan file"     2
check '"git add --all"'                        "add --all sweeps a plan file"  2
check '"git add . "'                           "add dot sweeps"                2
check '"git add README.md"'                    "add one clean path"            0
check '"git add docs/plans"'                   "add a forbidden directory"     2
check '"git add .claude/settings.json"'        "add a .claude file"            2
check '"git add docs"'                         "add the parent of a plan dir"  2
check '"git add *"'                            "add a bare glob"               2
check '"git add doc*"'                         "add a prefix glob"             2
check '"git add :/"'                           "add by pathspec magic"         2
check '"git -C docs add plans"'                "add behind git -C"             2
check '"cd docs && git add plans"'             "add behind a leading cd"       2
check '"git status\ngit add docs/plans"'       "add on a second line"          2
check '"nohup git add docs/plans"'             "add behind nohup"              2
check '"time git add .claude"'                 "add behind time"               2
check '"bash -c \"git add .claude\""'          "add inside bash -c"            2
check '"/usr/bin/git add .claude"'             "add through an absolute path"  2
check '"git stage docs/plans"'                 "stage a forbidden directory"   2
check '"git add docs/plans # sneaky comment"'  "add trailed by a comment"      2
check '"git commit -m \"has # hash\""'         "hash inside a commit message"  0
check '"git commit -m \"mentions ~/.claude\""' "commit message names .claude"  0
check '"git commit -m \"docs/plans in text\""' "commit message names a plan"   0
check '"git commit -m \"mentions ~/.claude and docs/plans and -u\""' \
                                               "commit message names all three" 0
check '"git add src/a.ts README.md"'           "add several clean paths"       0
check '"git add src && git commit -m x"'       "chained add of a clean path"   0
check '"git add ./src/a.ts"'                   "add a dot-slash clean path"    0
check '"git add src/.claudette"'               "add a path that only looks bad" 0
check '"git commit -m \"add -u flag docs\""'   "commit message contains -u"    0
check '"git -C . add -A"'                      "add -A behind a global option" 2
check '"command git add ."'                    "add dot behind command"        2
check '"git add -- src/a.ts"'                  "add a clean path after --"     0
check '"env -u X git add docs/plans"'           "add behind env -u with an operand" 2
check '"env --ignore-signal git add docs/plans"' "add behind bare --ignore-signal" 2
check '"time --output t.log git add docs/plans"' "add behind time --output FILE" 2

# Past the 64KB pipe buffer, where the old relevance check took SIGPIPE and
# failed open. Every path exists, so git resolves the list rather than rejecting it.
long_add="git add$(printf ' README.md%.0s' $(seq 1 5999)) .claude/settings.json"
check "\"$long_add\""                          "add with 6000 pathspecs"       2

printf 'docs/plans\n.claude\n' > "$FIXTURE/.gitignore"
check '"git add -A"'                           "add -A with plan dir ignored"  0
rm "$FIXTURE/.gitignore"

git -C "$FIXTURE" add README.md src/a.ts
check '"git commit -m \"chore: readme\""'      "commit, clean staging"         0

git -C "$FIXTURE" add -f docs/plans/x.md
check '"git commit -m \"chore: oops\""'        "commit, plan file staged"      2
check '"git commit -am \"chore: oops\""'       "commit -a, plan file staged"   2

# From here the plan file is tracked, so a commit can reach it without an add.
git -C "$FIXTURE" -c user.email=dev@example.com -c user.name=dev commit -q -m x
echo edited >> "$FIXTURE/docs/plans/x.md"
check '"git add -u"'                           "add -u with a modified plan"   2
check '"git add --update"'                     "add --update with the same"    2
check '"git commit -am x"'                     "commit -a over a modified plan" 2
check '"git commit -m x docs/plans/x.md"'      "commit with a plan pathspec"   2
check '"git add -u src/a.ts"'                  "add -u limited to a clean path" 0
check '"cd src && git add ."'                  "add dot in a clean subdirectory" 0

git -C "$FIXTURE" checkout -- docs/plans/x.md
check '"git commit -m x"'                      "commit with nothing to commit" 0

printf '\nload-project-rules.sh\n'
printf '  %-52s' "emits context when CLAUDE.md is present"
echo "instructions" > "$FIXTURE/CLAUDE.md"
out="$(printf '{"hook_event_name":"SessionStart","how":"startup","cwd":"%s"}' "$FIXTURE" \
  | "$HOOK_DIR/load-project-rules.sh" 2>/dev/null)"
if printf '%s' "$out" | python3 -c "
import json,sys
d=json.load(sys.stdin)
ctx=d['hookSpecificOutput']['additionalContext']
assert d['hookSpecificOutput']['hookEventName']=='SessionStart'
assert 'CLAUDE.md' in ctx
" 2>/dev/null; then
  echo "PASS"
else
  echo "FAIL"
  fail=1
fi

printf '  %-52s' "stays silent when there is nothing to load"
rm "$FIXTURE/CLAUDE.md"
out="$(printf '{"hook_event_name":"SessionStart","how":"startup","cwd":"%s"}' "$FIXTURE" \
  | "$HOOK_DIR/load-project-rules.sh" 2>/dev/null)"
if [ -z "$out" ]; then echo "PASS"; else echo "FAIL, expected no output"; fail=1; fi

printf '\nconfirm-remote-writes.sh\n'
ask() {
  # ask <json-quoted command> <label> <expected: ask|allow>
  printf '  %-52s' "$2"
  local out
  out="$(printf '{"tool_name":"Bash","tool_input":{"command":%s},"cwd":"%s"}' "$1" "$FIXTURE" \
    | "$HOOK_DIR/confirm-remote-writes.sh" 2>/dev/null)"
  local got=allow
  printf '%s' "$out" | grep -q '"permissionDecision": "ask"' && got=ask
  if [ "$got" = "$3" ]; then
    echo "$got PASS"
  else
    echo "$got FAIL, expected $3"
    fail=1
  fi
}

ask '"ls -la"'                                  "benign command"                 allow
ask '"git status"'                              "git status"                     allow
ask '"git push"'                                "plain push"                     allow
ask '"git push --set-upstream origin x"'        "push with upstream"             allow
ask '"gh pr view 5"'                            "gh pr view"                     allow
ask '"gh pr checks 5"'                          "gh pr checks"                   allow
ask '"echo gh pr create"'                       "gh pr create inside echo"       allow
ask '"gh pr create --draft --title t"'          "gh pr create --draft"           allow
ask '"gh pr create --title t --body b"'         "gh pr create without draft"     ask
ask '"gh pr create -df"'                        "draft inside a -df cluster"     allow
ask '"gh pr create -fd"'                        "draft at the end of a cluster"  allow
ask '"gh pr create -dt title"'                  "draft before a value letter"    allow
ask '"gh pr create -td"'                        "d as the value of -t"           ask
ask '"gh pr create --draft=false"'              "draft switched off"             ask
ask '"gh pr create -d --draft=false"'           "draft then switched off"        ask
ask '"gh pr create --fill --draft"'             "draft after fill"               allow
# Values of string options are not flags: gh and pflag consume them in order.
ask '"gh pr create --title '"'"'--draft'"'"' --body b"' "--draft as the value of --title" ask
ask '"gh pr create -t '"'"'-d'"'"' --body b"'          "-d as the value of -t"          ask
ask '"gh pr create --title=--draft --body b"'   "--draft attached to --title="    ask
ask '"gh pr create -t--draft --body b"'         "--draft attached to -t"          ask
ask '"gh pr create -t=-d --body b"'             "-d attached to -t="              ask
ask '"gh pr create --body -d --title t"'        "-d as the value of --body"       ask
ask '"gh pr create -b -d --title t"'            "-d as the value of -b"           ask
ask '"gh pr create -r --draft --title t"'       "--draft as the value of -r"      ask
ask '"gh pr create -R --draft --title t"'       "--draft as the value of -R"      ask
ask '"gh pr create --attach --draft --title t"' "--draft as the value of --attach" ask
ask '"gh pr create -Bd --title t"'              "d as the value of -B"            ask
ask '"gh pr create -fB main --draft"'           "draft after a cluster with a value" allow
ask '"gh pr create -R o/r -d --title t"'        "draft after -R with a value"     allow
ask '"gh pr create --title --draft -d"'         "draft after --draft as a title"  allow
ask '"gh pr create -d --title"'                 "missing value, gh rejects"       ask
# Every bool assignment pflag accepts, the last one winning.
ask '"gh pr create --draft -d=false --title t --body b"' "draft reset by -d=false"   ask
ask '"gh pr create -d --draft=0 --title t --body b"'     "draft reset by --draft=0"  ask
ask '"gh pr create --draft --draft=F"'          "draft reset by --draft=F"        ask
ask '"gh pr create -d -d=FALSE"'                "draft reset by -d=FALSE"         ask
ask '"gh pr create --draft -d=False"'           "draft reset by -d=False"         ask
ask '"gh pr create -d --draft=f"'               "draft reset by --draft=f"        ask
ask '"gh pr create --draft=false --draft=true"' "draft reset then set again"      allow
ask '"gh pr create -d=false -d"'                "-d after -d=false"               allow
ask '"gh pr create --draft=1"'                  "--draft=1"                       allow
ask '"gh pr create --draft=T"'                  "--draft=T"                       allow
ask '"gh pr create --draft=TRUE"'               "--draft=TRUE"                    allow
ask '"gh pr create --draft=True"'               "--draft=True"                    allow
ask '"gh pr create -d=t"'                       "-d=t"                            allow
ask '"gh pr create -d=true --title t"'          "-d=true before a title"          allow
ask '"gh pr create -fd=1"'                      "d=1 at the end of a cluster"     allow
ask '"gh pr create --draft=yes"'                "bool spelling gh rejects"        ask
ask '"gh pr create --draft="'                   "empty bool assignment"           ask
ask '"gh pr create --draft --unknown-option"'   "option the hook does not know"   ask
ask '"gh pr create --draft -z"'                 "short option the hook does not know" ask
# -- ends the options.
ask '"gh pr create -- --draft"'                 "--draft after --"                ask
ask '"gh pr create --draft -- --draft=false"'   "reset after -- is an operand"    allow
ask '"gh pr ready 5"'                           "gh pr ready"                    ask
ask '"gh pr ready"'                             "gh pr ready without a number"   ask
ask '"gh pr ready 5 --undo"'                    "gh pr ready --undo"             allow
ask '"gh pr ready 5 --undo --undo=false"'       "undo reset by --undo=false"     ask
ask '"gh pr ready 5 --undo=0"'                  "undo set to 0"                  ask
ask '"gh pr ready 5 --undo=F"'                  "undo set to F"                  ask
ask '"gh pr ready 5 --undo=false --undo"'       "undo reset then set again"      allow
ask '"gh pr ready --undo=true 5"'               "undo=true before the number"    allow
ask '"gh pr ready 5 --undo=1"'                  "undo=1"                         allow
ask '"gh pr ready 5 -R o/r --undo"'             "undo after -R with a value"     allow
ask '"gh pr ready 5 --repo --undo"'             "--undo as the value of --repo"  ask
ask '"gh pr ready -R --undo 5"'                 "--undo as the value of -R"      ask
ask '"gh pr ready -- --undo"'                   "--undo after --"                ask
ask '"gh pr ready --undo -- 5"'                 "undo then -- and the number"    allow
ask '"gh pr ready 5 --undo=maybe"'              "undo spelling gh rejects"       ask
ask '"gh pr edit 5 --title t"'                  "gh pr edit"                     allow
ask '"gh pr merge 5 --squash"'                  "gh pr merge is denied elsewhere" allow
ask '"git status && gh pr create -d"'           "draft create after &&"          allow
ask '"git status && gh pr create"'              "gh pr create after &&"          ask
ask '"git push --force"'                        "push --force"                   ask
ask '"git push -f origin x"'                    "push -f"                        ask
ask '"git push -fu origin x"'                   "push -fu cluster"               ask
ask '"git push --force-with-lease=x:abc"'       "lease pinned to a sha"          allow
ask '"git push --force-with-lease=x: origin x"'  "lease that expects no ref"      allow
ask '"git push --force-with-lease=x"'           "lease on a ref without a sha"   ask
ask '"git push --force-with-lease=x:abc --force-if-includes"' "pinned lease with if-includes" allow
ask '"git push --force-if-includes --force-with-lease=x:abc"' "if-includes before a pinned lease" allow
ask '"git push --force-w=x:abc origin x"'      "pinned lease by an abbreviation" allow
ask '"git push --force-w origin x"'            "bare lease by an abbreviation"  ask
ask '"git push --force-with-lease=x:abc origin +y"' "pinned lease beside a plus refspec" ask
ask '"git push --force-with-lease=x:abc -f"'    "pinned lease beside -f"         ask
ask '"git push origin -- +x"'                   "plus refspec after --"          ask
ask '"git push origin --force-with-lease"'      "push remote then lease"         ask
ask '"git push --force-if-includes"'            "push --force-if-includes"       ask
ask '"git push origin +main"'                   "push plus refspec"              ask
ask '"git -C . push -f"'                        "push -f behind git -C"          ask
ask '"nohup git push --force"'                  "push behind nohup"              ask
ask '"/usr/bin/gh pr ready 5"'                  "gh through an absolute path"    ask
ask '"git push origin \\\n  --force-with-lease"' "push with a line continuation"  ask
ask '"gh pr create \\\n  --draft \\\n  --title t"'  "draft create across lines"      allow
ask '"gh pr create \\\n  --title t"'          "gh pr create across lines"      ask
ask '"timeout 30 git push --force"'              "push behind timeout with a duration" ask
ask '"bash -c \"git push --force\""'             "push inside bash -c"            ask
ask '"git push origin main # --force in a comment"' "force only in a trailing comment" allow
ask '"echo '"'"'example;git push --force origin main'"'"'"' "separator inside quotes"       allow
ask '"git log --oneline\ngit push -f"'           "push -f on a second line"       ask
ask '"git push --force-with-lease \\\n origin x"' "lease then a continuation"     ask
ask '"env -u GITHUB_TOKEN gh pr create --draft"'  "draft create behind env -u"      allow
ask '"env -u GITHUB_TOKEN gh pr create"'          "gh behind env -u with an operand" ask
ask '"timeout --signal TERM 30 git push --force"' "push behind timeout --signal"   ask
ask '"sudo -u root git push -f"'                 "push behind sudo -u"            ask
ask '"nice -n 5 git push --force"'               "push behind nice -n"            ask
ask '"env -- gh pr ready 5"'                     "gh after a double dash"         ask
ask '"timeout -s TERM 30 git push"'              "plain push behind timeout -s"   allow
ask '"env --default-signal git push --force"'    "push behind bare --default-signal" ask
ask '"env --ignore-signal git push --force"'     "push behind bare --ignore-signal" ask
ask '"env --block-signal gh pr create"'          "gh behind bare --block-signal"  ask
ask '"env --default-signal=TERM git push -f"'    "push behind --default-signal=SIG" ask
ask '"xargs -i git push --force"'                "push behind xargs -i"           ask
ask '"xargs -l git push -f"'                     "push behind xargs -l"           ask
ask '"xargs --eof git push --force"'             "push behind bare --eof"         ask
ask '"xargs --max-lines git push --force"'       "push behind bare --max-lines"   ask
ask '"xargs --eof=END git push -f"'              "push behind --eof=END"          ask
ask '"xargs --max-lines=2 git push"'             "plain push behind --max-lines=2" allow
ask '"xargs -E END git push --force"'            "push behind xargs -E with a value" ask
ask '"xargs -L 2 git push"'                      "plain push behind xargs -L"     allow
ask '"/usr/bin/time --output result.log git push --force"' "push behind time --output FILE" ask
ask '"time --output-file result.log git push -f"' "push behind time --output-file FILE" ask
ask '"time --out result.log git push --force"'   "push behind an abbreviated long option" ask
ask '"time --output result.log git push"'        "plain push behind time --output" allow
ask '"env --uns GITHUB_TOKEN gh pr create"'      "gh behind abbreviated env --unset" ask
ask '"time --output=result.log git push"'        "plain push behind attached --output=" allow

printf '\nload-house-rules.sh\n'
printf '  %-52s' "emits every rule file as context"
out="$(printf '{"hook_event_name":"SessionStart","how":"startup","cwd":"%s"}' "$FIXTURE" \
  | "$HOOK_DIR/load-house-rules.sh" 2>/dev/null)"
if printf '%s' "$out" | python3 -c "
import json,sys,glob,os
d=json.load(sys.stdin)
ctx=d['hookSpecificOutput']['additionalContext']
assert d['hookSpecificOutput']['hookEventName']=='SessionStart'
assert 'House rules' in ctx
rules=sorted(glob.glob(os.path.join(os.environ['HOOK_DIR'],'..','rules','*.md')))
assert rules, 'no rule files found'
for r in rules:
    first=open(r,encoding='utf-8').readline().strip()
    assert first in ctx, first+' missing'
" 2>/dev/null; then
  echo "PASS"
else
  echo "FAIL"
  fail=1
fi

printf '\nrebase-not-merge.sh\n'
# The merge cases are judged from a feature branch, since git init leaves the
# fixture on a default-branch name; the default branch's own fast-forward is
# tested at the end of this block.
git -C "$FIXTURE" checkout -q -b topic
deny() {
  # deny <json-quoted command> <label> <expected exit> <hook>
  printf '  %-52s' "$2"
  printf '{"tool_name":"Bash","tool_input":{"command":%s},"cwd":"%s"}' "$1" "$FIXTURE" \
    | "$HOOK_DIR/$4" >/dev/null 2>&1
  local got=$?
  if [ "$got" = "$3" ]; then
    echo "exit=$got PASS"
  else
    echo "exit=$got FAIL, expected $3"
    fail=1
  fi
}

# The fixture has no remote, so the hook falls back to the common default names.
deny '"git status"'                              "git status"                     0 rebase-not-merge.sh
deny '"git merge feature-x"'                     "merge a feature branch"         0 rebase-not-merge.sh
deny '"git merge --abort"'                       "merge --abort"                  0 rebase-not-merge.sh
deny '"git rebase origin/main"'                  "rebase onto main"               0 rebase-not-merge.sh
deny '"git pull --rebase origin main"'           "pull --rebase main"             0 rebase-not-merge.sh
deny '"git pull"'                                "plain pull of the upstream"     0 rebase-not-merge.sh
deny '"git merge main"'                          "merge main"                     2 rebase-not-merge.sh
deny '"git merge origin/main"'                   "merge origin/main"              2 rebase-not-merge.sh
deny '"git merge --no-ff master"'                "merge --no-ff master"           2 rebase-not-merge.sh
deny '"git pull origin main"'                    "pull main without rebase"       2 rebase-not-merge.sh
deny '"git fetch && git merge origin/main"'      "merge main after &&"            2 rebase-not-merge.sh
deny '"git -C . merge main"'                     "merge main behind git -C"       2 rebase-not-merge.sh
deny '"git merge \\\n  origin/main"'             "merge main after a continuation" 2 rebase-not-merge.sh
deny '"timeout 30 git merge main"'               "merge main behind timeout"      2 rebase-not-merge.sh
deny '"echo '"'"'git merge main'"'"'"'            "merge main inside quotes"       0 rebase-not-merge.sh
deny '"git merge feature # not main"'            "main only in a comment"         0 rebase-not-merge.sh
deny '"git pull --rebase=false origin main"'     "pull main with --rebase=false"  2 rebase-not-merge.sh
deny '"git pull --rebase --no-rebase origin main"' "pull main, --no-rebase last"   2 rebase-not-merge.sh
deny '"git pull --no-rebase --rebase origin main"' "pull main, --rebase last"      0 rebase-not-merge.sh
deny '"git pull --rebase=merges origin main"'    "pull main with --rebase=merges" 0 rebase-not-merge.sh
git -C "$FIXTURE" config pull.rebase true
deny '"git pull origin main"'                    "plain pull with pull.rebase=true" 0 rebase-not-merge.sh
deny '"git -c pull.rebase=false pull origin main"' "pull main, -c false over config true" 2 rebase-not-merge.sh
deny '"git -c pull.rebase=false pull --rebase origin main"' "pull main, --rebase over -c false" 0 rebase-not-merge.sh
PULL_SETTING=false deny '"git --config-env pull.rebase=PULL_SETTING pull origin main"' "pull main, --config-env false over true" 2 rebase-not-merge.sh
git -C "$FIXTURE" config --unset pull.rebase
deny '"git -c pull.rebase=true pull origin main"' "pull main, -c true over unset config" 0 rebase-not-merge.sh
deny '"git -c pull.rebase pull origin main"'     "pull main, bare -c pull.rebase"  0 rebase-not-merge.sh
PULL_SETTING=true deny '"git --config-env=pull.rebase=PULL_SETTING pull origin main"' "pull main, --config-env true over unset" 0 rebase-not-merge.sh
# branch.<current>.rebase outranks pull.rebase, as it does for git pull itself.
FIXTURE_BRANCH="$(git -C "$FIXTURE" symbolic-ref --short HEAD)"
git -C "$FIXTURE" config pull.rebase true
git -C "$FIXTURE" config "branch.$FIXTURE_BRANCH.rebase" false
deny '"git pull origin main"'                    "pull main, branch false over pull true" 2 rebase-not-merge.sh
deny '"git pull --rebase origin main"'           "pull main, --rebase over branch false" 0 rebase-not-merge.sh
deny "\"git -c branch.$FIXTURE_BRANCH.rebase=true pull origin main\"" "pull main, -c branch true over stored false" 0 rebase-not-merge.sh
git -C "$FIXTURE" config pull.rebase false
git -C "$FIXTURE" config "branch.$FIXTURE_BRANCH.rebase" true
deny '"git pull origin main"'                    "pull main, branch true over pull false" 0 rebase-not-merge.sh
deny '"git pull --no-rebase origin main"'        "pull main, --no-rebase over branch true" 2 rebase-not-merge.sh
git -C "$FIXTURE" config --unset pull.rebase
git -C "$FIXTURE" config --unset "branch.$FIXTURE_BRANCH.rebase"

# A child repository whose default branch is stable, inside a fixture whose
# default branch is main. Each command resolves the default where it runs.
git init -q "$FIXTURE/child"
echo c > "$FIXTURE/child/c.txt"
git -C "$FIXTURE/child" add c.txt
git -C "$FIXTURE/child" -c user.email=dev@example.com -c user.name=dev commit -q -m c
git -C "$FIXTURE/child" update-ref refs/remotes/origin/stable HEAD
git -C "$FIXTURE/child" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/stable
git -C "$FIXTURE" update-ref refs/remotes/origin/main HEAD
git -C "$FIXTURE" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
deny '"git merge origin/stable"'                 "merge stable in the main repo"  0 rebase-not-merge.sh
deny '"git -C child merge origin/stable"'        "merge stable behind -C child"   2 rebase-not-merge.sh
deny '"cd child && git merge origin/stable"'     "merge stable after cd child"    2 rebase-not-merge.sh
deny '"git -C child merge origin/main"'          "merge main inside child"        0 rebase-not-merge.sh
# A cd is scoped to its shell: a subshell restores the directory at `)`, a
# pipeline element or a background job moves nothing, a brace group persists.
deny '"(cd child && git status); git merge origin/main"' "merge main after a subshell cd" 2 rebase-not-merge.sh
deny '"(cd child && git merge origin/stable)"'   "merge stable inside a subshell" 2 rebase-not-merge.sh
deny '"echo $(cd child && git status); git merge origin/main"' "merge main after a substitution cd" 2 rebase-not-merge.sh
deny '"cd child | git merge origin/main"'        "cd as a pipeline element"       2 rebase-not-merge.sh
deny '"echo x | cd child; git merge origin/main"' "cd after a pipe"                2 rebase-not-merge.sh
deny '"cd child & git merge origin/main"'        "cd as a background job"         2 rebase-not-merge.sh
deny '"cd child && git merge origin/stable | cat"' "merge stable piped after cd"   2 rebase-not-merge.sh
deny '"{ cd child; git merge origin/stable; }"'  "merge stable after cd in braces" 2 rebase-not-merge.sh
deny '"{ cd child; git status; }; git merge origin/stable"' "merge stable after a brace group" 2 rebase-not-merge.sh
# On the default branch itself, merging or pulling the default is the
# fast-forward of that checkout after a merge on GitHub, which the `pr`
# skill's Cleanup section runs. Any other branch, default-named or not, is still denied.
git -C "$FIXTURE" checkout -q -b main 2>/dev/null || git -C "$FIXTURE" checkout -q main
deny '"git merge --ff-only origin/main"'         "ff-only origin/main while on main" 0 rebase-not-merge.sh
deny '"git merge origin/main"'                   "merge origin/main while on main" 0 rebase-not-merge.sh
deny '"git pull origin main"'                    "pull main while on main"        0 rebase-not-merge.sh
deny '"git fetch origin main && git merge --ff-only origin/main"' "fetch then ff-only while on main" 0 rebase-not-merge.sh
deny '"git -C child merge origin/stable"'        "merge stable in child, not on stable" 2 rebase-not-merge.sh
# A checkout or switch earlier on the line moves the branch before the merge
# runs, so the branch the hook reads is stale and the exception is withheld.
deny '"git switch topic && git merge origin/main"' "switch then merge main, on main" 2 rebase-not-merge.sh
deny '"git checkout topic && git pull --no-rebase origin main"' "checkout then pull main, on main" 2 rebase-not-merge.sh
deny '"git checkout -b fresh && git merge main"'  "checkout -b then merge main, on main" 2 rebase-not-merge.sh
deny '"git switch -c fresh; git merge --ff-only origin/main"' "switch -c then ff-only, on main" 2 rebase-not-merge.sh
deny '"git -C child checkout -b x && git merge --ff-only origin/main"' "switch in another repo keeps the exception" 0 rebase-not-merge.sh
deny '"git merge --ff-only origin/main && git switch topic"' "ff-only then switch, on main" 0 rebase-not-merge.sh
# Without origin/HEAD every common default name counts, and a branch with one
# of those names merging a different one is still a merge of the default.
git -C "$FIXTURE" symbolic-ref --delete refs/remotes/origin/HEAD
git -C "$FIXTURE" checkout -q -b develop
deny '"git merge main"'                          "merge main while on develop"    2 rebase-not-merge.sh
deny '"git merge develop"'                       "merge develop while on develop" 0 rebase-not-merge.sh
git -C "$FIXTURE" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
git -C "$FIXTURE" checkout -q topic
deny '"git merge --ff-only origin/main"'         "ff-only origin/main while on topic" 2 rebase-not-merge.sh

printf '\nrequire-pr-skill.sh\n'
# Transcript fixtures in the shape Claude Code writes: a Skill call is an
# assistant tool_use block, a typed slash command is a user turn.
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Skill","input":{"skill":"jz:verify"}}]}}' \
  '{"type":"user","message":{"content":"please open the pr when the gate is green"}}' \
  '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"git status"}}]}}' > "$FIXTURE/no-pr.jsonl"
# A Skill call is a tool_use with an id; its result answers with the same id,
# is_error null on success and true when the load failed.
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_1","name":"Skill","input":{"skill":"jz:pr"}}]}}' \
  '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_1","is_error":null,"content":"Launching skill: jz:pr"}]}}' > "$FIXTURE/skill-pr.jsonl"
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_1","name":"Skill","input":{"skill":"house:pr"}}]}}' \
  '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_1","content":"Launching skill: house:pr"}]}}' > "$FIXTURE/other-plugin-pr.jsonl"
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_1","name":"Skill","input":{"skill":"jz:pr"}}]}}' \
  '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_1","is_error":true,"content":"Unknown skill: jz:pr"}]}}' > "$FIXTURE/skill-pr-failed.jsonl"
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_1","name":"Skill","input":{"skill":"jz:pr"}}]}}' > "$FIXTURE/skill-pr-pending.jsonl"
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_1","name":"Skill","input":{"skill":"jz:pr"}}]}}' \
  '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_9","content":"Launching skill: jz:verify"}]}}' > "$FIXTURE/skill-pr-other-result.jsonl"
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_1","name":"Skill","input":{"skill":"jz:pr"}}]}}' \
  '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_1","is_error":true,"content":"Unknown skill: jz:pr"}]}}' \
  '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_2","name":"Skill","input":{"skill":"jz:pr"}}]}}' \
  '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_2","content":"Launching skill: jz:pr"}]}}' > "$FIXTURE/skill-pr-retry.jsonl"
printf '%s\n' '{"type":"user","message":{"content":"<command-message>jz:pr</command-message>\n<command-name>/jz:pr</command-name>"}}' > "$FIXTURE/typed-pr.jsonl"
printf '%s\n' '{"type":"user","message":{"content":[{"type":"text","text":"<command-name>/jz:pr</command-name>"}]}}' > "$FIXTURE/typed-pr-blocks.jsonl"
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Skill","input":{"skill":"jz:pr-desc"}}]}}' > "$FIXTURE/near-miss.jsonl"
# A typed command for a skill that is not installed arrives as plain text,
# with no command-name tag and no skill body after it.
printf '%s\n' '{"type":"user","message":{"content":"/jz:pr"}}' > "$FIXTURE/typed-pr-missing.jsonl"
printf 'not json, mentions pr\n' > "$FIXTURE/broken.jsonl"
gate() {
  # gate <json-quoted command> <label> <expected exit> <transcript path or ->
  printf '  %-52s' "$2"
  if [ "$4" = "-" ]; then
    printf '{"tool_name":"Bash","tool_input":{"command":%s},"cwd":"%s"}' "$1" "$FIXTURE"
  else
    printf '{"tool_name":"Bash","tool_input":{"command":%s},"cwd":"%s","transcript_path":"%s"}' "$1" "$FIXTURE" "$4"
  fi | "$HOOK_DIR/require-pr-skill.sh" >/dev/null 2>&1
  local got=$?
  if [ "$got" = "$3" ]; then
    echo "exit=$got PASS"
  else
    echo "exit=$got FAIL, expected $3"
    fail=1
  fi
}
gate '"git status"'                              "git status without the skill"   0 "$FIXTURE/no-pr.jsonl"
gate '"git commit -m x"'                         "commit, no transcript path"     0 -
gate '"git commit -m x"'                         "commit, transcript file absent" 0 "$FIXTURE/absent.jsonl"
gate '"git commit -m x"'                         "commit without the skill"       2 "$FIXTURE/no-pr.jsonl"
gate '"git push -u origin HEAD"'                 "push without the skill"         2 "$FIXTURE/no-pr.jsonl"
gate '"gh pr create --draft --title t --body b"' "draft PR without the skill"     2 "$FIXTURE/no-pr.jsonl"
gate '"gh -R o/r pr create --draft"'             "PR create behind a global option" 2 "$FIXTURE/no-pr.jsonl"
gate '"gh pr view 42"'                           "pr view without the skill"      0 "$FIXTURE/no-pr.jsonl"
gate '"git add a && git -C sub commit -m x"'     "commit behind git -C after &&"  2 "$FIXTURE/no-pr.jsonl"
gate '"echo '"'"'git commit'"'"'"'                "commit inside quotes"           0 "$FIXTURE/no-pr.jsonl"
gate '"git commit -m \"unbalanced"'              "unparseable line naming commit" 2 "$FIXTURE/no-pr.jsonl"
gate '"git commit -m x"'                         "commit after Skill jz:pr"     0 "$FIXTURE/skill-pr.jsonl"
gate '"git push origin topic"'                   "push after Skill jz:pr"       0 "$FIXTURE/skill-pr.jsonl"
gate '"gh pr create --draft"'                    "PR create after Skill jz:pr"  0 "$FIXTURE/skill-pr.jsonl"
gate '"git commit -m x"'                         "commit after Skill house:pr"  0 "$FIXTURE/other-plugin-pr.jsonl"
gate '"git commit -m x"'                         "Skill call whose result is an error" 2 "$FIXTURE/skill-pr-failed.jsonl"
gate '"git commit -m x"'                         "Skill call with no result yet"  2 "$FIXTURE/skill-pr-pending.jsonl"
gate '"git commit -m x"'                         "result that answers another call" 2 "$FIXTURE/skill-pr-other-result.jsonl"
gate '"git commit -m x"'                         "failed call, then a successful one" 0 "$FIXTURE/skill-pr-retry.jsonl"
gate '"git commit -m x"'                         "commit after a typed /jz:pr"  0 "$FIXTURE/typed-pr.jsonl"
gate '"git commit -m x"'                         "typed /jz:pr in text blocks"  0 "$FIXTURE/typed-pr-blocks.jsonl"
gate '"git commit -m x"'                         "typed /jz:pr as plain text, not installed" 2 "$FIXTURE/typed-pr-missing.jsonl"
gate '"git commit -m x"'                         "Skill jz:pr-desc is not pr"  2 "$FIXTURE/near-miss.jsonl"
gate '"git commit -m x"'                         "a transcript that is not JSON"  2 "$FIXTURE/broken.jsonl"
printf '  %-52s' "the reason names Skill jz:pr"
reason="$(printf '{"tool_name":"Bash","tool_input":{"command":"git commit -m x"},"cwd":"%s","transcript_path":"%s"}' "$FIXTURE" "$FIXTURE/no-pr.jsonl" \
    | "$HOOK_DIR/require-pr-skill.sh" 2>&1 >/dev/null)"
if printf '%s' "$reason" | grep -q 'jz:pr'; then
  echo "PASS"
else
  echo "FAIL"
  fail=1
fi

printf '\nno-restricted-words.sh\n'
printf '## Restricted words\n\n- oracle\n- predecessor\n' > "$FIXTURE/AGENTS.md"
printf 'Summary with a tick \342\234\223 mark\n' > "$FIXTURE/body-emoji.md"
printf 'Plain summary.\n\nCo-Authored-By: Claude <noreply@example.com>\n' > "$FIXTURE/body-trailer.md"
printf 'Plain summary that mentions Claude Code and Codex as products.\n' > "$FIXTURE/body-clean.md"
printf '{"body":"see claude://claude.ai/epitaxy/local_abc"}\n' > "$FIXTURE/input-link.json"

deny '"git commit -m \"fix(core): handle empty input\""'          "plain commit message"           0 no-restricted-words.sh
deny '"git commit -m \"docs: mention Claude Code and Codex\""'   "product names are allowed"      0 no-restricted-words.sh
deny '"git commit -m \"feat: oracles plural is a different word\""' "restricted word inside a longer word" 0 no-restricted-words.sh
deny '"gh pr view 5"'                                             "gh pr view"                     0 no-restricted-words.sh
deny '"gh pr create --draft --body-file body-clean.md"'           "clean body file"                0 no-restricted-words.sh
deny '"git commit -m \"feat: done ✅\""'                "commit message with an emoji"   2 no-restricted-words.sh
deny '"git commit -m \"feat: x\" -m \"Co-Authored-By: Claude <a@example.com>\""' "attribution trailer in a commit" 2 no-restricted-words.sh
deny '"git commit -m \"feat: tuned for claude-opus-5-5\""'        "model slug in a commit"         2 no-restricted-words.sh
deny '"gh pr create --title t --body \"the oracle says\""'        "restricted word in a PR body"   2 no-restricted-words.sh
deny '"gh pr comment 5 --body \"matches the predecessor repo\""'  "restricted word in a comment"   2 no-restricted-words.sh
deny '"gh pr create --draft --body-file body-emoji.md"'           "emoji in a body file"           2 no-restricted-words.sh
deny '"gh pr create --draft -F body-trailer.md"'                  "trailer in a body file via -F"  2 no-restricted-words.sh
deny '"gh api repos/o/r/pulls/5/comments -f body=\"an Oracle again\""' "restricted word via gh api -f" 2 no-restricted-words.sh
deny '"gh api --method POST repos/o/r/issues/5/comments --input input-link.json"' "session link via gh api --input" 2 no-restricted-words.sh
deny '"gh pr review 5 --comment --body \"ok 👍\""'  "emoji in a review"              2 no-restricted-words.sh
deny '"gh pr comment 5 \\\n  --body \"the oracle\""'   "restricted word after a continuation" 2 no-restricted-words.sh
deny '"echo '"'"'git commit -m oracle'"'"'"'      "restricted word in echoed text" 0 no-restricted-words.sh
deny '"git commit -am \"feat: oracle\""'          "restricted word via -am cluster" 2 no-restricted-words.sh
deny '"git commit -sam \"feat: oracle\""'         "restricted word via -sam cluster" 2 no-restricted-words.sh
deny '"git commit -a -m \"feat: fine\""'          "clean message after -a"         0 no-restricted-words.sh
deny '"git commit -m \"feat: x\" --trailer \"Co-authored-by: Claude <a@example.com>\""' "attribution via --trailer" 2 no-restricted-words.sh
deny '"git commit -m \"feat: x\" --trailer=Reviewed-by:dev"' "plain trailer"      0 no-restricted-words.sh
python3 -c "import json;json.dump({'body':'Looks good '+chr(0x1f44d)},open('$FIXTURE/input-escaped.json','w'))"
python3 -c "import json;json.dump({'body':'ok\n\nCo-Authored-By: Claude <a@example.com>'},open('$FIXTURE/input-trailer.json','w'))"
python3 -c "import json;json.dump({'event':'COMMENT','body':'fine','comments':[{'path':'a','body':'the oracle'}]},open('$FIXTURE/input-nested.json','w'))"
python3 -c "import json;json.dump({'body':'all fine here'},open('$FIXTURE/input-clean.json','w'))"
deny '"gh api repos/o/r/issues/1/comments --input input-escaped.json"' "escaped emoji in JSON input" 2 no-restricted-words.sh
deny '"gh api repos/o/r/issues/1/comments --input input-trailer.json"' "trailer in JSON input"     2 no-restricted-words.sh
deny '"gh api repos/o/r/pulls/1/reviews --input input-nested.json"'    "restricted word in a nested review comment" 2 no-restricted-words.sh
deny '"gh api repos/o/r/issues/1/comments --input input-clean.json"'   "clean JSON input"          0 no-restricted-words.sh
mkdir -p "$FIXTURE/child"
printf '## Restricted words\n\n- secretword\n' > "$FIXTURE/child/AGENTS.md"
printf 'mentions secretword here\n' > "$FIXTURE/child/body.md"
deny '"cd child && gh pr create --body-file body.md"' "body file resolved after cd child" 2 no-restricted-words.sh
deny '"git -C child commit -m \"feat: secretword\""' "child policy behind -C child"    2 no-restricted-words.sh
deny '"git commit -m \"feat: secretword\""'       "parent policy does not restrict it" 0 no-restricted-words.sh
deny '"cd child && git commit -m \"feat: oracle\""' "parent policy not applied in child" 0 no-restricted-words.sh
deny '"(cd child && git status); git commit -m \"feat: oracle\""' "parent policy after a subshell cd" 2 no-restricted-words.sh
deny '"(cd child && git commit -m \"feat: secretword\")"' "child policy inside a subshell" 2 no-restricted-words.sh
# src/ is an ordinary directory of the fixture repository: the root policy applies.
printf 'the oracle\n' > "$FIXTURE/src/body.md"
mkdir -p "$FIXTURE/src/deep"
printf '## Restricted words\n\n- deepword\n' > "$FIXTURE/src/AGENTS.md"
deny '"git -C src commit -am \"feat: oracle\""'  "root policy behind -C src"       2 no-restricted-words.sh
deny '"cd src && git commit -am \"feat: oracle\""' "root policy after cd src"      2 no-restricted-words.sh
deny '"cd src && gh pr create --body-file body.md"' "body file in src, root policy" 2 no-restricted-words.sh
deny '"cd src/deep && git commit -m \"feat: deepword\""' "ancestor policy below the root" 2 no-restricted-words.sh
deny '"cd src/deep && git commit -m \"feat: oracle\""' "root policy two levels down"  2 no-restricted-words.sh
deny '"git commit -m \"feat: deepword\""'        "src policy not applied at the root" 0 no-restricted-words.sh
deny '"cd src && git commit -m \"feat: fine\""'  "clean message in src"           0 no-restricted-words.sh
rm -f "$FIXTURE"/input-*.json "$FIXTURE/child/AGENTS.md" "$FIXTURE/child/body.md" "$FIXTURE/src/body.md" "$FIXTURE/src/AGENTS.md"
rm -f "$FIXTURE/AGENTS.md" "$FIXTURE"/body-*.md "$FIXTURE/input-link.json"

printf '\nscan-secrets-before-push.sh\n'
scan() {
  # scan <json-quoted command> <label> <expected: ask|allow> [cwd]
  printf '  %-52s' "$2"
  local out
  out="$(printf '{"tool_name":"Bash","tool_input":{"command":%s},"cwd":"%s"}' "$1" "${4:-$PUSHREPO}" \
    | "$HOOK_DIR/scan-secrets-before-push.sh" 2>/dev/null)"
  local got=allow
  printf '%s' "$out" | grep -q '"permissionDecision": "ask"' && got=ask
  if [ "$got" = "$3" ]; then
    echo "$got PASS"
  else
    echo "$got FAIL, expected $3"
    fail=1
  fi
}

# A repository with a bare remote, so "published" means reachable from a
# remote-tracking ref. The fake token is random so an installed scanner's
# entropy check and the builtin shape both recognise it; the suite passes with
# betterleaks, with gitleaks or with neither on PATH.
PUSHREPO="$FIXTURE/pushrepo"
git init -q -b main "$PUSHREPO"
git init -q --bare "$FIXTURE/remote.git"
git -C "$PUSHREPO" remote add origin "$FIXTURE/remote.git"
pushgit() { git -C "$PUSHREPO" -c user.email=dev@example.com -c user.name=dev "$@"; }
FAKE_TOKEN="ghp_$(python3 -c 'import secrets,string;print("".join(secrets.choice(string.ascii_letters+string.digits) for _ in range(36)))')"
echo 'export const name = "example";' > "$PUSHREPO/index.ts"
pushgit add index.ts && pushgit commit -q -m 'feat: start' && pushgit push -q -u origin main
scan '"git push origin main"'                   "nothing unpublished"            allow
printf 'const token = "%s";\n' "$FAKE_TOKEN" > "$PUSHREPO/client.ts"
pushgit add client.ts && pushgit commit -q -m 'feat: add client'
scan '"git push origin main"'                   "token in an unpublished commit" ask
scan '"git push"'                               "bare push of the same head"     ask
scan '"git push --force origin main"'           "forced push is scanned too"     ask
scan '"git push -u origin main:main"'           "refspec with source and target" ask
scan '"git -C pushrepo push origin main"'       "push behind git -C"             ask "$FIXTURE"
scan '"cd pushrepo && git push"'                "push after cd"                  ask "$FIXTURE"
scan '"echo git push origin main"'              "push inside echo"               allow
scan '"git push origin --delete main"'          "branch deletion publishes nothing" allow
scan '"git push origin :main"'                  "empty-source refspec"           allow
pushgit push -q origin main
scan '"git push origin main"'                   "token already on the remote"    allow
echo 'export const more = 1;' >> "$PUSHREPO/index.ts"
pushgit commit -q -am 'feat: more'
scan '"git push"'                               "clean commit after the leak"    allow
printf 'const key = "%s"; // betterleaks:allow\n' "$FAKE_TOKEN" > "$PUSHREPO/fixture.ts"
pushgit add fixture.ts && pushgit commit -q -m 'test: add fixture'
scan '"git push"'                               "allow comment on the line"      allow
pushgit commit -q --allow-empty -m "chore: rotate $FAKE_TOKEN"
scan '"git push"'                               "token in a commit message"      ask
pushgit push -q origin main
scan '"git push"'                               "everything published again"     allow
# Only the destination's refs count as published: a commit on another remote
# is not public at origin.
git init -q --bare "$FIXTURE/archive.git"
pushgit remote add archive "$FIXTURE/archive.git"
printf 'const second = "%s";\n' "$FAKE_TOKEN" > "$PUSHREPO/second.ts"
pushgit add second.ts && pushgit commit -q -m 'feat: second'
pushgit push -q archive main
scan '"git push origin main"'                   "token only on another remote"   ask
scan '"git push archive main"'                  "same token already at the target" allow
scan '"git push --dry-run origin main"'         "a dry run publishes nothing"    allow
scan '"git push -n origin main"'                "-n publishes nothing"           allow
pushgit push -q origin main
# A merge commit's own diff carries what the resolution introduced.
pushgit checkout -q -b side
printf 'side\n' > "$PUSHREPO/value" && pushgit add value && pushgit commit -q -m 'feat: side value'
pushgit checkout -q main
printf 'main\n' > "$PUSHREPO/value" && pushgit add value && pushgit commit -q -m 'feat: main value'
pushgit push -q origin main side
pushgit merge -q side >/dev/null 2>&1 || true
printf 'const merged = "%s";\n' "$FAKE_TOKEN" > "$PUSHREPO/value"
pushgit add value && pushgit commit -q --no-edit
scan '"git push origin main"'                   "token in a merge resolution"    ask
pushgit push -q origin main
scan '"git push origin main"'                   "merge published"                allow
# Git decides which refs a push publishes: configured refspecs, push.default
# and wildcards select branches other than HEAD.
pushgit branch -q leaky
pushgit push -q origin leaky
pushgit checkout -q leaky
printf 'const leak = "%s";\n' "$FAKE_TOKEN" > "$PUSHREPO/leaky.ts"
pushgit add leaky.ts && pushgit commit -q -m 'feat: leaky'
pushgit checkout -q main
scan '"git push origin"'                        "clean HEAD with the default refspec" allow
pushgit config remote.origin.push refs/heads/leaky:refs/heads/leaky
scan '"git push origin"'                        "configured refspec publishes leaky" ask
pushgit config --unset remote.origin.push
pushgit config push.default matching
scan '"git push origin"'                        "push.default matching publishes leaky" ask
pushgit config --unset push.default
scan '"git push origin refs/heads/*:refs/heads/*"' "wildcard refspec publishes leaky" ask
scan '"git push --all origin"'                  "--all publishes leaky"          ask
scan '"git push origin leaky"'                  "leaky named directly"           ask
# The preview is a dry run whatever the caller asked for, and running the hook
# must never move the remote.
before_tip="$(git -C "$FIXTURE/remote.git" rev-parse refs/heads/leaky)"
scan '"git push --no-dry-run origin leaky"'     "--no-dry-run cannot make the preview push" ask
scan '"git push -n --no-dry-run origin leaky"'  "-n reset by a later --no-dry-run" ask
scan '"git push --no-dry-run -n origin leaky"'  "--no-dry-run reset by a later -n" allow
scan '"git push --dry origin leaky"'            "abbreviated --dry-run is a dry run" allow
scan '"git push --no-dry -n origin leaky"'      "abbreviated --no-dry-run reset by -n" allow
scan '"git push -o n origin leaky"'             "n as the value of -o"           ask
git -C "$FIXTURE/remote.git" config receive.advertisePushOptions true
scan '"git push -o -- origin leaky"'            "-- as the value of -o"          ask
scan '"git push -o -n origin leaky"'            "-n as the value of -o"          ask
scan '"git push --push-option=-n origin leaky"' "-n attached to --push-option"   ask
scan '"git push --push-option -- origin leaky"' "-- as the value of --push-option" ask
scan '"git push --push-opt -- origin leaky"'    "-- as the value of an abbreviated option" ask
scan '"git push --receive-pack -n origin leaky"' "-n as the value of --receive-pack" ask
scan '"git push -on origin leaky"'              "n attached to -o"               ask
scan '"git push origin leaky -o"'               "dangling -o asks"               ask
scan '"git push --bogus origin leaky"'          "option outside the table asks"  ask
scan '"git push origin -- leaky -n"'            "-n after the terminator is an operand" ask
printf '  %-52s' "remote tip unchanged by the previews"
if [ "$(git -C "$FIXTURE/remote.git" rev-parse refs/heads/leaky)" = "$before_tip" ]; then
  echo "PASS"
else
  echo "FAIL, a preview pushed"
  fail=1
fi
# The caller's -c and --config-env options travel into the preview, since they
# can move the destination or the refspec; a pushurl is another repository, so
# tracking refs of the named remote do not count as published there.
git init -q --bare "$FIXTURE/target2.git"
scan "\"git -c remote.origin.pushurl=$FIXTURE/target2.git push origin main\"" "pushurl override to an empty target" ask
scan '"git -c remote.origin.push=leaky:leaky push origin"' "refspec override selects leaky" ask
PUSHSPEC=leaky:leaky scan '"git --config-env=remote.origin.push=PUSHSPEC push origin"' "refspec override via --config-env" ask
scan '"git -c push.default=matching push origin"' "push.default override selects leaky" ask
scan '"git -c user.name=dev push origin main"'  "unrelated -c on a clean HEAD"   allow
# When git cannot say what the push publishes, the hook asks.
pushgit remote add dead "$FIXTURE/no-such-remote.git"
scan '"git push dead main"'                     "unreachable remote asks"        ask
scan '"git push origin nosuchbranch"'           "unknown ref asks"               ask
rm -rf "$PUSHREPO" "$FIXTURE/remote.git" "$FIXTURE/archive.git" "$FIXTURE/target2.git"

printf '\nprotect-default-branches.sh\n'
protect() {
  # protect <json-quoted command> <label> <expected exit> [cwd]
  printf '  %-52s' "$2"
  printf '{"tool_name":"Bash","tool_input":{"command":%s},"cwd":"%s"}' "$1" "${4:-$PROTREPO}" \
    | "$HOOK_DIR/protect-default-branches.sh" >/dev/null 2>&1
  local got=$?
  if [ "$got" = "$3" ]; then
    echo "exit=$got PASS"
  else
    echo "exit=$got FAIL, expected $3"
    fail=1
  fi
}

# A repository with a bare remote, main and a feature branch both published,
# and one unpublished commit on each, so every push below would move a ref.
PROTREPO="$FIXTURE/protrepo"
git init -q -b main "$PROTREPO"
git init -q --bare "$FIXTURE/protremote.git"
git -C "$PROTREPO" remote add origin "$FIXTURE/protremote.git"
protgit() { git -C "$PROTREPO" -c user.email=dev@example.com -c user.name=dev "$@"; }
protgit commit -q --allow-empty -m 'feat: start' && protgit push -q -u origin main
protgit checkout -q -b feature && protgit commit -q --allow-empty -m 'feat: one'
protgit push -q -u origin feature
protgit commit -q --allow-empty -m 'feat: two'
protgit checkout -q main && protgit commit -q --allow-empty -m 'feat: on main'
protgit checkout -q feature
feature_tip="$(git -C "$FIXTURE/protremote.git" rev-parse refs/heads/feature)"

protect '"git push"'                             "bare push of a feature branch"  0
protect '"git push origin feature"'              "push a feature branch"          0
protect "\"git push --force-with-lease=feature:$feature_tip origin feature\"" "pinned lease on a feature branch" 0
protect '"git push origin main"'                 "push main"                      2
protect '"git push origin feature:main"'         "feature onto main"              2
protect '"git push origin HEAD:main"'            "HEAD onto main"                 2
protect '"git push origin +feature:main"'        "forced refspec onto main"       2
protect '"git push origin feature:refs/heads/master"' "feature onto a new master"  2
protect '"git push origin feature:develop"'      "feature onto a new develop"     2
protect '"git push origin :main"'                "delete main by refspec"         2
protect '"git push origin --delete main"'        "delete main by --delete"        2
protect '"git push --all origin"'                "--all with main ahead"          2
protect '"git push --mirror origin"'             "--mirror"                       2
protect '"git push --dry-run origin main"'       "a dry run moves nothing"        0
protect '"git push origin feature && git push origin main"' "main after a feature push" 2
protect '"cd protrepo && git push origin main"'  "push main after cd"             2 "$FIXTURE"
protect '"git -C protrepo push origin main"'     "push main behind git -C"        2 "$FIXTURE"
protect '"bash -c \"git push origin main\""'     "push main inside bash -c"       2
protect '"git -c remote.origin.push=refs/heads/feature:refs/heads/main push origin"' "configured refspec onto main" 2
protect '"echo git push origin main"'            "push inside echo"               0
protect '"git commit -m \"merge main notes\""'   "merge only in a commit message" 0
protgit checkout -q main
protect '"git push"'                             "bare push from main"            2
protgit push -q origin main
protgit checkout -q feature
protect '"git push --all origin"'                "--all with main up to date"     0
# The remote's own default counts, whatever its name.
protgit symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/release
protect '"git push origin feature:release"'      "onto the default origin/HEAD names" 2
protgit symbolic-ref -d refs/remotes/origin/HEAD
# When the dry run cannot answer, the arguments are read by hand.
protgit remote add dead "$FIXTURE/no-such-remote.git"
protect '"git push dead feature"'                "unreachable remote, feature"    0
protect '"git push dead main"'                   "unreachable remote, main"       2
protect '"git push dead feature:main"'           "unreachable remote, onto main"  2
protect '"git push --all dead"'                  "unreachable remote, --all"      2
protgit checkout -q main
protect '"git push dead"'                        "unreachable remote from main"   2
protgit checkout -q feature
protect '"git push origin main \"unterminated"'  "unparseable push of main"       2

protect '"gh pr view 5"'                         "gh pr view"                     0
protect '"gh pr merge 5 --squash"'               "gh pr merge"                    2
protect '"gh pr merge --auto --squash 5"'        "gh pr merge --auto"             2
protect '"gh pr merge 5 --disable-auto"'         "gh pr merge --disable-auto"     0
protect '"/usr/bin/gh pr merge 5"'               "gh pr merge by absolute path"   2
protect '"env -u GITHUB_TOKEN gh pr merge 5"'    "gh pr merge behind env -u"      2
protect '"bash -c \"gh pr merge 5\""'            "gh pr merge inside bash -c"     2
protect '"echo gh pr merge 5"'                   "gh pr merge inside echo"        0
protect '"gh api repos/o/r/pulls/5/merge"'       "GET on the merge endpoint"      0
protect '"gh api -X PUT repos/o/r/pulls/5/merge"' "PUT on the merge endpoint"     2
protect '"gh api -XPUT repos/o/r/pulls/5/merge"' "attached -XPUT"                 2
protect '"gh api --method=PUT /repos/o/r/pulls/5/merge"' "--method=PUT"           2
protect '"gh api repos/o/r/pulls/5/merge -f merge_method=squash"' "fields imply a write" 2
protect '"gh api repos/o/r/merges -f base=main -f head=x"' "repository merges endpoint" 2
protect '"gh api repos/o/r/pulls/5"'             "read a pull request"            0
protect '"gh api graphql -f query=\"mutation { mergePullRequest(input: {}) { clientMutationId } }\""' "GraphQL mergePullRequest" 2
protect '"gh api graphql -f query=\"mutation { enablePullRequestAutoMerge(input: {}) { clientMutationId } }\""' "GraphQL auto-merge" 2
protect '"gh api graphql -f query=\"query { viewer { login } }\""' "GraphQL query"  0
printf 'mutation { mergePullRequest(input: {}) { clientMutationId } }' > "$PROTREPO/q.graphql"
protect '"gh api graphql --input q.graphql"'     "GraphQL mutation from --input"  2
protect '"gh pr merge 5 \"unterminated"'         "unparseable gh pr merge"        2
rm -rf "$PROTREPO" "$FIXTURE/protremote.git"

exit "$fail"
