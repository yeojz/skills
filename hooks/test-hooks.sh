#!/usr/bin/env bash
# Regression suite for the hook scripts. Builds a throwaway repo, feeds each
# hook the PreToolUse payload shape it will see in real use, and checks the
# exit code. Exit 0 allows the tool call, exit 2 denies it.
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

git init -q "$FIXTURE"
mkdir -p "$FIXTURE/docs/plans" "$FIXTURE/.claude" "$FIXTURE/src"
echo plan > "$FIXTURE/docs/plans/x.md"
echo settings > "$FIXTURE/.claude/settings.json"
echo readme > "$FIXTURE/README.md"
echo code > "$FIXTURE/src/a.ts"

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
check '"ls -la"'                               "benign command"                0
check '"git add -A"'                           "add -A sweeps a plan file"     2
check '"git add README.md"'                    "add one clean path"            0
check '"git add docs/plans"'                   "add a forbidden directory"     2
check '"git add .claude/settings.json"'        "add a .claude file"            2
check '"git commit -m \"mentions ~/.claude\""' "commit message names .claude"  0
check '"git commit -m \"docs/plans in text\""' "commit message names a plan"   0
check '"git add . "'                           "add dot sweeps"                2
check '"git add src/a.ts README.md"'           "add several clean paths"       0
check '"git add src && git commit -m x"'       "chained add of a clean path"   0

git -C "$FIXTURE" add README.md
check '"git commit -m \"chore: readme\""'      "commit, clean staging"         0

git -C "$FIXTURE" add -f docs/plans/x.md
check '"git commit -m \"chore: oops\""'        "commit, plan file staged"      2
check '"git commit -am \"chore: oops\""'       "commit -a, plan file staged"   2

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

exit "$fail"
