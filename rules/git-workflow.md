# Git and PR workflow

- Check the current branch before the first edit.
- Detect the repo's default branch from `origin` with `git ls-remote --symref origin HEAD`. Never assume it is `main`.
- Create a branch before editing. Never edit on the default branch.
- If you have already edited on the default branch, move the changes onto a new branch before committing.
- Give every task its own branch in its own worktree under `.claude/worktrees/`, so the main checkout stays clean.
- Before creating a worktree, check `git worktree list` and the branch list for one that already belongs to the task, and reuse it.
- Ask, with lettered options, when more than one existing branch or worktree could be the task's.
- Never use a bare `git stash`; the stash is shared across worktrees.

- Name branches `<type>/<scope>-<description>`.
- Write commit subjects as Conventional Commits.
- Write the PR title as a Conventional Commit subject (why: PRs squash-merge into the default branch).
- Keep the commit body to why the change was made, not a list of touched files.

- Limit the PR body to summary, trade-offs and follow-ups.
- Do not add a test plan section.
- Do not paste chat narrative or session transcript.
- Do not add security-review commentary.
- Do not state a release-type opinion; that decision belongs to the repo owner.
- Open PRs as drafts unless told otherwise.

- List the repo owner as the commit author.
- Attribution follows the harness. Never add a co-author trailer yourself.
- Never include an agent session link in a commit message or PR body.

- Never stage `.claude/`, `docs/plans/` or `.plans/`.
- Stage only the files you changed for this task. Never `git add -A` blindly.
- Never pass `--no-verify`.
- Fix what the hook reports instead of bypassing it.

- Ask before running `git push`.
- Ask before running `gh pr create`.
- Never force-push without first stating exactly which commits will be discarded.
- Never rewrite history that is already on a shared branch without asking.
- Do not generate a CHANGELOG or migration guide unless asked.
