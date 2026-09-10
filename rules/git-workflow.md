# Git and PR workflow

- Check the current branch before the first edit.
- Create a branch before editing. Never edit on `main`.
- If you have already edited on `main`, move the changes onto a new branch before committing.
- Treat `main` as the default branch. Never assume, create or target `master`.
- Do not create a git worktree unless explicitly asked.

- Name branches `<type>/<scope>-<description>`.
- Write commit subjects as Conventional Commits.
- Write the PR title as a Conventional Commit subject (why: PRs squash-merge into main).
- Keep the commit body to why the change was made, not a list of touched files.

- Limit the PR body to summary, trade-offs and follow-ups.
- Do not add a test plan section.
- Do not paste chat narrative or session transcript.
- Do not add security-review commentary.
- Do not state a release-type opinion; that decision belongs to the repo owner.
- Open PRs as drafts unless told otherwise.

- List the repo owner as the commit author.
- Take attribution from settings: honour `includeCoAuthoredBy` and `attribution` in settings.json.
- Add a `Co-Authored-By` trailer only when settings ask for one.
- Never include a Claude session link in a commit message or PR body.

- Never stage `.claude/`, `docs/plans/` or `.plans/`.
- Stage only the files you changed for this task. Never `git add -A` blindly.
- Never pass `--no-verify`.
- Fix what the hook reports instead of bypassing it.

- Ask before running `git push`.
- Ask before running `gh pr create`.
- Never force-push without first stating exactly which commits will be discarded.
- Never rewrite history that is already on a shared branch without asking.
- Do not generate a CHANGELOG or migration guide unless asked.
