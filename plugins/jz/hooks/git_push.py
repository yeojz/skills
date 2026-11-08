"""Read the push forms an agent writes, and work out from the repository alone which refs each would update.

Shared by the guards that judge a push, with the one git runner every guard
uses, its safe configuration and the run's deadline.

Nothing here contacts the remote or runs anything the caller named. A push
dry run would answer more exactly, but it spawns receive-pack and the ssh
command, both of which the caller chooses with --receive-pack, --exec and
-c core.sshCommand, and a PreToolUse hook runs before the owner has approved
the command. The destination, the refspecs and the old tips are read from
the repository's configuration and its remote-tracking refs instead.

The forms followed are `git push`, `git push <remote>`, `git push <remote>
<branch>`, `git push <remote> <src>:<dst>`, `git push <remote> HEAD[:<dst>]`,
`git push <remote> :<dst>` and `git push --delete <remote> <name>`, with
more than one refspec allowed, plus `--tags`, and the options in PUSH_FLAGS
and PUSH_SHORT_FLAGS. The remote must be configured, with one url and no
pushurl, mirror flag, pushInsteadOf rewrite or remote.<name>.push refspec,
so that its tracking refs describe where the push lands. The bare form
follows branch.<name>.pushRemote, remote.pushDefault, branch.<name>.remote,
then origin, and push.default simple, current or upstream. Anything else,
from --all and --mirror to a wildcard, a URL destination or an option
outside the set, is an error; the guards turn an error into an ask, or into
a deny when a protected name is visible in the arguments.
"""

import os
import re
import subprocess
import time

from command_lines import SHORT_CLUSTER

# The push options followed. Any other option is an error, and so is a
# --no- spelling of one not listed here.
PUSH_FLAGS = {"--set-upstream", "--force", "--force-if-includes", "--dry-run", "--verify", "--no-verify",
              "--quiet", "--verbose", "--tags", "--follow-tags", "--porcelain", "--progress", "--no-progress",
              "--atomic", "--delete"}
PUSH_SHORT_FLAGS = {"u": "--set-upstream", "f": "--force", "n": "--dry-run", "q": "--quiet", "v": "--verbose",
                    "d": "--delete"}


def seconds_from_environment(name, default):
    """A tuning knob for the test suite; anything that is not a number is the default."""
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


GIT_TIMEOUT_SECONDS = seconds_from_environment("JZ_GIT_TIMEOUT_SECONDS", 10)
COMMON_DEFAULTS = {"main", "master", "develop", "trunk"}
HEADS = "refs/heads/"
TAGS = "refs/tags/"
# Configuration that chooses the destination or the refspecs of a push. A
# one-off override of one of these on the command line is not followed, so a
# guard asks or denies instead of guessing.
PUSH_CONFIG_PREFIXES = ("remote.", "push.", "branch.", "url.")
FALSE_VALUES = {"false", "no", "off", "0"}
# Short destinations git completes against the remote's own refs; `heads/main` lands on refs/heads/main.
REF_NAMESPACES = ("heads/", "tags/", "remotes/")


class GuardTimeout(Exception):
    """The run's deadline passed. The dispatcher asks instead of letting the host's timeout fail open."""


_deadline = [None]


def set_deadline(seconds):
    """Give every git and scanner call in this run a shared budget."""
    _deadline[0] = time.monotonic() + seconds


def remaining(limit):
    """The timeout for one call: `limit`, or less when the run's deadline is nearer. Raises GuardTimeout once it has passed."""
    if _deadline[0] is None:
        return limit
    left = _deadline[0] - time.monotonic()
    if left <= 0:
        raise GuardTimeout()
    return min(limit, left)


# Configuration that would make a read-only git call run a program from the
# repository's own config: the filesystem monitor, signature display, hooks.
# Switched off for every call a guard makes.
SAFE_CONFIG = ["-c", "core.fsmonitor=false", "-c", "log.showSignature=false",
               "-c", "core.hooksPath=/dev/null",
               # A dry run on a scratch index must not write a shared index into the real .git.
               "-c", "core.splitIndex=false", "-c", "splitIndex.sharedIndexExpire=never"]


def run_git(directory, options, args, environment=None):
    """Run one read-only git call with prompts, locks, the pager and repository-run programs off.

    The one git runner every guard uses. Returns the completed process, or
    None when git is missing, failed to start or ran past its timeout.
    """
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_PAGER="cat", GIT_EDITOR="true")
    if environment:
        env.update(environment)
    timeout = remaining(GIT_TIMEOUT_SECONDS)
    try:
        # SAFE_CONFIG last, so no caller option can override it.
        return subprocess.run(["git", "--no-pager", "-C", directory] + options + SAFE_CONFIG + args,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              errors="replace", env=env, timeout=timeout)
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


def config(directory, options, key):
    return git_text(directory, options, ["config", "--get", key])


def current_branch(directory, options):
    return git_text(directory, options, ["symbolic-ref", "-q", "--short", "HEAD"]) or None


def origin_head(directory, options):
    """The branch refs/remotes/origin/HEAD names, or None when the clone does not record one."""
    out = git_text(directory, options, ["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"])
    return out.split("/", 1)[-1] if out else None


def resolve_commit(directory, options, revision):
    return git_text(directory, options, ["rev-parse", "--verify", "--quiet", revision + "^{commit}"]) or None


def full_ref(directory, options, name):
    """The full name of the local ref `name` abbreviates, or None for a sha or an expression."""
    return git_text(directory, options, ["rev-parse", "--verify", "--quiet", "--symbolic-full-name", name]) or None


def unfollowed_config_override(config_overrides):
    """The `-c` or `--config-env` token pair that would change what a push publishes, or None.

    `config_overrides` is the flat token list command_lines.git_config_overrides
    returns. A key under remote., push., branch. or url. moves the destination
    or the refspecs, and nothing local records the override, so the guard
    cannot follow it. Any other key, such as user.name, is left alone.
    """
    for name, value in zip(config_overrides[::2], config_overrides[1::2]):
        key = value.split("=", 1)[0].lower()
        if key.startswith(PUSH_CONFIG_PREFIXES):
            return name + " " + value
    return None


class Push:
    """What a push would do, as far as the repository can tell.

    `remote` is the configured remote the push goes to; its tracking refs
    describe the destination, since the resolver accepts no remote whose
    pushes go elsewhere. `updates` holds (source, destination ref) pairs,
    source None for a deletion; the destination is a full ref name.
    `forced` says a force option or a `+refspec` was given, so a tip that
    matches the tracking ref may still rewind the remote.
    """

    def __init__(self, remote, updates, dry_run, forced):
        self.remote = remote
        self.updates = updates
        self.dry_run = dry_run
        self.forced = forced

    def tracking_ref(self, name):
        """The tracking ref for branch `name` at the destination."""
        return "refs/remotes/%s/%s" % (self.remote, name)


def walk_push_options(args):
    """(operands, flags, error) of a git push argument list.

    Flags are the long spellings in PUSH_FLAGS; a short cluster such as -fu
    is read letter by letter. A `--force-with-lease` with or without a value
    is a flag. `--` ends the options. An option outside the set is an error.
    """
    operands = []
    flags = set()
    index = 0
    while index < len(args):
        token = args[index]
        index += 1
        if token == "--":
            operands.extend(args[index:])
            break
        if token in PUSH_FLAGS or token == "--force-with-lease" or token.startswith("--force-with-lease="):
            flags.add(token.partition("=")[0])
        elif SHORT_CLUSTER.match(token) and all(letter in PUSH_SHORT_FLAGS for letter in token[1:]):
            flags.update(PUSH_SHORT_FLAGS[letter] for letter in token[1:])
        elif token.startswith("-") and len(token) > 1:
            return None, None, "git push option %s is not one the hook follows" % token
        else:
            operands.append(token)
    return operands, flags, None


def remote_problem(directory, options, remote):
    """Why refs/remotes/<remote>/* would not describe where a push to `remote` lands, or None.

    One `git config` call reads the remote's section and every pushInsteadOf
    rewrite. A key with no value, such as a bare `mirror`, is true to git.
    """
    settings = {}
    for line in git_lines(directory, options, ["config", "--get-regexp",
                                                r"^(remote\.%s\..*|url\..*\.pushinsteadof)$" % re.escape(remote)]):
        key, _, value = line.partition(" ")
        settings.setdefault(key.lower(), []).append(value)
    section = "remote.%s." % remote.lower()
    if section + "url" not in settings:
        return "destination %s is not a configured remote" % remote
    if section + "pushurl" in settings:
        return "remote %s has a pushurl" % remote
    if len(settings[section + "url"]) > 1:
        return "remote %s has more than one url" % remote
    if any(key.startswith("url.") for key in settings):
        return "a url.<base>.pushInsteadOf rewrite is configured"
    if any(value.lower() not in FALSE_VALUES for value in settings.get(section + "mirror", [])):
        return "remote %s is a mirror" % remote
    if section + "push" in settings:
        return "remote.%s.push configures the refspecs" % remote
    return None


def full_destination(name):
    """A destination the stricter way: a short name is a branch, whatever the source, and `heads/x` is refs/heads/x."""
    if name.startswith("refs/"):
        return name
    if name.startswith(REF_NAMESPACES):
        return "refs/" + name
    return HEADS + name


def resolve_push(directory, options, args):
    """What `git push` with these arguments would update, read from the repository. Returns (Push, error)."""
    operands, flags, error = walk_push_options(args)
    if error:
        return None, error
    branch = current_branch(directory, options)
    if operands:
        remote = operands[0]
    else:
        remote = ((branch and config(directory, options, "branch.%s.pushRemote" % branch))
                  or config(directory, options, "remote.pushDefault")
                  or (branch and config(directory, options, "branch.%s.remote" % branch))
                  or "origin")
    error = remote_problem(directory, options, remote)
    if error:
        return None, error
    refspecs = operands[1:]
    forced = bool(flags & {"--force", "--force-with-lease"}) or any(refspec.startswith("+") for refspec in refspecs)
    push = Push(remote, [], "--dry-run" in flags, forced)
    if "--delete" in flags:
        if not refspecs:
            return None, "git push --delete names nothing"
        push.updates = [(None, full_destination(name)) for name in refspecs]
        return push, None
    if "--tags" in flags:
        push.updates.extend((ref, ref) for ref in git_lines(directory, options, ["for-each-ref", "--format=%(refname)", TAGS]))
    elif not refspecs:
        if branch is None:
            return None, "a bare push from a detached HEAD publishes nothing git can name"
        default = (config(directory, options, "push.default") or "simple").lower()
        if default in {"simple", "current"}:
            refspecs = [branch + ":" + branch]
        elif default in {"upstream", "tracking"}:
            merge = config(directory, options, "branch.%s.merge" % branch)
            if not merge:
                return None, "push.default is upstream and the branch has no upstream"
            refspecs = [branch + ":" + merge]
        else:
            return None, "push.default is %s" % default
    for refspec in refspecs:
        if "*" in refspec:
            return None, "refspec %s has a wildcard" % refspec
        source, colon, destination = refspec.lstrip("+").partition(":")
        if not source:
            if not destination:
                return None, "refspec %s names nothing" % refspec
            push.updates.append((None, full_destination(destination)))
            continue
        if not colon:
            destination = full_ref(directory, options, source)
            if destination is None:
                return None, "refspec %s names no local ref, so its destination is unknown" % refspec
        push.updates.append((source, full_destination(destination)))
    return push, None
