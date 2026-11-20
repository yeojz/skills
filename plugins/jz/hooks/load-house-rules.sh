#!/usr/bin/env bash
# SessionStart hook.
#
# A plugin cannot ship always-on rule files, so this hook injects the plugin's
# rules into the session as context instead. The rules live beside this script
# in ../rules, so the hook works wherever the plugin is installed and needs no
# path from the host.
#
# rules/*.md apply everywhere. rules/cloud/*.md apply in a Claude Code cloud
# session (CLAUDE_CODE_REMOTE=true), and rules/local/*.md everywhere else,
# because a cloud session works on an assigned branch with no worktrees and
# no fan-out by default.
set -uo pipefail

# This hook only adds context, so a missing python3 is not worth blocking on.
command -v python3 >/dev/null 2>&1 || exit 0

rules_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../rules" 2>/dev/null && pwd)"
[ -n "$rules_dir" ] || exit 0

# Drain stdin so the host never sees a broken pipe; the payload carries nothing
# this hook needs.
cat >/dev/null 2>&1 || true

if [ "${CLAUDE_CODE_REMOTE:-}" = true ]; then
  scoped="cloud"
else
  scoped="local"
fi

files=()
for f in "$rules_dir"/*.md "$rules_dir/$scoped"/*.md; do
  [ -f "$f" ] && files+=("$f")
done
[ "${#files[@]}" -gt 0 ] || exit 0

{
  echo "House rules from the jz plugin. They apply to every change in every repository and override general defaults:"
  for f in "${files[@]}"; do
    echo
    cat "$f"
  done
} | python3 -c '
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": sys.stdin.read(),
    }
}))
'
exit 0
