#!/usr/bin/env bash
# SessionStart hook, matcher "compact".
#
# After a compaction, tells the session to confirm its branch, log any
# decision the summary marked unlogged, and continue each flow it marked as
# running from the flow's folder and its skill's Resume paragraph.
set -uo pipefail
command -v python3 >/dev/null 2>&1 || { cat >/dev/null 2>&1; exit 0; }
# A failed hook shows the owner an error on every compaction, so the
# interpreter's own status never leaves this script.
python3 -B "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/flows.py" after-compact
exit 0
