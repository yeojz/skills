#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# Asks for confirmation before a remote write that is externally visible or
# hard to take back: opening or merging a pull request, and any force push.
# A plugin cannot add permissions.ask entries to the host's settings, so the
# ask lives here instead.
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

printf '%s' "$payload" | python3 -c '
import json
import re
import shlex
import sys

WRAPPERS = {"command", "env", "sudo", "nohup", "time", "timeout", "nice"}
FORCE_FLAGS = {"--force", "-f", "--force-if-includes"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*=")
SHORT_CLUSTER = re.compile(r"^-[A-Za-z]+$")


def segments(command):
    # Split on the shell operators that start a new simple command.
    return [s for s in re.split(r"\|\||&&|[;|\n]", command) if s.strip()]


def words(segment):
    try:
        tokens = shlex.split(segment, comments=True)
    except ValueError:
        tokens = segment.split()
    while tokens and (tokens[0] in WRAPPERS or ASSIGNMENT.match(tokens[0])):
        tokens = tokens[1:]
    return tokens


def reason_for(tokens):
    if not tokens:
        return None
    name = tokens[0].rsplit("/", 1)[-1]
    rest = tokens[1:]
    if name == "gh" and len(rest) >= 2 and rest[0] == "pr" and rest[1] in {"create", "merge"}:
        return "gh pr " + rest[1] + " is a remote write; confirm before opening or merging a pull request."
    if name == "git":
        # Skip global options such as -C <dir> or -c key=value.
        i = 0
        while i < len(rest) and rest[i].startswith("-"):
            i += 2 if rest[i] in {"-C", "-c", "--git-dir", "--work-tree"} else 1
        if i < len(rest) and rest[i] == "push":
            for token in rest[i + 1:]:
                if token in FORCE_FLAGS or token.startswith("--force-with-lease") or token.startswith("+"):
                    return "git push with a force option rewrites the remote branch; confirm first."
                if SHORT_CLUSTER.match(token) and "f" in token[1:]:
                    return "git push with a force option rewrites the remote branch; confirm first."
    return None


try:
    event = json.load(sys.stdin)
    command = event.get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)

for segment in segments(command):
    reason = reason_for(words(segment))
    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            }
        }))
        break
'
exit 0
