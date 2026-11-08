"""The guards the Bash PreToolUse hook runs, and what they share.

A guard is a module with a NAME and a check(context) function that returns
None to allow the call, Deny(lines) to block it, or Ask(reason) to have the
host confirm it. The dispatcher in ../guard.py parses the payload once and
hands every guard the same Context. A guard judges the commands the parser
could read; the dispatcher itself asks about anything it could not follow,
so no guard needs a fallback of its own for an unreadable line.
"""

import re
import shlex

from command_lines import git_config_overrides, git_global_options, git_location_options, parse, start_directory
from git_push import run_git

# Subcommands that are never aliases, so no config lookup is needed for them.
KNOWN_GIT_COMMANDS = {
    "add", "am", "apply", "archive", "bisect", "blame", "branch", "cat-file", "checkout", "cherry-pick",
    "clean", "clone", "commit", "commit-tree", "config", "count-objects", "describe", "diff", "fetch",
    "for-each-ref", "format-patch", "fsck", "gc", "grep", "hash-object", "help", "init", "log",
    "ls-files", "ls-remote", "ls-tree", "merge", "merge-base", "mktree", "mv", "notes", "pull",
    "push", "range-diff", "rebase", "reflog", "remote", "reset", "restore", "rev-list", "rev-parse",
    "revert", "rm", "shortlog", "show", "stage", "stash", "status", "submodule", "switch",
    "symbolic-ref", "tag", "update-ref", "var", "version", "worktree",
}
ALIAS_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def safe_text(text, limit=120):
    """Text from a repository or a tool, made fit for a reason the model reads: printable ASCII, cut to `limit`."""
    cleaned = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in str(text))
    return cleaned if len(cleaned) <= limit else cleaned[:limit - 3] + "..."


def resolve_aliases(parsed):
    """Replace a git alias with the command it stands for, so `git p` is judged as the push it runs.

    A shell alias (`!...`) runs a command line the parser cannot see and is
    reported instead. The lookup passes the call's own -c overrides, since
    `git -c alias.x=push x` is an alias too, and only ever runs `git config`.
    """
    resolved = []
    for argv, directory in parsed.calls:
        split = git_global_options(argv)
        if split is None or not split[1] or split[1][0] in KNOWN_GIT_COMMANDS or not ALIAS_NAME.match(split[1][0]):
            resolved.append((argv, directory))
            continue
        subcommand = split[1][0]
        out = run_git(directory, git_location_options(argv) + git_config_overrides(argv),
                      ["config", "--get", "alias." + subcommand])
        value = out.stdout.strip() if out is not None and out.returncode == 0 else ""
        if not value:
            resolved.append((argv, directory))
            continue
        try:
            words = shlex.split(value) if not value.startswith("!") else None
        except ValueError:
            words = None
        if not words:
            parsed.skip("a shell alias (%s)" % subcommand)
            parsed.hidden = True
            continue
        head = argv[:len(argv) - len(split[1])]
        resolved.append((head + words + split[1][1:], directory))
    parsed.calls = resolved


class Deny:
    """Block the call. `lines` go to stderr, the first one the reason."""

    def __init__(self, *lines):
        self.lines = [line for line in lines if line is not None]


class Ask:
    """Have the host confirm the call, giving `reason`."""

    def __init__(self, reason):
        self.reason = reason


class Context:
    """The PreToolUse payload, parsed once for every guard."""

    def __init__(self, event):
        event = event if isinstance(event, dict) else {}
        tool_input = event.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        self.command = command if isinstance(command, str) else ""
        cwd = event.get("cwd")
        self.transcript_path = event.get("transcript_path")
        self.start = start_directory(cwd if isinstance(cwd, str) else "")
        self._parsed = None

    @property
    def parsed(self):
        if self._parsed is None:
            self._parsed = parse(self.command, self.start)
            resolve_aliases(self._parsed)
        return self._parsed

    @property
    def calls(self):
        """(argv, directory) for every simple command the parser could read."""
        return self.parsed.calls

    @property
    def unfollowed(self):
        """The constructs on the line the parser did not follow, each named once."""
        return self.parsed.unfollowed
