"""The guards the Bash PreToolUse hook runs, and what they share.

A guard is a module with a NAME and a check(context) function that returns
None to allow the call, Deny(lines) to block it, or Ask(reason) to have the
host confirm it. The dispatcher in ../guard.py parses the payload once and
hands every guard the same Context. A guard judges the plain commands the
parser followed; the dispatcher itself asks about anything outside the
parser's grammar, so no guard needs a fallback of its own for such a line.
"""

import os
import stat

from command_lines import parse, start_directory

def safe_text(text, limit=120):
    """Text from a repository or a tool, made fit for a reason the model reads: printable ASCII, cut to `limit`."""
    cleaned = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in str(text))
    return cleaned if len(cleaned) <= limit else cleaned[:limit - 3] + "..."


# A file a command names is read for inspection only. A device, a FIFO or
# a socket would block or never end, and a guard runs before the owner has
# approved the command that names it, so only a regular file is read, and
# only this much of it.
MAX_READ_BYTES = 1_000_000


def read_text(path, limit=MAX_READ_BYTES):
    """(text, complete) for the first `limit` bytes of a regular file, or None.

    None for a missing path, a directory, a device, a FIFO, a socket or a
    read error. `complete` is False when the file was longer than `limit`.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        # Checked on the open descriptor, so a path swapped for a FIFO between
        # a stat and the open cannot block the read.
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            data = handle.read(limit + 1)
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return data[:limit].decode("utf-8", errors="replace"), len(data) <= limit


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
        return self._parsed

    @property
    def calls(self):
        """(argv, directory) for every plain command the parser followed."""
        return self.parsed.calls

    @property
    def unfollowed(self):
        """The constructs on the line outside the parser's grammar, each named once."""
        return self.parsed.unfollowed
