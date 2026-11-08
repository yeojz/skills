"""Ask before a remote write that is hard to take back or that signals reviewers.

Opening a pull request ready for review, marking one ready, and a force push
that is not pinned to the sha it replaces. A branch push, a draft pull
request and a `--force-with-lease=<ref>:<sha>` push can be withdrawn or fail
safe, and pass without a prompt. Merging a pull request and pushing to a
default branch are denied outright by protect_default_branches. A plugin
cannot add permissions.ask entries to the host's settings, so the ask lives
here instead.
"""

import re

from command_lines import SHORT_CLUSTER, git_call
from gh_options import gh_command
from guards import Ask

NAME = "confirm-remote-writes"

# A lease expectation git cannot re-resolve: a full object id, or empty for
# "the ref must not exist yet". Anything else, a ref name or a short hex that
# could be one, is read from a ref a fetch can move.
PINNED_EXPECTATION = re.compile(r"^(|[0-9a-f]{40}|[0-9a-f]{64})$")
# A draft and an undo are read as literal tokens: `--draft`, or a short
# cluster of letters with `d` in it, and `--undo`. gh's own option parser is
# not emulated, so `--draft=false` or `--title --draft` are read by their
# surface; both are rare, and an ask or a draft PR is cheap either way.
DRAFT_CLUSTER = re.compile(r"^-[A-Za-z]*d[A-Za-z]*$")


def push_is_forced(args):
    """Whether a git push can overwrite a remote branch without naming the sha it replaces.

    A lease that names the full expected object id, `--force-with-lease=<ref>:<sha>`,
    fails unless the remote is still where the caller last saw it, so it passes,
    as does an empty expectation, which requires the ref not to exist. A bare
    lease, or one whose expectation is a ref name such as
    `refs/remotes/origin/x`, checks against a ref a background fetch can move,
    so it is treated like --force, as are --mirror and --prune, which delete
    remote refs. --force-if-includes only refines a lease and asks on its
    own. Options are read as literal tokens; an abbreviation is one the
    push resolver does not follow, so the guards that use it ask.
    """
    pinned = False
    forced = False
    includes = False
    for token in args:
        if token.startswith("--") and token != "--":
            name, has_value, value = token[2:].partition("=")
            if name in {"force", "mirror", "prune"}:
                # --mirror is an implicit +refs/*:refs/* that also deletes; --prune deletes too.
                forced = True
            elif name == "force-with-lease":
                if has_value and ":" in value and PINNED_EXPECTATION.match(value.split(":", 1)[1]):
                    pinned = True
                else:
                    forced = True
            elif name == "force-if-includes":
                includes = True
            continue
        if token.startswith("+"):
            forced = True
        elif SHORT_CLUSTER.match(token) and "f" in token[1:]:
            forced = True
    return forced or (includes and not pinned)


def create_is_draft(args):
    return any(token == "--draft" or DRAFT_CLUSTER.match(token) for token in args)


def ready_is_undo(args):
    return "--undo" in args


def reason_for(argv):
    gh = gh_command(argv)
    if gh is not None:
        words, args = gh
        if words == ("pr", "create") and not create_is_draft(args):
            return "gh pr create without --draft opens a pull request ready for review; confirm first, or open it as a draft."
        if words == ("pr", "ready") and not ready_is_undo(args):
            return "gh pr ready signals reviewers; confirm before marking a pull request ready."
        return None
    call = git_call(argv, ".")
    if call is not None:
        subcommand, args, _ = call
        if subcommand == "push" and push_is_forced(args):
            return "git push with a force option not pinned to the sha it replaces can discard commits on the remote; confirm first, or use --force-with-lease=<branch>:<sha>."
    return None


def check(context):
    for argv, _ in context.calls:
        reason = reason_for(argv)
        if reason:
            return Ask(reason)
    return None
