"""Deny staging or committing while a Claude Code working artifact could go in.

`.claude/`, `docs/plans/` and `.plans/` hold session state and plans, and
belong in `.gitignore` or `.git/info/exclude`. Instead of working out which
paths a particular `git add` would stage, the guard asks git for the
artifact paths that are untracked and unignored, modified, or already
staged in the command's repository, and denies any add, stage or commit
while there is one. The fix is the exclusion the house rule asks for, after
which every add passes.
"""

import re

from guards import Deny

NAME = "no-claude-artifacts"

FORBIDDEN = re.compile(r"(^|/)(\.claude|docs/plans|\.plans)(/|$)")
MAX_REPORTED = 5


def artifacts_in_play(context):
    """Artifact paths an add or commit could pick up: untracked and unignored, modified, or staged."""
    found = set()
    for args in (["ls-files", "--full-name", "--others", "--exclude-standard"],
                 ["ls-files", "--full-name", "--modified"],
                 ["diff", "--cached", "--name-only"]):
        out = context.git(*args)
        for path in (out.splitlines() if out else []):
            if FORBIDDEN.search(path):
                found.add(path)
    return sorted(found)


def check(context):
    if not (context.runs("git", "add") or context.runs("git", "stage") or context.runs("git", "commit")):
        return None
    paths = artifacts_in_play(context)
    if not paths:
        return None
    shown = ", ".join(paths[:MAX_REPORTED]) + (" and %d more" % (len(paths) - MAX_REPORTED) if len(paths) > MAX_REPORTED else "")
    return Deny("Blocked: %s could be staged or committed from an agent session: %s." % (
                    "these working artifacts" if len(paths) > 1 else "this working artifact", shown),
                "Add .claude/, docs/plans/ and .plans/ to .gitignore or .git/info/exclude, unstage any that are staged, then rerun.")
