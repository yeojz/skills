#!/usr/bin/env bash
# Check every skill, rule, agent and template in this repo is well formed.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

fail=0
note() { printf '  %s\n' "$*"; }
bad()  { printf '  FAIL %s\n' "$*"; fail=1; }

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
    python3 -c "
import json,sys
d=json.load(open('$dir/evals/evals.json'))
assert d['skill_name']=='$name', 'skill_name is '+d['skill_name']
assert len(d['evals'])>=3, 'only %d evals' % len(d['evals'])
for e in d['evals']:
    for key in ('id','prompt','expected_output','expectations'):
        assert key in e, 'eval %s missing %s' % (e.get('id'), key)
    assert e['expectations'], 'eval %s has no expectations' % e['id']
" 2>/dev/null || bad "$name: evals.json invalid or incomplete"
  fi

  grep -qE '## Common Mistakes' "$dir/SKILL.md" || bad "$name: no Common Mistakes table"

  # BSD grep has no -P, so the emoji check goes through python3.
  if ! python3 - "$dir/SKILL.md" <<'EMOJI'
import re, sys
pattern = re.compile('[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]')
sys.exit(1 if pattern.search(open(sys.argv[1], encoding='utf-8').read()) else 0)
EMOJI
  then
    bad "$name: SKILL.md contains emoji"
  fi

  evals_count="$(python3 -c "import json;print(len(json.load(open('$dir/evals/evals.json'))['evals']))" 2>/dev/null || echo '?')"
  note "$(printf '%-16s %s lines, %s evals' "$name" "$(grep -c '' "$dir/SKILL.md")" "$evals_count")"
done

printf '\nRules\n'
for f in rules/*.md; do
  [ -e "$f" ] || { bad "no rule files"; break; }
  lines="$(grep -c '' "$f")"
  [ "$lines" -le 80 ] || bad "$(basename "$f"): $lines lines, rules must stay short"
  note "$(printf '%-24s %s lines' "$(basename "$f")" "$lines")"
done

printf '\nAgents\n'
for f in agents/*.md; do
  [ -e "$f" ] || { bad "no agent files"; break; }
  head -1 "$f" | grep -q '^---$' || bad "$(basename "$f"): no frontmatter"
  grep -qE '^tools:' "$f" || bad "$(basename "$f"): no tools line"
  grep -qE '^tools:.*(Edit|Write)' "$f" && bad "$(basename "$f"): review agents must not have Edit or Write"
  note "$(basename "$f")"
done

printf '\nTemplates\n'
for f in templates/*.md; do
  [ -e "$f" ] || { bad "no templates"; break; }
  head -1 "$f" | grep -q '^---$' && bad "$(basename "$f"): templates must not have frontmatter"
  note "$(basename "$f")"
done

printf '\nHooks\n'
for f in hooks/*.sh; do
  [ -x "$f" ] || bad "$(basename "$f"): not executable"
  bash -n "$f" || bad "$(basename "$f"): syntax error"
  note "$(basename "$f")"
done
python3 -c "import json;json.load(open('hooks/settings.fragment.json'))" 2>/dev/null \
  || bad "settings.fragment.json is not valid JSON"
grep -q '__AI_WORKFLOWS_DIR__' hooks/settings.fragment.json \
  || bad "settings.fragment.json lost its path placeholder"
note "settings.fragment.json"

printf '\nHook behaviour\n'
if ./hooks/test-hooks.sh >/dev/null 2>&1; then
  note "hook regression suite passed"
else
  bad "hook regression suite failed, run ./hooks/test-hooks.sh to see which case"
fi

printf '\nScripts\n'
bash -n install.sh && note "install.sh syntax ok" || bad "install.sh syntax error"

if [ "$fail" = 0 ]; then
  printf '\nAll checks passed\n'
else
  printf '\nThere are failures above\n'
fi
exit "$fail"
