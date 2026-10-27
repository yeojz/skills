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
# Wrapper options whose value is always the next token. An `--option=value`
# form is a single token and needs no entry. An option whose argument is
# optional, such as env's --default-signal[=SIG] or xargs' -i[R], must stay out:
# its bare form is followed by the executable, which must not be consumed.
WRAPPER_OPTIONS_WITH_VALUE = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "sudo": {"-u", "--user", "-g", "--group", "-C", "--close-from", "-D", "--chdir",
             "-h", "--host", "-p", "--prompt", "-r", "--role", "-t", "--type",
             "-U", "--other-user", "-T", "--command-timeout"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "--class", "-n", "--classdata", "-p", "--pid", "-P", "--pgid",
               "-u", "--uid"},
    "stdbuf": {"-i", "--input", "-o", "--output", "-e", "--error"},
    "time": {"-f", "--format", "-o", "--output"},
    "xargs": {"-I", "-n", "--max-args", "-L", "--max-lines", "-P", "--max-procs",
              "-s", "--max-chars", "-d", "--delimiter", "-E", "--eof", "-a",
              "--arg-file", "--process-slot-var"},
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


def simple_commands(tokens):
    """Split a token stream on separators, newlines and subshell parentheses."""
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
            continue
        current.append(token)
    if current:
        yield current


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
            if option in takes_value and rest:
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


def git_call(argv, directory):
    """Return (subcommand, args, directory) for a git invocation, else None."""
    if os.path.basename(argv[0]) != "git":
        return None
    index = 1
    while index < len(argv) and argv[index].startswith("-"):
        option = argv[index]
        index += 1
        if option == "-C" and index < len(argv):
            directory = os.path.join(directory, argv[index])
            index += 1
        elif option.startswith("-C") and len(option) > 2:
            directory = os.path.join(directory, option[2:])
        elif option in GIT_OPTIONS_WITH_VALUE:
            index += 1
    if index >= len(argv):
        return None
    return argv[index], argv[index + 1:], os.path.normpath(directory)


def commands_in(command_line, depth=0):
    """Yield (argv, via_xargs) for every simple command, wrappers peeled.

    A `bash -c "..."` script is expanded in place, up to MAX_SHELL_DEPTH.
    Raises ValueError on unbalanced quotes.
    """
    for words in simple_commands(lex(command_line)):
        argv, via_xargs = peel_wrappers(words)
        if not argv:
            continue
        script = shell_script_argument(argv)
        if script is not None:
            if depth < MAX_SHELL_DEPTH:
                for inner in commands_in(script, depth + 1):
                    yield inner
            continue
        yield argv, via_xargs
