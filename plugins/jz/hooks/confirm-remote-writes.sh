#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# Asks for confirmation before a remote write that is hard to take back or
# that signals reviewers: opening a pull request ready for review, marking one
# ready, and a force push that is not pinned to the sha it replaces. A branch
# push, a draft pull request and a `--force-with-lease=<ref>:<sha>` push can
# be withdrawn or fail safe, and pass without a prompt. Merging a pull request
# and pushing to a default branch are denied outright by
# protect-default-branches.sh. A plugin cannot add permissions.ask entries to
# the host's settings, so the ask lives here instead.
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
from git_push import resolve_push_long_option  # noqa: E402

SHORT_CLUSTER = re.compile(r"^-[A-Za-z]+$")
# The option tables of gh pr create and gh pr ready (cli/cli v2.103.0), with
# the persistent --repo/-R. gh parses them with pflag: a bool option takes an
# attached =value only, every other option consumes the rest of its token or
# the next token. A line that uses an option missing here, or a bool spelling
# gh rejects, is not provably a draft, so it asks.
PR_CREATE_BOOL_OPTIONS = {
    "draft": "d", "editor": "e", "web": "w", "fill": "f", "fill-verbose": None,
    "fill-first": None, "no-maintainer-edit": None, "dry-run": None, "help": "h",
}
PR_CREATE_VALUE_OPTIONS = {
    "title": "t", "body": "b", "body-file": "F", "base": "B", "head": "H",
    "reviewer": "r", "assignee": "a", "label": "l", "project": "p",
    "milestone": "m", "recover": None, "template": "T", "attach": None, "repo": "R",
}
PR_READY_BOOL_OPTIONS = {"undo": None, "help": "h"}
PR_READY_VALUE_OPTIONS = {"repo": "R"}
# strconv.ParseBool, which pflag applies to every bool assignment.
BOOL_SPELLINGS = {
    "1": True, "t": True, "T": True, "TRUE": True, "true": True, "True": True,
    "0": False, "f": False, "F": False, "FALSE": False, "false": False, "False": False,
}
# When the line cannot be lexed at all, lean towards asking.
RAW_REMOTE_WRITE = re.compile(r"\bgh\s+pr\s+(create|ready)\b|\bgit\s+push\b.*(--force|\s-f\b|\s\+\S)")


def push_is_forced(args):
    """Whether a git push can overwrite a remote branch without naming the sha it replaces.

    A lease that names the expected sha, `--force-with-lease=<ref>:<sha>`, fails
    unless the remote is still where the caller last saw it, so it passes. A bare
    lease checks against the remote-tracking ref, which a background fetch can
    move, so it is treated like --force. --force-if-includes only refines a lease
    and asks on its own. Long options resolve by unambiguous prefix, as git
    resolves them.
    """
    pinned = False
    forced = False
    includes = False
    for token in args:
        if token.startswith("--") and token != "--":
            name, has_value, value = token[2:].partition("=")
            resolved = resolve_push_long_option(name)
            if resolved == "force":
                forced = True
            elif resolved == "force-with-lease":
                if has_value and ":" in value:
                    pinned = True
                else:
                    forced = True
            elif resolved == "force-if-includes":
                includes = True
            continue
        if token.startswith("+"):
            forced = True
        elif SHORT_CLUSTER.match(token) and "f" in token[1:]:
            forced = True
    return forced or (includes and not pinned)


def final_bool_option(args, bool_options, value_options, name):
    """The value pflag leaves in the bool option `name` after reading `args` in order.

    Returns None when gh would reject the line or the hook cannot follow it.
    """
    shorts = {}
    for long_name, letter in bool_options.items():
        if letter:
            shorts[letter] = ("bool", long_name)
    for long_name, letter in value_options.items():
        if letter:
            shorts[letter] = ("value", long_name)
    result = False
    rest = list(args)
    while rest:
        token = rest.pop(0)
        if token == "--":
            break
        if not token.startswith("-") or token == "-":
            continue
        if token.startswith("--"):
            long_name, has_value, raw = token[2:].partition("=")
            if long_name in bool_options:
                if has_value:
                    if raw not in BOOL_SPELLINGS:
                        return None
                    value = BOOL_SPELLINGS[raw]
                else:
                    value = True
                if long_name == name:
                    result = value
            elif long_name in value_options:
                if not has_value:
                    if not rest:
                        return None
                    rest.pop(0)
            else:
                return None
            continue
        cluster = token[1:]
        while cluster:
            letter, cluster = cluster[0], cluster[1:]
            if letter not in shorts:
                return None
            kind, long_name = shorts[letter]
            if kind == "bool":
                if cluster.startswith("="):
                    if cluster[1:] not in BOOL_SPELLINGS:
                        return None
                    value = BOOL_SPELLINGS[cluster[1:]]
                    cluster = ""
                else:
                    value = True
                if long_name == name:
                    result = value
            elif cluster:
                cluster = ""
            elif rest:
                rest.pop(0)
            else:
                return None
    return result


def create_is_draft(args):
    return final_bool_option(args, PR_CREATE_BOOL_OPTIONS, PR_CREATE_VALUE_OPTIONS, "draft") is True


def ready_is_undo(args):
    return final_bool_option(args, PR_READY_BOOL_OPTIONS, PR_READY_VALUE_OPTIONS, "undo") is True


def reason_for(argv):
    name = os.path.basename(argv[0])
    if name == "gh" and len(argv) >= 3 and argv[1] == "pr":
        if argv[2] == "create" and not create_is_draft(argv[3:]):
            return "gh pr create without --draft opens a pull request ready for review; confirm first, or open it as a draft."
        if argv[2] == "ready" and not ready_is_undo(argv[3:]):
            return "gh pr ready signals reviewers; confirm before marking a pull request ready."
    call = git_call(argv, ".")
    if call is not None:
        subcommand, args, _ = call
        if subcommand == "push" and push_is_forced(args):
            return "git push with a force option not pinned to the sha it replaces can discard commits on the remote; confirm first, or use --force-with-lease=<branch>:<sha>."
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
