"""Split a Bash tool call into the simple commands it would run, and say what it could not follow.

Shared by every guard that has to decide something about a command line. The
parser follows what an agent writes when it is doing ordinary work: commands
joined by `;`, `&&`, `||`, `|` or a newline, a quoted argument, a trailing
comment, a line continuation, a `cd` that moves the commands after it, a
`git -C`, and a bare wrapper such as `nohup`, `sudo`, `command`, `env`,
`time` or `timeout 30` in front of the program.

It does not follow a subshell, a brace group, a command substitution, a
variable, a backtick, a wrapper given options, or a nested shell such as
`bash -c`, `eval`, `exec`, `xargs` or `source`. Each of those is reported as
an unfollowed construct instead, and the dispatcher asks the owner about the
line when it also names a command a guard judges. Following them exactly
would mean reimplementing the shell, and every construct the parser does not
follow is one that cannot be used to slip a call past it.
"""

import os
import re
import shlex

SEPARATOR_CHARS = set("();<>|&\n")
GROUPING_CHARS = set("()")
REDIRECTIONS = {"<", ">", ">>", "<<", "<&", ">&", "&>", "<<<", ">|"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*=")
DURATION = re.compile(r"^[0-9]+(\.[0-9]+)?[smhd]?$")

# Wrappers that run the program after them unchanged. A wrapper given an
# option, such as `env -u X` or `timeout -s KILL 30`, is not followed: its
# option table would have to be known to tell an option's value from the
# program.
WRAPPERS = {"command", "env", "sudo", "nohup", "time", "timeout", "nice", "stdbuf", "ionice"}
# Programs that run a command line of their own, which the parser cannot see.
NESTED_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "eval", "exec", "xargs", "source", "."}

GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                          "--exec-path", "--config-env"}
GIT_CONFIG_OPTIONS = {"-c", "--config-env"}
GIT_LOCATION_OPTIONS = {"--git-dir", "--work-tree", "--namespace"}


class Parsed:
    """The simple commands of a line and the constructs the parser did not follow.

    `calls` holds (argv, directory) for each command it could read; `unfollowed`
    names each construct it could not, in the order found, so a line with any
    of them is judged on what was visible and asked about for the rest.
    """

    def __init__(self):
        self.calls = []
        self.unfollowed = []

    def skip(self, construct):
        if construct not in self.unfollowed:
            self.unfollowed.append(construct)


def strip_comments(line, parsed):
    """Drop unquoted `# ...` runs and line continuations, the way a shell does, and note expansions.

    A `$` or a backtick outside single quotes expands in the shell, inside
    double quotes too, so the text the parser sees is not the text that will
    run. Those are reported, not expanded.
    """
    kept = []
    quote = ""
    index = 0
    at_word_start = True
    while index < len(line):
        char = line[index]
        index += 1
        if quote:
            if quote == '"' and char == "\\" and index < len(line):
                # An escape inside double quotes; keep both characters.
                kept.append(char)
                kept.append(line[index])
                index += 1
                continue
            if quote == '"' and char in "$`":
                parsed.skip("a command substitution or variable" if char == "$" else "a backtick")
            kept.append(char)
            if char == quote:
                quote = ""
            continue
        if char == "\\":
            if index < len(line) and line[index] == "\n":
                # A line continuation. Drop it so the lexer sees one command.
                index += 1
                continue
            kept.append(char)
            if index < len(line):
                kept.append(line[index])
                index += 1
            at_word_start = False
            continue
        if char in "'\"":
            quote = char
            kept.append(char)
            at_word_start = False
            continue
        if char == "#" and at_word_start:
            while index < len(line) and line[index] != "\n":
                index += 1
            continue
        if char in "$`":
            parsed.skip("a command substitution or variable" if char == "$" else "a backtick")
        kept.append(char)
        at_word_start = char in " \t\n;|&()"
    return "".join(kept)


def lex(line, parsed):
    """Tokenise a command line, keeping newlines as command separators.

    Raises ValueError on unbalanced quotes, as shlex does.
    """
    lexer = shlex.shlex(strip_comments(line, parsed), posix=True,
                        punctuation_chars="();<>|&\n")
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    lexer.commenters = ""
    return list(lexer)


def command_segments(tokens, parsed):
    """Yield each simple command as a list and each separator run as a string.

    `;`, `&&`, `||`, `|`, `&` and a newline all end a command. Parentheses and
    braces group commands in a subshell or in the current shell, with their
    own working directory in the subshell case; the parser does not model
    that and reports them.
    """
    current = []
    drop_next = False
    for token in tokens:
        if drop_next:
            drop_next = False
            continue
        if token in REDIRECTIONS:
            drop_next = True
            continue
        if token and set(token) <= SEPARATOR_CHARS:
            if set(token) & GROUPING_CHARS:
                parsed.skip("a subshell")
            if current:
                yield current
            current = []
            yield token
            continue
        if token in {"{", "}"}:
            parsed.skip("a brace group")
            continue
        current.append(token)
    if current:
        yield current


def runs_apart(separator):
    """Whether a command beside this separator runs in a process of its own: a pipeline element or a background job."""
    return ("|" in separator and separator != "||") or separator == "&"


def peel_wrappers(argv, parsed):
    """Drop leading assignments and bare wrapper programs. Returns the program's argv, or None when the wrapper has options."""
    rest = list(argv)
    while rest:
        name = os.path.basename(rest[0])
        if ASSIGNMENT.match(rest[0]):
            rest.pop(0)
            continue
        if name not in WRAPPERS:
            break
        rest.pop(0)
        if name == "timeout" and rest and DURATION.match(rest[0]):
            rest.pop(0)
        if rest and rest[0].startswith("-"):
            parsed.skip("a %s option" % name)
            return None
    return rest


def git_global_options(argv):
    """Split a git invocation into (options, rest), or None for another program.

    Options are (name, value) pairs, value None for a flag; rest starts at the
    subcommand. An `--option=value` token is split into its two parts.
    """
    if os.path.basename(argv[0]) != "git":
        return None
    options = []
    index = 1
    while index < len(argv) and argv[index].startswith("-"):
        token = argv[index]
        index += 1
        if token in GIT_OPTIONS_WITH_VALUE:
            options.append((token, argv[index] if index < len(argv) else ""))
            index += 1
        elif token.startswith("--") and "=" in token:
            options.append(tuple(token.split("=", 1)))
        else:
            options.append((token, None))
    return options, argv[index:]


def git_call(argv, directory):
    """Return (subcommand, args, directory) for a git invocation, else None."""
    split = git_global_options(argv)
    if split is None or not split[1]:
        return None
    options, rest = split
    for name, value in options:
        if name == "-C":
            directory = os.path.join(directory, value)
    return rest[0], rest[1:], os.path.normpath(directory)


def git_options_named(argv, names):
    """The global options of a git call whose names are in `names`, as tokens for another git call."""
    split = git_global_options(argv)
    if split is None:
        return []
    passed = []
    for name, value in split[0]:
        if name in names and value is not None:
            passed.extend([name, value])
    return passed


def git_config_overrides(argv):
    """The `-c` and `--config-env` options of a git call, as a flat token list.

    A guard that queries a plain value, such as pull.rebase, may pass them to
    `git config` so git resolves the one-off override the way the inspected
    command will. A guard that runs anything heavier never passes them: a -c
    can name a command for git to run, such as core.sshCommand.
    """
    return git_options_named(argv, GIT_CONFIG_OPTIONS)


def git_location_options(argv):
    """The options that pick the repository: `--git-dir`, `--work-tree`, `--namespace`."""
    return git_options_named(argv, GIT_LOCATION_OPTIONS)


def start_directory(cwd):
    """The directory a guard judges a command line from.

    The event's cwd when it exists. A session whose own worktree was removed
    keeps sending that path, so a missing cwd falls back to its nearest
    existing ancestor: a command that names its repository with `git -C` or
    an absolute path is judged where it points, and one that relies on the
    cwd is still judged somewhere real rather than nowhere. Without a cwd,
    the process's own directory, or the root when even that was removed.
    """
    if isinstance(cwd, str) and cwd:
        try:
            here = os.path.abspath(cwd)
        except OSError:
            here = cwd
        while not os.path.isdir(here):
            parent = os.path.dirname(here)
            if parent == here:
                break
            here = parent
        return here
    try:
        return os.getcwd()
    except OSError:
        return os.sep


def parse(command_line, directory):
    """Read a command line into a Parsed: its simple commands with their directories, and what was not followed.

    A `cd` moves the directory of every command after it on the line, unless
    it is a pipeline element or a background job, which runs in a process of
    its own and moves nothing; that is reported. A `git -C` is resolved per
    call by git_call. Unbalanced quotes leave no commands and are reported.
    """
    parsed = Parsed()
    try:
        tokens = lex(command_line, parsed)
    except ValueError:
        parsed.skip("unbalanced quotes")
        return parsed
    segments = list(command_segments(tokens, parsed))
    for index, segment in enumerate(segments):
        if isinstance(segment, str):
            continue
        argv = peel_wrappers(segment, parsed)
        if not argv:
            continue
        name = os.path.basename(argv[0])
        if name in NESTED_SHELLS:
            parsed.skip("a nested shell (%s)" % argv[0])
            continue
        if argv[0] == "cd":
            before = segments[index - 1] if index > 0 and isinstance(segments[index - 1], str) else ""
            after = segments[index + 1] if index + 1 < len(segments) and isinstance(segments[index + 1], str) else ""
            if runs_apart(before) or runs_apart(after):
                parsed.skip("a cd in a pipeline or background job")
            elif len(argv) > 1:
                directory = os.path.normpath(os.path.join(directory, argv[1]))
            continue
        parsed.calls.append((argv, directory))
    return parsed
