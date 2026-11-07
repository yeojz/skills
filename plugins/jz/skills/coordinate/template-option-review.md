# Option review: <unit id>, fork <n>: <the question in a few words>

<!--
Filled by the coordinate skill in auto mode for one ADR-tier fork. The
reviewer is a fresh session, never the worker and never the coordinator.
Every field is filled. The worker's recommendation and its reasons stay out
of this brief. Delete this comment before sending.
-->

Model tier: <one tier above the worker's, from rules/models.md, up to top; at top already, the other family where present. Name the host, its model and its reasoning effort>
Repo: <absolute path to the main checkout>
Branch under work: `<branch>` at `<head sha>`, or "no PR yet"
Notes folder: <absolute path>; write the verdict as `option-review-<unit id>-<n>.md` there
Fork file: `<notes folder>/fork-<unit id>-<n>.md`, the question, the constraints and the options

You are deciding nothing and editing nothing. Reach your own pick from your
own research and report it; the coordinator makes the call.

## Read first, in this order

1. `AGENTS.md`, the Standing orders section in particular
2. `CONTEXT.md` and the ADRs the fork touches: <list them>
3. `docs/specs/<slug>.md`: the requirements and criteria the fork affects: <list them>
4. The fork file

## Research

Read the code each option would change, and its callers. Where an option
claims a cost or a property, such as speed, size or compatibility, check it:
in a throwaway worktree, a spike that is deleted at the end, or the
documentation of the thing in question. Cite what you read or ran.

```bash
spike_dir="$(mktemp -d)"
git worktree add --detach "$spike_dir" "<head sha or default branch>"
( cd "$spike_dir" && <the spike or measurement> ) > spike.log 2>&1; echo "exit=$?"
git worktree remove --force "$spike_dir"; git worktree prune
```

With nothing to measure, skip the spike and say so in the verdict.

An option outside the list is allowed when the research turns one up. Give
it the next letter.

## Verdict

Write the file, then message the coordinator with:

- Pick: the letter, and one sentence why
- For each option: what it costs, what it buys, and the evidence, each with a `file:line`, a command and its exit code, or a link
- What would change the pick, as a fact someone could check
- New dependency: yes or no for the pick; yes goes to the owner whatever the pick
- Not checked, and why
