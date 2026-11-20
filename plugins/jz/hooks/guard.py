"""Run every guard over one Bash PreToolUse payload and give the host a single decision.

Reads the event JSON on stdin. A guard that denies ends the run: its lines go
to stderr and the exit code is 2. Otherwise the asks are joined into one
"ask" decision on stdout, and a call no guard objects to exits 0 with no
output. A guard that raises is reported on stderr and skipped, so one broken
rule never blocks an ordinary Bash call; the exit code stays 0 in that case
because a non-zero code other than 2 is shown to the user as a hook error and
allows the call anyway.

The guards read the command as text (see guards/__init__.py). Denying guards
run first, so a line that both denies and asks is denied.

JZ_GUARDS, a comma-separated list of guard names, restricts the run to those
guards; the test suite uses it to exercise one guard at a time.

In a Claude Code cloud session (CLAUDE_CODE_REMOTE=true) the guards whose
workflow the cloud session cannot follow are skipped: it has no gh to open a
PR with the pr skill, and runs with no one watching for an ask. The
default-branch, rebase, artifact and secret guards still run; the cloud
rules recover a rejected push by rebasing. JZ_GUARDS_SKIP, a comma-separated list of guard
names, skips those guards anywhere and, when set, replaces the cloud list, so
JZ_GUARDS_SKIP=none runs every guard in the cloud.
"""

import json
import os
import sys

from guards import Ask, Context, Deny
from guards import (  # noqa: E402
    confirm_remote_writes,
    no_claude_artifacts,
    protect_default_branches,
    rebase_not_merge,
    require_pr_skill,
    scan_secrets_before_push,
)

GUARDS = [
    protect_default_branches,
    rebase_not_merge,
    require_pr_skill,
    no_claude_artifacts,
    confirm_remote_writes,
    scan_secrets_before_push,
]


# Guards whose workflow a cloud session cannot follow.
REMOTE_SKIPS = {
    require_pr_skill.NAME,
    confirm_remote_writes.NAME,
}


def names_in(variable):
    return {name.strip() for name in os.environ.get(variable, "").split(",") if name.strip()}


def skipped_names():
    if "JZ_GUARDS_SKIP" in os.environ:
        return names_in("JZ_GUARDS_SKIP")
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        return REMOTE_SKIPS
    return set()


def selected_guards():
    guards = GUARDS
    if os.environ.get("JZ_GUARDS"):
        wanted = names_in("JZ_GUARDS")
        guards = [guard for guard in guards if guard.NAME in wanted]
    skipped = skipped_names()
    return [guard for guard in guards if guard.NAME not in skipped]


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    context = Context(event)
    if not context.text or not context.runs():
        return 0
    asks = []
    for guard in selected_guards():
        try:
            decision = guard.check(context)
        except Exception as failure:  # one broken guard must not block every Bash call
            print("%s guard failed: %s: %s" % (guard.NAME, type(failure).__name__, failure), file=sys.stderr)
            continue
        if isinstance(decision, Deny):
            for line in decision.lines:
                print(line, file=sys.stderr)
            return 2
        if isinstance(decision, Ask):
            asks.append(decision.reason)
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
