#!/usr/bin/env bash
# SessionStart hook, matcher "compact".
#
# After a compaction, tells the session to confirm its branch, log any
# decision the summary marked unlogged, and resume each running flow from its
# folder's next.md and resume command rather than from the summary.
set -uo pipefail
command -v python3 >/dev/null 2>&1 || { cat >/dev/null 2>&1; exit 0; }
exec python3 -B "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/flows.py" after-compact
