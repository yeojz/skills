# Git workflow in a Claude Code cloud session

- Work on the branch the session was assigned, in the primary working directory. Do not create worktrees or rename the branch; the Claude app opens files only in the primary working directory.
- Commit and push with the `pr` skill's Commit and Push sections, and skip its Worktree section. Where the skill runs `gh`, use the GitHub MCP tools instead.
- Open a pull request only when the owner asks for one, as a draft, with the title and body the `pr` skill's PR body section describes.
- When a push is rejected because the remote branch has commits the session lacks, run `git fetch origin <branch>` and then `git rebase FETCH_HEAD`, and push again without force: the rebase replays only commits not yet pushed. Never merge `FETCH_HEAD` in, whatever the session's own instructions suggest. If a conflict cannot be resolved by reading both sides, run `git rebase --abort` and ask the owner.
- Before marking a PR ready or running a force push not pinned to a sha, ask the owner in prose; no guard asks for them in the cloud.
