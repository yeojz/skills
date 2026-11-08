#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# Blocks any git call that would stage or commit Claude Code working artifacts.
# These stay local and never reach a commit.
#
# The decision is delegated to git. The arguments of the command are replayed
# through `git add --dry-run` and `git commit --dry-run --porcelain`, and the
# paths git reports are matched against the forbidden pattern. Deciding what a
# token means by how it is spelled cannot survive globs, pathspec magic, parent
# directories or `-A`; asking git costs one process and resolves all of them.
# A dry run touches neither the index nor the object store and runs no hooks.
#
# Reads the PreToolUse event JSON on stdin. Exit 0 allows, exit 2 denies.
set -uo pipefail

payload="$(cat)"

# Cheap pre-filter, so an ordinary shell call does not pay for a python start-up.
case "$payload" in
  *git*) ;;
  *) exit 0 ;;
esac

# Deny rather than fail open, but only for calls that mention git: a missing
# interpreter must not block every Bash call in the session.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Blocked: no-claude-artifacts hook needs python3 on PATH to inspect git calls." >&2
  exit 2
fi

inspector="$(cat <<'PY'
"""Decide whether a Bash tool call would stage or commit a Claude working artifact.

Reads the PreToolUse payload on stdin. Exits 2 with a reason on stderr to deny
the call, exits 0 to allow it.
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, sys.argv[1])
from command_lines import commands_with_directory, git_call, start_directory  # noqa: E402

FORBIDDEN = re.compile(r"(^|/)(\.claude|docs/plans|\.plans)(/|$)")

GIT_TIMEOUT_SECONDS = 5
MAX_REPORTED = 20

SHORT_CLUSTER = re.compile(r"^-[A-Za-z]+$")

STAGING_SUBCOMMANDS = {"add", "stage"}

# --dry-run refuses to run beside these, and none of them change which paths the
# command puts in play.
ADD_FLAGS_DROPPED = {"--dry-run", "--interactive", "--patch", "--edit", "--verbose"}
ADD_LETTERS_DROPPED = "nipev"
# These would reshape the porcelain report this hook has to read.
COMMIT_FLAGS_DROPPED = {"--dry-run", "--porcelain", "--patch", "--short", "--long", "--null"}
COMMIT_LETTERS_DROPPED = "pz"

ADD_REPORT = re.compile(r"^(?:add|remove) '(.*)'$")
STAGED_STATUS = "MADRCU"


class GitMissing(Exception):
    """git is not on PATH, so no command in this call can stage anything."""


class Unresolvable(Exception):
    """git could not answer for this call, so the working tree is all we have."""


def plan_checks(command_line, directory):
    """Collect every git add, stage or commit the command line would run.

    The shared parser resolves each command's directory, so a leading `cd`,
    a `bash -c` script and a `-C` held in a shell variable are judged where
    they point.
    """
    checks = []
    for argv, via_xargs, command_directory in commands_with_directory(command_line, directory):
        call = git_call(argv, command_directory)
        if call is None:
            continue
        subcommand, args, git_directory = call
        if subcommand in STAGING_SUBCOMMANDS:
            checks.append(("add", git_directory, args, via_xargs))
        elif subcommand == "commit":
            checks.append(("commit", git_directory, args, via_xargs))
    return checks


def run_git(directory, args):
    """Run one read-only git call under a timeout, with locks and pager off."""
    environment = dict(os.environ,
                       GIT_OPTIONAL_LOCKS="0",
                       GIT_PAGER="cat",
                       GIT_EDITOR="true",
                       GIT_TERMINAL_PROMPT="0")
    try:
        return subprocess.run(["git", "--no-pager", "-C", directory] + args,
                              stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              text=True,
                              env=environment,
                              timeout=GIT_TIMEOUT_SECONDS)
    except FileNotFoundError:
        raise GitMissing()
    except (subprocess.TimeoutExpired, OSError):
        raise Unresolvable()


def drop_flags(args, long_flags, letters):
    """Remove flags that a dry run refuses, keeping every pathspec and value."""
    kept = []
    for token in args:
        if token in long_flags:
            continue
        if SHORT_CLUSTER.match(token):
            remainder = "".join(c for c in token[1:] if c not in letters)
            if remainder:
                kept.append("-" + remainder)
            continue
        kept.append(token)
    return kept


def is_repository(directory):
    return run_git(directory, ["rev-parse", "--git-dir"]).returncode == 0


def has_pathspec(args):
    return any(not token.startswith("-") for token in args if token != "--")


def staged_by_add(directory, args, via_xargs):
    """Ask git which paths `git add` with these arguments would put in the index."""
    if via_xargs and not has_pathspec(args):
        raise Unresolvable()
    result = run_git(directory, ["add", "--dry-run"]
                     + drop_flags(args, ADD_FLAGS_DROPPED, ADD_LETTERS_DROPPED))
    return [match.group(1) for match in
            (ADD_REPORT.match(line) for line in result.stdout.splitlines()) if match]


def patch_mode(args):
    return any(token in ("-p", "--patch")
               or (SHORT_CLUSTER.match(token) and "p" in token[1:]) for token in args)


def committed_by_commit(directory, args, via_xargs):
    """Ask git which paths `git commit` with these arguments would record."""
    if via_xargs and not has_pathspec(args):
        raise Unresolvable()
    result = run_git(directory, ["commit", "--dry-run", "--porcelain"]
                     + drop_flags(args, COMMIT_FLAGS_DROPPED, COMMIT_LETTERS_DROPPED))
    # Column one is the index status. An untracked (??) or worktree-only ( M)
    # entry is reported but would not be committed, unless -p is picking hunks
    # straight out of the working tree.
    columns = (0, 1) if patch_mode(args) else (0,)
    paths = []
    for line in result.stdout.splitlines():
        if len(line) > 3 and any(line[column] in STAGED_STATUS for column in columns):
            paths.extend(unquote(part) for part in line[3:].split(" -> "))
    return paths


def dirty_paths(directory):
    """Everything the working tree could contribute to a commit right now."""
    staged = run_git(directory, ["diff", "--cached", "--name-only"]).stdout.splitlines()
    status = run_git(directory, ["status", "--porcelain", "-uall"]).stdout.splitlines()
    return staged + [unquote(line[3:]) for line in status if len(line) > 3]


def unquote(path):
    if len(path) > 1 and path.startswith('"') and path.endswith('"'):
        return path[1:-1]
    return path


def deny(offenders, unparsed):
    report = sorted(set(offenders))[:MAX_REPORTED]
    print("Blocked: this would stage or commit Claude Code working artifacts.", file=sys.stderr)
    print(file=sys.stderr)
    for path in report:
        print("  " + path, file=sys.stderr)
    print(file=sys.stderr)
    if unparsed:
        print("The command could not be parsed, so the working tree was checked instead.",
              file=sys.stderr)
    print("These paths are never committed. Unstage them first:", file=sys.stderr)
    print("  git reset HEAD -- .claude docs/plans .plans", file=sys.stderr)
    print("and add them to .gitignore if they are not there already.", file=sys.stderr)
    sys.exit(2)


def forbidden(paths):
    return [path for path in paths if FORBIDDEN.search(path)]


def read_payload():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    cwd = payload.get("cwd")
    return (command if isinstance(command, str) else "",
            cwd if isinstance(cwd, str) else "")


def deny_if_any(offenders, unparsed):
    if offenders:
        deny(offenders, unparsed)


def main():
    command_line, cwd = read_payload()
    if "git" not in command_line:
        return
    directory = start_directory(cwd)

    try:
        checks = plan_checks(command_line, directory)
    except ValueError:
        # Unbalanced quotes. Fall back to the tree, and deny only a real offender.
        if is_repository(directory):
            deny_if_any(forbidden(dirty_paths(directory)), unparsed=True)
        return

    offenders = []
    unparsed = False
    for kind, check_directory, args, via_xargs in checks:
        if not is_repository(check_directory):
            continue
        resolve = staged_by_add if kind == "add" else committed_by_commit
        try:
            offenders.extend(forbidden(resolve(check_directory, args, via_xargs)))
        except Unresolvable:
            unparsed = True
            offenders.extend(forbidden(dirty_paths(check_directory)))
    deny_if_any(offenders, unparsed)


try:
    main()
except GitMissing:
    pass
except Unresolvable:
    # Even the fallback could not run. Nothing observed, nothing to block.
    pass
PY
)"

printf '%s' "$payload" | python3 -B -c "$inspector" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
