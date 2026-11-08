"""Deny merging the default branch into a feature branch.

The house workflow rebases a branch onto the default branch and never merges
it in, and the correction had to be typed in three repositories before this
guard existed. The desktop app's own "merge the base branch in" prompt lands
here too.

A checkout that is on the default branch itself is the one place a merge of
the default is the house workflow: after a PR lands on GitHub, the main
checkout is brought level with `git merge --ff-only origin/<default>`, as the
pr skill's cleanup step runs it. That call is allowed. A merge of the default
into any other branch is denied, and so is one that follows a checkout or
switch on the same line, since the branch the guard can read is not the one
the merge will run on. The advice names the branch the command tried to
merge, since without origin/HEAD the default is only known to be one of the
common names.
"""

import re
import subprocess

from command_lines import git_call, git_config_overrides
from guards import Deny

NAME = "rebase-not-merge"

COMMON_DEFAULTS = {"main", "master", "develop", "trunk"}
REBASE_VALUES_THAT_REBASE = {"true", "merges", "interactive", "preserve", "i"}
# When the line cannot be lexed at all, lean towards denying a merge of a default name.
RAW_MERGE = re.compile(r"\bgit\b.*\bmerge\s+(?:--\S+\s+)*(?:origin/|upstream/)?(main|master|develop|trunk)\b")

def run_git(directory, args):
    try:
        return subprocess.run(["git", "-C", directory] + args, capture_output=True,
                              text=True, timeout=5)
    except Exception:
        return None


def default_branch(directory, defaults_by_directory):
    if directory in defaults_by_directory:
        return defaults_by_directory[directory]
    names = COMMON_DEFAULTS
    out = run_git(directory, ["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"])
    if out is not None and out.returncode == 0 and out.stdout.strip():
        names = {out.stdout.strip().split("/", 1)[-1]}
    defaults_by_directory[directory] = names
    return names


def bare_name(token):
    return token.split("/", 1)[-1] if token.startswith(("origin/", "upstream/")) else token


def names_default(token, defaults):
    return bare_name(token) in defaults


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


def reason_for(argv, directory, switched, defaults_by_directory):
    """The reason to deny this call and the branch it names, or (None, None).

    `switched` holds the git directories where an earlier command on the same
    line was a checkout or switch. The checkout is read before any of the line
    runs, so after such a command the branch it reports is not the branch the
    merge will run on, and the default branch's own fast-forward exception is
    withheld there.
    """
    call = git_call(argv, directory)
    if call is None:
        return None, None
    sub, args, git_directory = call
    if sub in {"checkout", "switch"}:
        switched.add(git_directory)
        return None, None
    defaults = default_branch(git_directory, defaults_by_directory)
    current = None if git_directory in switched else current_branch(git_directory)
    if sub == "merge":
        if any(a in {"--abort", "--continue", "--quit"} for a in args):
            return None, None
        for a in args:
            if a.startswith("-") or not names_default(a, defaults):
                continue
            if current is not None and names_default(a, {current}):
                continue
            return "Merging the default branch into this branch is not the house workflow.", bare_name(a)
    if sub == "pull":
        positional = [a for a in args if not a.startswith("-")]
        if (len(positional) >= 2 and names_default(positional[1], defaults)
                and not (current is not None and names_default(positional[1], {current}))
                and not pull_rebases(args, git_directory, git_config_overrides(argv))):
            return ("Pulling the default branch without an effective --rebase merges it into this branch.",
                    bare_name(positional[1]))
    return None, None


def deny(reason, branch):
    """Deny with advice to rebase onto the branch the command names."""
    return Deny("Blocked: " + reason,
                "Rebase instead: git fetch origin " + branch + " && git rebase origin/" + branch)


def check(context):
    if "git" not in context.command:
        return None
    if context.calls is None:
        match = RAW_MERGE.search(context.command)
        if match:
            return deny("The command could not be parsed and looks like a merge of the default branch.", match.group(1))
        return None
    switched = set()
    defaults_by_directory = {}
    for argv, _, directory in context.calls:
        reason, branch = reason_for(argv, directory, switched, defaults_by_directory)
        if reason:
            return deny(reason, branch)
    return None
