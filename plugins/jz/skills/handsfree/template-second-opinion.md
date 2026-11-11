# Second opinion: <slug>, round <N>: questions <Q numbers>

<!--
Filled by the handsfree skill, at most twice per round: once for the
assessor thread, covering every question below the ADR tier whose first two
picks differ, and once for a fresh session, covering every ADR-tier question
in the round. Never one brief per question. The brief carries the questions,
their options, the facts and the constraints. It never carries the asking
skill's recommendation, handsfree's own pick, or who disagreed with whom.
Every field is filled. Delete this comment before sending.
-->

Model tier: <below the ADR tier: standard. ADR tier: top. The other family where present, otherwise this one. Name the host, its model and its reasoning effort>
Repo: <absolute path to the main checkout>
Questions file: `<absolute run folder>/round-<N>-questions.md`
Answer: <the question numbers, such as Q4, Q6 and Q7; leave the others alone>
Research: <ADR tier: yes, do your own. Below the ADR tier: no, use the facts in the questions file>
Write to: append to `<absolute run folder>/round-<N>-second.md` under the heading `## <ADR tier, or Below the ADR tier>`

You are deciding nothing and editing nothing outside that file. Reach your
own pick on each question and report it. Read no other file in the run
folder unless this brief names it.

## Read first

Once per thread; a later round on the same thread skips to the questions.

1. `AGENTS.md`, the Standing orders section in particular
2. `CONTEXT.md`, the glossary; use its terms and no others
3. `docs/adr/`: <the ADRs the questions touch, or all of them on a first round>
4. `docs/specs/<slug>.md` as written so far: <the requirements the questions affect>
5. <A new assessor thread only: `<absolute run folder>/decisions.tsv`, the decision column and the reason column, so your picks agree with what is settled>
6. The questions file

## Constraints

- <a decision already made that an option must respect, from an ADR or the spec's Decisions>
- <a limit the owner set: a deadline, a platform, a budget>

## Research

With `Research: no`, skip this section. Work from the facts under each
question. A fact you would need and do not have goes under Not checked; do
not go and find it.

With `Research: yes`, read the code each option would change, and its
callers. Where an option claims a cost or a property, such as speed, size or
compatibility, check it: in a throwaway worktree, in a spike that is deleted
at the end, or in the documentation of the thing in question. Cite what you
read or ran.

```bash
spike_dir="$(mktemp -d)"
git worktree add --detach "$spike_dir" "<head sha or default branch>"
( cd "$spike_dir" && <the spike or measurement> ) > spike.log 2>&1; echo "exit=$?"
git worktree remove --force "$spike_dir"; git worktree prune
```

With nothing to measure, skip the spike and say so.

An option outside the list is allowed when the facts or the research turn
one up. Give it the next letter.

## Verdict

Append to the file, per question:

- `Q<n>: <letter>`, and one sentence why
- What would change the pick, as a fact someone could check
- New dependency: yes or no for the pick
- With `Research: yes`, for each option: what it costs, what it buys, and the evidence, each with a `file:line`, a command and its exit code, or a link
- Not checked, and why

Then reply with one line per question, such as `Q4: B`, and a last line
`Context: <percent of your context used>`. Nothing else goes in the reply.
