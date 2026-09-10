#!/usr/bin/env bash
#
# Install this repo's skills, rules, agents and hooks into ~/.claude.
#
# Everything is symlinked, so `git pull` in this repo updates every machine
# without reinstalling. Only settings.json is copied into, and it is backed up
# first and merged rather than overwritten.
#
#   ./install.sh              install or refresh
#   ./install.sh --dry-run    print what would change, touch nothing
#   ./install.sh --uninstall  remove this repo's symlinks and settings entries
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CLAUDE_DIR/settings.json"
FRAGMENT="$REPO_DIR/hooks/settings.fragment.json"

DRY_RUN=0
UNINSTALL=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 1 ;;
  esac
done

info()  { printf '  %s\n' "$*"; }
step()  { printf '\n%s\n' "$*"; }
run()   { if [ "$DRY_RUN" = 1 ]; then info "would: $*"; else "$@"; fi; }

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }

# ---------------------------------------------------------------- link helper

link_into() {
  # link_into <source dir> <target dir> <glob>
  local src_dir="$1" dest_dir="$2" glob="$3"
  [ -d "$src_dir" ] || return 0
  run mkdir -p "$dest_dir"

  local src name dest
  for src in "$src_dir"/$glob; do
    [ -e "$src" ] || continue
    name="$(basename "$src")"
    dest="$dest_dir/$name"

    if [ "$UNINSTALL" = 1 ]; then
      if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$src" ]; then
        run rm "$dest"
        info "removed $dest"
      fi
      continue
    fi

    if [ -L "$dest" ]; then
      if [ "$(readlink "$dest")" = "$src" ]; then
        info "ok       $name"
        continue
      fi
      info "replace  $name (was a link to $(readlink "$dest"))"
      run rm "$dest"
    elif [ -e "$dest" ]; then
      info "SKIPPED  $name already exists and is not a link from this repo"
      info "         move or delete $dest, then re-run"
      continue
    else
      info "link     $name"
    fi
    run ln -s "$src" "$dest"
  done
}

# ------------------------------------------------------------------- settings

merge_settings() {
  local mode="$1"
  if [ ! -f "$FRAGMENT" ]; then
    info "no settings fragment, skipping"
    return 0
  fi

  if [ "$DRY_RUN" = 1 ]; then
    info "would $mode hook and permission entries in $SETTINGS"
    return 0
  fi

  mkdir -p "$CLAUDE_DIR/.install-backup"
  if [ -f "$SETTINGS" ]; then
    cp "$SETTINGS" "$CLAUDE_DIR/.install-backup/settings.json.$(date +%Y%m%d-%H%M%S)"
  fi

  REPO_DIR="$REPO_DIR" SETTINGS="$SETTINGS" FRAGMENT="$FRAGMENT" MODE="$mode" python3 <<'PY'
import json, os, sys

repo = os.environ["REPO_DIR"]
path = os.environ["SETTINGS"]
mode = os.environ["MODE"]

fragment = json.load(open(os.environ["FRAGMENT"]))
fragment = json.loads(json.dumps(fragment).replace("__AI_WORKFLOWS_DIR__", repo))

try:
    settings = json.load(open(path))
except FileNotFoundError:
    settings = {}
except json.JSONDecodeError as exc:
    sys.exit(f"{path} is not valid JSON ({exc}). Fix it and re-run.")


hook_scripts = [
    name for name in os.listdir(os.path.join(repo, "hooks"))
    if name.endswith(".sh")
]


def owned(entry):
    """True when a hook entry belongs to this repo.

    Matches on the current path, and also on the hook script filenames, so a
    stale entry left behind by an earlier clone or a renamed directory is
    replaced rather than duplicated.
    """
    blob = json.dumps(entry)
    if repo in blob:
        return True
    return any(name in blob for name in hook_scripts)


hooks = settings.setdefault("hooks", {})
for event, entries in fragment.get("hooks", {}).items():
    current = [e for e in hooks.get(event, []) if not owned(e)]
    if mode == "install":
        current.extend(entries)
    if current:
        hooks[event] = current
    else:
        hooks.pop(event, None)
if not hooks:
    settings.pop("hooks", None)

perms = settings.setdefault("permissions", {})
for bucket, values in fragment.get("permissions", {}).items():
    current = perms.get(bucket, [])
    if mode == "install":
        for value in values:
            if value not in current:
                current.append(value)
    else:
        current = [v for v in current if v not in values]
    if current:
        perms[bucket] = current
    else:
        perms.pop(bucket, None)
if not perms:
    settings.pop("permissions", None)

with open(path, "w") as fh:
    json.dump(settings, fh, indent=2)
    fh.write("\n")
print(f"  {mode}ed hook and permission entries in {path}")
PY
}

# ----------------------------------------------------------------------- main

if [ "$UNINSTALL" = 1 ]; then
  step "Uninstalling from $CLAUDE_DIR"
else
  step "Installing $REPO_DIR into $CLAUDE_DIR"
fi

step "Skills"
link_into "$REPO_DIR/skills" "$CLAUDE_DIR/skills" '*'

step "Rules"
link_into "$REPO_DIR/rules" "$CLAUDE_DIR/rules" '*.md'

step "Agents"
link_into "$REPO_DIR/agents" "$CLAUDE_DIR/agents" '*.md'

step "Hooks and permissions"
if [ "$UNINSTALL" = 1 ]; then
  merge_settings uninstall
else
  merge_settings install
fi

if [ "$UNINSTALL" = 0 ]; then
  step "Notes"
  info "a standalone commit skill or plugin will compete with ship; disable one"
  info "start a new session for rules and hooks to take effect"
fi

step "Done"
