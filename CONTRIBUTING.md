# Contributing

Read [AUTHORING.md](AUTHORING.md) first. It defines the skill, rule, agent and
template formats and the house facts every skill assumes.

Before opening a pull request:

```bash
make validate
```

It must pass. CI runs the same target on every push and pull request. The
Makefile also exposes `make test` for the hook suite alone. When the Claude
Code CLI is on `PATH`, `make validate` also runs `claude plugin validate` over
the marketplace and the plugin.

- Name branches `<type>/<scope>-<description>`.
- Write the PR title as a Conventional Commit subject. PRs squash-merge, so the
  title becomes the commit on `main`.
- Open PRs as drafts.
- Never commit plans or `.claude/`. The `.gitignore` covers them, and the
  `no-claude-artifacts.sh` hook blocks staging them from an agent session.
