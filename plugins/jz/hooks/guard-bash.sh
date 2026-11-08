#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# The one hook the plugin wires to Bash calls. It hands the payload to
# guard.py, which parses the command line once and runs every guard in
# guards/ over it: the artifact check, the pr-skill gate, the rebase rule, the
# restricted words, the default-branch guard, the remote-write confirmation
# and the secret scan. The parser follows plain commands only; a line with
# anything else on it is asked about when it names something a guard judges
# or holds a construct that could stand for one. Exit 0 allows, exit 2
# denies with the reason on stderr, and an "ask" decision is printed as JSON
# on stdout.
#
# Every payload goes to python, about 45 ms. A text pre-filter for "git" was
# tried and dropped: the shell spells a word in too many ways (g'i't, ${g}t)
# for a substring test to be worth its false negatives.
set -uo pipefail

payload="$(cat)"

# Deny rather than fail open, but only for calls that mention git or gh: a
# missing interpreter must not block every Bash call in the session.
if ! command -v python3 >/dev/null 2>&1; then
  case "$payload" in
    *git*|*gh*)
      echo "Blocked: the jz guards need python3 on PATH to inspect git and gh calls." >&2
      exit 2 ;;
    *) exit 0 ;;
  esac
fi

printf '%s' "$payload" | exec python3 -B "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/guard.py"
