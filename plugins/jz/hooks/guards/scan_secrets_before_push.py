"""Ask before a push whose unpublished commits carry something that looks like a secret.

A branch push no longer waits for the owner, and a pushed commit cannot be
scrubbed: GitHub keeps it retrievable by sha after the branch is deleted.
This scan is the last look before content goes public.

The commits scanned are the ones reachable from HEAD in the command's
repository but from no remote-tracking ref, whatever the push line says
about refspecs. Merge commits are rendered against their first parent, with
external diff drivers and textconv off. The patches and messages go to
betterleaks when it is on PATH, else to gitleaks, since both read stdin and
share their config files; with neither installed a small builtin set of
token shapes runs instead. Nothing is installed. A finding asks, naming the
rule, the commit and the file; when the scan cannot run, the guard asks
rather than guessing.
"""

import json
import os
import re
import shutil
import subprocess

from guards import Ask

NAME = "scan-secrets-before-push"

SCANNERS = ("betterleaks", "gitleaks")
SCANNER_FINDINGS_EXIT = 3
CONFIG_FILES = (".betterleaks.toml", ".gitleaks.toml")
MAX_FINDINGS_NAMED = 5
SCAN_TIMEOUT_SECONDS = 40

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


def safe_text(text, limit=120):
    cleaned = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in str(text))
    return cleaned if len(cleaned) <= limit else cleaned[:limit - 3] + "..."


def unpublished_patch(context):
    """The patches and messages of HEAD's commits on no remote: text, "" when there are none, None when git failed."""
    listed = context.git("rev-list", "HEAD", "--not", "--remotes")
    if listed is None:
        return None
    if not listed:
        return ""
    return context.git("log", "--no-color", "-p", "--diff-merges=first-parent", "--no-ext-diff", "--no-textconv",
                       "--no-show-signature", "--format=commit %h%n%B", "HEAD", "--not", "--remotes")


def locate(lines, line_number):
    """The commit and file a line of the patch stream belongs to."""
    commit = file_path = None
    for text in reversed(lines[:line_number]):
        if file_path is None and text.startswith("diff --git a/"):
            file_path = text[len("diff --git a/"):].split(" b/", 1)[0]
        if text.startswith("commit "):
            commit = text.split(" ", 1)[1]
            break
    return "%s in commit %s" % ("the message" if file_path is None else file_path, commit or "?")


def scanner_config(directory):
    for name in CONFIG_FILES:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return ["-c", path]
    return []


def scan_with(tool, directory, patch):
    """Run an installed scanner over the patch stream. Returns (findings, error)."""
    command = [tool, "stdin", "--no-banner", "--no-color", "--redact", "--report-format", "json",
               "--report-path", "-", "--exit-code", str(SCANNER_FINDINGS_EXIT)] + scanner_config(directory)
    try:
        result = subprocess.run(command, input=patch, capture_output=True, text=True, errors="replace",
                                timeout=SCAN_TIMEOUT_SECONDS, cwd=directory)
    except Exception as failure:
        return [], "%s could not run: %s" % (tool, failure)
    if result.returncode == 0:
        return [], None
    if result.returncode != SCANNER_FINDINGS_EXIT:
        tail = result.stderr.strip().splitlines()[-1:] or ["no output"]
        return [], "%s exited %d: %s" % (tool, result.returncode, safe_text(tail[0]))
    try:
        report = json.loads(result.stdout or "[]")
    except ValueError:
        return [], "%s reported findings but its report could not be read" % tool
    lines = patch.splitlines()
    findings = ["%s at %s" % (safe_text(entry.get("RuleID") or entry.get("Description") or "secret", 60),
                              safe_text(locate(lines, entry.get("StartLine") or 0))) for entry in report]
    return findings or ["%s reported findings" % tool], None


def scan_builtin(patch):
    lines = patch.splitlines()
    findings = []
    for number, text in enumerate(lines, start=1):
        if ALLOW_COMMENT.search(text):
            continue
        for rule, pattern in BUILTIN_RULES:
            if pattern.search(text):
                findings.append("%s at %s" % (rule, safe_text(locate(lines, number))))
                break
    return findings


def incomplete(error):
    return Ask("The secret scan did not complete (" + error + "), so the commits this push would publish are unscanned. "
               "Confirm the push or fix the cause.")


def check(context):
    if not context.runs("git", "push") or context.flag(r"--dry-run|-n"):
        return None
    patch = unpublished_patch(context)
    if patch is None:
        return incomplete("git could not list or show the unpublished commits")
    if not patch:
        return None
    tool = next((name for name in SCANNERS if shutil.which(name)), None)
    if tool:
        findings, error = scan_with(tool, context.cwd, patch)
        if error:
            return incomplete(error)
        source = tool
    else:
        findings = scan_builtin(patch)
        source = "the builtin shapes (no betterleaks or gitleaks on PATH)"
    if not findings:
        return None
    named = "; ".join(findings[:MAX_FINDINGS_NAMED])
    more = "" if len(findings) <= MAX_FINDINGS_NAMED else "; and %d more" % (len(findings) - MAX_FINDINGS_NAMED)
    return Ask("Possible secret in the commits this push would publish, found by %s: %s%s. "
               "A pushed commit stays retrievable by sha even after the branch is deleted. "
               "Confirm only if these are not credentials." % (source, named, more))
