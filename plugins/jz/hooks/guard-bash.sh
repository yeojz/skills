#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# The one hook the plugin wires to Bash calls. It hands the payload to
# guard.py, which runs every guard in guards/ over the command text: the
# default-branch guard, the rebase rule, the pr-skill gate, the artifact
# check, the remote-write confirmation and the secret scan. Exit 0 allows,
# exit 2 denies with the reason on stderr, and an "ask" decision is printed
# as JSON on stdout.
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
