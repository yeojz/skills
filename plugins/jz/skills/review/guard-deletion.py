#!/usr/bin/env python3
"""Guard-deletion sampling for a diff-scoped review.

For every rejecting guard the diff added, neutralise its condition, run the
package's tests, restore the file, and report which mutants survived. A guard
whose deletion leaves the suite green has no test behind it.

Usage:   guard-deletion.py [--list] <base-ref> <test-command> [path ...]
Example: guard-deletion.py origin/main 'pnpm --filter @scope/core test:ci' packages/core

The diff is the working tree against the merge base of <base-ref> and HEAD,
so a branch review sees what the branch did plus anything uncommitted, and
HEAD as the base ref scopes it to the uncommitted changes alone. The script
samples the tree it runs in and prints that tree's HEAD and the merge base
it used, so run it in a checkout of the reviewed revision. Paths narrow the
scan and are handed to git diff as given. Untracked files are not in a diff,
so `git add -N` them first.

A rejecting guard is an added `if` whose body throws, returns, rejects,
raises, exits, panics, aborts, fails, calls a fatal routine or answers with a
4xx or 5xx status.
JavaScript, TypeScript, Java, Kotlin, C-family and PHP conditions are read
between the parentheses after `if`; Go, Rust and Swift conditions run from
`if` to the brace that opens the body; Python conditions run to the colon.
Neutralising means `if (false && (<condition>))`, `if false && (<condition>) {`
or `if False and (<condition>):`, so the file still parses and every name the
condition used is still referenced. A Go init statement stays in front of the
neutralised condition. A guard the mutation cannot wrap, such as `if let` or
a comma-separated Swift condition, is listed as unsupported and not sampled.
Conditional lines in files the script does not parse are counted and named.

The test command is the repo's own declared script, run through the shell
from the current directory. The suite must be green before the first
mutation; otherwise nothing a mutant does can be told from the baseline. A
mutant that fails to parse or compile is invalid and never counted as killed:
a Python compile or a `node --check` where one applies, otherwise a compiler
diagnostic in the test log that locates an error in the mutated file, in the
shapes tsc, clang, swiftc, javac, esbuild, go build, rustc and node print; a
stack frame or a message that quotes the file name is not a diagnostic. A
TypeScript guard that narrows a type is such a case: without it the file does
not type-check, so the compiler covers it and no test is shown to.

--list prints the guards and runs nothing.

Exit codes: 0 when every guard was sampled and every mutant was killed, 1 when
at least one mutant survived, 2 on a usage error, a red baseline, a file that
could not be restored, or a guard that was not sampled because its mutant did
not parse or compile or its construct was unsupported.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

PAREN_SUFFIXES = {
    '.ts', '.tsx', '.mts', '.cts', '.js', '.jsx', '.mjs', '.cjs',
    '.java', '.kt', '.kts', '.php', '.c', '.h', '.cc', '.cpp', '.hpp', '.cs',
}
FREE_SUFFIXES = {'.go', '.rs', '.swift'}
PYTHON_SUFFIXES = {'.py'}
REGEX_LITERAL_SUFFIXES = {'.ts', '.tsx', '.mts', '.cts', '.js', '.jsx', '.mjs', '.cjs'}
NODE_CHECK_SUFFIXES = {'.js', '.mjs', '.cjs'}

REJECTS = re.compile(
    r'\b(throw|return|reject|raise|exit|panic|abort|fail|fatal\w*)\b'
    r'|\.status\(\s*[45]\d\d',
    re.IGNORECASE,
)
BRACE_IF = re.compile(r'\s*(?:\}\s*)?(?:else\s+)?if\b')
PYTHON_IF = re.compile(r'(\s*)(?:el)?if\s+')
ANY_CONDITIONAL = re.compile(r'\s*(?:\}\s*)?(?:else\s+)?(?:if|elif|elsif|unless|guard|when)\b')
HUNK = re.compile(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')
BEFORE_REGEX = set('(,=!&|?:;{}[+-*%<>~^')
# A diagnostic that locates an error in the mutated file, in the shapes
# compilers print: `file(3,16): error TS2339`, `file:3:16 - error TS2339`,
# `file:3:16: error:` from clang, swiftc and javac, `file:3:16: ERROR:` from
# esbuild, `./file:3:16: undefined: x` from a go build that then reports
# `[build failed]`, `error[E0308]` followed by ` --> file:2:8` from rustc,
# and a bare `file:2` line followed by `SyntaxError` from node. A stack frame
# such as `at f (file:3:5)` or a message that happens to quote the file name
# matches none of them.
SAME_LINE_DIAGNOSTIC = re.compile(r'\s*(?:-\s*)?(?:error|ERROR|fatal error)\b')
GO_BUILD_FAILED = re.compile(r'\[(?:build|setup) failed\]')
RUST_ERROR_LINE = re.compile(r'^\s*error(?:\[E\d+\])?:', re.MULTILINE)
NODE_SYNTAX_LINE = re.compile(r'^\s*SyntaxError\b', re.MULTILINE)
ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
# Only a path may stand before the file name on a diagnostic line; a stack
# frame's `at f (` or a test runner's marker rules the line out.
PATH_PREFIX = re.compile(r'(?:#\s*)?[\w./\\~:-]*')


class Guard:
    def __init__(self, path, line, kind, cond_start, cond_end, condition, unsupported=None):
        self.path = path
        self.line = line
        self.kind = kind
        self.cond_start = cond_start
        self.cond_end = cond_end
        self.condition = condition
        self.unsupported = unsupported
        self.result = None
        self.exit_code = None

    def location(self):
        return '%s:%d' % (self.path, self.line)

    def label(self):
        collapsed = ' '.join(self.condition.split())
        if len(collapsed) > 60:
            collapsed = collapsed[:57] + '...'
        if self.kind == 'python':
            return 'if %s:' % collapsed
        if self.kind == 'free':
            return 'if %s {' % collapsed
        return 'if (%s)' % collapsed

    def mutate(self, text):
        condition = text[self.cond_start:self.cond_end]
        if self.kind == 'python':
            wrapped = 'False and (' + condition + ')'
        else:
            wrapped = 'false && (' + condition + ')'
        return text[:self.cond_start] + wrapped + text[self.cond_end:]

    def verdict(self):
        if self.unsupported:
            return 'unsupported (%s), not sampled' % self.unsupported
        if self.result == 'invalid':
            return 'INVALID mutant (did not parse or compile), not sampled'
        if self.result == 'survived':
            return 'SURVIVED, exit %d' % self.exit_code
        return 'killed, exit %d' % self.exit_code


def usage(message=None):
    if message:
        print(message, file=sys.stderr)
    name = os.path.basename(sys.argv[0])
    print('Usage:   %s [--list] <base-ref> <test-command> [path ...]' % name, file=sys.stderr)
    print("Example: %s origin/main 'pnpm --filter @scope/core test:ci' packages/core" % name, file=sys.stderr)
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


class Syntax:
    """What counts as noise, text the delimiter scan must step over, in one language."""

    def __init__(self, line_comment, block_comments, regex_literals):
        self.line_comment = line_comment
        self.block_comments = block_comments
        self.regex_literals = regex_literals

    def skip_noise(self, text, index):
        """Index just past the string, comment or regex literal starting at index, or None."""
        char = text[index]
        if char in '\'"`':
            return skip_string(text, index)
        if text.startswith(self.line_comment, index):
            end = text.find('\n', index)
            return len(text) if end < 0 else end
        if self.block_comments and text.startswith('/*', index):
            end = text.find('*/', index + 2)
            return len(text) if end < 0 else end + 2
        if self.regex_literals and char == '/' and starts_regex(text, index):
            return skip_regex(text, index)
        return None


BRACE_SYNTAX = Syntax('//', True, False)
JS_SYNTAX = Syntax('//', True, True)
PYTHON_SYNTAX = Syntax('#', False, False)


def skip_string(text, index):
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


def starts_regex(text, index):
    """A slash opens a regex literal when nothing an operand ends with precedes it."""
    before = index - 1
    while before >= 0 and text[before] in ' \t\r\n':
        before -= 1
    return before < 0 or text[before] in BEFORE_REGEX


def skip_regex(text, index):
    index += 1
    in_class = False
    while index < len(text):
        char = text[index]
        if char == '\\':
            index += 2
            continue
        if char == '\n':
            return index
        if in_class:
            if char == ']':
                in_class = False
        elif char == '[':
            in_class = True
        elif char == '/':
            index += 1
            while index < len(text) and text[index].isalpha():
                index += 1
            return index
        index += 1
    return index


def match_delimiter(text, open_index, open_char, close_char, syntax):
    """Index of the delimiter closing the one at open_index, or None."""
    depth = 0
    index = open_index
    while index < len(text):
        skipped = syntax.skip_noise(text, index)
        if skipped is not None:
            index = skipped
            continue
        char = text[index]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def scan_to_body_brace(text, start, syntax):
    """Index of the `{` at depth zero that opens the body of a paren-free `if`, or None."""
    depth = 0
    index = start
    while index < len(text):
        skipped = syntax.skip_noise(text, index)
        if skipped is not None:
            index = skipped
            continue
        char = text[index]
        if char in '([':
            depth += 1
        elif char in ')]':
            depth -= 1
        elif char == '{' and depth == 0:
            return index
        elif char == '\n' and depth == 0 and text[start:index].strip() == '':
            return None
        index += 1
    return None


def top_level_positions(text, start, end, wanted, syntax):
    """Offsets of each `wanted` character between start and end outside brackets and strings."""
    positions = []
    depth = 0
    index = start
    while index < end:
        skipped = syntax.skip_noise(text, index)
        if skipped is not None:
            index = skipped
            continue
        char = text[index]
        if char in '([{':
            depth += 1
        elif char in ')]}':
            depth -= 1
        elif char == wanted and depth == 0:
            positions.append(index)
        index += 1
    return positions


def brace_body(text, after_condition, syntax):
    index = after_condition
    while index < len(text) and text[index] in ' \t\r\n':
        index += 1
    if index < len(text) and text[index] == '{':
        close = match_delimiter(text, index, '{', '}', syntax)
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
        skipped = PYTHON_SYNTAX.skip_noise(text, index)
        if skipped is not None:
            index = skipped
            continue
        char = text[index]
        if char in '([{':
            depth += 1
        elif char in ')]}':
            depth -= 1
        elif char == ':' and depth == 0:
            return index
        elif char == '\n' and depth == 0:
            return None
        elif char == '\\':
            index += 1
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


def language_of(path):
    suffix = os.path.splitext(path)[1]
    if suffix in PAREN_SUFFIXES:
        return 'paren', JS_SYNTAX if suffix in REGEX_LITERAL_SUFFIXES else BRACE_SYNTAX
    if suffix in FREE_SUFFIXES:
        return 'free', BRACE_SYNTAX
    if suffix in PYTHON_SUFFIXES:
        return 'python', PYTHON_SYNTAX
    return None, None


def paren_guard(path, text, number, after_if, syntax):
    open_index = after_if
    while open_index < len(text) and text[open_index] in ' \t':
        open_index += 1
    if open_index >= len(text) or text[open_index] != '(':
        return None
    close_index = match_delimiter(text, open_index, '(', ')', syntax)
    if close_index is None:
        return None
    body = brace_body(text, close_index + 1, syntax)
    if not REJECTS.search(body):
        return None
    return Guard(path, number, 'paren', open_index + 1, close_index, text[open_index + 1:close_index])


def free_guard(path, text, number, after_if, syntax):
    suffix = os.path.splitext(path)[1]
    start = after_if
    while start < len(text) and text[start] in ' \t':
        start += 1
    brace = scan_to_body_brace(text, start, syntax)
    if brace is None:
        return None
    body = brace_body(text, brace, syntax)
    if not REJECTS.search(body):
        return None
    end = brace
    while end > start and text[end - 1] in ' \t\r\n':
        end -= 1
    condition = text[start:end]
    cond_start = start
    if suffix == '.go':
        semicolons = top_level_positions(text, start, end, ';', syntax)
        if semicolons:
            cond_start = semicolons[-1] + 1
            while cond_start < end and text[cond_start] in ' \t':
                cond_start += 1
    unsupported = None
    if suffix in ('.rs', '.swift') and re.search(r'\b(let|var|case)\b', text[cond_start:end]):
        unsupported = 'binding in the condition'
    elif suffix == '.swift' and top_level_positions(text, cond_start, end, ',', syntax):
        unsupported = 'comma-separated condition'
    return Guard(path, number, 'free', cond_start, end, condition, unsupported)


def python_guard(path, text, lines, offsets, number, head):
    start = offsets[number - 1] + head.end()
    colon = python_condition_end(text, start)
    if colon is None:
        return None
    colon_line = text.count('\n', 0, colon)
    after_colon = text[colon + 1:offsets[colon_line] + len(lines[colon_line])]
    body = python_body(lines, colon_line, len(head.group(1)), after_colon)
    if not REJECTS.search(body):
        return None
    return Guard(path, number, 'python', start, colon, text[start:colon])


def find_guards(path, text, line_numbers):
    kind, syntax = language_of(path)
    if kind is None:
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
        if kind == 'python':
            head = PYTHON_IF.match(line)
            guard = python_guard(path, text, lines, offsets, number, head) if head else None
        else:
            head = BRACE_IF.match(line)
            if not head:
                continue
            after_if = offsets[number - 1] + head.end()
            if kind == 'paren':
                guard = paren_guard(path, text, number, after_if, syntax)
            else:
                guard = free_guard(path, text, number, after_if, syntax)
        if guard:
            guards.append(guard)
    return guards


def unscanned_conditionals(path, text, line_numbers):
    lines = text.split('\n')
    return sum(1 for number in line_numbers
               if 1 <= number <= len(lines) and ANY_CONDITIONAL.match(lines[number - 1]))


def run_tests(command, log_path):
    started = time.monotonic()
    with open(log_path, 'wb') as log:
        completed = subprocess.run(command, shell=True, stdout=log, stderr=subprocess.STDOUT)
    return completed.returncode, time.monotonic() - started


def tail(log_path, count=20):
    with open(log_path, 'rb') as log:
        lines = log.read().decode('utf-8', 'replace').splitlines()
    return '\n'.join(lines[-count:])


def parses(path, mutated):
    """False when the mutant is known not to parse; True when it parses or no parser is at hand."""
    suffix = os.path.splitext(path)[1]
    if suffix in PYTHON_SUFFIXES:
        try:
            compile(mutated.decode('utf-8'), path, 'exec')
        except SyntaxError:
            return False
        return True
    if suffix in NODE_CHECK_SUFFIXES and shutil.which('node'):
        check = subprocess.run(['node', '--check', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return check.returncode == 0
    return True


def log_reports_compile_failure(log_path, path):
    """True when the run's output carries a compiler diagnostic located in the mutated file."""
    with open(log_path, 'rb') as log:
        content = ANSI_ESCAPE.sub('', log.read().decode('utf-8', 'replace'))
    lines = content.splitlines()
    located = re.compile(r'(?<![\w.-])' + re.escape(os.path.basename(path))
                         + r'(?:\(\d+,\d+\)|:\d+(?::\d+)?)')
    go_build_failed = GO_BUILD_FAILED.search(content) is not None
    for index, line in enumerate(lines):
        found = located.search(line)
        if not found:
            continue
        prefix = line[:found.start()].strip()
        path_only = PATH_PREFIX.fullmatch(prefix) is not None
        rest = line[found.end():]
        if prefix == '-->' and RUST_ERROR_LINE.search('\n'.join(lines[max(0, index - 3):index])):
            return True
        if not path_only:
            continue
        if rest.startswith(':') and SAME_LINE_DIAGNOSTIC.match(rest[1:]):
            return True
        if rest.lstrip().startswith('-') and SAME_LINE_DIAGNOSTIC.match(rest):
            return True
        if go_build_failed and re.match(r':\s', rest):
            return True
        if rest.strip() == '' and NODE_SYNTAX_LINE.search('\n'.join(lines[index + 1:index + 5])):
            return True
    return False


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
    head = git('rev-parse', '--short', 'HEAD').strip()
    merge_base = git('merge-base', base_ref, 'HEAD').strip()
    print('Sampling the working tree at %s against merge base %s of %s and HEAD.'
          % (head, merge_base[:12], base_ref))
    changed = added_lines(merge_base, paths)

    originals = {}
    guards = []
    unscanned = {}
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
        if language_of(path)[0] is None:
            count = unscanned_conditionals(path, text, changed[path])
            if count:
                unscanned[path] = count
            continue
        found = find_guards(path, text, changed[path])
        if found:
            originals[path] = (absolute, original, text)
            guards.extend(found)

    if unscanned:
        print('Not scanned: %d conditional lines in files this script does not parse: %s'
              % (sum(unscanned.values()), ', '.join(sorted(unscanned))))

    if not guards:
        print('No new rejecting guard in the diff against %s (%d changed files).' % (base_ref, len(changed)))
        return 0

    print('%d rejecting guards added since %s:' % (len(guards), base_ref))
    for guard in guards:
        note = '  [%s]' % guard.verdict() if guard.unsupported else ''
        print('  %s  %s%s' % (guard.location(), guard.label(), note))
    sampled = [guard for guard in guards if not guard.unsupported]
    if list_only:
        return 0 if len(sampled) == len(guards) else 2
    if not sampled:
        print('\nNothing to sample: every guard is an unsupported construct.')
        return 2

    log_dir = tempfile.mkdtemp(prefix='guard-deletion-')
    baseline_log = os.path.join(log_dir, 'baseline.log')
    code, seconds = run_tests(test_command, baseline_log)
    if code != 0:
        sys.stdout.flush()
        print('\nBaseline is red (exit %d), so nothing a mutant does can be told from it. Last lines:\n%s'
              % (code, tail(baseline_log)), file=sys.stderr)
        return 2
    print('\nBaseline green in %.0fs; %d mutants to run, about %.0f minutes.\n'
          % (seconds, len(sampled), seconds * len(sampled) / 60))

    for index, guard in enumerate(sampled, 1):
        absolute, original, text = originals[guard.path]
        mutated = guard.mutate(text).encode('utf-8')
        log_path = os.path.join(log_dir, 'mutant-%d.log' % index)
        try:
            with open(absolute, 'wb') as handle:
                handle.write(mutated)
            if not parses(absolute, mutated):
                guard.result = 'invalid'
            else:
                guard.exit_code, _ = run_tests(test_command, log_path)
                if guard.exit_code == 0:
                    guard.result = 'survived'
                elif log_reports_compile_failure(log_path, guard.path):
                    guard.result = 'invalid'
                else:
                    guard.result = 'killed'
        finally:
            restore(absolute, original)
        print('[%d/%d] %s  %s  %s' % (index, len(sampled), guard.location(), guard.label(), guard.verdict()))

    survivors = [guard for guard in guards if guard.result == 'survived']
    not_sampled = [guard for guard in guards if guard.unsupported or guard.result == 'invalid']
    print('\n| Guard | Location | Result |\n|---|---|---|')
    for guard in guards:
        print('| `%s` | `%s` | %s |' % (guard.label(), guard.location(), guard.verdict()))
    print('\nFiles restored byte for byte: %d. Logs: %s' % (len(originals), log_dir))
    if not_sampled:
        print('\nNot sampled: %d of %d guards; the sample is incomplete and the report must name them.'
              % (len(not_sampled), len(guards)))
        for guard in not_sampled:
            print('  %s  %s  %s' % (guard.location(), guard.label(), guard.verdict()))
    if survivors:
        print('\nSurvivors: %d of %d sampled. Each is a High: no test fails when the guard is removed. Name the test that should have caught it.'
              % (len(survivors), len(sampled) - sum(1 for guard in sampled if guard.result == 'invalid')))
        for guard in survivors:
            print('  %s  %s' % (guard.location(), guard.label()))
        return 1
    if not_sampled:
        return 2
    print('\nSurvivors: 0 of %d. Every new rejecting guard has a test behind it.' % len(guards))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
