"""Name the flows this session is running, for the compaction hooks.

A flow (coordinate, factory, handsfree, intake) keeps its state in a folder
under docs/plans/ and writes that folder's flow.md once, when the run starts:

    flow: coordinate
    state: running
    session: 2914f9c8-c61b-5d38-8391-ea86b5f612d7

The file marks the folder and holds nothing else. Where the run stands is in
the flow's own ledgers, and the way back in is the Resume paragraph of the
flow's skill. So the hooks print the flow's name, which is one of four known
words, and its folder's path, and no text from the file.

A folder is this session's when its marker says `running` and carries the
session id the hook payload carries. A marker anyone else wrote, in another
session or in a checked-out branch, never matches. Everything here is
read-only and bounded. The wrapper scripts turn any failure into exit 0 with
nothing printed, because a hook that only adds context must never stop
compaction or a session start.

Usage: flows.py pre-compact | after-compact, with the hook payload on stdin.
"""

import glob
import json
import os
import subprocess
import sys

FLOWS = ("coordinate", "factory", "handsfree", "intake")
MARKER = "flow.md"
MAX_FLOWS = 5
MAX_BYTES = 4096
MAX_BRANCH = 120
MAX_PATH = 300
GIT_TIMEOUT = 2
MARKUP = "-*#>` \t"


def plain(text, limit):
    """True for text that can be printed whole: printable and short enough.
    Anything else is left out rather than altered, since a cut path or branch
    names another."""
    return 0 < len(text) <= limit and text.isprintable()


def read_marker(path):
    """The marker's flow, state and session, tolerant of list and emphasis markup."""
    fields = {}
    try:
        with open(path, "rb") as handle:
            text = handle.read(MAX_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return fields
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip(MARKUP).lower()] = value.strip(MARKUP)
    return fields


def git(cwd, *args):
    try:
        done = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def roots(cwd):
    """Where a flow's folder can sit: the directory the session is in now, the
    one it started in, and the checkout each belongs to. The payload's cwd
    follows a `cd`, and CLAUDE_PROJECT_DIR does not."""
    found = []
    for start in (cwd, os.environ.get("CLAUDE_PROJECT_DIR")):
        if start and os.path.isdir(start):
            found.append(start)
            found.append(git(start, "rev-parse", "--show-toplevel"))
    return {os.path.realpath(root) for root in found if root}


def session_flows(cwd, session):
    if not isinstance(session, str) or not session:
        return []
    found = {}
    for root in roots(cwd):
        for path in glob.glob(os.path.join(root, "docs", "plans", "*", MARKER)):
            folder = os.path.dirname(path)
            if not plain(folder, MAX_PATH) or not os.path.isfile(path):
                continue
            fields = read_marker(path)
            flow = fields.get("flow", "").lower()
            if flow not in FLOWS or fields.get("state", "").lower() != "running":
                continue
            if fields.get("session") != session:
                continue
            found[folder] = (os.path.getmtime(path), flow)
    newest = sorted(found.items(), key=lambda item: item[1][0], reverse=True)
    return [(flow, folder) for folder, (_, flow) in newest[:MAX_FLOWS]]


def describe(flows):
    return ["- %s, folder `%s`" % (flow, folder) for flow, folder in flows]


def pre_compact(cwd, flows):
    branch = git(cwd, "branch", "--show-current")
    out = [
        "Write the summary so the work can continue from files on disk.",
        "Keep: the branch%s, the task list with what is done and what remains, "
        "every decision agreed in this conversation with its options, marking any that is "
        "not yet in its folder's decisions.tsv as unlogged, every question the owner "
        "still owes, and each run a skill is driving with its skill and its folder, spec "
        "or plan path. Drop tool output and exploration that led nowhere."
        % (" (%s)" % branch if plain(branch, MAX_BRANCH) else ""),
    ]
    if flows:
        out.append("Flows this session marked as running, each continued from its folder "
                   "rather than from this summary:")
        out.extend(describe(flows))
    return "\n".join(out)


def after_compact(flows):
    out = [
        "Context was compacted. The summary is a pointer and the files on disk are the "
        "record. `git status -sb` confirms the branch. A decision the summary marks "
        "unlogged goes into its folder's decisions.tsv before other work. A run the "
        "summary names continues from its folder: its skill is loaded again when its "
        "steps are no longer in context, and its Resume paragraph says how to pick up."
    ]
    if flows:
        out.append("This session marked these flows as running:")
        out.extend(describe(flows))
    return "\n".join(out)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        cwd = os.getcwd()
    flows = session_flows(cwd, payload.get("session_id"))
    if mode == "pre-compact":
        print(pre_compact(cwd, flows))
    elif mode == "after-compact":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": after_compact(flows),
            }
        }))


if __name__ == "__main__":
    main()
