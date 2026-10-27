#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# Denies merging the default branch into a feature branch. The house workflow
# rebases a branch onto the default branch and never merges it in, and the
# correction had to be typed in three repositories before this hook existed.
# The desktop app's own "merge the base branch in" prompt lands here too.
#
# The command line is split by command_lines.py, the parser every hook shares,
# and each command is judged in the directory it runs in, so a leading `cd` or
# a `git -C` resolves the default branch of the repository it targets.
#
# Reads the PreToolUse event JSON on stdin. Exit 0 allows, exit 2 denies.
set -uo pipefail

payload="$(cat)"

# Cheap pre-filter, so an ordinary shell call does not pay for a python start-up.
case "$payload" in
  *git*) ;;
  *) exit 0 ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "Blocked: rebase-not-merge hook needs python3 on PATH to inspect git calls." >&2
  exit 2
fi

inspector="$(cat <<'PY'
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, sys.argv[1])
from command_lines import commands_with_directory, git_call, git_config_overrides  # noqa: E402

COMMON_DEFAULTS = {"main", "master", "develop", "trunk"}
REBASE_VALUES_THAT_REBASE = {"true", "merges", "interactive", "preserve", "i"}
# When the line cannot be lexed at all, lean towards denying a merge of a default name.
RAW_MERGE = re.compile(r"\bgit\b.*\bmerge\s+(?:--\S+\s+)*(?:origin/|upstream/)?(main|master|develop|trunk)\b")

defaults_by_directory = {}


def run_git(directory, args):
    try:
        return subprocess.run(["git", "-C", directory] + args, capture_output=True,
                              text=True, timeout=5)
    except Exception:
        return None


def default_branch(directory):
    if directory in defaults_by_directory:
        return defaults_by_directory[directory]
    names = COMMON_DEFAULTS
    out = run_git(directory, ["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"])
    if out is not None and out.returncode == 0 and out.stdout.strip():
        names = {out.stdout.strip().split("/", 1)[-1]}
    defaults_by_directory[directory] = names
    return names


def names_default(token, defaults):
    bare = token.split("/", 1)[-1] if token.startswith(("origin/", "upstream/")) else token
    return bare in defaults


def config_value(directory, config_overrides, key):
    """A config value as git pull would read it, or None when the key is unset.

    The query carries the call's own `-c` and `--config-env` options, so a
    one-off override is judged the way git will apply it. A bare `-c
    pull.rebase` means true, which --type=bool-or-str spells out.
    """
    out = run_git(directory, config_overrides + ["config", "--type=bool-or-str", "--get", key])
    if out is None or out.returncode != 0:
        return None
    return out.stdout.strip().lower()


def current_branch(directory):
    out = run_git(directory, ["symbolic-ref", "-q", "--short", "HEAD"])
    if out is None or out.returncode != 0:
        return None
    return out.stdout.strip()


def pull_rebases(args, directory, config_overrides):
    """The effective rebase setting of a git pull, in git's own order of precedence.

    The last explicit flag wins; otherwise branch.<current>.rebase, then
    pull.rebase, then false.
    """
    setting = None
    for arg in args:
        if arg == "--rebase" or arg == "-r":
            setting = True
        elif arg.startswith("--rebase="):
            setting = arg.split("=", 1)[1] in REBASE_VALUES_THAT_REBASE
        elif arg == "--no-rebase":
            setting = False
    if setting is not None:
        return setting
    keys = ["pull.rebase"]
    branch = current_branch(directory)
    if branch:
        keys.insert(0, "branch." + branch + ".rebase")
    for key in keys:
        value = config_value(directory, config_overrides, key)
        if value is not None:
            return value in REBASE_VALUES_THAT_REBASE
    return False


def reason_for(argv, directory):
    call = git_call(argv, directory)
    if call is None:
        return None, directory
    sub, args, git_directory = call
    defaults = default_branch(git_directory)
    if sub == "merge":
        if any(a in {"--abort", "--continue", "--quit"} for a in args):
            return None, git_directory
        if any(names_default(a, defaults) for a in args if not a.startswith("-")):
            return "Merging the default branch into this branch is not the house workflow.", git_directory
    if sub == "pull":
        positional = [a for a in args if not a.startswith("-")]
        if (len(positional) >= 2 and names_default(positional[1], defaults)
                and not pull_rebases(args, git_directory, git_config_overrides(argv))):
            return "Pulling the default branch without an effective --rebase merges it into this branch.", git_directory
    return None, git_directory


def deny(reason, directory):
    base = sorted(default_branch(directory))[0]
    print("Blocked: " + reason, file=sys.stderr)
    print("Rebase instead: git fetch origin " + base + " && git rebase origin/" + base, file=sys.stderr)
    sys.exit(2)


try:
    event = json.load(sys.stdin)
    command = event.get("tool_input", {}).get("command", "")
    cwd = event.get("cwd", "")
except Exception:
    sys.exit(0)
if not isinstance(command, str):
    sys.exit(0)
start = cwd if isinstance(cwd, str) and cwd else os.getcwd()

try:
    for argv, _, directory in commands_with_directory(command, start):
        reason, git_directory = reason_for(argv, directory)
        if reason:
            deny(reason, git_directory)
except ValueError:
    if RAW_MERGE.search(command):
        deny("The command could not be parsed and looks like a merge of the default branch.", start)
sys.exit(0)
PY
)"

printf '%s' "$payload" | python3 -B -c "$inspector" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
