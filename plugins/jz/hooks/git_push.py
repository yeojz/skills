"""Read a `git push` call the way git reads it, and work out from the repository alone which refs it would update.

Shared by the hooks that judge a push, so the option table, the walk over the
arguments and the resolution of the destination and refspecs are the same for
each of them.

Nothing here contacts the remote or runs anything the caller named. A push
dry run would answer more exactly, but it spawns receive-pack and the ssh
command, both of which the caller chooses with --receive-pack, --exec and
-c core.sshCommand, and a PreToolUse hook runs before the owner has approved
the command. The destination, the refspecs and the old tips are read from the
repository's configuration and its remote-tracking refs instead. A tracking
ref can be behind the remote, so a hook built on this scans or denies a
little more than git would, never less.
"""

import os
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
SHORT_FLAGS = {"d": "delete", "n": "dry-run"}
GIT_TIMEOUT_SECONDS = 10

HEADS = "refs/heads/"
TAGS = "refs/tags/"
WHOLESALE = {"all", "branches", "mirror", "tags", "delete"}
# Configuration that chooses the destination or the refspecs of a push. A
# one-off override of one of these on the command line is not followed, so a
# hook asks or denies instead of guessing.
PUSH_CONFIG_PREFIXES = ("remote.", "push.", "branch.", "url.")


def run_git(directory, options, args):
    """Run one read-only git call with prompts, locks and the pager off."""
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
                       GIT_PAGER="cat", GIT_EDITOR="true")
    try:
        return subprocess.run(["git", "--no-pager", "-C", directory] + options + args,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              errors="replace", env=environment, timeout=GIT_TIMEOUT_SECONDS)
    except Exception:
        return None


def git_text(directory, options, args):
    """The stripped output of a successful git call, else None."""
    out = run_git(directory, options, args)
    if out is None or out.returncode != 0:
        return None
    return out.stdout.strip()


def git_lines(directory, options, args):
    text = git_text(directory, options, args)
    return [] if not text else text.splitlines()


class PushOptionWalk:
    """How git push reads its arguments: the options, the operands from the real -- on, the flags set and the final dry-run value."""

    def __init__(self):
        self.options = []
        self.operands = []
        self.flags = set()
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
    stops at the real --; everything from it on is an operand. A flag's final
    value is the last of its --flag and --no-flag spellings, and -n is a
    dry run. A dangling option with no value, an unknown option or an
    ambiguous prefix is an error.
    """
    walk = PushOptionWalk()
    index = 0
    while index < len(args):
        token = args[index]
        index += 1
        if token == "--":
            walk.operands.extend(args[index:])
            break
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
            elif negated:
                walk.flags.discard(resolved)
            else:
                walk.flags.add(resolved)
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
                if letter in SHORT_FLAGS:
                    walk.flags.add(SHORT_FLAGS[letter])
            continue
        walk.operands.append(token)
    walk.dry_run = "dry-run" in walk.flags
    return walk


def unfollowed_config_override(config_overrides):
    """The `-c` or `--config-env` token pair that would change what a push publishes, or None.

    `config_overrides` is the flat token list command_lines.git_config_overrides
    returns. A key under remote., push., branch. or url. moves the destination
    or the refspecs, and nothing local records the override, so the hook
    cannot follow it. Any other key, such as user.name, is left alone.
    """
    for name, value in zip(config_overrides[::2], config_overrides[1::2]):
        key = value.split("=", 1)[0].lower()
        if key.startswith(PUSH_CONFIG_PREFIXES):
            return name + " " + value
    return None


class Push:
    """What a push would do, as far as the repository can tell.

    `destination` is the remote name or URL the push goes to. `remote` is that
    name when it is a configured remote, else None. `tracked` says whether
    refs/remotes/<remote>/* describe the destination: true for a configured
    remote without a pushurl, since tracking refs are filled from the fetch
    URL. `updates` holds (source, destination ref) pairs, source None for a
    deletion; the destination is a full ref name.
    """

    def __init__(self, destination, remote, tracked, updates, dry_run):
        self.destination = destination
        self.remote = remote
        self.tracked = tracked
        self.updates = updates
        self.dry_run = dry_run


def current_branch(directory, options):
    return git_text(directory, options, ["symbolic-ref", "-q", "--short", "HEAD"]) or None


def config(directory, options, key):
    return git_text(directory, options, ["config", "--get", key])


def config_all(directory, options, key):
    return git_lines(directory, options, ["config", "--get-all", key])


def local_refs(directory, options, pattern):
    """The full names of the local refs a for-each-ref pattern matches."""
    return git_lines(directory, options, ["for-each-ref", "--format=%(refname)", pattern])


def resolve_commit(directory, options, revision):
    return git_text(directory, options, ["rev-parse", "--verify", "--quiet", revision + "^{commit}"]) or None


def full_ref(directory, options, name):
    """The full name of the local ref `name` abbreviates, or None for a sha or an expression."""
    return git_text(directory, options, ["rev-parse", "--verify", "--quiet", "--symbolic-full-name", name]) or None


def qualify(destination, source_ref):
    """A destination the way git completes a short one: under refs/heads/, or refs/tags/ for a tag source."""
    if destination.startswith("refs/"):
        return destination
    if source_ref and source_ref.startswith(TAGS):
        return TAGS + destination
    return HEADS + destination


def expand_refspec(directory, options, refspec):
    """The (source, destination ref) pairs one refspec selects, or an error.

    `+src:dst` forces; `:dst` deletes; a bare `src` lands on the ref of the
    same name; a `*` in both sides is expanded over the local refs it
    matches.
    """
    source, colon, destination = refspec.lstrip("+").partition(":")
    if "*" in source or "*" in destination:
        if "*" not in source or (colon and "*" not in destination):
            return None, "refspec %s is not one the hook can follow" % refspec
        prefix, _, suffix = source.partition("*")
        pairs = []
        for ref in local_refs(directory, options, source):
            matched = ref[len(prefix):len(ref) - len(suffix) if suffix else None]
            target = destination.replace("*", matched, 1) if colon else ref
            pairs.append((ref, qualify(target, ref)))
        return pairs, None
    if not source:
        if not destination:
            return None, "refspec %s names nothing" % refspec
        return [(None, qualify(destination, None))], None
    source_ref = full_ref(directory, options, source)
    if not colon:
        if source_ref is None:
            return None, "refspec %s names no local ref, so its destination is unknown" % refspec
        destination = source_ref
    return [(source, qualify(destination, source_ref))], None


def resolve_push(directory, options, args):
    """What `git push` with these arguments would update, read from the repository. Returns (Push, error).

    The destination is the first operand, else the branch's pushRemote, then
    remote.pushDefault, then the branch's remote, then origin. The refspecs
    are the operands after it, else remote.<name>.push, else what
    push.default selects for the current branch. --all, --branches, --tags
    and --mirror select whole namespaces; --delete turns each operand into a
    deletion.
    """
    walk = walk_push_options(args)
    if walk.error:
        return None, walk.error
    branch = current_branch(directory, options)
    operands = walk.operands
    if operands:
        destination = operands[0]
    else:
        destination = ((branch and config(directory, options, "branch.%s.pushRemote" % branch))
                       or config(directory, options, "remote.pushDefault")
                       or (branch and config(directory, options, "branch.%s.remote" % branch))
                       or "origin")
    remote = destination if destination in git_lines(directory, options, ["remote"]) else None
    tracked = remote is not None and config(directory, options, "remote.%s.pushurl" % remote) is None
    refspecs = operands[1:]
    flags = walk.flags
    updates = []
    if "mirror" in flags:
        updates.extend((ref, ref) for ref in local_refs(directory, options, "refs/"))
    else:
        if "all" in flags or "branches" in flags:
            updates.extend((ref, ref) for ref in local_refs(directory, options, HEADS))
        if "tags" in flags:
            updates.extend((ref, ref) for ref in local_refs(directory, options, TAGS))
        if "delete" in flags:
            updates.extend((None, qualify(name, None)) for name in refspecs)
            refspecs = []
        if not refspecs and not flags & WHOLESALE:
            refspecs = config_all(directory, options, "remote.%s.push" % remote) if remote else []
        if not refspecs and not flags & WHOLESALE:
            default = (config(directory, options, "push.default") or "simple").lower()
            if default in {"simple", "current"}:
                if branch is None:
                    return None, "a bare push from a detached HEAD publishes nothing git can name"
                refspecs = [branch + ":" + branch]
            elif default in {"upstream", "tracking"}:
                merge = branch and config(directory, options, "branch.%s.merge" % branch)
                if not merge:
                    return None, "push.default is upstream and the branch has no upstream"
                refspecs = [branch + ":" + merge]
            elif default == "matching":
                for ref in local_refs(directory, options, HEADS):
                    name = ref[len(HEADS):]
                    if tracked and resolve_commit(directory, options, "refs/remotes/%s/%s" % (remote, name)) is None:
                        continue
                    updates.append((ref, ref))
            else:
                return None, "push.default is %s" % default
        for refspec in refspecs:
            pairs, error = expand_refspec(directory, options, refspec)
            if error:
                return None, error
            updates.extend(pairs)
    return Push(destination, remote, tracked, updates, walk.dry_run), None
