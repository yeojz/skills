"""Run every guard over one Bash PreToolUse payload and give the host a single decision.

Reads the event JSON on stdin. A guard that denies ends the run: its lines go
to stderr and the exit code is 2. Otherwise the asks are joined into one
"ask" decision on stdout, and a call no guard objects to exits 0 with no
output. A guard that raises is reported on stderr and skipped, so one broken
rule never blocks an ordinary Bash call; the exit code stays 0 in that case
because a non-zero code other than 2 is shown to the user as a hook error and
allows the call anyway.

A construct the parser does not follow (a subshell, a variable, a nested
shell, a wrapper with options, unbalanced quotes) is judged on what was
visible and asked about for the rest, when the line also names a command a
guard judges or the construct itself mentions git or gh. The run has one
deadline under the host's 60 s hook timeout; when it passes, the owner is
asked rather than the host failing open.

JZ_GUARDS, a comma-separated list of guard names, restricts the run to those
guards. The test suite uses it to exercise one guard at a time; the ask for
an unfollowed construct is the dispatcher's and is not restricted by it.
"""

import json
import os
import re
import sys

from git_push import GuardTimeout, set_deadline
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

# A line with a construct the parser does not follow is asked about only when
# it also names something a guard judges; a read-only `git -C "$repo" status`
# passes in silence.
JUDGED = re.compile(r"\b(add|stage|commit|push|merge|pull|pr|api)\b")
# Under the 60 s the host gives the hook, with room for the interpreter.
DEADLINE_SECONDS = 50

# Denying guards first, cheapest first, so a blocked call never pays for the
# secret scan; the asking guards last.
GUARDS = [
    no_claude_artifacts,
    require_pr_skill,
    rebase_not_merge,
    no_restricted_words,
    protect_default_branches,
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
    for guard in selected_guards():
        try:
            decision = guard.check(context)
        except GuardTimeout:
            asks.append("The guards ran out of time before %s finished, so part of the command was not checked; "
                        "confirm it, or split the line." % guard.NAME)
            break
        except Exception as failure:  # one broken guard must not block every Bash call
            print("%s guard failed: %s: %s" % (guard.NAME, type(failure).__name__, failure), file=sys.stderr)
            continue
        if isinstance(decision, Deny):
            for line in decision.lines:
                print(line, file=sys.stderr)
            return 2
        if isinstance(decision, Ask):
            asks.append(decision.reason)
    if context.unfollowed and (context.parsed.hidden or JUDGED.search(context.command)):
        asks.append("The command uses %s, which the guards do not follow, so part of it was not checked. "
                    "Write plain git and gh commands joined by && or ;, run from the repository directory "
                    "or with git -C <path>, or confirm it as written." % " and ".join(context.unfollowed))
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
