#!/usr/bin/env bash
# Runs test files one at a time and stops at the first one that leaves the
# given path behind, so a stray file or directory can be pinned on a single
# test instead of on the whole suite.
#
# Usage:   find-polluter.sh <path-to-check> <test-root> <name-glob> <test-command>
# Example: find-polluter.sh .git src '*.test.ts' 'pnpm test:ci --'
#
# The test command is the repo's own declared script; each test file path is
# appended to it as the last argument.
set -euo pipefail

if [ "$#" -ne 4 ]; then
  printf 'Usage: %s <path-to-check> <test-root> <name-glob> <test-command>\n' "$0" >&2
  printf "Example: %s .git src '*.test.ts' 'pnpm test:ci --'\n" "$0" >&2
  exit 2
fi

pollution_path="$1"
test_root="$2"
name_glob="$3"
read -r -a test_command <<< "$4"

# Bisection only means something from a clean state; otherwise the first test
# to run looks guilty regardless of what it did.
if [ -e "$pollution_path" ]; then
  printf '%s already exists. Remove it, then run this again.\n' "$pollution_path" >&2
  exit 2
fi

total="$(find "$test_root" -type f -name "$name_glob" -print0 | tr -dc '\0' | wc -c | tr -d ' ')"
if [ "$total" -eq 0 ]; then
  printf 'No files matching %s under %s\n' "$name_glob" "$test_root" >&2
  exit 2
fi
printf 'Checking %s test files for one that creates %s\n' "$total" "$pollution_path"

# The list is sorted so a re-run visits the files in the same order and its
# report can be compared with the previous one.
count=0
while IFS= read -r -d '' test_file; do
  count=$((count + 1))
  printf '[%s/%s] %s\n' "$count" "$total" "$test_file"

  # A failing test can still pollute, so its exit code is not the signal here.
  "${test_command[@]}" "$test_file" > /dev/null 2>&1 || true

  if [ -e "$pollution_path" ]; then
    printf '\nPolluter: %s\nCreated:  %s\n\n' "$test_file" "$pollution_path"
    ls -la "$pollution_path"
    printf '\nNext: run that file alone with the same command and read its setup code.\n'
    exit 1
  fi
done < <(find "$test_root" -type f -name "$name_glob" -print0 | sort -z)

printf '\nNo polluter found among %s files.\n' "$total"
exit 0
