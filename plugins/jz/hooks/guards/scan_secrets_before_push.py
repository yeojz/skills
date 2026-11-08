"""Ask before a push whose commits carry something that looks like a secret.

A branch push no longer waits for the owner, and a pushed commit cannot be
scrubbed: GitHub keeps it retrievable by sha after the branch is deleted.
This scan is the last look before content goes public.

Which refs the push would update is read from the repository alone, by
git_push.resolve_push. The commits scanned are the ones reachable from the
pushed refs but not from that remote's tracking refs; when the destination
is a URL, or the remote has a pushurl, every remote's refs are excluded
instead. Merge commits are rendered against their first parent, with
external diff drivers and textconv off. The patches and messages go to
betterleaks when it is on PATH, else to gitleaks, since both read stdin and
share their config files; with neither installed a small builtin set of
token shapes runs instead. Nothing is installed. A finding asks, naming the
rule, the commit and the file, so a fixture that looks like a key is a
question for the owner, never a wall. When the push cannot be resolved, the
guard asks rather than guessing.
"""

import json
import os
import re
import shutil
import subprocess

from command_lines import git_call, git_config_overrides, git_location_options
from git_push import resolve_commit, resolve_push, run_git, unfollowed_config_override
from guards import Ask

NAME = "scan-secrets-before-push"

SCANNERS = ("betterleaks", "gitleaks")
SCANNER_FINDINGS_EXIT = 3
CONFIG_FILES = (".betterleaks.toml", ".gitleaks.toml")
MAX_FINDINGS_NAMED = 5
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


def published_revisions(directory, options, push):
    """rev-list arguments for the commits the push would make public at the destination.

    A deletion publishes nothing. The tracking refs of the destination remote
    are excluded; when nothing local describes the destination, every
    remote's refs are.
    """
    revisions = []
    for source, _ in push.updates:
        if source is None:
            continue
        sha = resolve_commit(directory, options, source)
        if sha is None:
            return None, "cannot resolve the pushed ref %s to a commit" % source
        revisions.append(sha)
    if not revisions:
        return [], None
    excluded = "--remotes=" + push.remote if push.tracked else "--remotes"
    return revisions + ["--not", excluded], None


def unpublished_patch(directory, options, revision_arguments):
    """The patches and messages of the selected commits: text, or empty when there are none."""
    listed = run_git(directory, options, ["rev-list"] + revision_arguments)
    if listed is None or listed.returncode != 0:
        tail = ((listed.stderr.strip().splitlines() if listed else []) or ["no output"])[-1]
        return None, "git rev-list failed: " + tail
    if not listed.stdout.strip():
        return "", None
    shown = run_git(directory, options, ["log", "--no-color", "-p", "--diff-merges=first-parent",
                                "--no-ext-diff", "--no-textconv", "--no-show-signature",
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


def scan_incomplete(error):
    return ("The secret scan did not complete (" + error + "), so the commits this push would "
            "publish are unscanned. Confirm the push or fix the cause.")


def reason_for_push(directory, options, args, config_overrides):
    override = unfollowed_config_override(config_overrides)
    if override:
        return scan_incomplete("the push carries %s, a command-line configuration override the hook does not follow; "
                               "put the setting in the repository's configuration" % override)
    push, error = resolve_push(directory, options, args)
    if error:
        return scan_incomplete(error)
    if push.dry_run:
        return None
    revision_arguments, error = published_revisions(directory, options, push)
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


def check(context):
    if "push" not in context.command:
        return None
    if context.calls is None:
        if RAW_PUSH.search(context.command):
            return Ask("The command could not be parsed and looks like a push, so its commits were not scanned for secrets; confirm first.")
        return None
    for argv, _, directory in context.calls:
        call = git_call(argv, directory)
        if call is None or call[0] != "push":
            continue
        reason = reason_for_push(call[2], git_location_options(argv), call[1], git_config_overrides(argv))
        if reason:
            return Ask(reason)
    return None
