"""Run every guard over one Bash PreToolUse payload and give the host a single decision.

Reads the event JSON on stdin. A guard that denies ends the run: its lines go
to stderr and the exit code is 2. Otherwise the asks are joined into one
"ask" decision on stdout, and a call no guard objects to exits 0 with no
output. A guard that raises is reported on stderr and skipped, so one broken
rule never blocks an ordinary Bash call; the exit code stays 0 in that case
because a non-zero code other than 2 is shown to the user as a hook error and
allows the call anyway.

The parser follows plain commands only (see command_lines.py). A line with
anything else on it, a subshell, a variable, a here-document, a wrapper, a
nested shell, is judged on the plain commands it does have and asked about
for the rest, when the line also names a command a guard judges or the
construct could stand for one: a nested shell, a command-running git
option, a dashed git binary, an unknown git or gh word. The run has one
deadline under the
host's 60 s hook timeout; when it passes, the owner is asked rather than the
host failing open.

JZ_GUARDS, a comma-separated list of guard names, restricts the run to those
guards. The test suite uses it to exercise one guard at a time; the ask for
an unfollowed construct is the dispatcher's and is not restricted by it.
"""

import json
import os
import re
import sys

from git_push import GuardTimeout, seconds_from_environment, set_deadline
from guards import Ask, Context, Deny
from guards import (  # noqa: E402
    confirm_remote_writes,
    no_claude_artifacts,
    no_restricted_words,
    protect_default_branches,
    rebase_not_merge,
    require_pr_skill,
    scan_secrets_before_push,
)

# A line with a construct outside the grammar is asked about only when it
# also names something a guard judges; a read-only `git -C "$repo" status`
# passes in silence.
JUDGED = re.compile(r"\b(add|stage|commit|push|merge|pull|pr|api)\b")
# Under the 60 s the host gives the hook, with room for the interpreter.
DEADLINE_SECONDS = seconds_from_environment("JZ_DEADLINE_SECONDS", 50)

# Denying guards first, the ones that need the least git first, so a push to
# the default branch is denied before any dry run can use up the deadline;
# the asking guards last.
GUARDS = [
    protect_default_branches,
    rebase_not_merge,
    require_pr_skill,
    no_restricted_words,
    no_claude_artifacts,
    confirm_remote_writes,
    scan_secrets_before_push,
]


def selected_guards():
    names = os.environ.get("JZ_GUARDS")
    if not names:
        return GUARDS
    wanted = {name.strip() for name in names.split(",") if name.strip()}
    return [guard for guard in GUARDS if guard.NAME in wanted]


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    context = Context(event)
    if not context.command:
        return 0
    set_deadline(DEADLINE_SECONDS)
    asks = []
    timed_out = []
    for guard in selected_guards():
        try:
            decision = guard.check(context)
        except GuardTimeout:
            # The guards after this one get their turn; those that need git
            # time out at once, those that do not still decide.
            timed_out.append(guard.NAME)
            continue
        except Exception as failure:  # one broken guard must not block every Bash call
            print("%s guard failed: %s: %s" % (guard.NAME, type(failure).__name__, failure), file=sys.stderr)
            continue
        if isinstance(decision, Deny):
            for line in decision.lines:
                print(line, file=sys.stderr)
            return 2
        if isinstance(decision, Ask):
            asks.append(decision.reason)
    if timed_out:
        asks.append("The guards ran out of time before %s finished, so part of the command was not checked; "
                    "confirm it, or split the line." % " and ".join(timed_out))
    if context.unfollowed and (context.parsed.hidden or JUDGED.search(context.command)):
        asks.append("The command uses %s, which the guards do not follow, so part of it was not checked. "
                    "The guards follow plain commands joined by separators, a cd <dir> or git -C <dir>, and "
                    "at most a 2>&1 or >/dev/null; write it that way, or confirm it as written."
                    % " and ".join(context.unfollowed))
    if asks:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": "\n\n".join(asks),
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
