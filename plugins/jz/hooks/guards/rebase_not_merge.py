"""Deny merging into a feature branch; the house workflow rebases.

The correction had to be typed in three repositories before this guard
existed, and the desktop app's own "merge the base branch in" prompt lands
here too. Any `git merge` is denied, apart from `--ff-only`, which creates
no merge commit and is how the pr skill's cleanup brings the default
branch's checkout level, and `--abort`. A `git pull` is denied unless it
says `--rebase`, whatever the configuration says, so the line itself shows
what it does.
"""

from guards import Deny

NAME = "rebase-not-merge"


def check(context):
    if context.runs("git", "merge") and not context.flag(r"--ff-only|--abort"):
        return Deny("Blocked: the house workflow rebases and never merges a branch in.",
                    "Run git fetch origin <base> && git rebase origin/<base> instead; a default branch's own checkout "
                    "may run git merge --ff-only origin/<base>.")
    if context.runs("git", "pull") and not context.flag(r"--rebase(?:=\S+)?|-r"):
        return Deny("Blocked: git pull without --rebase merges the remote branch in.",
                    "Run git pull --rebase, or git fetch followed by git rebase.")
    return None
