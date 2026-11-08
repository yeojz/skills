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

A merge is `gh pr merge`, which arms auto-merge too, unless its final
--disable-auto is true; `gh api` with a write to pulls/<n>/merge or to the
repository merges endpoint; and a GraphQL call carrying mergePullRequest,
enablePullRequestAutoMerge or mergeBranch, inline, in an --input file or in
a typed `-F key=@file` field. A query read from standard input cannot be
inspected and is denied. This is a guardrail against a mistake, not a wall:
branch protection on GitHub is what holds.
"""

import os
import re

from command_lines import git_call, git_config_overrides, git_location_options
from gh_options import final_bool_option, gh_command
from git_push import COMMON_DEFAULTS, HEADS, origin_head, resolve_commit, resolve_push, unfollowed_config_override
from guards import Deny, safe_text

NAME = "protect-default-branches"


MERGE_MUTATIONS = re.compile(r"\b(mergePullRequest|enablePullRequestAutoMerge|mergeBranch)\b")
PULL_MERGE_ENDPOINT = re.compile(r"(^|/)pulls/[^/]+/merge/?$")
REPO_MERGES_ENDPOINT = re.compile(r"(^|/)merges/?$")
# The option table of gh pr merge (cli/cli v2.103.0) with the persistent
# --repo/-R, read by gh_options.final_bool_option. Only a line whose final
# --disable-auto is provably true passes; an option missing here asks gh
# something the hook cannot follow, so the line is denied.
PR_MERGE_BOOL_OPTIONS = {
    "admin": None, "auto": None, "delete-branch": "d", "disable-auto": None,
    "merge": "m", "rebase": "r", "squash": "s", "help": "h",
}
PR_MERGE_VALUE_OPTIONS = {
    "author-email": "A", "body": "b", "body-file": "F", "match-head-commit": None,
    "subject": "t", "repo": "R",
}
# The option table of gh api (cli/cli v2.103.0); every option outside the
# value set is a flag. A typed field, -F or --field, reads `key=@path` from
# the file, and `@-` or --input - from standard input.
GH_API_VALUE_SHORTS = {"X", "f", "F", "H", "p", "q", "t"}
GH_API_VALUE_LONGS = {"method", "raw-field", "field", "header", "preview", "jq",
                      "template", "input", "hostname", "cache"}
GH_API_FIELD_OPTIONS = {"-f", "-F", "--raw-field", "--field", "--input"}
GH_API_TYPED_FIELD_OPTIONS = {"-F", "--field"}

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
    """(method, endpoint, values, files) of a gh api call.

    `values` holds every option value and operand as written; `files` holds
    the paths whose contents gh sends: the --input file and each typed field's
    `@path`, with "-" for standard input.
    """
    method = None
    endpoint = None
    values = []
    files = []
    has_fields = False
    rest = list(args)
    while rest:
        token = rest.pop(0)
        option = value = None
        if token.startswith("--"):
            name, has_value, attached = token[2:].partition("=")
            if name in GH_API_VALUE_LONGS:
                option = "--" + name
                value = attached if has_value else (rest.pop(0) if rest else "")
        elif token.startswith("-") and len(token) > 1:
            letter, attached = token[1], token[2:]
            if letter in GH_API_VALUE_SHORTS:
                option = "-" + letter
                value = attached[1:] if attached.startswith("=") else attached
                if not attached:
                    value = rest.pop(0) if rest else ""
        elif endpoint is None:
            endpoint = token
            continue
        else:
            values.append(token)
            continue
        if option is None:
            continue
        values.append(value)
        if option in {"-X", "--method"}:
            method = value
        elif option == "--input":
            files.append(value)
        elif option in GH_API_TYPED_FIELD_OPTIONS and "=@" in value:
            files.append(value.split("=@", 1)[1])
        has_fields = has_fields or option in GH_API_FIELD_OPTIONS
    if method is None:
        method = "POST" if has_fields else "GET"
    return method.upper(), endpoint or "", values, files


def reason_for_gh(words, args, directory):
    if words == ("pr", "merge"):
        if final_bool_option(args, PR_MERGE_BOOL_OPTIONS, PR_MERGE_VALUE_OPTIONS, "disable-auto") is True:
            return None
        return "gh pr merge lands a pull request on the default branch, and merging is the owner's click on GitHub."
    if words == ("api",):
        method, endpoint, values, files = gh_api_call(args)
        if method != "GET" and PULL_MERGE_ENDPOINT.search(endpoint):
            return "gh api %s %s merges a pull request, and merging is the owner's click on GitHub." % (method, endpoint)
        if method == "POST" and REPO_MERGES_ENDPOINT.search(endpoint):
            return "gh api POST %s merges one branch into another on the remote." % endpoint
        if endpoint == "graphql":
            text = " ".join(values)
            for path in files:
                if path == "-":
                    return ("This GraphQL call reads its query from standard input, which the hook cannot inspect "
                            "for a merge; pass the query inline or from a file.")
                try:
                    with open(os.path.join(directory, path), encoding="utf-8", errors="replace") as handle:
                        text += " " + handle.read()
                except OSError:
                    pass
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
