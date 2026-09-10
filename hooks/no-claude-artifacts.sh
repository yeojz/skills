#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# Blocks any git staging or commit that would include Claude Code working
# artifacts. These stay local and never reach a commit.
#
# Reads the PreToolUse event JSON on stdin. Exit 0 allows, exit 2 denies.
set -uo pipefail

# Deny rather than fail open: without python3 the guard cannot inspect the call.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Blocked: no-claude-artifacts hook needs python3 on PATH to inspect git calls." >&2
  exit 2
fi

FORBIDDEN_RE='(^|/)\.claude(/|$)|(^|/)docs/plans(/|$)|(^|/)\.plans(/|$)'

payload="$(cat)"

read_field() {
  printf '%s' "$payload" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
cur = data
for key in sys.argv[1].split("."):
    if not isinstance(cur, dict):
        sys.exit(0)
    cur = cur.get(key)
    if cur is None:
        sys.exit(0)
print(cur if isinstance(cur, str) else "")
' "$1" 2>/dev/null
}

command_line="$(read_field tool_input.command)"
cwd="$(read_field cwd)"

# Cheap pre-filter before spending a python start-up on every shell call.
case "$command_line" in
  *git*) ;;
  *) exit 0 ;;
esac

[ -n "$cwd" ] && cd "$cwd" 2>/dev/null || true

# Tokenise the command line so text inside a commit message, a `./` prefix or
# a wrapper such as `command`, `env` or `git -C` cannot fool a substring match.
# Prints RELEVANT when a git add, stage or commit is present, SWEEP when it
# would pull in every dirty path, and one PATH line per named path that exists.
# An unparseable line (unbalanced quotes) prints nothing and is allowed.
analysis="$(python3 - "$command_line" <<'PY'
import os
import shlex
import sys

SEPARATOR_CHARS = set("();<>|&")
REDIRECTS = {"<", ">", ">>", "<<", "<&", ">&", "&>", "<<<", ">|"}
WRAPPERS = {"command", "env", "sudo"}
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
ADD_SWEEP_FLAGS = {"-A", "--all", "-u", "--update", "--no-ignore-removal"}
COMMIT_VALUE_OPTIONS = {"-m", "-F", "--message", "--file"}


def tokenise(line):
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def simple_commands(tokens):
    current = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token in REDIRECTS:
            skip_next = True
            continue
        if token and set(token) <= SEPARATOR_CHARS:
            if current:
                yield current
            current = []
            continue
        current.append(token)
    if current:
        yield current


def is_assignment(token):
    return "=" in token and not token.startswith("-")


def git_subcommand(words):
    index = 0
    while index < len(words) and (words[index] in WRAPPERS or is_assignment(words[index])):
        index += 1
    if index >= len(words) or words[index] != "git":
        return None, []
    index += 1
    while index < len(words) and words[index].startswith("-"):
        option = words[index]
        index += 1
        if option in GIT_VALUE_OPTIONS:
            index += 1
    if index >= len(words):
        return None, []
    return words[index], words[index + 1:]


def is_short_cluster(token):
    return token.startswith("-") and not token.startswith("--") and len(token) > 1


def inspect_add(args):
    sweep = False
    paths = []
    options_done = False
    for token in args:
        if not options_done and token == "--":
            options_done = True
            continue
        if not options_done and token.startswith("-"):
            if token in ADD_SWEEP_FLAGS or (is_short_cluster(token) and set("Au") & set(token[1:])):
                sweep = True
            continue
        if os.path.normpath(token) == ".":
            sweep = True
            continue
        if os.path.exists(token):
            paths.append(token)
    return sweep, paths


def inspect_commit(args):
    skip_next = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if token == "--":
            break
        if token in ("-a", "--all"):
            return True
        if token in COMMIT_VALUE_OPTIONS:
            skip_next = True
            continue
        if is_short_cluster(token):
            for letter in token[1:]:
                if letter == "a":
                    return True
                if letter in "mF":
                    skip_next = token.endswith(letter)
                    break
    return False


def main():
    try:
        tokens = tokenise(sys.argv[1])
    except ValueError:
        return
    relevant = False
    sweep = False
    paths = []
    for words in simple_commands(tokens):
        subcommand, args = git_subcommand(words)
        if subcommand in ("add", "stage"):
            relevant = True
            found_sweep, found_paths = inspect_add(args)
            sweep = sweep or found_sweep
            paths.extend(found_paths)
        elif subcommand == "commit":
            relevant = True
            sweep = sweep or inspect_commit(args)
    if not relevant:
        return
    print("RELEVANT")
    if sweep:
        print("SWEEP")
    for path in paths:
        print("PATH " + path)


main()
PY
)"

printf '%s\n' "$analysis" | grep -qx RELEVANT || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Anything already staged.
candidates="$(git diff --cached --name-only 2>/dev/null || true)"

# A sweep pulls in everything currently dirty. -uall stops git from collapsing
# an untracked directory to its parent, which would hide the match.
if printf '%s\n' "$analysis" | grep -qx SWEEP; then
  candidates="$candidates
$(git status --porcelain -uall 2>/dev/null | sed 's/^...//' || true)"
fi

# Paths named directly, so `git add docs/plans` is caught before anything is staged.
candidates="$candidates
$(printf '%s\n' "$analysis" | sed -n 's/^PATH //p')"

offenders="$(printf '%s\n' "$candidates" | grep -E "$FORBIDDEN_RE" | sort -u | head -20 || true)"

if [ -n "$offenders" ]; then
  {
    echo "Blocked: this would stage Claude Code working artifacts."
    echo
    echo "$offenders"
    echo
    echo "These paths are never committed. Unstage them first:"
    echo "  git reset HEAD -- .claude docs/plans .plans"
    echo "and add them to .gitignore if they are not there already."
  } >&2
  exit 2
fi

exit 0
