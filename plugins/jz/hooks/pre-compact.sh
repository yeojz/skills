#!/usr/bin/env bash
# PreCompact hook.
#
# Its stdout becomes instructions for the compaction summary: keep the branch,
# the task list, decisions not yet logged and the owner's open questions, and
# name the flows running in this session so the summary points at their
# folders. It writes no file and never blocks compaction.
set -uo pipefail
command -v python3 >/dev/null 2>&1 || { cat >/dev/null 2>&1; exit 0; }
exec python3 -B "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/flows.py" pre-compact
