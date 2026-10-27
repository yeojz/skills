#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# Asks for confirmation before a remote write that is externally visible or
# hard to take back: opening or merging a pull request, and any force push.
# A plugin cannot add permissions.ask entries to the host's settings, so the
# ask lives here instead.
#
# The command line is split by command_lines.py, the parser every hook shares,
# so a line continuation, a quoted separator, a comment or a wrapper such as
# `timeout 30` is read the way the shell will read it.
#
# Reads the PreToolUse event JSON on stdin. Prints an "ask" decision for a
# matching call and nothing otherwise. Always exits 0: the decision is in the
# output, and a hook failure must never block an ordinary Bash call.
set -uo pipefail

payload="$(cat)"

# Cheap pre-filter, so an ordinary shell call does not pay for a python start-up.
case "$payload" in
  *gh*|*git*) ;;
  *) exit 0 ;;
esac

command -v python3 >/dev/null 2>&1 || exit 0

inspector="$(cat <<'PY'
import json
import os
import re
import sys

sys.path.insert(0, sys.argv[1])
from command_lines import commands_in, git_call  # noqa: E402

FORCE_FLAGS = {"--force", "-f", "--force-if-includes"}
SHORT_CLUSTER = re.compile(r"^-[A-Za-z]+$")
# When the line cannot be lexed at all, lean towards asking.
RAW_REMOTE_WRITE = re.compile(r"\bgh\s+pr\s+(create|merge)\b|\bgit\s+push\b.*(--force|\s-f\b|\s\+\S)")


def push_is_forced(args):
    for token in args:
        if token in FORCE_FLAGS or token.startswith("--force-with-lease") or token.startswith("+"):
            return True
        if SHORT_CLUSTER.match(token) and "f" in token[1:]:
            return True
    return False


def reason_for(argv):
    name = os.path.basename(argv[0])
    if name == "gh" and len(argv) >= 3 and argv[1] == "pr" and argv[2] in {"create", "merge"}:
        return "gh pr " + argv[2] + " is a remote write; confirm before opening or merging a pull request."
    call = git_call(argv, ".")
    if call is not None:
        subcommand, args, _ = call
        if subcommand == "push" and push_is_forced(args):
            return "git push with a force option rewrites the remote branch; confirm first."
    return None


def ask(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }))


try:
    event = json.load(sys.stdin)
    command = event.get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)
if not isinstance(command, str):
    sys.exit(0)

try:
    for argv, _ in commands_in(command):
        reason = reason_for(argv)
        if reason:
            ask(reason)
            break
except ValueError:
    if RAW_REMOTE_WRITE.search(command):
        ask("The command could not be parsed and looks like a remote write; confirm first.")
PY
)"

printf '%s' "$payload" | python3 -B -c "$inspector" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exit 0
