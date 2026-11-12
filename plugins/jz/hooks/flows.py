"""Find the flows running in a session's working directory, for the
compaction hooks.

A flow (coordinate, factory, handsfree, intake, implement) keeps its state in
a folder under docs/plans/ and overwrites that folder's next.md at every step
boundary. next.md is a handful of `key: value` lines:

    flow: coordinate
    state: running
    cwd: /abs/path/of/the/owning/session
    step: Step 5, unit 03
    next: brief the reviewer for unit 03
    resume: column -t -s $'\\t' docs/plans/x/units.tsv
    updated: 2026-11-12T14:05

A folder is active when its next.md says a state other than `done`, names
this session's working directory (or names none), and changed in the last
week. Everything here is read-only and bounded, and any failure prints
nothing, because a hook that only adds context must never stop compaction or
a session start.

Usage: flows.py pre-compact | after-compact, with the hook payload on stdin.
"""

import glob
import json
import os
import subprocess
import sys
import time

KEYS = ("flow", "state", "cwd", "step", "next", "resume", "updated")
MAX_FLOWS = 5
MAX_LINES = 20
MAX_VALUE = 300
MAX_AGE = 7 * 24 * 3600
READ_ONLY = {"ls", "cat", "tail", "head", "column", "wc", "grep"}
UNSAFE = ("|", "&", "<", ">", "`", "$(", "\n")
WITHHELD = "(withheld: not a read-only command; read next.md and decide)"


def clean(text):
    """Keep printable text only and cap its length."""
    text = "".join(ch for ch in text if ch == "\t" or ch.isprintable())
    return text.strip()[:MAX_VALUE]


def read_next(path):
    fields = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for _, line in zip(range(MAX_LINES), handle):
                key, sep, value = line.partition(":")
                key = key.strip().lower()
                if sep and key in KEYS and key not in fields:
                    fields[key] = clean(value)
    except OSError:
        return None
    return fields


def read_only(command):
    """True when every `;`-separated part is a plain read-only command.

    next.md is repository text, and the session is told to run `resume`, so a
    planted file must not smuggle a write or a network call through it.
    """
    if not command or any(mark in command for mark in UNSAFE):
        return False
    for part in command.split(";"):
        words = part.split()
        if not words:
            return False
        head = words[0]
        if head in READ_ONLY:
            continue
        if head == "git" and len(words) > 1 and words[1] in ("status", "log"):
            continue
        if head.strip('"\'').endswith("/scripts/job") and words[1:] == ["next"]:
            continue
        return False
    return True


def git(cwd, *args):
    try:
        done = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def same_dir(left, right):
    try:
        return os.path.realpath(left) == os.path.realpath(right)
    except (OSError, ValueError):
        return False


def active_flows(cwd):
    root = git(cwd, "rev-parse", "--show-toplevel") or cwd
    now = time.time()
    found = []
    for path in glob.glob(os.path.join(root, "docs", "plans", "*", "next.md")):
        try:
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if now - mtime > MAX_AGE:
            continue
        fields = read_next(path)
        if not fields or fields.get("state", "running") == "done":
            continue
        if fields.get("cwd") and not same_dir(fields["cwd"], cwd):
            continue
        if "resume" in fields and not read_only(fields["resume"]):
            fields["resume"] = WITHHELD
        fields["folder"] = os.path.relpath(os.path.dirname(path), root)
        found.append((mtime, fields))
    found.sort(key=lambda item: item[0], reverse=True)
    return [fields for _, fields in found[:MAX_FLOWS]]


def describe(flow):
    lines = ["- %s, folder `%s`, state %s" % (
        flow.get("flow", "unknown flow"), flow["folder"], flow.get("state", "running"))]
    for key in ("step", "next", "resume"):
        if flow.get(key):
            lines.append("  %s: %s" % (key, flow[key]))
    return "\n".join(lines)


def pre_compact(cwd, flows):
    branch = git(cwd, "branch", "--show-current") or "(detached or not a repository)"
    status = git(cwd, "status", "-sb").splitlines()
    out = [
        "Write the summary so the work can continue from files on disk.",
        "Keep: the branch (%s, %s), the task list with what is done and what remains, "
        "every decision agreed in this conversation with its options, marking any that is "
        "not yet in its folder's decisions.tsv as unlogged, and every question the owner "
        "still owes. Drop tool output and exploration that led nowhere."
        % (branch, status[0] if status else "no status"),
    ]
    if flows:
        out.append("Active flows, each resumed from its folder rather than from this summary:")
        out.extend(describe(flow) for flow in flows)
    return "\n".join(out)


def after_compact(cwd, flows):
    out = [
        "Context was just compacted. Before the next action, run `git status -sb` "
        "and confirm the branch. Append any decision the summary marks unlogged to "
        "its folder's decisions.tsv before continuing."
    ]
    if flows:
        out.append("Resume these flows from disk, not from the summary: read each "
                   "folder's next.md, then run its resume command, which this hook "
                   "has checked is read-only.")
        out.extend(describe(flow) for flow in flows)
    return "\n".join(out)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        cwd = os.getcwd()
    flows = active_flows(cwd)
    if mode == "pre-compact":
        print(pre_compact(cwd, flows))
    elif mode == "after-compact":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": after_compact(cwd, flows),
            }
        }))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # A context-only hook never blocks compaction or a session start.
        pass
    sys.exit(0)
