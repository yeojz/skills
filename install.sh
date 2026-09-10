#!/usr/bin/env bash
#
# Install this repo's skills, rules, agents and hooks into ~/.claude, and its
# skills into ~/.codex when Codex CLI is present.
#
# Everything is symlinked, so `git pull` in this repo updates every machine
# without reinstalling. Only settings.json is copied into, and it is backed up
# first and merged rather than overwritten.
#
#   ./install.sh              install or refresh
#   ./install.sh --dry-run    print what would change, touch nothing
#   ./install.sh --uninstall  remove this repo's symlinks and settings entries
#
# CLAUDE_CONFIG_DIR overrides ~/.claude. CODEX_HOME overrides ~/.codex; only
# skills go there, since Codex reads rules from AGENTS.md (see make-agents-md.sh).
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
SETTINGS="$CLAUDE_DIR/settings.json"
BACKUP_DIR="$CLAUDE_DIR/.install-backup"
FRAGMENT="$REPO_DIR/hooks/settings.fragment.json"

DRY_RUN=0
UNINSTALL=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 1 ;;
  esac
done

info()  { printf '  %s\n' "$*"; }
step()  { printf '\n%s\n' "$*"; }
run()   { if [ "$DRY_RUN" = 1 ]; then info "would: $*"; else "$@"; fi; }

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }

# The repo path is embedded in a hook command line; a newline cannot be
# escaped inside a double-quoted shell word, so refuse rather than install a
# broken hook.
case "$REPO_DIR" in
  *$'\n'*) echo "refusing to install: the repo path contains a newline" >&2; exit 1 ;;
esac

# ---------------------------------------------------------------- link helper

link_into() {
  # link_into <source dir> <target dir> <glob>
  local src_dir="$1" dest_dir="$2" glob="$3"
  [ -d "$src_dir" ] || return 0
  if [ "$UNINSTALL" = 1 ]; then
    [ -d "$dest_dir" ] || return 0
  else
    run mkdir -p "$dest_dir"
  fi

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
      if [ -e "$dest" ]; then
        info "SKIPPED  $name already exists and is not a link from this repo (links to $(readlink "$dest"))"
        info "         move or delete $dest, then re-run"
        continue
      fi
      # A dangling link points at nothing, so replacing it loses nothing.
      info "replace  $name (was a dangling link to $(readlink "$dest"))"
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

  mkdir -p "$CLAUDE_DIR"

  REPO_DIR="$REPO_DIR" SETTINGS="$SETTINGS" FRAGMENT="$FRAGMENT" \
  BACKUP_DIR="$BACKUP_DIR" MODE="$mode" python3 <<'PY'
import json, os, re, sys, tempfile, time

repo = os.environ["REPO_DIR"]
path = os.environ["SETTINGS"]
mode = os.environ["MODE"]
backup_dir = os.environ["BACKUP_DIR"]
PLACEHOLDER = "__AGENT_CONFIG_DIR__"
KEEP_BACKUPS = 5

# The path lands inside a double-quoted shell word, so only the characters
# the shell still interprets there need escaping.
shell_safe_repo = re.sub(r'([\\"$`])', r"\\\1", repo)


def substitute(node):
    if isinstance(node, dict):
        return {key: substitute(value) for key, value in node.items()}
    if isinstance(node, list):
        return [substitute(value) for value in node]
    if isinstance(node, str):
        return node.replace(PLACEHOLDER, shell_safe_repo)
    return node


with open(os.environ["FRAGMENT"]) as fh:
    fragment = substitute(json.load(fh))

try:
    with open(path) as fh:
        original = fh.read()
    settings = json.loads(original)
except FileNotFoundError:
    original = None
    settings = {}
except json.JSONDecodeError as exc:
    sys.exit(f"{path} is not valid JSON ({exc}). Fix it and re-run.")


def commands_in(entry):
    if not isinstance(entry, dict):
        return []
    return [
        hook.get("command", "")
        for hook in entry.get("hooks", [])
        if isinstance(hook, dict)
    ]


def unquote(command):
    if len(command) >= 2 and command[0] == '"' and command[-1] == '"':
        return command[1:-1]
    return command


fragment_commands = {
    command
    for entries in fragment.get("hooks", {}).values()
    for entry in entries
    for command in commands_in(entry)
}
hook_suffixes = {
    "/hooks/" + os.path.basename(unquote(command)) for command in fragment_commands
}


def owned(entry):
    """True when a hook entry was installed by this repo.

    The suffix match keeps recognising an entry written by an earlier clone
    at another path, so a moved checkout replaces it instead of duplicating it.
    """
    for command in commands_in(entry):
        if command in fragment_commands:
            return True
        if any(unquote(command).endswith(suffix) for suffix in hook_suffixes):
            return True
    return False


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

merged = json.dumps(settings, indent=2) + "\n"
if merged == original:
    print(f"  no change to {path}")
    sys.exit(0)

if original is not None:
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    backup = os.path.join(backup_dir, "settings.json." + time.strftime("%Y%m%d-%H%M%S"))
    with open(backup, "w") as fh:
        fh.write(original)
    print(f"  backed up {path} to {backup}")
    backups = sorted(
        name for name in os.listdir(backup_dir) if name.startswith("settings.json.")
    )
    for stale in backups[:-KEEP_BACKUPS]:
        os.remove(os.path.join(backup_dir, stale))

# Write beside the target and rename so a crash never leaves a half-written
# settings file behind.
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".settings.json.")
with os.fdopen(fd, "w") as fh:
    fh.write(merged)
if original is not None:
    os.chmod(tmp, os.stat(path).st_mode & 0o777)
os.replace(tmp, path)
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
  if [ "$DRY_RUN" = 0 ] && [ -d "$BACKUP_DIR" ]; then
    if rmdir "$BACKUP_DIR" 2>/dev/null; then
      info "removed empty $BACKUP_DIR"
    else
      info "kept $BACKUP_DIR, it still holds settings backups"
    fi
  fi
else
  merge_settings install
fi

step "Codex skills"
if [ -d "$CODEX_DIR" ]; then
  link_into "$REPO_DIR/skills" "$CODEX_DIR/skills" '*'
else
  info "Codex not detected at $CODEX_DIR, skipped"
fi

if [ "$UNINSTALL" = 0 ]; then
  step "Notes"
  info "a standalone commit skill or plugin will compete with ship; disable one"
  info "start a new session for rules and hooks to take effect"
fi

step "Done"
