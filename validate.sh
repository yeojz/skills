#!/usr/bin/env bash
# Check every skill, rule, agent, template, hook, manifest and script in this
# repo is well formed.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

# jz is the one plugin, read by both Claude Code and Codex.
PLUGIN=plugins/jz

fail=0
note() { printf '  %s\n' "$*"; }
bad()  { printf '  FAIL %s\n' "$*"; fail=1; }

# BSD grep has no -P, so the emoji check goes through python3.
# Exits 0 when the file is clean, 1 when it contains an emoji.
emoji_free() {
  python3 - "$1" <<'EMOJI'
import re, sys
pattern = re.compile('[\U0001F300-\U0001FAFF☀-➿️]')
sys.exit(1 if pattern.search(open(sys.argv[1], encoding='utf-8').read()) else 0)
EMOJI
}

# A skill or template that removes a throwaway worktree and then names its
# directory again tells the reader to run a step in a checkout that is gone.
# Prints each such use and exits 1; a later assignment to the variable starts
# a new lifetime.
worktree_lifetime_ok() {
  python3 - "$1" <<'WORKTREE'
import re, sys
path = sys.argv[1]
removed = {}
ok = True
for number, line in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
    for name in re.findall(r'git worktree remove\s+(?:--force\s+)?"\$(\w+)"', line):
        removed[name] = number
        continue
    for name, at in list(removed.items()):
        if re.match(r'\s*' + name + r'=', line):
            del removed[name]
        elif at != number and re.search(r'\$\{?' + name + r'\b', line):
            print('  FAIL %s:%d: $%s is used after its worktree was removed at line %d' % (path, number, name, at))
            ok = False
sys.exit(0 if ok else 1)
WORKTREE
}

# Claude Code fills a skill's text with its arguments before the model reads
# it: $ARGUMENTS, and $<digits> not followed by a word character, counted from
# $0. An awk $2 in a snippet arrives as a word the user typed. A backslash
# escape is not a fix, since Codex reads the file as written. Prints each
# such placeholder and exits 1.
no_argument_placeholders() {
  python3 - "$1" <<'PLACEHOLDER'
import re, sys
path = sys.argv[1]
ok = True
for number, line in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
    for match in re.finditer(r'\$(?:\d+(?!\w)|ARGUMENTS)', line):
        print('  FAIL %s:%d: %s is replaced with the skill arguments on load; use ${N} in shell, a -v variable or regex in awk' % (path, number, match.group(0)))
        ok = False
sys.exit(0 if ok else 1)
PLACEHOLDER
}

printf '\nManifests\n'
# Every directory under plugins/ is a plugin both marketplaces list, with a
# portable plugin.json at its root and a source that exists.
python3 - "$PLUGIN" <<'MANIFESTS' || fail=1
import json, os, sys
ok = True

def load(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)

def check(cond, message):
    global ok
    if not cond:
        print('  FAIL ' + message)
        ok = False

plugin_dirs = sorted('plugins/' + d for d in os.listdir('plugins') if os.path.isdir(os.path.join('plugins', d)))
check(plugin_dirs == sorted(sys.argv[1:]), 'plugins/ holds %r, this script knows %r' % (plugin_dirs, sorted(sys.argv[1:])))

claude_mp = load('.claude-plugin/marketplace.json')
check('name' in claude_mp and 'owner' in claude_mp and 'plugins' in claude_mp,
      '.claude-plugin/marketplace.json needs name, owner and plugins')
entries = {p.get('name'): p for p in claude_mp.get('plugins', [])}
codex_mp = load('.agents/plugins/marketplace.json')
check(codex_mp.get('name') == claude_mp.get('name'),
      'marketplace names differ: %r and %r' % (codex_mp.get('name'), claude_mp.get('name')))
codex_entries = {p.get('name'): p for p in codex_mp.get('plugins', [])}
check(set(entries) == set(os.path.basename(d) for d in plugin_dirs),
      '.claude-plugin/marketplace.json lists %r, plugins/ holds %r' % (sorted(entries), [os.path.basename(d) for d in plugin_dirs]))

for plugin_dir in plugin_dirs:
    plugin_name = os.path.basename(plugin_dir)
    check(plugin_name in entries, '.claude-plugin/marketplace.json does not list ' + plugin_name)
    claude_entry = entries.get(plugin_name, {})
    if plugin_name in entries:
        source = claude_entry.get('source')
        check(source == './' + plugin_dir, '.claude-plugin/marketplace.json source is %r, expected %r' % (source, './' + plugin_dir))
    for field in ('description', 'author', 'license'):
        check(field in claude_entry, '.claude-plugin/marketplace.json entry for %s needs %s' % (plugin_name, field))
    check('version' not in claude_entry, '.claude-plugin/marketplace.json entry for %s must not pin a version; installs track commits' % plugin_name)

    portable_path = os.path.join(plugin_dir, 'plugin.json')
    claude_path = os.path.join(plugin_dir, '.claude-plugin', 'plugin.json')
    if os.path.isfile(portable_path):
        # Agent-agnostic: the marketplace entry is the manifest for Claude Code,
        # so there is no .claude-plugin/plugin.json, and Codex reads plugin.json.
        check(not os.path.isfile(claude_path), '%s has both plugin.json and .claude-plugin/plugin.json' % plugin_dir)
        portable = load(portable_path)
        check(portable.get('name') == plugin_name, '%s name is %r' % (portable_path, portable.get('name')))
        check(portable.get('$schema', '').startswith('https://agent-plugins.org/schemas/'), portable_path + ' needs the agent-plugins.org $schema')
        check(portable.get('description') == claude_entry.get('description'), '%s: descriptions differ between the marketplace entry and plugin.json' % plugin_name)
        check(plugin_name in codex_entries, '.agents/plugins/marketplace.json does not list ' + plugin_name)
        if plugin_name in codex_entries:
            path = (codex_entries[plugin_name].get('source') or {}).get('path')
            check(path == './' + plugin_dir, '.agents/plugins/marketplace.json path is %r, expected %r' % (path, './' + plugin_dir))

        hooks = load(os.path.join(plugin_dir, 'hooks', 'hooks.json'))
        check('hooks' in hooks, plugin_dir + '/hooks/hooks.json needs a top-level hooks object')
        for event, groups in hooks.get('hooks', {}).items():
            for group in groups:
                for hook in group.get('hooks', []):
                    command = hook.get('command', '')
                    check('${CLAUDE_PLUGIN_ROOT}' in command, '%s hook command does not use ${CLAUDE_PLUGIN_ROOT}: %s' % (event, command))
                    script = command.strip('"').replace('${CLAUDE_PLUGIN_ROOT}', plugin_dir)
                    check(os.path.isfile(script), '%s hook names a missing script: %s' % (event, script))
                    check(os.access(script, os.X_OK), '%s hook script is not executable: %s' % (event, script))
        print('  ' + portable_path)
    else:
        check(False, plugin_dir + ' has no plugin.json')
    print('  ' + os.path.join(plugin_dir, 'hooks', 'hooks.json'))

for name in ('.claude-plugin/marketplace.json', '.agents/plugins/marketplace.json'):
    print('  ' + name)
sys.exit(0 if ok else 1)
MANIFESTS

printf '\nSkills\n'
for dir in "$PLUGIN"/skills/*/; do
  name="$(basename "$dir")"
  [ -f "$dir/SKILL.md" ] || { bad "$name: no SKILL.md"; continue; }
  [ -f "$dir/evals/evals.json" ] || bad "$name: no evals/evals.json"

  head -1 "$dir/SKILL.md" | grep -q '^---$' || bad "$name: SKILL.md does not open with frontmatter"

  fm_name="$(sed -n '2,10p' "$dir/SKILL.md" | grep -m1 '^name:' | sed 's/^name:[[:space:]]*//')"
  [ "$fm_name" = "$name" ] || bad "$name: frontmatter name is '$fm_name', expected '$name'"

  sed -n '2,10p' "$dir/SKILL.md" | grep -q '^description:' || bad "$name: no description in frontmatter"

  if [ -f "$dir/evals/evals.json" ]; then
    # Paths and names travel as argv, never interpolated into the Python source.
    if ! python3 - "$dir/evals/evals.json" "$name" <<'EVALS' 2>/dev/null
import json, sys
evals_path, skill_name = sys.argv[1], sys.argv[2]
d = json.load(open(evals_path, encoding='utf-8'))
assert d['skill_name'] == skill_name, 'skill_name is ' + d['skill_name']
assert len(d['evals']) >= 3, 'only %d evals' % len(d['evals'])
for e in d['evals']:
    for key in ('id', 'prompt', 'expected_output', 'expectations'):
        assert key in e, 'eval %s missing %s' % (e.get('id'), key)
    assert e['expectations'], 'eval %s has no expectations' % e['id']
EVALS
    then
      bad "$name: evals.json invalid or incomplete"
    fi
  fi

  grep -qE '## Common Mistakes' "$dir/SKILL.md" || bad "$name: no Common Mistakes table"

  # A skill is read in full on every load, so its length is a cost paid each time.
  skill_lines="$(grep -c '' "$dir/SKILL.md")"
  [ "$skill_lines" -le 300 ] || bad "$name: SKILL.md is $skill_lines lines, over the 300-line limit"

  emoji_free "$dir/SKILL.md" || bad "$name: SKILL.md contains emoji"

  worktree_lifetime_ok "$dir/SKILL.md" || bad "$name: SKILL.md uses a worktree after removing it"

  no_argument_placeholders "$dir/SKILL.md" || bad "$name: SKILL.md has a placeholder the skill arguments would replace"

  # Every skill has to be discoverable from the README's Skills table.
  grep -q "^|.*\`$name\`" README.md || bad "$name: not listed in the README Skills table"

  evals_count="$(python3 -c 'import json, sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))["evals"]))' "$dir/evals/evals.json" 2>/dev/null || echo '?')"
  note "$(printf '%-16s %s lines, %s evals' "$name" "$(grep -c '' "$dir/SKILL.md")" "$evals_count")"
done

printf '\nRules\n'
for f in "$PLUGIN"/rules/*.md; do
  [ -e "$f" ] || { bad "no rule files"; break; }
  lines="$(grep -c '' "$f")"
  [ "$lines" -le 80 ] || bad "$(basename "$f"): $lines lines, rules must stay short"
  emoji_free "$f" || bad "$(basename "$f"): contains emoji"
  note "$(printf '%-24s %s lines' "$(basename "$f")" "$lines")"
done

printf '\nAgents\n'
for f in "$PLUGIN"/agents/*.md; do
  [ -e "$f" ] || { bad "no agent files"; break; }
  head -1 "$f" | grep -q '^---$' || bad "$(basename "$f"): no frontmatter"
  sed -n '2,10p' "$f" | grep -q '^name:' || bad "$(basename "$f"): no name in frontmatter"
  sed -n '2,10p' "$f" | grep -q '^description:' || bad "$(basename "$f"): no description in frontmatter"
  grep -qE '^tools:' "$f" || bad "$(basename "$f"): no tools line"
  grep -qE '^tools:.*(Edit|Write)' "$f" && bad "$(basename "$f"): review agents must not have Edit or Write"
  emoji_free "$f" || bad "$(basename "$f"): contains emoji"
  note "$(basename "$f")"
done

printf '\nTemplates\n'
# Templates live beside the skill that uses them; a top-level directory
# would drift out of sync with the skill, so it must not come back.
[ -d templates ] && bad "top-level templates/ must not exist, templates live at $PLUGIN/skills/<name>/template.md"
for f in "$PLUGIN"/skills/*/template.md "$PLUGIN"/skills/*/template-*.md; do
  [ -e "$f" ] || continue
  label="$(basename "$(dirname "$f")")/$(basename "$f")"
  head -1 "$f" | grep -q '^---$' && bad "$label: templates must not have frontmatter"
  emoji_free "$f" || bad "$label: contains emoji"
  worktree_lifetime_ok "$f" || bad "$label: uses a worktree after removing it"
  no_argument_placeholders "$f" || bad "$label: has a placeholder the skill arguments would replace"
  note "$label"
done

printf '\nDocs\n'
for f in README.md AUTHORING.md CONTRIBUTING.md; do
  [ -e "$f" ] || continue
  emoji_free "$f" || bad "$f: contains emoji"
  note "$f"
done
# A plugin-root CLAUDE.md is never loaded, so its presence is a mistake.
[ -e "$PLUGIN/CLAUDE.md" ] && bad "$PLUGIN/CLAUDE.md is not loaded by plugins; put instructions in a skill or a rule"

printf '\nHooks\n'
for f in "$PLUGIN"/hooks/*.sh; do
  [ -x "$f" ] || bad "$(basename "$f"): not executable"
  note "$(basename "$f")"
done
for f in "$PLUGIN"/hooks/*.py "$PLUGIN"/hooks/guards/*.py; do
  python3 -m py_compile "$f" 2>/dev/null || bad "$(basename "$f"): does not compile"
  note "$(basename "$f")"
done

printf '\nHook behaviour\n'
if "$PLUGIN/hooks/test-hooks.sh" >/dev/null 2>&1; then
  note "hook regression suite passed"
else
  bad "hook regression suite failed, run $PLUGIN/hooks/test-hooks.sh to see which case"
fi

printf '\nFactory scripts\n'
# The factory's stages and gate are scripts, so they are checked the way the
# hooks are: executable, compiling, and passing their own suite.
FACTORY="$PLUGIN/skills/factory/scripts"
for f in "$FACTORY/job" "$FACTORY/gate" "$FACTORY/test-factory.sh"; do
  [ -x "$f" ] || bad "$(basename "$f"): not executable"
done
for f in "$FACTORY/job" "$FACTORY/gate" "$FACTORY/factorylib.py" "$FACTORY/dashboard.py"; do
  python3 -m py_compile "$f" 2>/dev/null || bad "$(basename "$f"): does not compile"
  note "$(basename "$f")"
done
if "$FACTORY/test-factory.sh" >/dev/null 2>&1; then
  note "factory regression suite passed"
else
  bad "factory regression suite failed, run $FACTORY/test-factory.sh to see which case"
fi

printf '\nPlugin validation\n'
# Claude Code's own validator is the authority on the manifests. It is optional
# here so a machine without the CLI still validates the rest.
if command -v claude >/dev/null 2>&1; then
  if claude plugin validate . >/dev/null 2>&1 && claude plugin validate "$PLUGIN" >/dev/null 2>&1; then
    note "claude plugin validate passed for the marketplace and the plugin"
  else
    bad "claude plugin validate failed, run it on . and $PLUGIN to see why"
  fi
else
  note "claude not installed, plugin validation skipped"
fi

printf '\nMakefile\n'
# A dry run proves every target parses and names a script that exists.
if make -n validate test >/dev/null 2>&1; then
  note "make targets parse"
else
  bad "Makefile: a target failed to parse, run 'make -n validate test'"
fi

if [ "$fail" = 0 ]; then
  printf '\nAll checks passed\n'
else
  printf '\nThere are failures above\n'
fi
exit "$fail"
