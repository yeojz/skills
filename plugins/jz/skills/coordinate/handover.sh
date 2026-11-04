#!/usr/bin/env bash
# Hands a fix round's state from one session to the next without losing
# work, including a rebase stopped on a conflict.
#
# Usage:
#   handover.sh save <branch> <notes-dir> <round> <owns-path>...
#     Run by the last round's session in its own worktree. Writes
#     round-<round>.patch, round-<round>.env and, mid-rebase,
#     round-<round>.bundle to <notes-dir>, then aborts any rebase. Nothing
#     changes the rebase until every artifact is written.
#   handover.sh restore <notes-dir> <round>
#     Run by the escalated session in its own clean worktree. Rebuilds the
#     state on a detached HEAD and proves it by tree id. Mid-rebase, it
#     commits the stopped commit's resolution and starts replaying the rest
#     with `git rebase --onto`, leaving any new conflict to the session.
#
# Only the given Owns paths are snapshotted, in a throwaway index, so the
# notes folder and the owner's other files never enter the patch.
set -euo pipefail

usage() {
  sed -n '5,14p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

save() {
  [ "$#" -ge 4 ] || usage
  local branch="$1" notes="$2" round="$3"
  shift 3
  local pushed rebase_dir onto="" stopped="" base bundle="" snap tree
  pushed="$(git rev-parse --verify "origin/$branch^{commit}")"
  rebase_dir="$(git rev-parse --git-path rebase-merge)"

  if [ -d "$rebase_dir" ]; then
    onto="$(cat "$rebase_dir/onto")"
    if [ ! -f "$rebase_dir/stopped-sha" ]; then
      echo "A rebase is in progress but not stopped on a commit; resolve it by hand." >&2
      exit 2
    fi
    stopped="$(git rev-parse --verify "$(cat "$rebase_dir/stopped-sha")^{commit}")"
    base="$(git rev-parse HEAD)"
    if [ "$base" != "$onto" ]; then
      bundle="$notes/round-$round.bundle"
      git bundle create "$bundle" HEAD "^$onto" >/dev/null 2>&1
    fi
  else
    base="$pushed"
  fi

  snap="$(mktemp)"
  # shellcheck disable=SC2064
  trap "rm -f '$snap'" EXIT
  GIT_INDEX_FILE="$snap" git read-tree "$base"
  GIT_INDEX_FILE="$snap" git add -A -- "$@"
  GIT_INDEX_FILE="$snap" git diff --cached --binary "$base" > "$notes/round-$round.patch"
  tree="$(GIT_INDEX_FILE="$snap" git write-tree)"

  {
    printf 'branch=%s\npushed=%s\nbase=%s\ntree=%s\n' "$branch" "$pushed" "$base" "$tree"
    printf 'onto=%s\nstopped=%s\nbundle=%s\n' "$onto" "$stopped" "$bundle"
  } > "$notes/round-$round.env"

  [ -z "$onto" ] || git rebase --abort
  cat "$notes/round-$round.env"
}

restore() {
  [ "$#" -eq 2 ] || usage
  local notes="$1" round="$2" branch pushed base tree onto stopped bundle
  local env="$notes/round-$round.env"
  [ -f "$env" ] || { echo "No $env." >&2; exit 2; }
  # shellcheck disable=SC1090
  . "$env"

  if [ -n "$(git status --porcelain)" ]; then
    echo "This checkout is not clean; restore needs a clean one." >&2
    exit 2
  fi
  git fetch --quiet origin "$branch"
  [ "$(git rev-parse "origin/$branch")" = "$pushed" ] \
    || { echo "origin/$branch moved since the handover; stop." >&2; exit 1; }
  if [ -n "$bundle" ]; then
    git bundle verify "$bundle" >/dev/null 2>&1
    git fetch --quiet "$bundle" HEAD
  fi

  git checkout --quiet --detach "$base"
  git apply --index "$notes/round-$round.patch"
  if [ "$(git write-tree)" != "$tree" ]; then
    echo "MISMATCH: the patch does not rebuild tree $tree; stop." >&2
    exit 1
  fi
  echo "Rebuilt tree $tree on $base."

  [ -n "$stopped" ] || return 0
  git commit --quiet -C "$stopped"
  echo "Committed the resolution of $stopped; replaying the rest onto it."
  if git rebase --onto HEAD "$stopped" "$pushed"; then
    echo "Replay finished at $(git rev-parse HEAD)."
  else
    echo "Replay stopped on a conflict: resolve it against the replayed commit, then git rebase --continue." >&2
    exit 3
  fi
}

case "${1:-}" in
  save) shift; save "$@" ;;
  restore) shift; restore "$@" ;;
  *) usage ;;
esac
