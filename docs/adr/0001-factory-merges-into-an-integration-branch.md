# The factory merges into an integration branch, never the default branch

Sign-off: Gerald Yeo

The factory has to take a signed-off spec to a finished product without the
owner merging each step, yet the default branch moves only when the owner
merges a reviewed pull request. Each step's pull request therefore targets
`factory/<spec-slug>`, the factory's merge script merges it there once the
gate, the reviews and the approver agree on one head commit, and the owner
merges a single final pull request into the default branch. The merge script
refuses a protected base, and the `protect-default-branches` guard keeps
denying a merge an agent types itself.

## Considered options

- The owner merges every step, as `coordinate` does. Rejected: the run would
  wait on the owner at every step.
- The factory merges low-risk steps straight into the default branch.
  Rejected: it would relax the merge guard, and one misjudged risk rating
  would land unreviewed by the owner.

## Consequences

The owner's one review is of a large pull request. It is made of step pull
requests that were each gated and reviewed, merged as merge commits so that
one step can be read or reverted on its own.
