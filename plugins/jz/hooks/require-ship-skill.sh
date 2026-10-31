#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# Denies git commit, git push and gh pr create until the session has loaded
# the ship skill. The skill holds the procedure around those commands: the
# gate before the commit, the body from pr-desc, the detached gate before
# ready, the tip checks before a branch is deleted. Nothing routes a request
# to it, since a skill description is a suggestion the model weighs, and in
# every recent session where no one named the skill it stayed unloaded while
# the house rules were in context. A hook runs whether or not anyone
# remembers.
#
# The transcript the payload names is the evidence: a Skill tool call whose
# skill is `ship` or `<plugin>:ship` and whose result did not report an
# error, or a typed `/ship` command. A call that failed or has no result yet
# unlocks nothing, since the procedure never reached the session. A typed
# command reaches the transcript inside a `<command-name>` tag only when the
# skill is installed; one that is not arrives as plain text and the skill body
# never follows it, so the tag is the evidence on that path. A payload
# without a transcript path, from another host, the test suite or a headless
# run, is allowed through, so the gate holds on Claude Code only until another
# host's payload is known to carry one. A subagent is judged on its own
# transcript, since the parent's loaded steps are not in its context.
#
# Reads the PreToolUse event JSON on stdin. Exit 0 allows, exit 2 denies.
set -uo pipefail

payload="$(cat)"

case "$payload" in
  *git*|*gh*) ;;
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

GATED_GIT = {"commit", "push"}
SHIP = re.compile(r"(^|:)ship$")
TYPED = re.compile(r"<command-name>/(?:[^<>/]*:)?ship</command-name>")
RAW_GATED = re.compile(r"\bgit\b.*\b(commit|push)\b|\bgh\b.*\bpr\s+create\b")


def gated_call(argv):
    call = git_call(argv, ".")
    if call is not None:
        return call[0] in GATED_GIT
    if os.path.basename(argv[0]) != "gh":
        return False
    positional = [a for a in argv[1:] if not a.startswith("-")]
    return any(positional[i:i + 2] == ["pr", "create"] for i in range(len(positional) - 1))


def skill_call_loads_ship(block):
    if not isinstance(block, dict) or block.get("type") != "tool_use" or block.get("name") != "Skill":
        return False
    skill = block.get("input") or {}
    return bool(SHIP.search(str(skill.get("skill", ""))))


def user_turn_types_ship(content):
    if isinstance(content, str):
        texts = [content]
    elif isinstance(content, list):
        texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    else:
        return False
    return any(TYPED.search(text) for text in texts)


def ship_loaded(path):
    """True once the transcript shows the skill loaded.

    A Skill call counts only with its result: the tool_use block carries an id,
    and the tool_result block that answers it carries the same id. A result
    with is_error true is a load that failed, so the session never received
    the procedure, and a call with no result yet is pending; neither unlocks
    anything. A later call that succeeds does.
    """
    pending = set()
    with open(path, encoding="utf-8", errors="replace") as transcript:
        for line in transcript:
            if "ship" not in line and "tool_result" not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            message = entry.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if entry.get("type") == "assistant" and isinstance(content, list):
                for block in content:
                    if skill_call_loads_ship(block) and block.get("id"):
                        pending.add(block["id"])
            elif entry.get("type") == "user":
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_result":
                            continue
                        if block.get("tool_use_id") not in pending:
                            continue
                        if block.get("is_error") is True:
                            pending.discard(block["tool_use_id"])
                        else:
                            return True
                if user_turn_types_ship(content):
                    return True
    return False


try:
    event = json.load(sys.stdin)
    command = event.get("tool_input", {}).get("command", "")
    transcript = event.get("transcript_path")
except Exception:
    sys.exit(0)
if not isinstance(command, str):
    sys.exit(0)

try:
    gated = any(gated_call(argv) for argv, _ in commands_in(command))
except ValueError:
    gated = bool(RAW_GATED.search(command))
if not gated:
    sys.exit(0)

if not isinstance(transcript, str) or not os.path.isfile(transcript):
    sys.exit(0)
try:
    if ship_loaded(transcript):
        sys.exit(0)
except OSError:
    sys.exit(0)

print("Blocked: git commit, git push and gh pr create run through the ship skill, "
      "and this session has not loaded it.", file=sys.stderr)
print("Load it first: call the Skill tool with skill \"jz:ship\", or type /jz:ship, "
      "then run the command again in the mode the request asked for.", file=sys.stderr)
sys.exit(2)
PY
)"

printf '%s' "$payload" | python3 -B -c "$inspector" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
