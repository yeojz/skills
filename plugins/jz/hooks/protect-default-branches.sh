#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# Denies the two ways an agent could move a default branch itself: a push
# that updates or deletes one, and merging a pull request. The default branch
# moves only when the owner merges a reviewed pull request on GitHub, so both
# are the owner's to run, never an agent's, whatever the go-ahead says. A
# command the owner types with `!` does not pass through this hook.
#
# A protected branch is main, master, develop or trunk, and whatever
# refs/remotes/origin/HEAD names. Which refs a push updates is git's answer,
# not the hook's: `git push --dry-run --porcelain` with the same arguments
# resolves configured refspecs, push.default, HEAD, wildcards, --all and
# --mirror, the way scan-secrets-before-push.sh reads it. When the dry run
# cannot say, the call is read by hand: a refspec naming a protected branch,
# --all, --mirror or --branches, or a bare push from a protected branch is
# denied, and anything else is left to the other hooks.
#
# A merge is `gh pr merge`, which arms auto-merge too, unless its final
# --disable-auto is true; `gh api` with a write to pulls/<n>/merge or to the
# repository merges endpoint; and a GraphQL call carrying mergePullRequest,
# enablePullRequestAutoMerge or mergeBranch, inline, in an --input file or in
# a typed `-F key=@file` field. A query read from standard input cannot be
# inspected and is denied. This is a guardrail against a
# mistake, not a wall: branch protection on GitHub is what holds.
#
# The command line is split by command_lines.py, the parser every hook shares,
# and each command is judged in the directory it runs in.
#
# Reads the PreToolUse event JSON on stdin. Exit 0 allows, exit 2 denies.
set -uo pipefail

payload="$(cat)"

# Cheap pre-filter, so an ordinary shell call does not pay for a python start-up.
case "$payload" in
  *push*|*merge*|*Merge*|*graphql*) ;;
  *) exit 0 ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "Blocked: protect-default-branches hook needs python3 on PATH to inspect git and gh calls." >&2
  exit 2
fi

inspector="$(cat <<'PY'
import json
import os
import re
import sys

sys.path.insert(0, sys.argv[1])
from command_lines import commands_with_directory, git_call, git_repository_options, start_directory  # noqa: E402
from git_push import dry_run_updates, resolve_push_long_option, run_git, walk_push_options  # noqa: E402
from gh_options import final_bool_option, gh_command  # noqa: E402

COMMON_DEFAULTS = {"main", "master", "develop", "trunk"}
BRANCH_PREFIX = "refs/heads/"
# Flags of a porcelain line whose ref the push leaves where it is.
UNCHANGED_FLAGS = set("=")
WHOLESALE_PUSH_OPTIONS = {"all", "branches", "mirror"}

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
# When the line cannot be lexed at all, lean towards denying.
RAW_MERGE = re.compile(r"\bgh\b.*\bpr\s+merge\b")
RAW_PUSH = re.compile(r"\bgit\b.*\bpush\b.*(\s|:|\+|/)(main|master|develop|trunk)\b|\bgit\b.*\bpush\b.*\s--(all|mirror|branches)\b")

protected_by_directory = {}


def protected_branches(directory, options):
    if directory not in protected_by_directory:
        names = set(COMMON_DEFAULTS)
        out = run_git(directory, options, ["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"])
        if out is not None and out.returncode == 0 and out.stdout.strip():
            names.add(out.stdout.strip().split("/", 1)[-1])
        protected_by_directory[directory] = names
    return protected_by_directory[directory]


def current_branch(directory, options):
    out = run_git(directory, options, ["symbolic-ref", "-q", "--short", "HEAD"])
    if out is None or out.returncode != 0:
        return None
    return out.stdout.strip()


def branch_name(ref):
    return ref[len(BRANCH_PREFIX):] if ref.startswith(BRANCH_PREFIX) else ref


def push_by_hand(directory, options, args, protected):
    """The protected branch a push names, read from its arguments alone, or None.

    Used when git's own dry run cannot answer. The first operand is the
    remote; each one after it is a refspec whose destination is the part after
    the colon, or the source itself.
    """
    operands = []
    for token in args:
        if token.startswith("--"):
            name = token[2:].partition("=")[0]
            if resolve_push_long_option(name) in WHOLESALE_PUSH_OPTIONS:
                return "every branch (" + token + ")"
            continue
        if token.startswith("-") and token != "-":
            continue
        operands.append(token)
    refspecs = operands[1:]
    current = current_branch(directory, options)
    if not refspecs:
        return current if current in protected else None
    for refspec in refspecs:
        source, colon, destination = refspec.lstrip("+").partition(":")
        target = destination if colon else source
        if target == "HEAD":
            target = current or ""
        if branch_name(target) in protected:
            return branch_name(target)
    return None


def reason_for_push(directory, options, args):
    walk = walk_push_options(args)
    if not walk.error and walk.dry_run:
        return None
    protected = protected_branches(directory, options)
    url, updates, error = dry_run_updates(directory, options, args)
    if error:
        branch = push_by_hand(directory, options, args, protected)
        if branch:
            return "This push would update %s, and the default branch moves only through a merged pull request." % branch
        return None
    for flag, _, destination, _ in updates:
        if flag in UNCHANGED_FLAGS:
            continue
        if destination.startswith(BRANCH_PREFIX) and branch_name(destination) in protected:
            action = "delete" if flag == "-" else "update"
            return ("This push would %s %s on %s, and the default branch moves only through a merged pull request."
                    % (action, branch_name(destination), url))
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


def reason_for(argv, directory):
    gh = gh_command(argv)
    if gh is not None:
        return reason_for_gh(gh[0], gh[1], directory)
    call = git_call(argv, directory)
    if call is not None and call[0] == "push":
        return reason_for_push(call[2], git_repository_options(argv), call[1])
    return None


def deny(reason):
    print("Blocked: " + reason, file=sys.stderr)
    print("Push the work to its own branch and open a pull request; the owner merges it.", file=sys.stderr)
    sys.exit(2)


try:
    event = json.load(sys.stdin)
    command = event.get("tool_input", {}).get("command", "")
    cwd = event.get("cwd", "")
except Exception:
    sys.exit(0)
if not isinstance(command, str):
    sys.exit(0)
start = start_directory(cwd)

try:
    for argv, _, directory in commands_with_directory(command, start):
        reason = reason_for(argv, directory)
        if reason:
            deny(reason)
except ValueError:
    if RAW_MERGE.search(command) or MERGE_MUTATIONS.search(command) or RAW_PUSH.search(command):
        deny("The command could not be parsed and looks like a merge or a push to a default branch.")
sys.exit(0)
PY
)"

printf '%s' "$payload" | python3 -B -c "$inspector" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
