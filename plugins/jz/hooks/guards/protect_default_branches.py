"""Deny the two ways an agent could move a default branch itself: a push that updates or deletes one, and merging a pull request.

The default branch moves only when the owner merges a reviewed pull request
on GitHub, so both are the owner's to run, never an agent's, whatever the
go-ahead says. A command the owner types with `!` does not pass through the
hook.

A protected branch is main, master, develop or trunk, and whatever
refs/remotes/origin/HEAD names. Which refs a push updates is read from the
repository alone, by git_push.resolve_push; nothing is asked of the remote
and nothing the caller named is run. A -c or --config-env override of
remote.*, push.*, branch.* or url.* cannot be followed and is denied.

A merge is `gh pr merge` in any form, --disable-auto included, since the
owner can run that one themselves; `gh api` with a write to pulls/<n>/merge
or to the repository merges endpoint; and a GraphQL call carrying
mergePullRequest, enablePullRequestAutoMerge or mergeBranch, inline, in an
--input file or in a typed `-F key=@file` field. A query read from standard
input cannot be inspected and is denied. This is a guardrail against a mistake, not a wall:
branch protection on GitHub is what holds.
"""

import os
import re

from command_lines import git_call, git_config_overrides, git_location_options
from gh_options import gh_command
from git_push import COMMON_DEFAULTS, HEADS, origin_head, resolve_commit, resolve_push, unfollowed_config_override
from guards import Deny, read_text, safe_text

NAME = "protect-default-branches"


MERGE_MUTATIONS = re.compile(r"\b(mergePullRequest|enablePullRequestAutoMerge|mergeBranch)\b")
# An endpoint may carry a query string or a fragment after the path.
PULL_MERGE_ENDPOINT = re.compile(r"(^|/)pulls/[^/?#]+/merge/?(?:[?#]|$)")
REPO_MERGES_ENDPOINT = re.compile(r"(^|/)merges/?(?:[?#]|$)")
# A gh api write is one with a method other than GET, or one that sends a
# field or an input body. The tokens are read by their surface: a merge
# endpoint among them, a merge mutation in them or in a file a typed field
# or --input names, or a body read from standard input, which cannot be
# inspected.
GH_API_METHOD_OPTIONS = {"-X", "--method"}
GH_API_BODY_OPTIONS = {"-f", "-F", "--raw-field", "--field", "--input"}
GH_API_FILE_OPTIONS = {"-F", "--field", "--input"}
GRAPHQL_ENDPOINT = re.compile(r"(^|/)graphql(?:[?#]|$)")


def protected_branches(directory, options, protected_by_directory):
    if directory not in protected_by_directory:
        names = set(COMMON_DEFAULTS)
        head = origin_head(directory, options)
        if head:
            names.add(head)
        protected_by_directory[directory] = names
    return protected_by_directory[directory]


def branch_name(ref):
    return ref[len(HEADS):] if ref.startswith(HEADS) else ref


def reason_for_push(directory, options, args, config_overrides, cache):
    override = unfollowed_config_override(config_overrides)
    if override:
        return ("This push carries %s, which changes where or what it publishes, and a command-line "
                "configuration override is not followed; put the setting in the repository's configuration." % override)
    protected = protected_branches(directory, options, cache)
    push, error = resolve_push(directory, options, args)
    if error:
        # Unresolved is not safe: a token naming a protected branch is enough to deny.
        for token in args:
            if token.startswith("-"):
                continue
            target = token.lstrip("+").partition(":")[2] or token
            if branch_name(target) in protected:
                return ("This push could not be resolved (%s) and names %s, and the default branch moves only "
                        "through a merged pull request." % (safe_text(error), safe_text(branch_name(target))))
        return None
    if push.dry_run:
        return None
    for source, destination in push.updates:
        if not destination.startswith(HEADS) or branch_name(destination) not in protected:
            continue
        name = branch_name(destination)
        if source is None:
            return "This push would delete %s on %s, and the default branch moves only through a merged pull request." % (name, push.destination)
        tracking = push.tracking_ref(name)
        if tracking:
            pushed = resolve_commit(directory, options, source)
            held = resolve_commit(directory, options, tracking)
            if pushed is not None and pushed == held:
                continue
        return "This push would update %s on %s, and the default branch moves only through a merged pull request." % (name, push.destination)
    return None


def gh_api_call(args):
    """(is a write, tokens, files) of a gh api call, read from the tokens' surface.

    `files` holds the paths whose contents gh would send: the --input file
    and each typed field's `@path`, with "-" for standard input.
    """
    write = False
    files = []
    tokens = list(args)
    for index, token in enumerate(tokens):
        name, has_value, attached = token.partition("=")
        following = tokens[index + 1] if index + 1 < len(tokens) else ""
        if name in GH_API_METHOD_OPTIONS:
            write = write or (attached if has_value else following).upper() != "GET"
        elif token[:2] in GH_API_METHOD_OPTIONS and len(token) > 2:
            write = write or token[2:].lstrip("=").upper() != "GET"
        if name in GH_API_BODY_OPTIONS or (token[:2] in {"-f", "-F"} and len(token) > 2):
            write = True
        if name == "--input":
            files.append(attached if has_value else following)
            continue
        if token[:2] == "-F" and len(token) > 2:
            field = token[2:]
        elif name in GH_API_FILE_OPTIONS:
            field = attached if has_value else following
        else:
            continue
        if "=@" in field:
            files.append(field.split("=@", 1)[1])
    return write, tokens, files


def reason_for_gh(words, args, directory):
    if words == ("pr", "merge"):
        return ("gh pr merge lands a pull request on the default branch, and merging is the owner's click on GitHub; "
                "to disarm auto-merge, the owner runs gh pr merge --disable-auto themselves.")
    if words == ("api",):
        write, tokens, files = gh_api_call(args)
        if not write:
            return None
        for token in tokens:
            if PULL_MERGE_ENDPOINT.search(token):
                return "gh api on %s merges a pull request, and merging is the owner's click on GitHub." % token
            if REPO_MERGES_ENDPOINT.search(token):
                return "gh api on %s merges one branch into another on the remote." % token
        # The GraphQL endpoint is spelled graphql, /graphql or a full URL, so
        # every write's text and body files are scanned for a merge mutation.
        text = " ".join(tokens)
        graphql = any(GRAPHQL_ENDPOINT.search(token) for token in tokens)
        for path in files:
            if path == "-":
                if graphql:
                    return ("This GraphQL call reads its query from standard input, which the guard cannot inspect "
                            "for a merge; pass the query inline or from a file.")
                continue
            found = read_text(os.path.join(directory, path))
            if found is None or not found[1]:
                if not os.path.exists(os.path.join(directory, path)):
                    continue
                if graphql:
                    return ("This GraphQL call reads its body from %s, which is not a plain file under a megabyte that "
                            "the guard can inspect for a merge; pass the query inline or from a smaller plain file." % safe_text(path))
                continue
            text += " " + found[0]
        if MERGE_MUTATIONS.search(text):
            return "This GraphQL call merges a pull request or arms auto-merge, and merging is the owner's click on GitHub."
    return None


def reason_for(argv, directory, cache):
    gh = gh_command(argv)
    if gh is not None:
        return reason_for_gh(gh[0], gh[1], directory)
    call = git_call(argv, directory)
    if call is not None and call[0] == "push":
        return reason_for_push(call[2], git_location_options(argv), call[1], git_config_overrides(argv), cache)
    return None


def deny(reason):
    return Deny("Blocked: " + reason,
                "Push the work to its own branch and open a pull request; the owner merges it.")


def check(context):
    # No pre-filter on the raw text: an alias such as `git p` resolves to a push only after parsing.
    cache = {}
    for argv, directory in context.calls:
        reason = reason_for(argv, directory, cache)
        if reason:
            return deny(reason)
    return None
