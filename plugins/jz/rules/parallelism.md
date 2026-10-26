# Parallelism and decisions

- Fan independent work out to subagents by default, without being asked.
- Treat two tasks as independent when they touch different files and neither's output feeds the other.
- Launch independent subagents in a single batch so they run concurrently.
- Never launch independent subagents one at a time.
- Split a large task by file or package boundary so the parts stay independent.

- Give each subagent absolute paths, the acceptance criteria, and the house rules it needs.
- Give each subagent enough context to work without the parent conversation.
- Tell each subagent to report findings back rather than write a summary file.
- Name the files each subagent owns, so two of them never edit the same file.

- Do not fan out work that shares a file.
- Do not fan out work that shares a branch, commit or other git operation.
- Do not fan out work that shares a build artifact or output directory.
- Do not fan out a task whose input is another task's output.
- Do not fan out work that needs a shared dev server, database or port.
- Run dependent steps in order in the main session.

- Verify the combined result yourself after subagents return.
- Re-run lint, typecheck and tests once over the merged result, not per subagent.
- Report what was fanned out, what had to run in order, and why.

- Present design decisions as lettered options with a recommendation before implementing.
- Present naming decisions the same way, with the trade-off for each candidate.
- Wait for the choice rather than implementing the recommendation straight away.
- Keep options to three or four, each meaningfully different.
- Say which option you would pick and why, in one sentence.
