"""Deny a commit whose new or changed ADR carries a sign-off in the wrong shape.

grill's template-adr.md gives two shapes. A person's decision reads
`Sign-off: <name>` and nothing more. A decision made without the owner reads
`Sign-off: <family>`, the coordinator's family, followed by
`Opinions: coordinator B (Claude); worker B (Claude); reviewer A (Codex)`,
one entry per pick that was asked. Any family is accepted, but a family is
one word with no digits, so a model name and its version fail the check, and
the coordinator's entry must carry the family the sign-off names. Without an
Opinions line the sign-off reads as a person's. The guard reads the
staged copy of each ADR under docs/adr/ that the commit adds or changes,
plus the modified ones when the commit runs with -a, and never an ADR the
commit leaves alone, so an older ADR written before this shape stays valid.
"""

import re

from guards import Deny

NAME = "adr-sign-off"

ADR_PATH = re.compile(r"(^|/)docs/adr/[^/]+\.md$")
# A family: one word of letters, such as Claude, Codex or Gemini. A model carries a version or a second word.
FAMILY = r"[A-Za-z][A-Za-z-]*"
OPINION = r"(coordinator|worker|reviewer) [A-Z] \((%s)\)" % FAMILY
OPINIONS_LINE = re.compile(r"^Opinions: %s(?:; %s)*$" % (OPINION, OPINION))
# A person's name: no digits, brackets or separators, which a model or a list would carry.
PERSON = re.compile(r"^[^\d()\[\]<>;,]+$")
SHAPE = ("Sign-off: <the git user.name of the person who chose>, or Sign-off: <the coordinator's family> followed by "
         "Opinions: coordinator <pick> (<family>); worker <pick> (<family>); reviewer <pick> (<family>)")


def problem(text):
    """Why an ADR's sign-off breaks the shape, or None when it holds."""
    lines = [line.strip() for line in text.splitlines()]
    signed = [line for line in lines if line.startswith("Sign-off:")]
    if not signed:
        return "has no Sign-off line"
    value = signed[0][len("Sign-off:"):].strip()
    opinions = [line for line in lines if line.startswith("Opinions:")]
    if not opinions:
        if not value or not PERSON.match(value):
            return "signs off as %r, which is neither a person's name nor a family with an Opinions line" % value
        return None
    if not re.fullmatch(FAMILY, value):
        return "signs off as %r over an Opinions line; a decision with opinions signs off as the coordinator's family, one word" % value
    if not OPINIONS_LINE.match(opinions[0]):
        return "has an Opinions line that is not role, pick and family per entry, a family being one word: %s" % opinions[0]
    entries = re.findall(OPINION, opinions[0])
    if (("coordinator", value)) not in entries:
        return "signs off as %s, but no coordinator entry in the Opinions line carries that family" % value
    return None


def changed_adrs(context):
    names = set()
    staged = context.git("diff", "--cached", "--name-only", "--diff-filter=AMR")
    names.update(staged.splitlines() if staged else [])
    if context.flag(r"--all|-[A-Za-z]*a[A-Za-z]*"):
        modified = context.git("diff", "--name-only", "--diff-filter=M")
        names.update(modified.splitlines() if modified else [])
    return sorted(name for name in names if ADR_PATH.search(name))


def check(context):
    if not context.runs("git", "commit"):
        return None
    root = context.git("rev-parse", "--show-toplevel")
    if not root:
        return None
    found = []
    for path in changed_adrs(context):
        # The index holds what the commit records; -a commits the working copy.
        text = context.git("show", ":" + path)
        if text is None or context.flag(r"--all|-[A-Za-z]*a[A-Za-z]*"):
            try:
                with open("%s/%s" % (root, path), encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
            except OSError:
                continue
        reason = problem(text)
        if reason:
            found.append("%s %s" % (path, reason))
    if not found:
        return None
    return Deny("Blocked: %s." % "; ".join(found), "Write the sign-off as " + SHAPE + ".")
