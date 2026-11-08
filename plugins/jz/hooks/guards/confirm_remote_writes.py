"""Ask before a remote write that is hard to take back or that signals reviewers.

Opening a pull request ready for review, marking one ready, and a force push
that is not pinned to the sha it replaces. A branch push, a draft pull
request and a `--force-with-lease=<ref>:<sha>` push can be withdrawn or fail
safe, and pass without a prompt. Merging a pull request and pushing to a
default branch are denied outright by protect_default_branches. A plugin
cannot add permissions.ask entries to the host's settings, so the ask lives
here instead. Under a host that answers prompts itself, an ask is advice to
that host rather than a stop.
"""

import re

from guards import Ask

NAME = "confirm-remote-writes"

# A lease pinned to a full object id, or to "the ref must not exist yet".
PINNED_LEASE = re.compile(r"(?<!\S)--force-with-lease=\S+:(?:[0-9a-f]{40}|[0-9a-f]{64})?(?!\S)")
UNPINNED_FORCE = r"--force|-[A-Za-z]*f[A-Za-z]*|--force-with-lease(?:=\S*)?|--force-if-includes|--mirror|--prune|\+\S+"


def check(context):
    if context.runs("gh", "pr", "create") and not context.flag(r"--draft|-[A-Za-z]*d[A-Za-z]*"):
        return Ask("gh pr create without --draft opens a pull request ready for review; confirm first, or open it as a draft.")
    if context.runs("gh", "pr", "ready") and not context.flag("--undo"):
        return Ask("gh pr ready signals reviewers; confirm before marking a pull request ready.")
    if context.runs("git", "push"):
        unpinned = re.sub(PINNED_LEASE, "", context.text)
        if re.search(r"(?<!\S)(?:%s)(?!\S)" % UNPINNED_FORCE, unpinned):
            return Ask("git push with a force option not pinned to the sha it replaces can discard commits on the remote; "
                       "confirm first, or use --force-with-lease=<branch>:<sha>.")
    return None
