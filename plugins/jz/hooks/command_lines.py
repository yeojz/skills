"""Split a Bash tool call into the simple commands it would run.

Shared by every PreToolUse hook that has to decide something about a command
line. One parser, so a line continuation, a quoted separator, a trailing
comment or a wrapper such as `timeout 30` is handled the same way everywhere.
"""

import os
import re
import shlex

MAX_SHELL_DEPTH = 3

SEPARATOR_CHARS = set("();<>|&\n")
REDIRECTIONS = {"<", ">", ">>", "<<", "<&", ">&", "&>", "<<<", ">|"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*=")
DURATION = re.compile(r"^[0-9]+(\.[0-9]+)?[smhd]?$")

WRAPPERS = {"command", "env", "sudo", "nohup", "time", "timeout", "stdbuf",
            "nice", "ionice", "xargs"}
# Wrapper options whose value is always the next token, checked against each
# program's option table (GNU coreutils env, timeout, nice and stdbuf, GNU
# findutils xargs, GNU time, util-linux ionice, sudo 1.9). An `--option=value`
# form is a single token and needs no entry. An option whose argument is
# optional, such as env's --default-signal[=SIG] or xargs' --eof[=EOF], stays
# out: its bare form is followed by the executable, which must not be consumed.
# getopt_long also accepts any unambiguous abbreviation of a long option, so a
# token is matched as a prefix of these names, never only as an exact name.
WRAPPER_OPTIONS_WITH_VALUE = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string", "--quoting-style"},
    "sudo": {"-u", "--user", "-g", "--group", "-C", "--close-from", "-D", "--chdir",
             "-h", "--host", "-p", "--prompt", "-r", "--role", "-t", "--type",
             "-U", "--other-user", "-T", "--command-timeout", "-R", "--chroot"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "--class", "-n", "--classdata", "-p", "--pid", "-P", "--pgid",
               "-u", "--uid"},
    "stdbuf": {"-i", "--input", "-o", "--output", "-e", "--error"},
    "time": {"-f", "--format", "-o", "--output-file"},
    "xargs": {"-I", "-n", "--max-args", "-L", "-P", "--max-procs", "-s", "--max-chars",
              "-d", "--delimiter", "-E", "-a", "--arg-file", "--process-slot-var"},
}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}

GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                          "--exec-path", "--config-env"}


def strip_comments(line):
    """Drop unquoted `# ...` runs and line continuations, the way a shell does.

    The lexer cannot do this itself: its commenter would swallow the newline and
    with it every command on the following lines.
    """
    kept = []
    quote = ""
    index = 0
    at_word_start = True
    while index < len(line):
        char = line[index]
        index += 1
        if quote:
            if quote == '"' and char == "\\" and index < len(line) and line[index] == "\n":
                # A backslash-newline inside double quotes joins the lines.
                index += 1
                continue
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
        kept.append(char)
        at_word_start = char in " \t\n;|&()"
    return "".join(kept)


def lex(line):
    """Tokenise a command line, keeping newlines as command separators.

    Raises ValueError on unbalanced quotes, as shlex does.
    """
    lexer = shlex.shlex(strip_comments(line), posix=True,
                        punctuation_chars="();<>|&\n")
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    lexer.commenters = ""
    return list(lexer)


def command_segments(tokens):
    """Yield each simple command as a list and each separator run as a string.

    A separator run is a token made only of `;`, `|`, `&`, newlines and
    parentheses, such as `&&`, `|` or `);`. The braces of a `{ ...; }` group
    are dropped: they group commands without changing where they run.
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
            if current:
                yield current
            current = []
            yield token
            continue
        if token in {"{", "}"} and not current:
            continue
        current.append(token)
    if current:
        yield current


def simple_commands(tokens):
    """Split a token stream on separators, newlines and subshell parentheses."""
    for segment in command_segments(tokens):
        if isinstance(segment, list):
            yield segment


def is_pipe(separator):
    return "|" in separator and separator != "||"


def is_background(separator):
    return separator == "&"


def takes_separate_value(option, takes_value):
    """Whether a wrapper option consumes the next token as its value.

    A short option matches exactly. A long option matches as getopt_long does,
    as an unambiguous prefix of one known name; an ambiguous prefix makes the
    program itself refuse to run, so nothing is consumed for it.
    """
    if not option.startswith("--"):
        return option in takes_value
    if "=" in option:
        return False
    matches = [name for name in takes_value
               if name.startswith("--") and name.startswith(option)]
    return len(matches) == 1 or option in matches


def peel_wrappers(argv):
    """Drop leading assignments and wrapper programs such as env, sudo or nohup.

    Also reports whether the command was reached through xargs, whose arguments
    arrive on a pipe a hook cannot see.
    """
    rest = list(argv)
    via_xargs = False
    while rest:
        name = os.path.basename(rest[0])
        if ASSIGNMENT.match(rest[0]):
            rest.pop(0)
            continue
        if name not in WRAPPERS:
            break
        via_xargs = via_xargs or name == "xargs"
        rest.pop(0)
        takes_value = WRAPPER_OPTIONS_WITH_VALUE.get(name, set())
        while rest and (rest[0].startswith("-") or DURATION.match(rest[0])
                        or ASSIGNMENT.match(rest[0])):
            option = rest.pop(0)
            if option == "--":
                break
            if rest and takes_separate_value(option, takes_value):
                rest.pop(0)
    return rest, via_xargs


def shell_script_argument(argv):
    """Return the script string of an `sh -c` or `bash -c` call, else None."""
    if not argv or os.path.basename(argv[0]) not in SHELLS:
        return None
    for index, token in enumerate(argv[1:], start=1):
        if not token.startswith("-") or token.startswith("--"):
            continue
        if "c" in token[1:] and index + 1 < len(argv):
            return argv[index + 1]
    return None


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


GIT_CONFIG_OPTIONS = {"-c", "--config-env"}
GIT_REPOSITORY_OPTIONS = GIT_CONFIG_OPTIONS | {"--git-dir", "--work-tree", "--namespace"}


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
    """The `-c` and `--config-env` options of a git call.

    Passing them to a `git config` query makes git itself resolve the one-off
    override over the stored value, the way the inspected command will.
    """
    return git_options_named(argv, GIT_CONFIG_OPTIONS)


def git_repository_options(argv):
    """The options that pick the repository and its configuration: `-c`, `--config-env`, `--git-dir`, `--work-tree`, `--namespace`.

    A hook that runs git on the caller's behalf passes them through, so its
    queries see the repository and the settings the inspected command will.
    """
    return git_options_named(argv, GIT_REPOSITORY_OPTIONS)


def commands_with_directory(command_line, directory, depth=0):
    """Yield (argv, via_xargs, directory) for every simple command.

    Wrappers are peeled, a `bash -c "..."` script is expanded in place up to
    MAX_SHELL_DEPTH, and a `cd` moves the directory the commands after it run
    in, within its own shell scope: a `( ... )` subshell restores the outer
    directory at `)`, and a `cd` that is a pipeline element or a background job
    runs in a subshell of its own and moves nothing. `git -C` is not applied
    here; git_call resolves it per call. Raises ValueError on unbalanced quotes.
    """
    scopes = [directory]
    moved_to = None
    previous_separator = ""
    for segment in command_segments(lex(command_line)):
        if isinstance(segment, str):
            if moved_to is not None and not is_pipe(segment) and not is_background(segment):
                scopes[-1] = moved_to
            moved_to = None
            for char in segment:
                if char == "(":
                    scopes.append(scopes[-1])
                elif char == ")" and len(scopes) > 1:
                    scopes.pop()
            previous_separator = segment
            continue
        argv, via_xargs = peel_wrappers(segment)
        if not argv:
            continue
        script = shell_script_argument(argv)
        if script is not None:
            if depth < MAX_SHELL_DEPTH:
                for inner in commands_with_directory(script, scopes[-1], depth + 1):
                    yield inner
            continue
        if argv[0] == "cd" and len(argv) > 1:
            if not is_pipe(previous_separator):
                moved_to = os.path.normpath(os.path.join(scopes[-1], argv[1]))
            continue
        yield argv, via_xargs, scopes[-1]


def commands_in(command_line, depth=0):
    """Yield (argv, via_xargs) for every simple command, directory ignored."""
    for argv, via_xargs, _ in commands_with_directory(command_line, ".", depth):
        yield argv, via_xargs
