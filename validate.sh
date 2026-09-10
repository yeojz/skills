#!/usr/bin/env bash
# Check every skill, rule, agent, template, hook and script in this repo is well formed.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

fail=0
note() { printf '  %s\n' "$*"; }
bad()  { printf '  FAIL %s\n' "$*"; fail=1; }

# BSD grep has no -P, so the emoji check goes through python3.
# Exits 0 when the file is clean, 1 when it contains an emoji.
emoji_free() {
  python3 - "$1" <<'EMOJI'
import re, sys
pattern = re.compile('[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]')
sys.exit(1 if pattern.search(open(sys.argv[1], encoding='utf-8').read()) else 0)
EMOJI
}

printf '\nSkills\n'
for dir in skills/*/; do
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

  emoji_free "$dir/SKILL.md" || bad "$name: SKILL.md contains emoji"

  # Every skill has to be discoverable from the README's Skills table.
  grep -q "^|.*\`$name\`" README.md || bad "$name: not listed in the README Skills table"

  evals_count="$(python3 -c 'import json, sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))["evals"]))' "$dir/evals/evals.json" 2>/dev/null || echo '?')"
  note "$(printf '%-16s %s lines, %s evals' "$name" "$(grep -c '' "$dir/SKILL.md")" "$evals_count")"
done

printf '\nRules\n'
for f in rules/*.md; do
  [ -e "$f" ] || { bad "no rule files"; break; }
  lines="$(grep -c '' "$f")"
  [ "$lines" -le 80 ] || bad "$(basename "$f"): $lines lines, rules must stay short"
  emoji_free "$f" || bad "$(basename "$f"): contains emoji"
  note "$(printf '%-24s %s lines' "$(basename "$f")" "$lines")"
done

printf '\nAgents\n'
for f in agents/*.md; do
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
[ -d templates ] && bad "top-level templates/ must not exist, templates live at skills/<name>/template.md"
for f in skills/*/template.md; do
  [ -e "$f" ] || break
  label="$(basename "$(dirname "$f")")/template.md"
  head -1 "$f" | grep -q '^---$' && bad "$label: templates must not have frontmatter"
  emoji_free "$f" || bad "$label: contains emoji"
  note "$label"
done

printf '\nDocs\n'
for f in README.md AUTHORING.md CONTRIBUTING.md; do
  [ -e "$f" ] || continue
  emoji_free "$f" || bad "$f: contains emoji"
  note "$f"
done

printf '\nHooks\n'
for f in hooks/*.sh; do
  [ -x "$f" ] || bad "$(basename "$f"): not executable"
  note "$(basename "$f")"
done
python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' hooks/settings.fragment.json 2>/dev/null \
  || bad "settings.fragment.json is not valid JSON"
grep -q '__AGENT_CONFIG_DIR__' hooks/settings.fragment.json \
  || bad "settings.fragment.json lost its path placeholder"
note "settings.fragment.json"

printf '\nHook behaviour\n'
if ./hooks/test-hooks.sh >/dev/null 2>&1; then
  note "hook regression suite passed"
else
  bad "hook regression suite failed, run ./hooks/test-hooks.sh to see which case"
fi

printf '\nScripts\n'
scripts=(install.sh make-agents-md.sh validate.sh hooks/*.sh)
for f in "${scripts[@]}"; do
  if bash -n "$f" 2>/dev/null; then
    note "$f syntax ok"
  else
    bad "$f: syntax error"
  fi
done

# Static analysis is optional so a fresh clone still validates without shellcheck.
if command -v shellcheck >/dev/null 2>&1; then
  if shellcheck -S warning "${scripts[@]}"; then
    note "shellcheck clean"
  else
    bad "shellcheck reported warnings above"
  fi
else
  note "shellcheck not installed, static analysis skipped"
fi

if [ "$fail" = 0 ]; then
  printf '\nAll checks passed\n'
else
  printf '\nThere are failures above\n'
fi
exit "$fail"
