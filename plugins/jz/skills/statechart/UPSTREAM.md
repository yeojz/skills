# Upstream

This skill is vendored from pstack by Lauren Tan, under the MIT licence in
`LICENSE`.

- Source: https://github.com/backnotprop/pstack, a harness-neutral mirror of
  https://github.com/cursor/plugins/tree/main/pstack
- Path: `skills/statechart`
- Commit: `a6342ded43a2437e3c664b46c2cff103787773fd` (2026-11-07)
- Left out: `scripts/test/` (the TLC test suite and its 3.6 MB corpus). Run
  it from an upstream checkout when re-syncing.

## Local edits

Each one is marked `jz edit` in the code, or listed here.

| File | Edit | Why |
|---|---|---|
| `scripts/run.ts` | `findTlc` no longer runs `mise install`; it throws with the install command | Skills never install tools; the user runs the command |
| `scripts/statechart` | Node only; the Bun and Deno fallbacks are gone | The house toolchain is Node with npm or pnpm |
| `references/render.md` | The user installs Pele, not the agent | Same no-install rule |
| `SKILL.md` | Two-key frontmatter with a "Use when" description, a Requirements section, a Common Mistakes table, and a pointer here | The jz skill format in `AUTHORING.md` |
| `evals/evals.json` | Added | The jz skill format |

## Re-syncing

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/backnotprop/pstack.git /tmp/pstack
git -C /tmp/pstack sparse-checkout set skills/statechart
git diff --no-index -- /tmp/pstack/skills/statechart plugins/jz/skills/statechart
```

Carry upstream changes across, keep the local edits above, run the upstream
tests from `/tmp/pstack/skills/statechart/scripts` with `npm test`, and update
the commit line.
