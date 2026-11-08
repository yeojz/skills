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

from command_lines import git_call, git_config_overrides, git_global_options, git_location_options, parse, start_directory
from git_push import run_git

# Subcommands git never reads as aliases, so no lookup is needed for them.
KNOWN_GIT_COMMANDS = {
    "add", "am", "apply", "archive", "bisect", "blame", "branch", "bundle", "cat-file", "checkout",
    "cherry", "cherry-pick", "clean", "clone", "commit", "commit-tree", "config", "count-objects",
    "describe", "diff", "fetch", "for-each-ref", "format-patch", "fsck", "gc", "grep", "hash-object",
    "help", "init", "log", "ls-files", "ls-remote", "ls-tree", "maintenance", "merge", "merge-base",
    "mktree", "mv", "notes", "pull", "push", "range-diff", "rebase", "reflog", "remote", "reset",
    "restore", "rev-list", "rev-parse", "revert", "rm", "shortlog", "show", "show-ref",
    "sparse-checkout", "stage", "stash", "status", "submodule", "switch", "symbolic-ref", "tag",
    "update-ref", "var", "version", "worktree",
}
# git follows an alias that names another alias; a chain longer than this is
# reported rather than followed.
MAX_ALIAS_DEPTH = 5
ALIAS_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def safe_text(text, limit=120):
    """Text from a repository or a tool, made fit for a reason the model reads: printable ASCII, cut to `limit`."""
    cleaned = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in str(text))
    return cleaned if len(cleaned) <= limit else cleaned[:limit - 3] + "..."


def alias_map(directory, options, config_overrides, cache):
    """The aliases a git call in `directory` would see: the repository's and the user's, plus the call's own -c alias.* overrides.

    The overrides are read from the command's tokens, never passed to git, so
    the lookup is one plain `git config` per directory with nothing from the
    command in it.
    """
    key = (directory, tuple(options))
    if key not in cache:
        aliases = {}
        out = run_git(directory, list(options), ["config", "--get-regexp", r"^alias\."])
        for line in (out.stdout.splitlines() if out is not None and out.returncode == 0 else []):
            name, _, value = line.partition(" ")
            aliases[name[len("alias."):].lower()] = value
        cache[key] = aliases
    aliases = dict(cache[key])
    for name, value in zip(config_overrides[::2], config_overrides[1::2]):
        setting, has_value, expansion = value.partition("=")
        if setting.lower().startswith("alias.") and has_value:
            if name == "--config-env":
                # The expansion is in an environment variable the guard cannot see.
                return None
            aliases[setting[len("alias."):].lower()] = expansion
    return aliases


def resolve_aliases(parsed):
    """Replace a git alias with the command it stands for, so `git p` is judged as the push it runs.

    The lookup happens in the directory the call runs in, after `cd` and
    `git -C`, and follows a chain of aliases to its end. A shell alias
    (`!...`), a chain past MAX_ALIAS_DEPTH or an alias that cannot be split
    runs a command line the parser cannot see and is reported instead.
    """
    cache = {}
    resolved = []
    for argv, directory in parsed.calls:
        for _ in range(MAX_ALIAS_DEPTH + 1):
            split = git_global_options(argv)
            if split is None or not split[1] or split[1][0] in KNOWN_GIT_COMMANDS or not ALIAS_NAME.match(split[1][0]):
                resolved.append((argv, directory))
                break
            # git matches alias names without regard to case.
            subcommand = split[1][0]
            git_directory = git_call(argv, directory)[2]
            aliases = alias_map(git_directory, git_location_options(argv), git_config_overrides(argv), cache)
            if aliases is None:
                parsed.skip("an alias set through --config-env")
                parsed.hidden = True
                break
            value = aliases.get(subcommand.lower())
            if value is None:
                resolved.append((argv, directory))
                break
            try:
                words = shlex.split(value) if not value.startswith("!") else None
            except ValueError:
                words = None
            if not words:
                parsed.skip("a shell alias (%s)" % subcommand)
                parsed.hidden = True
                break
            head = argv[:len(argv) - len(split[1])]
            argv = head + words + split[1][1:]
        else:
            parsed.skip("an alias chain deeper than %d" % MAX_ALIAS_DEPTH)
            parsed.hidden = True
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
