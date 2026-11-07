#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# Scans the commits a `git push` would publish for secrets before they leave
# the machine. A branch push no longer waits for the owner, and a pushed commit
# cannot be scrubbed: GitHub keeps it retrievable by sha after the branch is
# deleted. This scan is the last look before content goes public.
#
# Git itself says what the push would publish: `git push --dry-run --porcelain`
# with the same arguments resolves configured refspecs, push.default,
# wildcards and the destination, and reports each ref's old tip there. The
# commits scanned are the ones reachable from the pushed refs but not from
# those tips nor from that one remote's tracking refs; another remote having a
# commit does not make it public here. Merge commits are rendered against their
# first parent, so a secret introduced in a conflict resolution is in the
# stream. The patches and messages are piped to betterleaks when it is on
# PATH, else to gitleaks, since both read stdin and share their config files;
# with neither installed a small builtin set of token shapes runs instead.
# Nothing is installed by this hook. A finding produces an "ask" decision that
# names the rule, the commit and the file, so a fixture that looks like a key
# is a question for the owner, never a wall. When git cannot say what the push
# publishes, the hook asks rather than guessing.
#
# The preview is forced into a dry run after every option the caller passed,
# read with the option table of git push so a value such as -o -- or -o -n is
# a value and not a terminator or a flag, so no caller argument can turn it
# into a real push, and it carries the caller's
# -c, --config-env, --git-dir, --work-tree and --namespace options, so it
# describes the destination and refs the real push will use. A remote's
# tracking refs count as published only when the push goes to that remote's
# fetch URL; a pushurl is another repository.
#
# The command line is split by command_lines.py, the parser every hook shares,
# and each push is scanned in the repository it targets, after any `cd` or
# `git -C`.
#
# Reads the PreToolUse event JSON on stdin. Prints an "ask" decision for a
# push with findings and nothing otherwise. Always exits 0: the decision is in
# the output, and a hook failure must never block an ordinary Bash call.
set -uo pipefail

payload="$(cat)"

# Cheap pre-filter, so an ordinary shell call does not pay for a python start-up.
case "$payload" in
  *push*) ;;
  *) exit 0 ;;
esac

command -v python3 >/dev/null 2>&1 || exit 0

inspector="$(cat <<'PY'
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, sys.argv[1])
from command_lines import commands_with_directory, git_call, git_repository_options, start_directory  # noqa: E402
from git_push import dry_run_updates, run_git, walk_push_options  # noqa: E402

SCANNERS = ("betterleaks", "gitleaks")
SCANNER_FINDINGS_EXIT = 3
CONFIG_FILES = (".betterleaks.toml", ".gitleaks.toml")
MAX_FINDINGS_NAMED = 5
# The summary of a porcelain update line holds the old tip at the destination
# as old..new, or old...new for a forced update.
SUMMARY_RANGE = re.compile(r"^([0-9a-f]+)\.\.\.?([0-9a-f]+)")
SKIPPED_FLAGS = set("-=!")
SCAN_TIMEOUT_SECONDS = 50

# Fallback shapes, used only when no scanner is on PATH. Each is a well-known
# token prefix or a key block rather than a bare high-entropy string, so the
# fallback stays quiet on ordinary code and loud on the credentials that leak.
BUILTIN_RULES = [
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{82}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("stripe-live-key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{24,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("generic-credential", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['\"][A-Za-z0-9_\-/+=]{20,}['\"]")),
]
ALLOW_COMMENT = re.compile(r"(?:betterleaks|gitleaks):allow")
# When the line cannot be lexed at all, lean towards asking.
RAW_PUSH = re.compile(r"\bgit\b.*\bpush\b")


def remote_tracking(directory, options, url):
    """The remote whose tracking refs describe the destination, else None.

    Tracking refs are filled from the fetch URL of a remote, so they say what is at
    the destination only when the push goes to that same URL. A pushurl
    override sends the push elsewhere, and nothing local describes that.
    """
    listed = run_git(directory, options, ["remote"])
    if listed is None or listed.returncode != 0:
        return None
    for name in listed.stdout.split():
        fetch_url = run_git(directory, options, ["remote", "get-url", name])
        if fetch_url is not None and fetch_url.returncode == 0 and fetch_url.stdout.strip() == url:
            return name
    return None


def commit_of(directory, options, ref):
    out = run_git(directory, options, ["rev-parse", "--verify", "--quiet", ref + "^{commit}"])
    if out is None or out.returncode != 0:
        return None
    return out.stdout.strip()


def is_known_commit(directory, options, sha):
    out = run_git(directory, options, ["cat-file", "-e", sha + "^{commit}"])
    return out is not None and out.returncode == 0


def published_revisions(directory, options, url, updates):
    """rev-list arguments for the commits the push would make public at the destination.

    Deleted, up-to-date and rejected refs publish nothing. The old tips at the
    destination and its remote-tracking refs are excluded; a tip git reported but
    this clone has never fetched cannot be excluded, so more is scanned.
    """
    revisions = []
    exclusions = []
    for flag, source, _, summary in updates:
        if flag in SKIPPED_FLAGS or not source:
            continue
        sha = commit_of(directory, options, source)
        if sha is None:
            return None, "cannot resolve the pushed ref %s to a commit" % source
        revisions.append(sha)
        match = SUMMARY_RANGE.match(summary)
        if match and is_known_commit(directory, options, match.group(1)):
            exclusions.append(match.group(1))
    if not revisions:
        return [], None
    arguments = revisions + ["--not"] + exclusions
    remote = remote_tracking(directory, options, url)
    if remote:
        arguments.append("--remotes=" + remote)
    return arguments, None


def unpublished_patch(directory, options, revision_arguments):
    """The patches and messages of the selected commits: text, or empty when there are none."""
    listed = run_git(directory, options, ["rev-list"] + revision_arguments)
    if listed is None or listed.returncode != 0:
        tail = ((listed.stderr.strip().splitlines() if listed else []) or ["no output"])[-1]
        return None, "git rev-list failed: " + tail
    if not listed.stdout.strip():
        return "", None
    shown = run_git(directory, options, ["log", "--no-color", "-p", "--diff-merges=first-parent",
                                "--format=commit %h%n%B"] + revision_arguments)
    if shown is None or shown.returncode != 0:
        tail = ((shown.stderr.strip().splitlines() if shown else []) or ["no output"])[-1]
        return None, "git log failed: " + tail
    return shown.stdout, None


def locate(lines, line_number):
    """The commit and file a line of the patch stream belongs to."""
    commit = file_path = None
    for text in reversed(lines[:line_number]):
        if file_path is None and text.startswith("diff --git a/"):
            file_path = text[len("diff --git a/"):].split(" b/", 1)[0]
        if text.startswith("commit "):
            commit = text.split(" ", 1)[1]
            break
    where = "the message" if file_path is None else file_path
    return "%s in commit %s" % (where, commit or "?")


def scanner_config(directory):
    for name in CONFIG_FILES:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return ["-c", path]
    return []


def scan_with(tool, directory, patch):
    """Run an installed scanner over the patch stream. Returns (findings, error)."""
    command = [tool, "stdin", "--no-banner", "--no-color", "--redact",
               "--report-format", "json", "--report-path", "-",
               "--exit-code", str(SCANNER_FINDINGS_EXIT)] + scanner_config(directory)
    try:
        result = subprocess.run(command, input=patch, capture_output=True, text=True,
                                errors="replace", timeout=SCAN_TIMEOUT_SECONDS, cwd=directory)
    except Exception as failure:
        return [], "%s could not run: %s" % (tool, failure)
    if result.returncode == 0:
        return [], None
    if result.returncode != SCANNER_FINDINGS_EXIT:
        tail = result.stderr.strip().splitlines()[-1:] or ["no output"]
        return [], "%s exited %d: %s" % (tool, result.returncode, tail[0])
    try:
        report = json.loads(result.stdout or "[]")
    except ValueError:
        return [], "%s reported findings but its report could not be read" % tool
    lines = patch.splitlines()
    findings = []
    for entry in report:
        rule = entry.get("RuleID") or entry.get("Description") or "secret"
        line_number = entry.get("StartLine") or 0
        findings.append("%s at %s" % (rule, locate(lines, line_number)))
    return findings or ["%s reported findings" % tool], None


def scan_builtin(patch):
    lines = patch.splitlines()
    findings = []
    for number, text in enumerate(lines, start=1):
        if ALLOW_COMMENT.search(text):
            continue
        for rule, pattern in BUILTIN_RULES:
            if pattern.search(text):
                findings.append("%s at %s" % (rule, locate(lines, number)))
                break
    return findings


def ask(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }))


def scan_incomplete(error):
    return ("The secret scan did not complete (" + error + "), so the commits this push would "
            "publish are unscanned. Confirm the push or fix the cause.")


def reason_for_push(directory, options, args):
    walk = walk_push_options(args)
    if walk.error:
        return scan_incomplete(walk.error)
    if walk.dry_run:
        return None
    url, updates, error = dry_run_updates(directory, options, args)
    if error:
        return scan_incomplete(error)
    revision_arguments, error = published_revisions(directory, options, url, updates)
    if error:
        return scan_incomplete(error)
    if not revision_arguments:
        return None
    patch, error = unpublished_patch(directory, options, revision_arguments)
    if error:
        return scan_incomplete(error)
    if not patch:
        return None
    tool = next((name for name in SCANNERS if shutil.which(name)), None)
    if tool:
        findings, error = scan_with(tool, directory, patch)
        if error:
            return scan_incomplete(error)
        source = tool
    else:
        findings = scan_builtin(patch)
        source = "the builtin shapes (no betterleaks or gitleaks on PATH)"
    if not findings:
        return None
    named = "; ".join(findings[:MAX_FINDINGS_NAMED])
    more = "" if len(findings) <= MAX_FINDINGS_NAMED else "; and %d more" % (len(findings) - MAX_FINDINGS_NAMED)
    return ("Possible secret in the commits this push would publish, found by %s: %s%s. "
            "A pushed commit stays retrievable by sha even after the branch is deleted. "
            "Confirm only if these are not credentials." % (source, named, more))


try:
    event = json.load(sys.stdin)
    command = event.get("tool_input", {}).get("command", "")
    cwd = event.get("cwd", "")
except Exception:
    sys.exit(0)
if not isinstance(command, str):
    sys.exit(0)
start = start_directory(cwd)

try:
    for argv, _, directory in commands_with_directory(command, start):
        call = git_call(argv, directory)
        if call is None or call[0] != "push":
            continue
        reason = reason_for_push(call[2], git_repository_options(argv), call[1])
        if reason:
            ask(reason)
            break
except ValueError:
    if RAW_PUSH.search(command):
        ask("The command could not be parsed and looks like a push, so its commits were not scanned for secrets; confirm first.")
PY
)"

printf '%s' "$payload" | python3 -B -c "$inspector" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exit 0
