# Decisions and waiting

- Present a design fork as lettered options with a recommendation before implementing it when it would earn an ADR: a public API shape, a data model, a new dependency, a specification interpretation, or anything the brief lists as owner-decided.
- Present a naming decision the same way, with the trade-off for each candidate, when the user asked for naming proposals or the name is part of a public surface.
- Below that tier, decide, record the choice and the reason, and report it; an internal helper's name, test layout or the order of two commits never waits.
- Wait for the choice on options you presented rather than implementing the recommendation straight away.
- Keep options to three or four, each meaningfully different.
- Say which option you would pick and why, in one sentence.
- Under a running flow, append each decision to the flow's ledger the moment it is agreed; after a compaction the work continues from the ledgers, not from the conversation.

- Wait for the owner only at: a fork put as lettered options under the rule above, a remote write that asks (ready, a force push not pinned to a sha), an action the brief marks as the owner's, and a pause that a loaded skill's own steps name, such as `implement` stopping after each item or `pr` showing a body before replacing it.
- Everything else proceeds and is reported afterwards. Never stop to ask whether a branch is pushed or a PR is open; run the command that answers it.
- An unmerged dependency is a branch to base on, not a reason to stop: record the branch and its tip, say so in the report, and rebase from that tip once it merges.
