"""Deny the two ways an agent could move a default branch itself: a push to one, and merging a pull request.

The default branch moves only when the owner merges a reviewed pull request
on GitHub, so both are the owner's to run, never an agent's, whatever the
go-ahead says. A command the owner types with `!` does not pass through the
hook.

A protected branch is main, master, develop or trunk, and whatever
refs/remotes/origin/HEAD names. A push is denied when the line names a
protected branch, pushes every branch (--all, --branches, --mirror), picks
its destination with --repo or a wildcard, or runs while a protected branch
is checked out. A merge is `gh pr merge` in any form, `gh api` on a merge
endpoint, or a GraphQL call carrying a merge mutation. This is a guardrail
against a mistake, not a wall: branch protection on GitHub is what holds.
"""

import re

from guards import Deny

NAME = "protect-default-branches"

EVERY_BRANCH = r"--all|--branches|--mirror|--repo(?:=\S*)?|\S*\*\S*"
MERGE_ENDPOINT = re.compile(r"pulls/[^/\s]+/merge\b|/merges\b|\bmergePullRequest\b|\benablePullRequestAutoMerge\b|\bmergeBranch\b")
ADVICE = "Push the work to its own branch and open a pull request; the owner merges it."


def check(context):
    if context.runs("gh", "pr", "merge"):
        return Deny("Blocked: gh pr merge lands a pull request on the default branch, and merging is the owner's click on GitHub; "
                    "to disarm auto-merge, the owner runs gh pr merge --disable-auto themselves.", ADVICE)
    if context.runs("gh", "api") and MERGE_ENDPOINT.search(context.text):
        return Deny("Blocked: this gh api call merges a pull request or a branch, and merging is the owner's click on GitHub.", ADVICE)
    if not context.runs("git", "push") or context.flag(r"--dry-run|-n"):
        return None
    protected = context.protected_branches()
    named = sorted(name for name in protected if context.has(name) or context.has("origin/" + name))
    if named:
        return Deny("Blocked: this push names %s, and the default branch moves only through a merged pull request." % ", ".join(named), ADVICE)
    if context.flag(EVERY_BRANCH):
        return Deny("Blocked: this push selects its branches wholesale or by pattern, which reaches the default branch; "
                    "push one branch by name.", ADVICE)
    if context.branch in protected:
        return Deny("Blocked: this push runs with %s checked out, and the default branch moves only through a merged pull request." % context.branch,
                    "Check out a working branch first, then push it by name.")
    return None
