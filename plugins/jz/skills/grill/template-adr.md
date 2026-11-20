# <Short title of the decision>

Sign-off: <the git user.name of the person who chose, or the coordinator's family: Claude or Codex>
<A family sign-off only: Opinions: coordinator <pick> (<family>); worker <pick> (<family>); reviewer <pick> (<family>)>

<One to three sentences: the context, what was decided, and why.>

<!--
File name: docs/adr/NNNN-<slug>.md, numbered one above the highest existing.

Write an ADR only when all three hold:
1. Hard to reverse: changing the decision later costs something real.
2. Surprising without context: a future reader would wonder why it was done this way.
3. A real trade-off: there were genuine alternatives and one was picked for specific reasons.

Sign-off is always present and never edited later. A person's choice reads
their `git config user.name`, for example `Sign-off: Jane Doe`, with no
Opinions line. A decision made without the owner names the family of the
coordinator that decided it, `Claude` or `Codex`, never a model, and the
Opinions line under it lists every pick that was asked, in this order: the
coordinator's own, the worker's (the asking skill's session), then one
`reviewer` entry per second opinion, for example
`Opinions: coordinator B (Claude); worker B (Claude); reviewer A (Codex)`.
The `adr-sign-off` guard denies a commit whose ADR breaks this shape.
Someone who disagrees with a family sign-off writes a new ADR that
supersedes it.

Optional sections, only when they add something:
- Status frontmatter (proposed, accepted, deprecated, superseded by ADR-NNNN) when decisions get revisited.
- Considered options, when the rejected alternatives are worth remembering.
- Consequences, when a downstream effect is not obvious.

What qualifies: architectural shape, integration patterns between contexts, technology choices with lock-in, boundary and scope decisions (the explicit no is as valuable as the yes), deliberate deviations from the obvious path, constraints not visible in the code, rejected alternatives whose rejection is not obvious.
Delete this comment before saving.
-->
