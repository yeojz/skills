# <Short title of the decision>

Sign-off: <the git user.name of the person who chose, or (C) <model of the session running handsfree>, (W) <model of the asking skill's session>, (R) <model that gave the second opinion>>

<One to three sentences: the context, what was decided, and why.>

<!--
File name: docs/adr/NNNN-<slug>.md, numbered one above the highest existing.

Write an ADR only when all three hold:
1. Hard to reverse: changing the decision later costs something real.
2. Surprising without context: a future reader would wonder why it was done this way.
3. A real trade-off: there were genuine alternatives and one was picked for specific reasons.

Sign-off is always present and never edited later. A person's choice reads
their `git config user.name`, for example `Sign-off: Jane Doe`. A decision
made through the `handsfree` skill names the three models by display name,
as the briefs' Model tier lines give them, for example
`Sign-off: (C) Opus 5.5, (W) Opus 5.5, (R) Fable 5.1`: (C) the session
running handsfree, (W) the session of the skill that asked, a worker under
`coordinate`, and (R) the second opinion. Someone who disagrees with a
model sign-off writes a new ADR that supersedes it.

Optional sections, only when they add something:
- Status frontmatter (proposed, accepted, deprecated, superseded by ADR-NNNN) when decisions get revisited.
- Considered options, when the rejected alternatives are worth remembering.
- Consequences, when a downstream effect is not obvious.

What qualifies: architectural shape, integration patterns between contexts, technology choices with lock-in, boundary and scope decisions (the explicit no is as valuable as the yes), deliberate deviations from the obvious path, constraints not visible in the code, rejected alternatives whose rejection is not obvious.
Delete this comment before saving.
-->
