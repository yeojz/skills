"""Split a Bash tool call into the simple commands it would run, and say what it could not follow.

Shared by every guard that has to decide something about a command line. The
parser follows what an agent writes when it is doing ordinary work: commands
joined by `;`, `&&`, `||`, `|` or a newline, a quoted argument, a trailing
comment, a line continuation, a `cd` that moves the commands after it, a
`git -C`, and a bare wrapper such as `nohup`, `sudo`, `command`, `env`,
`time` or `timeout 30` in front of the program.

It does not follow a subshell, a brace group, a command substitution, a
variable, a backtick, a here-document, a wrapper given options, a GIT_*
environment variable, a git option it does not know, or a nested shell such
as `bash -c`, `eval`, `exec`, `xargs` or `source`. Each of those is reported
as an unfollowed construct instead, and the dispatcher asks the owner about
the line when it also names a command a guard judges, or when the construct
itself mentions git or gh. Following them exactly would mean reimplementing
the shell; reporting them means the owner sees the line instead.
"""

import os
import re
import shlex

SEPARATOR_CHARS = set("();<>|&\n")
GROUPING_CHARS = set("()")
REDIRECTIONS = {"<", ">", ">>", "<&", ">&", "&>", "<<", "<<<", ">|", "&>>", ">>&"}
HERE_DOCUMENTS = {"<<", "<<<"}
# Environment variables that change what git reads: its own GIT_* family, and
# the two that move the global configuration file.
ENVIRONMENT_GIT_READS = re.compile(r"^(GIT_[A-Za-z_0-9]*|HOME|XDG_CONFIG_HOME)=")
EXPORTERS = {"export", "declare", "typeset"}
JUDGED_PROGRAMS = {"git", "gh"}
MENTIONS_GIT = re.compile(r"\b(git|gh)\b")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*=")
DURATION = re.compile(r"^[0-9]+(\.[0-9]+)?[smhd]?$")
SHORT_CLUSTER = re.compile(r"^-[A-Za-z]+$")

# Wrappers that run the program after them unchanged. A wrapper given an
# option, such as `env -u X` or `timeout -s KILL 30`, is not followed: its
# option table would have to be known to tell an option's value from the
# program.
WRAPPERS = {"command", "env", "sudo", "nohup", "time", "timeout", "nice", "stdbuf", "ionice"}
# Programs that run a command line of their own, which the parser cannot see.
NESTED_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "eval", "exec", "xargs", "source", "."}

GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                          "--exec-path", "--config-env", "--attr-source", "--super-prefix"}
# The global flags of git that take no value. Any other option before the
# subcommand is one the parser does not know, so the call is not followed.
GIT_GLOBAL_FLAGS = {"--no-pager", "--paginate", "-p", "-P", "--bare", "--no-replace-objects",
                    "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs",
                    "--icase-pathspecs", "--no-optional-locks", "--no-lazy-fetch",
                    "--no-advice", "--version", "--help", "-h"}
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
        # True when an unfollowed construct itself mentions git or gh, such as
        # a `bash -c "git ..."` or a shell alias, so the dispatcher asks even
        # when the visible text names no judged command.
        self.hidden = False

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


def heredoc_delimiter(rest):
    """(delimiter, characters consumed) for the word after a `<<`, read with shell quoting, or None when the word cannot be read.

    bash removes the quoting from the word: `"E O F"` names `E O F`, `E"O"F`
    and `\\EOF` name `EOF`, and a backslash inside single quotes stays. The
    word ends at unquoted whitespace or a metacharacter, so `<<EOF;` and
    `<<EOF>out` name `EOF`.
    """
    quote = ""
    consumed = 0
    while consumed < len(rest):
        char = rest[consumed]
        if quote:
            if char == quote:
                quote = ""
            elif char == "\\" and quote == '"':
                consumed += 1
        elif char == "\\":
            consumed += 1
        elif char in "'\"":
            quote = char
        elif char in " \t;&|<>()":
            break
        consumed += 1
    if quote:
        return None
    try:
        words = shlex.split(rest[:consumed], posix=True)
    except ValueError:
        return None
    if len(words) != 1:
        return None
    return words[0], consumed


def strip_heredocs(line, parsed):
    """Remove the bodies of here-documents, so their lines are not read as commands.

    An unquoted `<<` or `<<-` outside a comment names a delimiter; the lines
    after the current one up to the line that equals it are the body and are
    dropped. The operator and the delimiter word stay, so the lexer sees
    `cmd <<EOF` and the segment reader can tell which command the body feeds.
    Quote state carries across lines, so a `<<` inside a multi-line string is
    text. A body whose delimiter never comes is left in place and reported,
    since bash would read the rest of the line as the body and nothing after
    it would run; judging those lines as commands errs towards asking.
    """
    lines = line.split("\n")
    kept = []
    index = 0
    quote = ""
    substitution = 0
    while index < len(lines):
        text = lines[index]
        index += 1
        kept.append(text)
        position = 0
        at_word_start = True
        delimiters = []
        unreadable = False
        while position < len(text):
            char = text[position]
            if quote:
                if char == quote:
                    quote = ""
                elif char == "\\" and quote == '"':
                    position += 1
            elif char == "\\":
                position += 1
                at_word_start = False
            elif char in "'\"":
                quote = char
                at_word_start = False
            elif char == "#" and at_word_start:
                break
            elif char == "$" and text.startswith("$(", position):
                # Inside $(...) or $((...)) a << is a shift, not a here-document.
                substitution += 1
                position += 1
                at_word_start = False
            elif text.startswith("((", position):
                # A (( ... )) arithmetic command, likewise, wherever it starts:
                # bash accepts it glued to a keyword, as in `if((1<<2))`.
                substitution += 1
                at_word_start = False
            elif substitution and char == "(":
                substitution += 1
            elif substitution and char == ")":
                substitution -= 1
            elif not substitution and text.startswith("<<", position) and not text.startswith("<<<", position) and not (position and text[position - 1] == "<"):
                match = re.match(r"<<(-?)\s*", text[position:])
                read = heredoc_delimiter(text[position + len(match.group(0)):])
                if read is None:
                    unreadable = True
                    break
                delimiters.append((match.group(1) == "-", read[0]))
                position += len(match.group(0)) + read[1] - 1
                at_word_start = False
            else:
                at_word_start = char in " \t;|&()"
            position += 1
        if unreadable:
            parsed.skip("a here-document whose delimiter cannot be read")
            parsed.hidden = True
            break
        for strip_tabs, delimiter in delimiters:
            closing = None
            for later in range(index, len(lines)):
                if (lines[later].lstrip("\t") if strip_tabs else lines[later]) == delimiter:
                    closing = later
                    break
            if closing is None:
                parsed.skip("a here-document whose delimiter never comes")
                parsed.hidden = True
                break
            index = closing + 1
    return "\n".join(kept)


def lex(line, parsed):
    """Tokenise a command line, keeping newlines as command separators.

    Raises ValueError on unbalanced quotes, as shlex does.
    """
    lexer = shlex.shlex(strip_comments(strip_heredocs(line, parsed), parsed), posix=True,
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
        if token in HERE_DOCUMENTS and current and os.path.basename(current[0]) in JUDGED_PROGRAMS:
            # A body fed to git or gh is text the guards never see.
            parsed.skip("a here-document fed to %s" % os.path.basename(current[0]))
        if token in REDIRECTIONS:
            # `2>&1`: the descriptor number in front of a redirection is not an operand.
            if current and current[-1].isdigit():
                current.pop()
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
            if current:
                yield current
            current = []
            yield token
            continue
        current.append(token)
    if current:
        yield current


def runs_apart(separator):
    """Whether a command beside this separator runs in a process of its own: a pipeline element or a background job."""
    separator = separator.strip("\n")
    return ("|" in separator and separator != "||") or separator == "&"


def group_depth_change(separator):
    """How many groups a separator run opens or closes."""
    return separator.count("(") + separator.count("{") - separator.count(")") - separator.count("}")


def peel_wrappers(argv, parsed):
    """Drop leading assignments and wrapper programs, reporting what the guards cannot account for.

    A GIT_*, HOME or XDG_CONFIG_HOME assignment changes what git reads as
    much as -c does, and a wrapper given options hides where the program
    starts. Both are reported; the program is still returned, best effort
    from the first git or gh token, so the denying guards see the call.
    """
    rest = list(argv)
    while rest:
        name = os.path.basename(rest[0])
        if ASSIGNMENT.match(rest[0]):
            if ENVIRONMENT_GIT_READS.match(rest[0]):
                parsed.skip("a %s environment variable" % ("GIT_*" if rest[0].startswith("GIT_") else rest[0].partition("=")[0]))
            rest.pop(0)
            continue
        if name not in WRAPPERS:
            break
        rest.pop(0)
        if name == "timeout" and rest and DURATION.match(rest[0]):
            rest.pop(0)
        if rest and rest[0].startswith("-"):
            parsed.skip("a %s option" % name)
            if name == "env" and (rest[0] in {"-C", "--chdir"} or rest[0].startswith("--chdir=")):
                # env -C runs the program elsewhere; the recorded call would be judged in the wrong directory.
                parsed.hidden = True
                return None
            # Without the wrapper's option table, a token may be a flag or a
            # value, so the program is the last of the first run of git or gh
            # tokens: `sudo -u gh git push` is git, `sudo -E git push` is git.
            start = None
            for index, token in enumerate(rest):
                if os.path.basename(token) in JUDGED_PROGRAMS:
                    start = index
                elif start is not None:
                    return rest[start:]
            return rest[start:] if start is not None else None
    return rest


def exports_git_reads(argv):
    """Whether an `export`, `declare` or `typeset` sets a variable git reads."""
    return os.path.basename(argv[0]) in EXPORTERS and any(ENVIRONMENT_GIT_READS.match(word) for word in argv[1:])


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
            directory = os.path.join(directory, os.path.expanduser(value))
    return rest[0], rest[1:], os.path.normpath(directory)


def unknown_git_option(argv):
    """The first global option of a git call the parser does not know, or None."""
    index = 1
    while index < len(argv) and argv[index].startswith("-"):
        token = argv[index]
        index += 1
        if token in GIT_OPTIONS_WITH_VALUE:
            index += 1
        elif token.partition("=")[0] in GIT_OPTIONS_WITH_VALUE and "=" in token:
            continue
        elif token not in GIT_GLOBAL_FLAGS:
            return token
    return None


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

    A plain `cd <dir>` moves the directory of every command after it on the
    line. One that is a pipeline element or a background job runs in a
    process of its own and moves nothing; one inside a subshell or brace
    group, one with options, and a bare `cd` or `cd -` are not followed and
    move nothing either. Each is reported. A `git -C` is resolved per call by
    git_call. Unbalanced quotes leave no commands and are reported.
    """
    parsed = Parsed()
    try:
        tokens = lex(command_line, parsed)
    except ValueError:
        parsed.skip("unbalanced quotes")
        return parsed
    segments = list(command_segments(tokens, parsed))
    depth = 0
    for index, segment in enumerate(segments):
        if isinstance(segment, str):
            depth = max(0, depth + group_depth_change(segment))
            continue
        argv = peel_wrappers(segment, parsed)
        if not argv:
            continue
        name = os.path.basename(argv[0])
        if name in NESTED_SHELLS:
            parsed.skip("a nested shell (%s)" % argv[0])
            if any(MENTIONS_GIT.search(token) for token in argv[1:]):
                parsed.hidden = True
            continue
        if exports_git_reads(argv):
            parsed.skip("an exported variable git reads")
            parsed.hidden = True
            continue
        if argv[0] == "cd":
            before = segments[index - 1] if index > 0 and isinstance(segments[index - 1], str) else ""
            after = segments[index + 1] if index + 1 < len(segments) and isinstance(segments[index + 1], str) else ""
            if runs_apart(before) or runs_apart(after):
                parsed.skip("a cd in a pipeline or background job")
            elif depth > 0:
                parsed.skip("a cd inside a subshell or brace group")
            elif len(argv) != 2 or argv[1].startswith("-") or argv[1] == "-":
                parsed.skip("a cd the parser does not follow")
            else:
                directory = os.path.normpath(os.path.join(directory, os.path.expanduser(argv[1])))
            continue
        if name == "git":
            unknown = unknown_git_option(argv)
            if unknown is not None:
                # Reported, and still judged: git_global_options reads an
                # unknown option as a flag, which is right for most of them.
                parsed.skip("a git option (%s)" % unknown)
                parsed.hidden = True
        parsed.calls.append((argv, directory))
    return parsed
