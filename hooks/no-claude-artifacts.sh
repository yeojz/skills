#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash).
#
# Blocks any git staging or commit that would include Claude Code working
# artifacts. These stay local and never reach a commit.
#
# Reads the PreToolUse event JSON on stdin. Exit 0 allows, exit 2 denies.
set -uo pipefail

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

# Only git staging and commit calls are of interest.
case "$command_line" in
  *"git add"*|*"git commit"*|*"git stage"*) ;;
  *) exit 0 ;;
esac

[ -n "$cwd" ] && cd "$cwd" 2>/dev/null || true
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Anything already staged.
candidates="$(git diff --cached --name-only 2>/dev/null || true)"

# A sweep flag pulls in everything currently dirty. -uall stops git from
# collapsing an untracked directory to its parent, which would hide the match.
case "$command_line" in
  *" -A"*|*" --all"*|*" -a"*|*"git add ."*|*" -u"*|*" --update"*)
    candidates="$candidates
$(git status --porcelain -uall 2>/dev/null | sed 's/^...//' || true)"
    ;;
esac

# Paths named directly on a `git add`, so `git add docs/plans` is caught even
# when nothing is staged yet. Only tokens that exist on disk count, and only for
# add or stage, so text inside a commit message is never mistaken for a path.
args=""
case "$command_line" in
  *"git add "*)   args="${command_line#*git add }" ;;
  *"git stage "*) args="${command_line#*git stage }" ;;
esac
# Stop at a shell separator so a chained command's words are not treated as paths.
args="${args%%&&*}"
args="${args%%;*}"
args="${args%%|*}"

for token in $args; do
  case "$token" in
    -*) continue ;;
  esac
  [ -e "$token" ] || continue
  candidates="$candidates
$token"
done

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
