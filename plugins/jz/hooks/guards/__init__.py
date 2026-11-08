"""The guards the Bash PreToolUse hook runs, and what they share.

A guard is a module with a NAME and a check(context) function that returns
None to allow the call, Deny(lines) to block it, or Ask(reason) to have the
host confirm it. The dispatcher in ../guard.py parses the payload once and
hands every guard the same Context.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command_lines import commands_with_directory, start_directory  # noqa: E402


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
        self.event = event if isinstance(event, dict) else {}
        tool_input = self.event.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        self.command = command if isinstance(command, str) else ""
        cwd = self.event.get("cwd")
        self.cwd = cwd if isinstance(cwd, str) else ""
        self.transcript_path = self.event.get("transcript_path")
        self.start = start_directory(self.cwd)
        self._calls = None
        self._parsed = False

    @property
    def calls(self):
        """(argv, via_xargs, directory) for every simple command, or None when the line cannot be lexed."""
        if not self._parsed:
            self._parsed = True
            try:
                self._calls = list(commands_with_directory(self.command, self.start))
            except ValueError:
                self._calls = None
        return self._calls
