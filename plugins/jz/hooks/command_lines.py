"""Read a Bash tool call as the plain commands the guards judge, and report anything outside that grammar.

Shared by every guard that decides something about a command line. The
grammar is small on purpose: every construct it follows is one the guards
have to get right, and a hook is a guardrail against an honest mistake,
not a shell.

A line is followed when it is plain commands joined by `;`, `&&`, `||`,
`|` or a newline, each a program with word arguments and at most the
output redirections `2>&1`, `>/dev/null`, `2>/dev/null` and `&>/dev/null`.
Quoted arguments, a trailing comment and a line continuation are read the
way bash reads them. A `cd <dir>` between separators moves the commands
after it, and a `git -C <dir>` moves one call. A git call may carry the
global options the guards know and a subcommand git ships.

Everything else is reported, not followed: a variable or command
substitution, a backtick, a here-document (nothing after it on the line is
read), any other redirection, a subshell, a brace group, an environment
assignment in front of a program, a wrapper such as `env`, `sudo`, `nohup`,
`time` or `timeout`, a nested shell such as `bash -c`, `eval` or `xargs`, a
git option or subcommand outside the known sets, an alias among them, and
unbalanced quotes. The dispatcher asks the owner about such a line when it
also names a command a guard judges, or when a nested shell's own text
mentions git or gh; the owner rewrites the line in the plain form or
confirms it as written.
"""

import os
import re
import shlex

SEPARATOR_CHARS = set("();<>|&\n")
REDIRECTIONS = {"<", ">", ">>", "<&", ">&", "&>", ">|", "<>", "&>>", ">>&"}
HERE_DOCUMENTS = {"<<", "<<<"}
# The redirections an accepted command may carry: output discarded or
# merged, nothing read in and no file written.
QUIET_REDIRECTIONS = {(">", "/dev/null"), ("&>", "/dev/null"), (">&", "1"), (">&", "2")}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*=")
MENTIONS_GIT = re.compile(r"\b(git|gh)\b")
SHORT_CLUSTER = re.compile(r"^-[A-Za-z]+$")
# A cd is followed when it stands between these separators, or at the start
# or end of the line. One in a pipeline, a background job, a subshell or a
# brace group runs where the next command does not.
CD_BEFORE = {"", ";", "&&", "\n"}
CD_AFTER = {"", ";", "&&", "||", "\n"}

# Programs that run the command after them changed: as another user, in
# another environment, under a timer, or in the shell's own state. Which
# token is the program depends on option tables the parser does not carry.
WRAPPERS = {"command", "env", "sudo", "doas", "nohup", "time", "timeout", "nice", "ionice", "stdbuf",
            "export", "declare", "typeset", "unset", "alias"}
# Programs that run a command line of their own, which the parser cannot see.
NESTED_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "eval", "exec", "xargs", "source", "."}

GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                          "--exec-path", "--config-env", "--attr-source"}
GIT_GLOBAL_FLAGS = {"--no-pager", "--paginate", "-p", "-P", "--bare", "--no-replace-objects",
                    "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs",
                    "--icase-pathspecs", "--no-optional-locks", "--no-lazy-fetch",
                    "--no-advice", "--version", "--help", "-h"}
GIT_CONFIG_OPTIONS = {"-c", "--config-env"}
GIT_LOCATION_OPTIONS = {"--git-dir", "--work-tree", "--namespace"}
# The subcommands git ships (`git --list-cmds=main`, git 2.54) and the
# common add-ons. Any other word is an alias, whose expansion the guards do
# not read, or a typo git will reject.
GIT_COMMANDS = set("""
add am annotate apply archive backfill bisect blame branch bugreport bundle cat-file check-attr
check-ignore check-mailmap check-ref-format checkout checkout-index cherry cherry-pick clean clone
column commit commit-graph commit-tree config count-objects credential describe diagnose diff
diff-files diff-index diff-tree difftool fast-export fast-import fetch fetch-pack filter-branch
fmt-merge-msg for-each-ref for-each-repo format-patch fsck gc get-tar-commit-id grep hash-object
help hook index-pack init interpret-trailers log ls-files ls-remote ls-tree mailinfo mailsplit
maintenance merge merge-base merge-file merge-index merge-tree mergetool mktag mktree
multi-pack-index mv name-rev notes pack-objects pack-refs patch-id prune prune-packed pull push
range-diff read-tree rebase receive-pack reflog refs remote repack replace replay request-pull
rerere reset restore rev-list rev-parse revert rm send-email send-pack shortlog show show-branch
show-index show-ref sparse-checkout stage stash status stripspace submodule subtree switch
symbolic-ref tag unpack-file unpack-objects update-index update-ref update-server-info upload-pack
var verify-commit verify-pack verify-tag version whatchanged worktree write-tree
absorb filter-repo flow lfs
""".split())


class Parsed:
    """The plain commands of a line and the constructs outside the grammar.

    `calls` holds (argv, directory) for each command that was followed;
    `unfollowed` names each construct that was not, in the order found, so a
    line with any of them is judged on what was followed and asked about for
    the rest. `hidden` is set when a construct's own text mentions git or
    gh, as `bash -c "git ..."` does, so the dispatcher asks even when the
    rest of the line names no judged command.
    """

    def __init__(self):
        self.calls = []
        self.unfollowed = []
        self.hidden = False

    def skip(self, construct):
        if construct not in self.unfollowed:
            self.unfollowed.append(construct)


def strip_comments(line, parsed):
    """Drop unquoted `# ...` runs and line continuations, the way a shell does, and report expansions.

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
    """Tokenise a command line, keeping newlines as command separators. Raises ValueError on unbalanced quotes."""
    lexer = shlex.shlex(strip_comments(line, parsed), posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    lexer.commenters = ""
    return list(lexer)


def segments(tokens):
    """Yield each command's tokens as a list and each separator as a string, braces included."""
    current = []
    for token in tokens:
        if token in {"{", "}"} or (token and set(token) <= SEPARATOR_CHARS and token not in REDIRECTIONS
                                    and token not in HERE_DOCUMENTS):
            if current:
                yield current
            current = []
            yield token
        else:
            current.append(token)
    if current:
        yield current


def plain_command(tokens, parsed):
    """The argv of a segment inside the grammar, or None after reporting what put it outside."""
    argv = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token in REDIRECTIONS:
            target = tokens[index] if index < len(tokens) else ""
            index += 1
            if argv and argv[-1] in {"1", "2"}:
                argv.pop()
            if (token, target) not in QUIET_REDIRECTIONS:
                parsed.skip("a redirection (%s%s)" % (token, target))
                return None
            continue
        argv.append(token)
    if not argv:
        return None
    if ASSIGNMENT.match(argv[0]):
        parsed.skip("an environment assignment (%s)" % argv[0].partition("=")[0])
        return None
    return argv


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


def git_problem(argv):
    """What puts a git call outside the grammar: an option or a subcommand the guards do not know. None when it is plain."""
    options, rest = git_global_options(argv)
    for name, _ in options:
        if name not in GIT_OPTIONS_WITH_VALUE and name not in GIT_GLOBAL_FLAGS:
            return "a git option (%s)" % name
    if rest and rest[0] not in GIT_COMMANDS:
        return "a git subcommand the guards do not know (%s)" % rest[0]
    return None


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
    """Read a command line into a Parsed: the plain commands with their directories, and what was not followed.

    A here-document ends the read: bash feeds the lines after it to the
    command, and the parser would otherwise read that text as commands. A
    `cd` moves the directory only when it stands between separators and
    names one plain directory; any other cd is reported and moves nothing.
    """
    parsed = Parsed()
    try:
        tokens = lex(command_line, parsed)
    except ValueError:
        parsed.skip("unbalanced quotes")
        return parsed
    pieces = list(segments(tokens))
    for index, piece in enumerate(pieces):
        if isinstance(piece, str):
            if "(" in piece or ")" in piece:
                parsed.skip("a subshell")
            elif piece in {"{", "}"}:
                parsed.skip("a brace group")
            continue
        if any(token in HERE_DOCUMENTS for token in piece):
            parsed.skip("a here-document (the lines after it were not read)")
            break
        argv = plain_command(piece, parsed)
        if argv is None:
            continue
        name = os.path.basename(argv[0])
        if argv[0] == "cd":
            before = pieces[index - 1] if index and isinstance(pieces[index - 1], str) else ""
            after = pieces[index + 1] if index + 1 < len(pieces) and isinstance(pieces[index + 1], str) else ""
            if before in CD_BEFORE and after in CD_AFTER and len(argv) == 2 and not argv[1].startswith("-"):
                directory = os.path.normpath(os.path.join(directory, os.path.expanduser(argv[1])))
            else:
                parsed.skip("a cd the parser does not follow")
            continue
        if name in WRAPPERS:
            parsed.skip("a wrapper (%s)" % name)
            continue
        if name in NESTED_SHELLS:
            parsed.skip("a nested shell (%s)" % argv[0])
            if any(MENTIONS_GIT.search(token) for token in argv[1:]):
                parsed.hidden = True
            continue
        if name == "git":
            problem = git_problem(argv)
            if problem is not None:
                parsed.skip(problem)
                parsed.hidden = True
                continue
        parsed.calls.append((argv, directory))
    return parsed
