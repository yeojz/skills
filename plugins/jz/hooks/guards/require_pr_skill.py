"""Deny git commit, git push and gh pr create until the session has loaded the pr skill.

The skill holds the procedure around those commands: verify before the
commit, the body written from the diff, the ancestor check before a rebase,
the tip checks before a branch is deleted. A skill description is a
suggestion the model weighs, and in every recent session where no one named
the skill it stayed unloaded while the house rules were in context. A guard
runs whether or not anyone remembers.

The transcript the payload names is the evidence: a Skill tool call whose
skill is `pr` or `<plugin>:pr` and whose result did not report an error, or
a typed `/pr` command. A call that failed or has no result yet unlocks
nothing. A payload without a transcript path, from another host, the test
suite or a headless run, is allowed through, so the gate holds on Claude
Code only. A subagent is judged on its own transcript.
"""

import json
import os
import re
import stat

from guards import Deny

NAME = "require-pr-skill"

PR = re.compile(r"(^|:)pr$")
TYPED = re.compile(r"<command-name>/(?:[^<>/]*:)?pr</command-name>")


def skill_call_loads_pr(block):
    if not isinstance(block, dict) or block.get("type") != "tool_use" or block.get("name") != "Skill":
        return False
    skill = block.get("input") or {}
    return bool(PR.search(str(skill.get("skill", ""))))


def user_turn_types_pr(content):
    if isinstance(content, str):
        texts = [content]
    elif isinstance(content, list):
        texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    else:
        return False
    return any(TYPED.search(text) for text in texts)


def pr_loaded(path):
    """True once the transcript shows the skill loaded.

    A Skill call counts only with its result: the tool_use block carries an id,
    and the tool_result block that answers it carries the same id. A result
    with is_error true is a load that failed, and a call with no result yet is
    pending; neither unlocks anything. A later call that succeeds does.
    """
    pending = set()
    if not stat.S_ISREG(os.stat(path).st_mode):
        return False
    with open(path, encoding="utf-8", errors="replace") as transcript:
        for line in transcript:
            if '"Skill"' not in line and "tool_result" not in line and "command-name" not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            message = entry.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if entry.get("type") == "assistant" and isinstance(content, list):
                for block in content:
                    if skill_call_loads_pr(block) and block.get("id"):
                        pending.add(block["id"])
            elif entry.get("type") == "user":
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_result":
                            continue
                        if block.get("tool_use_id") not in pending:
                            continue
                        if block.get("is_error") is True:
                            pending.discard(block["tool_use_id"])
                        else:
                            return True
                if user_turn_types_pr(content):
                    return True
    return False


def check(context):
    gated = (context.runs("git", "commit") or context.runs("git", "push") or context.runs("gh", "pr", "create"))
    if not gated:
        return None
    transcript = context.transcript_path
    if not isinstance(transcript, str) or not os.path.isfile(transcript):
        return None
    try:
        if pr_loaded(transcript):
            return None
    except OSError:
        return None
    return Deny("Blocked: git commit, git push and gh pr create run through the pr skill, "
                "and this session has not loaded it.",
                "Load it first: call the Skill tool with skill \"jz:pr\", or type /jz:pr, "
                "then run the command again in the mode the request asked for.")
