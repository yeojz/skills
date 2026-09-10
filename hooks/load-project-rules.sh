#!/usr/bin/env bash
# SessionStart hook.
#
# Surfaces the project's own instruction files so they are read at the start of
# a session, rather than only once someone notices they were skipped.
set -uo pipefail

# This hook only adds context, so a missing python3 is not worth blocking on.
command -v python3 >/dev/null 2>&1 || exit 0

payload="$(cat 2>/dev/null || true)"

cwd="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("cwd", ""))
except Exception:
    print("")
' 2>/dev/null)"

[ -n "$cwd" ] && cd "$cwd" 2>/dev/null || true

found=""
for f in CLAUDE.md AGENTS.md CONTRIBUTING.md; do
  [ -f "$f" ] && found="$found $f"
done

[ -z "$found" ] && exit 0

context="This repository has project instruction files:$found. Read them before making any change, and follow them over any general default."

printf '%s' "$context" | python3 -c '
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": sys.stdin.read(),
    }
}))
'
exit 0
