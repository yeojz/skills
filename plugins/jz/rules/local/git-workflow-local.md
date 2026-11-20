# Git workflow on your own machine

- Give every task its own branch in its own worktree under `.claude/worktrees/`, so the main checkout stays clean.
- Before creating a worktree, check `git worktree list` and the branch list for one that already belongs to the task, and reuse it.
- Ask, with lettered options, when more than one existing branch or worktree could be the task's; this counts as a fork under the decision rules.
- Name branches `<type>/<scope>-<description>`.

- Commit, push and open PRs through the `pr` skill, in the mode the request named. These rules summarise it and do not replace it; the `require-pr-skill` guard denies `git commit`, `git push` and `gh pr create` until the skill has been loaded.
- Open a draft PR without asking; it can be withdrawn.
- The `confirm-remote-writes` guard asks the host before marking a PR ready and before a force push not pinned to a sha, so do not ask again in prose.
