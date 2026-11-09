"""The guards the Bash PreToolUse hook runs, and what they share.

A guard is a module with a NAME and a check(context) function that returns
None to allow the call, Deny(lines) to block it, or Ask(reason) to have the
host confirm it. The dispatcher in ../guard.py hands every guard the same
Context.

A guard reads the command as text. It asks whether the line mentions `git`
or `gh` and the operation it cares about, as whole words, and nothing more:
no shell parsing, no option tables. A commit message that happens to say
"merge main" is denied until it is rephrased, which costs a retry and is
the safe side. What a guard needs to know about the repository it asks git
directly, in the directory the payload names, through one runner that
switches off every program the repository's own configuration could make
git run.
"""

import os
import re
import subprocess

# A whole word: not glued to a letter, digit, underscore or hyphen on either
# side, so `merge` is found in `git merge main` and not in `merge-base`.
def word(text):
    return re.compile(r"(?<![\w-])%s(?![\w-])" % re.escape(text))


GIT_OR_GH = re.compile(r"(?<![\w.-])(git|gh)(?![\w-])")
COMMON_DEFAULTS = ("main", "master", "develop", "trunk")
GIT_TIMEOUT_SECONDS = 10
# Configuration that would make a read-only git call run a program from the
# repository's own config: the filesystem monitor, signature display, hooks.
SAFE_CONFIG = ["-c", "core.fsmonitor=false", "-c", "log.showSignature=false", "-c", "core.hooksPath=/dev/null"]


class Deny:
    """Block the call. `lines` go to stderr, the first one the reason."""

    def __init__(self, *lines):
        self.lines = list(lines)


class Ask:
    """Have the host confirm the call, giving `reason`."""

    def __init__(self, reason):
        self.reason = reason


class Context:
    """The PreToolUse payload: the command text, where it runs, and the session transcript."""

    def __init__(self, event):
        event = event if isinstance(event, dict) else {}
        tool_input = event.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        self.text = command if isinstance(command, str) else ""
        self.transcript_path = event.get("transcript_path")
        self.cwd = start_directory(event.get("cwd"))
        self._branch = None

    def has(self, *words):
        """Whether the text names every word given, as whole words."""
        return all(word(text).search(self.text) for text in words)

    def runs(self, *words):
        """Whether the text mentions git or gh and every word given."""
        return bool(GIT_OR_GH.search(self.text)) and self.has(*words)

    def flag(self, pattern):
        """Whether an option spelled by `pattern` (a regex) stands on its own in the text."""
        return re.search(r"(?<!\S)(?:%s)(?!\S)" % pattern, self.text) is not None

    def git(self, *args):
        """The stripped output of a read-only git call in the command's directory, or None when it fails."""
        env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat", GIT_EDITOR="true")
        try:
            out = subprocess.run(["git", "--no-pager", "-C", self.cwd] + SAFE_CONFIG + list(args),
                                 stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                                 env=env, timeout=GIT_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    @property
    def branch(self):
        """The checked-out branch, or None when detached or outside a repository."""
        if self._branch is None:
            self._branch = self.git("symbolic-ref", "-q", "--short", "HEAD") or ""
        return self._branch or None

    def protected_branches(self):
        """main, master, develop, trunk, and whatever origin/HEAD names."""
        names = set(COMMON_DEFAULTS)
        head = self.git("symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
        if head:
            names.add(head.split("/", 1)[-1])
        return names


def start_directory(cwd):
    """The event's cwd, or its nearest existing ancestor when a removed worktree is still being named, else the process's own."""
    if isinstance(cwd, str) and cwd:
        here = os.path.abspath(cwd)
        while not os.path.isdir(here):
            parent = os.path.dirname(here)
            if parent == here:
                break
            here = parent
        return here
    try:
        return os.getcwd()
    except OSError:
        return os.sep
