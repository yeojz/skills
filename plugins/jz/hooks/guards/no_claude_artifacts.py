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
import shutil
import tempfile

from command_lines import SHORT_CLUSTER, git_call, git_location_options
from git_push import git_text, run_git
from guards import Ask, Deny, safe_text

NAME = "no-claude-artifacts"

FORBIDDEN = re.compile(r"(^|/)(\.claude|docs/plans|\.plans)(/|$)")

MAX_REPORTED = 20

STAGING_SUBCOMMANDS = {"add", "stage"}

# --dry-run refuses to run beside these, and none of them change which paths the
# command puts in play.
ADD_FLAGS_DROPPED = {"--dry-run", "--interactive", "--patch", "--edit", "--verbose"}
ADD_LETTERS_DROPPED = "nipev"
# These would reshape the porcelain report this guard has to read.
COMMIT_FLAGS_DROPPED = {"--dry-run", "--porcelain", "--patch", "--short", "--long", "--null"}
COMMIT_LETTERS_DROPPED = "pz"

ADD_REPORT = re.compile(r"^(?:add|remove) '(.*)'$")
STAGED_STATUS = "MADRCU"


class Unresolvable(Exception):
    """git could not answer for this call, so the working tree is all we have."""


# The dry runs and the modified-file listing would run a clean filter from
# .gitattributes, such as git-lfs, over a file that changed. With the empty
# tree as the attribute source and no attributes file, no filter applies;
# only $GIT_DIR/info/attributes still does. Needs git 2.40 or later, and an
# older git fails the call, which is then Unresolvable.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
NO_ATTRIBUTES = ["--attr-source=" + EMPTY_TREE, "-c", "core.attributesFile=/dev/null"]


def plan_checks(calls):
    """Collect every git add, stage or commit the command line would run, each with the options that pick its repository."""
    checks = []
    for argv, command_directory in calls:
        call = git_call(argv, command_directory)
        if call is None:
            continue
        subcommand, args, git_directory = call
        if subcommand in STAGING_SUBCOMMANDS:
            checks.append(("add", git_directory, git_location_options(argv), args))
        elif subcommand == "commit":
            checks.append(("commit", git_directory, git_location_options(argv), args))
    return checks


def git_answer(directory, options, args, environment=None, accepted=(0,)):
    """A git call whose exit code must be in `accepted` to count; anything else is Unresolvable."""
    out = run_git(directory, options, args, environment)
    if out is None or out.returncode not in accepted:
        raise Unresolvable()
    return out


def on_scratch_index(directory, options, args, accepted=(0,)):
    """Run a dry run against a copy of the index.

    `git add --dry-run` takes the index lock, and a git killed at the timeout
    leaves it behind, breaking every later write in the owner's repository.
    On a copy, the lock and the copy are both discarded here.
    """
    index = git_text(directory, options, ["rev-parse", "--git-path", "index"])
    if index is None:
        raise Unresolvable()
    index = os.path.join(directory, index)
    handle, scratch = tempfile.mkstemp(prefix="jz-index-")
    os.close(handle)
    try:
        if os.path.isfile(index):
            shutil.copyfile(index, scratch)
        else:
            # No index yet. An empty file is not a valid index; a missing one is.
            os.remove(scratch)
        return git_answer(directory, options + NO_ATTRIBUTES, args, {"GIT_INDEX_FILE": scratch}, accepted)
    finally:
        for leftover in (scratch, scratch + ".lock"):
            try:
                os.remove(leftover)
            except OSError:
                pass


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


def is_repository(directory, options):
    out = run_git(directory, options, ["rev-parse", "--git-dir"])
    return out is not None and out.returncode == 0


def staged_by_add(directory, options, args):
    """Ask git which paths `git add` with these arguments would put in the index."""
    result = on_scratch_index(directory, options, ["add", "--dry-run"]
                              + drop_flags(args, ADD_FLAGS_DROPPED, ADD_LETTERS_DROPPED))
    return [match.group(1) for match in
            (ADD_REPORT.match(line) for line in result.stdout.splitlines()) if match]


def patch_mode(args):
    return any(token in ("-p", "--patch")
               or (SHORT_CLUSTER.match(token) and "p" in token[1:]) for token in args)


def committed_by_commit(directory, options, args):
    """Ask git which paths `git commit` with these arguments would record."""
    # A commit dry run exits 1 when there is nothing to commit, and still reports.
    result = on_scratch_index(directory, options, ["commit", "--dry-run", "--porcelain"]
                              + drop_flags(args, COMMIT_FLAGS_DROPPED, COMMIT_LETTERS_DROPPED), accepted=(0, 1))
    # Column one is the index status. An untracked (??) or worktree-only ( M)
    # entry is reported but would not be committed, unless -p is picking hunks
    # straight out of the working tree.
    columns = (0, 1) if patch_mode(args) else (0,)
    paths = []
    for line in result.stdout.splitlines():
        if len(line) > 3 and any(line[column] in STAGED_STATUS for column in columns):
            paths.extend(unquote(part) for part in line[3:].split(" -> "))
    return paths


def dirty_paths(directory, options):
    """Everything the working tree could contribute to a commit right now, read with no attributes so no filter runs."""
    paths = []
    for args in (["diff", "--cached", "--name-only"],
                 ["ls-files", "--full-name", "--others", "--exclude-standard"],
                 ["ls-files", "--full-name", "--modified"]):
        paths.extend(unquote(line) for line in git_answer(directory, options + NO_ATTRIBUTES, args).stdout.splitlines())
    return paths


def unquote(path):
    if len(path) > 1 and path.startswith('"') and path.endswith('"'):
        return path[1:-1]
    return path


def deny(offenders, unparsed):
    report = sorted(set(offenders))[:MAX_REPORTED]
    lines = ["Blocked: this would stage or commit Claude Code working artifacts.", ""]
    lines += ["  " + safe_text(path) for path in report]
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
    offenders = []
    unparsed = False
    unseen = False
    for kind, check_directory, options, args in plan_checks(context.calls):
        if not is_repository(check_directory, options):
            continue
        resolve = staged_by_add if kind == "add" else committed_by_commit
        try:
            offenders.extend(forbidden(resolve(check_directory, options, args)))
        except Unresolvable:
            unparsed = True
            try:
                offenders.extend(forbidden(dirty_paths(check_directory, options)))
            except Unresolvable:
                # Even the fallback could not run: git is missing, too old for
                # --attr-source, or the repository would not answer. The other
                # calls on the line are still judged; a deny among them wins.
                unseen = True
    if offenders:
        return deny(offenders, unparsed)
    if unseen:
        return Ask("The artifact guard could not get git to say which paths this command stages or commits "
                   "(git missing, older than 2.40, or the repository did not answer), so nothing was checked "
                   "for .claude, docs/plans or .plans; confirm it, or run git status yourself first.")
    return None
