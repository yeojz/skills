"""Read a `git push` call the way git reads it, and ask git what it would update.

Shared by the hooks that judge a push, so the option table, the walk over the
arguments and the dry-run preview are the same for each of them.
"""

import re
import subprocess

# The long options of git push (builtin/push.c, git 2.50). git resolves any
# unambiguous prefix of a long option and accepts no- in front of a boolean,
# so a token is matched the same way; an option outside this table, or an
# ambiguous prefix, means the call cannot be followed.
PUSH_LONG_OPTIONS = {
    "verbose", "quiet", "repo", "all", "branches", "mirror", "delete", "tags",
    "dry-run", "porcelain", "force", "force-with-lease", "force-if-includes",
    "recurse-submodules", "thin", "receive-pack", "exec", "set-upstream",
    "progress", "prune", "verify", "follow-tags", "signed", "atomic",
    "push-option", "ipv4", "ipv6",
}
# Options whose value may be a separate token. Every other option is a flag or
# takes its value attached with =, so the token after it is never its value.
PUSH_LONG_OPTIONS_WITH_VALUE = {"repo", "receive-pack", "exec", "push-option"}
PUSH_SHORT_OPTIONS_WITH_VALUE = "o"
GIT_TIMEOUT_SECONDS = 30

# One porcelain line per ref: flag, source:destination, summary. The summary
# holds the old tip at the destination as old..new, or old...new for a forced update.
UPDATE_LINE = re.compile(r"^([ +\-*!=])\t([^:\t]*):([^\t]*)\t(.*)$")


def run_git(directory, options, args):
    try:
        return subprocess.run(["git", "-C", directory] + options + args, capture_output=True,
                              text=True, errors="replace", timeout=GIT_TIMEOUT_SECONDS)
    except Exception:
        return None


class PushOptionWalk:
    """How git push reads its arguments: the options, the operands from the real -- on, and the final dry-run value."""

    def __init__(self):
        self.options = []
        self.operands = []
        self.dry_run = False
        self.error = None


def resolve_push_long_option(name):
    """The push option a --name token means, or None when git would reject it."""
    if name in PUSH_LONG_OPTIONS:
        return name
    candidates = [option for option in PUSH_LONG_OPTIONS if option.startswith(name)]
    return candidates[0] if len(candidates) == 1 else None


def walk_push_options(args):
    """Walk a git push argument list the way git parses it.

    A value-taking option consumes the next token, so a -- or an -n given as
    the value of -o is a push option, not a terminator or a flag. The walk
    stops at the real --; everything from it on is an operand. The dry-run
    value is the last of --dry-run, -n and --no-dry-run. A dangling option
    with no value, an unknown option or an ambiguous prefix is an error.
    """
    walk = PushOptionWalk()
    index = 0
    while index < len(args):
        token = args[index]
        index += 1
        if token == "--":
            walk.operands = [token] + args[index:]
            return walk
        if token.startswith("--"):
            name, has_value, _ = token[2:].partition("=")
            negated = name.startswith("no-")
            resolved = resolve_push_long_option(name[3:] if negated else name)
            if resolved is None:
                walk.error = "git push option %s is not one the hook can follow" % token
                return walk
            walk.options.append(token)
            if resolved in PUSH_LONG_OPTIONS_WITH_VALUE and not has_value and not negated:
                if index >= len(args):
                    walk.error = "git push option %s has no value" % token
                    return walk
                walk.options.append(args[index])
                index += 1
            elif resolved == "dry-run":
                walk.dry_run = not negated
            continue
        if token.startswith("-") and len(token) > 1:
            walk.options.append(token)
            cluster = token[1:]
            while cluster:
                letter, cluster = cluster[0], cluster[1:]
                if letter in PUSH_SHORT_OPTIONS_WITH_VALUE:
                    if not cluster:
                        if index >= len(args):
                            walk.error = "git push option -%s has no value" % letter
                            return walk
                        walk.options.append(args[index])
                        index += 1
                    break
                if letter == "n":
                    walk.dry_run = True
            continue
        walk.options.append(token)
    return walk


def dry_run_updates(directory, options, args):
    """What `git push` with these arguments would update, according to the dry run git itself runs.

    The dry-run and porcelain flags go after every caller option, so a
    --no-dry-run in the call cannot switch the preview into a real push; the
    operands after a -- stay operands. Returns (destination url, update lines,
    error), each update line a (flag, source, destination, summary) tuple. A
    rejected ref still appears in the lines at a non-zero exit; no lines at
    all is an error.
    """
    walk = walk_push_options(args)
    if walk.error:
        return None, [], walk.error
    out = run_git(directory, options, ["push"] + walk.options + ["--dry-run", "--porcelain"] + walk.operands)
    if out is None:
        return None, [], "git push --dry-run did not finish"
    url = None
    updates = []
    for line in out.stdout.splitlines():
        if line.startswith("To "):
            url = line[3:].strip()
            continue
        match = UPDATE_LINE.match(line)
        if match:
            updates.append(match.groups())
    if url is None or (out.returncode != 0 and not updates):
        tail = (out.stderr.strip().splitlines() or ["no output"])[-1]
        return None, [], "git push --dry-run exited %d: %s" % (out.returncode, tail)
    return url, updates, None
