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
import re
import sys

sys.path.insert(0, sys.argv[1])
from command_lines import commands_in, git_call  # noqa: E402
from git_push import resolve_push_long_option  # noqa: E402
from gh_options import final_bool_option, gh_command  # noqa: E402

SHORT_CLUSTER = re.compile(r"^-[A-Za-z]+$")
# A lease expectation git cannot re-resolve: a full object id, or empty for
# "the ref must not exist yet". Anything else, a ref name or a short hex that
# could be one, is read from a ref a fetch can move.
PINNED_EXPECTATION = re.compile(r"^(|[0-9a-f]{40}|[0-9a-f]{64})$")
# The option tables of gh pr create and gh pr ready (cli/cli v2.103.0), with
# the persistent --repo/-R, read by gh_options.final_bool_option. A line that
# uses an option missing here, or a bool spelling gh rejects, is not provably
# a draft, so it asks.
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
# When the line cannot be lexed at all, lean towards asking.
RAW_REMOTE_WRITE = re.compile(r"\bgh\b.*\bpr\s+(create|ready)\b|\bgit\s+push\b.*(--force|\s-f\b|\s\+\S)")


def push_is_forced(args):
    """Whether a git push can overwrite a remote branch without naming the sha it replaces.

    A lease that names the full expected object id, `--force-with-lease=<ref>:<sha>`,
    fails unless the remote is still where the caller last saw it, so it passes,
    as does an empty expectation, which requires the ref not to exist. A bare
    lease, or one whose expectation is a ref name such as
    `refs/remotes/origin/x`, checks against a ref a background fetch can move,
    so it is treated like --force. --force-if-includes only refines a lease
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
                if has_value and ":" in value and PINNED_EXPECTATION.match(value.split(":", 1)[1]):
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


def create_is_draft(args):
    return final_bool_option(args, PR_CREATE_BOOL_OPTIONS, PR_CREATE_VALUE_OPTIONS, "draft") is True


def ready_is_undo(args):
    return final_bool_option(args, PR_READY_BOOL_OPTIONS, PR_READY_VALUE_OPTIONS, "undo") is True


def reason_for(argv):
    gh = gh_command(argv)
    if gh is not None:
        words, args = gh
        if words == ("pr", "create") and not create_is_draft(args):
            return "gh pr create without --draft opens a pull request ready for review; confirm first, or open it as a draft."
        if words == ("pr", "ready") and not ready_is_undo(args):
            return "gh pr ready signals reviewers; confirm before marking a pull request ready."
        return None
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
