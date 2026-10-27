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
ask '"gh pr create --draft --title t"'          "gh pr create"                   ask
ask '"gh pr merge 5 --squash"'                  "gh pr merge"                    ask
ask '"git status && gh pr create -d"'           "gh pr create after &&"          ask
ask '"git push --force"'                        "push --force"                   ask
ask '"git push -f origin x"'                    "push -f"                        ask
ask '"git push -fu origin x"'                   "push -fu cluster"               ask
ask '"git push --force-with-lease=x:abc"'       "push --force-with-lease=ref"    ask
ask '"git push origin --force-with-lease"'      "push remote then lease"         ask
ask '"git push --force-if-includes"'            "push --force-if-includes"       ask
ask '"git push origin +main"'                   "push plus refspec"              ask
ask '"git -C . push -f"'                        "push -f behind git -C"          ask
ask '"nohup git push --force"'                  "push behind nohup"              ask
ask '"/usr/bin/gh pr merge 5"'                  "gh through an absolute path"    ask
ask '"git push origin \\\n  --force-with-lease"' "push with a line continuation"  ask
ask '"gh pr create \\\n  --draft \\\n  --title t"'  "gh pr create across lines"      ask
ask '"timeout 30 git push --force"'              "push behind timeout with a duration" ask
ask '"bash -c \"git push --force\""'             "push inside bash -c"            ask
ask '"git push origin main # --force in a comment"' "force only in a trailing comment" allow
ask '"echo '"'"'example;git push --force origin main'"'"'"' "separator inside quotes"       allow
ask '"git log --oneline\ngit push -f"'           "push -f on a second line"       ask
ask '"git push --force-with-lease \\\n origin x"' "lease then a continuation"     ask
ask '"env -u GITHUB_TOKEN gh pr create --draft"'  "gh behind env -u with an operand" ask
ask '"timeout --signal TERM 30 git push --force"' "push behind timeout --signal"   ask
ask '"sudo -u root git push -f"'                 "push behind sudo -u"            ask
ask '"nice -n 5 git push --force"'               "push behind nice -n"            ask
ask '"env -- gh pr merge 5"'                     "gh after a double dash"         ask
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

exit "$fail"
