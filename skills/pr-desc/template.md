<!--
Never appears in a PR body:
- a test plan section
- chat narrative or session commentary
- security-review commentary
- release-type opinions (that decision belongs to the repo owner)
- agent session links
- model names or any AI identifier

PRs squash-merge, so the PR title becomes the commit on `main`. The title
follows Conventional Commits. Open the PR as a draft unless told otherwise.
Summary is always present. Omit the Trade-offs and Follow-ups sections
entirely when there is nothing to say under them: no empty heading, no `None.`,
no filler. Keep the order below and add no other sections.
-->

## Summary

<What changed and why, in a few bullets or a short paragraph. Write it from the
diff, not from how the work happened.>

- <change> - <why it was needed>
- <change> - <why it was needed>

## Trade-offs

<What was chosen over what, and what it costs. One line per decision.>

- <chosen approach> over <alternative>: <what this buys, what it gives up>
- <constraint accepted>: <the cost it leaves behind>

<Omit this whole section when there were none.>

## Follow-ups

<What was deliberately left out of this PR, and where it should land.>

- <deferred work> - <why it is out of scope here>
- <known gap> - <issue or branch that will pick it up>

<Omit this whole section when there are none.>
