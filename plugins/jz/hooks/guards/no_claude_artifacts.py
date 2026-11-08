"""Deny any git call that would stage or commit a Claude Code working artifact.

The decision is delegated to git: the arguments are replayed through
`git add --dry-run` and `git commit --dry-run --porcelain`, and the paths git
reports are matched against the forbidden pattern. Deciding what a token
means by how it is spelled cannot survive globs, pathspec magic, parent
directories or `-A`; asking git costs one process and resolves all of them.
A dry run touches neither the index nor the object store and runs no hooks.
"""

import os
import re
import subprocess

from command_lines import git_call
from guards import Deny

NAME = "no-claude-artifacts"

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


def plan_checks(calls):
    """Collect every git add, stage or commit the command line would run.

    The shared parser resolves each command's directory, so a leading `cd`
    and a `git -C` are judged where they point.
    """
    checks = []
    for argv, command_directory in calls:
        call = git_call(argv, command_directory)
        if call is None:
            continue
        subcommand, args, git_directory = call
        if subcommand in STAGING_SUBCOMMANDS:
            checks.append(("add", git_directory, args))
        elif subcommand == "commit":
            checks.append(("commit", git_directory, args))
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


def staged_by_add(directory, args):
    """Ask git which paths `git add` with these arguments would put in the index."""
    result = run_git(directory, ["add", "--dry-run"]
                     + drop_flags(args, ADD_FLAGS_DROPPED, ADD_LETTERS_DROPPED))
    return [match.group(1) for match in
            (ADD_REPORT.match(line) for line in result.stdout.splitlines()) if match]


def patch_mode(args):
    return any(token in ("-p", "--patch")
               or (SHORT_CLUSTER.match(token) and "p" in token[1:]) for token in args)


def committed_by_commit(directory, args):
    """Ask git which paths `git commit` with these arguments would record."""
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
    lines = ["Blocked: this would stage or commit Claude Code working artifacts.", ""]
    lines += ["  " + path for path in report]
    lines.append("")
    if unparsed:
        lines.append("git could not say which paths the command puts in play, so the working tree was checked instead.")
    lines += ["These paths are never committed. Unstage them first:",
              "  git reset HEAD -- .claude docs/plans .plans",
              "and add them to .gitignore if they are not there already."]
    return Deny(*lines)


def forbidden(paths):
    return [path for path in paths if FORBIDDEN.search(path)]

def check(context):
    if "git" not in context.command:
        return None
    try:
        offenders = []
        unparsed = False
        for kind, check_directory, args in plan_checks(context.calls):
            if not is_repository(check_directory):
                continue
            resolve = staged_by_add if kind == "add" else committed_by_commit
            try:
                offenders.extend(forbidden(resolve(check_directory, args)))
            except Unresolvable:
                unparsed = True
                offenders.extend(forbidden(dirty_paths(check_directory)))
        if offenders:
            return deny(offenders, unparsed)
    except (GitMissing, Unresolvable):
        # No git, or even the fallback could not run. Nothing observed, nothing to block.
        pass
    return None
