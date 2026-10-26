#!/usr/bin/env bash
# SessionStart hook.
#
# A plugin cannot ship always-on rule files, so this hook injects the plugin's
# rules into the session as context instead. The rules live beside this script
# in ../rules, so the hook works wherever the plugin is installed and needs no
# path from the host.
set -uo pipefail

# This hook only adds context, so a missing python3 is not worth blocking on.
command -v python3 >/dev/null 2>&1 || exit 0

rules_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../rules" 2>/dev/null && pwd)"
[ -n "$rules_dir" ] || exit 0

# Drain stdin so the host never sees a broken pipe; the payload carries nothing
# this hook needs.
cat >/dev/null 2>&1 || true

found=0
for f in "$rules_dir"/*.md; do
  [ -f "$f" ] && found=1 && break
done
[ "$found" = 1 ] || exit 0

{
  echo "House rules from the jz plugin. They apply to every change in every repository and override general defaults:"
  for f in "$rules_dir"/*.md; do
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
