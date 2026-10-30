#!/usr/bin/env python3
"""Guard-deletion sampling for a diff-scoped review.

For every rejecting guard the diff added, neutralise its condition, run the
package's tests, restore the file, and report which mutants survived. A guard
whose deletion leaves the suite green has no test behind it.

Usage:   guard-deletion.py [--list] <base-ref> <test-command> [path ...]
Example: guard-deletion.py origin/main 'pnpm --filter @scope/core test:ci' packages/core

The diff is the working tree against the merge base of <base-ref> and HEAD,
so a branch review sees what the branch did plus anything uncommitted, and
HEAD as the base ref scopes it to the uncommitted changes alone. Paths narrow
the scan and are handed to git diff as given. Untracked files are not in a
diff, so `git add -N` them first.

A rejecting guard is an added `if` whose body throws, returns, rejects,
raises, exits, panics, aborts, fails or answers with a 4xx or 5xx status, in
a JavaScript, TypeScript, Go, Rust, Java, Kotlin, Swift, C-family, PHP or
Python file. Neutralising means `if (false && (<condition>))`, or
`if False and (<condition>):` in Python, so the file still parses and every
name the condition used is still referenced.

The test command is the repo's own declared script, run through the shell
from the current directory. The suite must be green before the first
mutation; otherwise nothing a mutant does can be told from the baseline.

--list prints the guards and runs nothing.

Exit codes: 0 when every mutant was killed, 1 when at least one survived,
2 on a usage error, a red baseline, or a file that could not be restored.
"""

import os
import re
import subprocess
import sys
import tempfile
import time

BRACE_SUFFIXES = {
    '.ts', '.tsx', '.mts', '.cts', '.js', '.jsx', '.mjs', '.cjs',
    '.go', '.rs', '.java', '.kt', '.kts', '.swift', '.php',
    '.c', '.h', '.cc', '.cpp', '.hpp', '.cs',
}
PYTHON_SUFFIXES = {'.py'}

REJECTS = re.compile(
    r'\b(throw|return|reject|raise|exit|panic|abort|fail)\b'
    r'|\.status\(\s*[45]\d\d'
)
BRACE_IF = re.compile(r'\s*(?:\}\s*)?(?:else\s+)?if\s*\(')
PYTHON_IF = re.compile(r'(\s*)(?:el)?if\s+')
HUNK = re.compile(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')


class Guard:
    def __init__(self, path, line, kind, cond_start, cond_end, condition):
        self.path = path
        self.line = line
        self.kind = kind
        self.cond_start = cond_start
        self.cond_end = cond_end
        self.condition = condition
        self.exit_code = None

    def location(self):
        return '%s:%d' % (self.path, self.line)

    def label(self):
        collapsed = ' '.join(self.condition.split())
        if len(collapsed) > 60:
            collapsed = collapsed[:57] + '...'
        if self.kind == 'python':
            return 'if %s:' % collapsed
        return 'if (%s)' % collapsed

    def mutate(self, text):
        if self.kind == 'python':
            return (text[:self.cond_start] + 'False and ('
                    + text[self.cond_start:self.cond_end] + ')'
                    + text[self.cond_end:])
        return (text[:self.cond_start] + 'false && ('
                + text[self.cond_start:self.cond_end] + ')'
                + text[self.cond_end:])


def usage(message=None):
    if message:
        print(message, file=sys.stderr)
    print('Usage:   %s [--list] <base-ref> <test-command> [path ...]' % os.path.basename(sys.argv[0]), file=sys.stderr)
    print("Example: %s origin/main 'pnpm --filter @scope/core test:ci' packages/core" % os.path.basename(sys.argv[0]), file=sys.stderr)
    sys.exit(2)


def git(*args):
    completed = subprocess.run(
        ['git', '-c', 'core.quotepath=false', *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if completed.returncode != 0:
        print('git %s failed:\n%s' % (' '.join(args), completed.stderr.strip()), file=sys.stderr)
        sys.exit(2)
    return completed.stdout


def added_lines(merge_base, paths):
    """Map each changed file to the line numbers the diff added, working-tree numbering."""
    diff = git('diff', '-U0', '--no-color', '--no-ext-diff', merge_base, '--', *paths)
    added = {}
    current = None
    new_line = 0
    for raw in diff.splitlines():
        if raw.startswith('+++ '):
            target = raw[4:]
            if target == '/dev/null':
                current = None
                continue
            if target.startswith('"') and target.endswith('"'):
                target = target[1:-1]
            current = target[2:] if target.startswith('b/') else target
            added.setdefault(current, [])
        elif raw.startswith('@@'):
            hunk = HUNK.match(raw)
            if hunk:
                new_line = int(hunk.group(1))
        elif current is None or raw.startswith('\\'):
            continue
        elif raw.startswith('+'):
            added[current].append(new_line)
            new_line += 1
        elif raw.startswith(' '):
            new_line += 1
    return added


def skip_string(text, index):
    """Return the index just past the string literal opening at index."""
    quote = text[index]
    index += 1
    while index < len(text):
        char = text[index]
        if char == '\\':
            index += 2
            continue
        if char == quote:
            return index + 1
        if char == '\n' and quote != '`':
            return index
        index += 1
    return index


def match_delimiter(text, open_index, open_char, close_char):
    """Index of the delimiter closing the one at open_index, or None."""
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char in '\'"`':
            index = skip_string(text, index)
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def brace_body(text, after_condition):
    index = after_condition
    while index < len(text) and text[index] in ' \t\r\n':
        index += 1
    if index < len(text) and text[index] == '{':
        close = match_delimiter(text, index, '{', '}')
        return text[index:close + 1] if close is not None else text[index:]
    end = index
    while end < len(text) and text[end] not in ';\n':
        end += 1
    return text[index:end]


def python_condition_end(text, start):
    """Index of the colon that ends the condition opened at start, or None."""
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char in '\'"':
            index = skip_string(text, index)
            continue
        if char == '#':
            while index < len(text) and text[index] != '\n':
                index += 1
            continue
        if char in '([{':
            depth += 1
        elif char in ')]}':
            depth -= 1
        elif char == ':' and depth == 0:
            return index
        elif char == '\n' and depth == 0:
            return None
        index += 1
    return None


def python_body(lines, line_index, indent, after_colon):
    same_line = after_colon.strip()
    if same_line and not same_line.startswith('#'):
        return same_line
    body = []
    for following in lines[line_index + 1:]:
        if not following.strip():
            continue
        if len(following) - len(following.lstrip()) <= indent:
            break
        body.append(following)
    return '\n'.join(body)


def find_guards(path, text, line_numbers):
    suffix = os.path.splitext(path)[1]
    if suffix in BRACE_SUFFIXES:
        kind = 'brace'
    elif suffix in PYTHON_SUFFIXES:
        kind = 'python'
    else:
        return []

    lines = text.split('\n')
    offsets = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line) + 1

    guards = []
    for number in line_numbers:
        if number < 1 or number > len(lines):
            continue
        line = lines[number - 1]
        if kind == 'brace':
            head = BRACE_IF.match(line)
            if not head:
                continue
            open_index = offsets[number - 1] + head.end() - 1
            close_index = match_delimiter(text, open_index, '(', ')')
            if close_index is None:
                continue
            body = brace_body(text, close_index + 1)
            if REJECTS.search(body):
                guards.append(Guard(path, number, kind, open_index + 1, close_index,
                                    text[open_index + 1:close_index]))
        else:
            head = PYTHON_IF.match(line)
            if not head:
                continue
            start = offsets[number - 1] + head.end()
            colon = python_condition_end(text, start)
            if colon is None:
                continue
            colon_line = text.count('\n', 0, colon)
            after_colon = text[colon + 1:offsets[colon_line] + len(lines[colon_line])]
            body = python_body(lines, colon_line, len(head.group(1)), after_colon)
            if REJECTS.search(body):
                guards.append(Guard(path, number, kind, start, colon, text[start:colon]))
    return guards


def run_tests(command, log_path):
    started = time.monotonic()
    with open(log_path, 'wb') as log:
        completed = subprocess.run(command, shell=True, stdout=log, stderr=subprocess.STDOUT)
    return completed.returncode, time.monotonic() - started


def tail(log_path, count=20):
    with open(log_path, 'rb') as log:
        lines = log.read().decode('utf-8', 'replace').splitlines()
    return '\n'.join(lines[-count:])


def restore(path, original):
    with open(path, 'wb') as handle:
        handle.write(original)
    with open(path, 'rb') as handle:
        if handle.read() != original:
            print('%s could not be restored; the working tree is not the reviewed one' % path, file=sys.stderr)
            sys.exit(2)


def main(argv):
    list_only = False
    if argv and argv[0] == '--list':
        list_only = True
        argv = argv[1:]
    if len(argv) < 2:
        usage()
    base_ref, test_command, paths = argv[0], argv[1], argv[2:]

    root = git('rev-parse', '--show-toplevel').strip()
    merge_base = git('merge-base', base_ref, 'HEAD').strip()
    changed = added_lines(merge_base, paths)

    originals = {}
    guards = []
    for path in sorted(changed):
        absolute = os.path.join(root, path)
        if not os.path.isfile(absolute):
            continue
        with open(absolute, 'rb') as handle:
            original = handle.read()
        try:
            text = original.decode('utf-8')
        except UnicodeDecodeError:
            continue
        found = find_guards(path, text, changed[path])
        if found:
            originals[path] = (absolute, original, text)
            guards.extend(found)

    if not guards:
        print('No new rejecting guard in the diff against %s (%d changed files).' % (base_ref, len(changed)))
        return 0

    print('%d rejecting guards added since %s:' % (len(guards), base_ref))
    for guard in guards:
        print('  %s  %s' % (guard.location(), guard.label()))
    if list_only:
        return 0

    log_dir = tempfile.mkdtemp(prefix='guard-deletion-')
    baseline_log = os.path.join(log_dir, 'baseline.log')
    code, seconds = run_tests(test_command, baseline_log)
    if code != 0:
        sys.stdout.flush()
        print('\nBaseline is red (exit %d), so nothing a mutant does can be told from it. Last lines:\n%s'
              % (code, tail(baseline_log)), file=sys.stderr)
        return 2
    print('\nBaseline green in %.0fs; %d mutants to run, about %.0f minutes.\n'
          % (seconds, len(guards), seconds * len(guards) / 60))

    for index, guard in enumerate(guards, 1):
        absolute, original, text = originals[guard.path]
        mutated = guard.mutate(text).encode('utf-8')
        try:
            with open(absolute, 'wb') as handle:
                handle.write(mutated)
            guard.exit_code, _ = run_tests(test_command, os.path.join(log_dir, 'mutant-%d.log' % index))
        finally:
            restore(absolute, original)
        verdict = 'killed' if guard.exit_code != 0 else 'SURVIVED'
        print('[%d/%d] %s  %s  %s (exit %d)' % (index, len(guards), guard.location(), guard.label(), verdict, guard.exit_code))

    survivors = [guard for guard in guards if guard.exit_code == 0]
    print('\n| Guard | Location | Result |\n|---|---|---|')
    for guard in guards:
        verdict = 'killed' if guard.exit_code != 0 else 'SURVIVED'
        print('| `%s` | `%s` | %s, exit %d |' % (guard.label(), guard.location(), verdict, guard.exit_code))
    print('\nFiles restored byte for byte: %d. Logs: %s' % (len(originals), log_dir))
    if survivors:
        print('\nSurvivors: %d of %d. Each is a High: no test fails when the guard is removed. Name the test that should have caught it.'
              % (len(survivors), len(guards)))
        for guard in survivors:
            print('  %s  %s' % (guard.location(), guard.label()))
        return 1
    print('\nSurvivors: 0 of %d. Every new rejecting guard has a test behind it.' % len(guards))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
