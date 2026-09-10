---
name: naming
description: Use when settling what to call something, or when applying an agreed name across a codebase. Triggers on requests like "what should we call", "what should we rename X to", "which name is clearer", "is X or Y more semantic", "would X be more aptly named Y", "rename X to Y everywhere", "standardise the naming", "which would you recommend", or when a name is proposed and the reply needs options with a recommendation.
---

# naming

## Overview

Settles a name in one round instead of five, then applies it completely. Phase 1
produces three or four lettered candidates, each with what it implies and its
drawback, plus one recommendation with a reason. Phase 2 applies the chosen name
across every surface in a single pass and proves the old name is gone.

The two failures this exists to prevent are a proposal that hands back options
with no recommendation, and a rename that lands in source but not in the docs,
the fixtures or the CLI help text.

## Workflow

### Step 1: Identify the phase

| Signal | Phase |
|---|---|
| "what should we call", "which is clearer", "more semantic", a list of options | Phase 1, propose. Steps 2 to 5. |
| "rename X to Y", "standardise to Y", a name already agreed in this thread | Phase 2, rename. Steps 6 to 9. |
| "would X be more aptly named Y" | Phase 1 first. The user is asking, not instructing. |

Never skip Phase 1 because the user supplied a candidate. A supplied candidate is
one entry in the table, not the decision.

### Step 2: Gather the naming context before inventing anything

Run these before writing a single candidate. The answers decide the candidates.

```bash
rg -n --hidden -g '!node_modules' '\bOldName\b' .
rg -n -t ts -g '!node_modules' 'export (type|interface|const|function|class) ' packages/ apps/ internal/
ls packages apps internal 2>/dev/null
```

Four things to establish:

| Question | How to answer it |
|---|---|
| What do sibling packages call this concept? | `rg` the concept word across `packages/`, `apps/`, `internal/` |
| Is there an existing exported public type for it? | grep the `export type` and `export function` lines above |
| Does the spec the project implements name it? | Open the spec text and quote the term and its section |
| Does the codebase use `as` or `with` for conversions? | `rg -n -t ts '\b(as|with)[A-Z]\w+\('` and count which wins |

If the concept has no sibling and no spec term, say so explicitly in the reply
rather than silently inventing. An unprecedented name is a legitimate outcome,
an unstated one is not.

### Step 3: Run every check on each candidate before presenting it

A candidate that fails a check is dropped or repaired, not presented with the
flaw unmentioned.

| Check | What to do | The failure it prevents |
|---|---|---|
| Prefix and suffix collision | Write out the full derived name in every context it will appear, not just the base. Expand generated, prefixed and suffixed forms. | `SAMPLE_` prefixed onto `SAMPLE_API_KEY_RAW_INVALID` giving `SAMPLE_SAMPLE_API_KEY_RAW_INVALID` |
| Meaningful difference | Two candidates built from the same words in a different order are one candidate. Collapse them and say so. | Offering `GoodMorningHello` and `HelloGoodMorning` as a choice |
| Sibling consistency | Prefer the term a sibling package or an existing exported type already uses over a new coinage. | Three names for one concept across the workspace |
| Specificity | Reject a name that describes the generic mechanism when a name describing the purpose exists. | `truncate` where `clampToDigits` is available |
| Domain and spec precedent | Where the spec the project implements names the concept, quote the spec's own term and cite the section. | Paraphrasing a term the spec already fixed |
| Grammatical form | Apply the convention for the kind of thing being named. See the table in Step 4. | A function named as a noun, a boolean without `is` or `has` |

Rules that bound this step:

- Expand the derived name literally. Write `SAMPLE_` + `API_KEY_BASE64` =
  `SAMPLE_API_KEY_BASE64`, then do the same for every sibling constant in the
  same group, including the ones that already carry a qualifier.
- Quote the spec from the actual spec text. Open it and read it. Never assert a
  section number or a term from memory. If the text is not to hand, say the
  precedent is unverified rather than stating it.
- If collapsing word-order variants leaves fewer than three candidates, generate
  a genuinely different one rather than padding the list.

### Step 4: Apply the grammatical form convention

| Kind of thing | Form | Example shape |
|---|---|---|
| Function or method | Verb phrase | `generateToken`, `resolveConfig` |
| Type, interface alias, value, constant | Noun phrase | `TokenResult`, `RetryPolicy` |
| Boolean value, field or return | `is` or `has` prefix | `isExpired`, `hasSecret` |
| Conversion helper | Whichever of `as` or `with` the codebase already uses, from Step 2 | `asHex` or `withHex`, not both |
| React style hook | `use` prefix, and only for a hook | `useGuardrail` |
| Package or CLI command | Kebab case noun phrase naming the outcome | `schema-sync-pr` |
| Test fixture constant | SCREAMING_SNAKE, qualifier first, no repeated qualifier | `SAMPLE_API_KEY_RAW` |

State the applicable row in the reply. `useX` is not a free choice against
`setX` or `createX`: `use` claims hook semantics, `set` claims a mutation, and
`create` claims a constructor. Say which the code actually does.

### Step 5: Present lettered candidates and one recommendation

Exactly this shape, three or four rows:

```markdown
| | Name | What it implies to a reader who has not seen the code | Main drawback |
|---|---|---|---|
| A | <name> | <one line> | <one line> |
| B | <name> | <one line> | <one line> |
| C | <name> | <one line> | <one line> |

**Recommendation: B.** <one or two sentences of reason, citing the check or the
sibling or the spec term that decides it.>
```

Rules for the block:

- The recommendation is never omitted. A table of options with no recommendation
  only invites the question "which would you recommend?", so answer it unasked.
- Exactly one recommendation. Not "B or C depending on taste".
- The reason cites something checkable: a sibling name, a spec term, a
  collision, a grammatical rule. Not "reads better".
- If a candidate was collapsed under the meaningful-difference check, add a line
  under the table naming the pair and saying they are the same candidate.
- If the user's own suggestion is not the recommendation, it still appears as a
  lettered row with its drawback stated.

Stop after presenting. Do not begin renaming until the user picks. Applying a
name that was only proposed is the same error as presenting options with no
recommendation, in the other direction.

### Step 6: Enumerate the surfaces before touching any of them

Once a name is chosen, list every surface, then edit them in one pass. A rename
is a single change, not a series of follow-ups.

| Surface | How to find it |
|---|---|
| Source | `rg -n --hidden -g '!node_modules' '\bOldName\b' packages apps internal` |
| Tests | same search, `*.test.ts`, `*.spec.ts` |
| Test fixture names and fixture values | `rg -n 'OLD_NAME' -g '*fixture*' -g '*.test.ts'` |
| Type names and their exported aliases | `rg -n 'export (type\|interface) .*OldName'` |
| Doc comments and JSDoc | `rg -n -B2 'OldName' -g '*.ts' \| rg '\*'` |
| READMEs | `rg -n 'OldName' -g '*.md'` |
| Docs site guide, VitePress | `rg -n 'OldName' docs/` |
| CLI help text, usage strings, command registration | `rg -n 'OldName' -g '*.ts' -g '*.txt' -g '*.json'` |
| Changeset or release notes | `rg -n 'OldName' .changeset/ CHANGELOG.md 2>/dev/null` |
| File names, where the codebase names files after their export | `fd -H 'old-name'` or `rg --files \| rg 'old-name'` |

If a surface does not exist in this repo, write "none" for that row rather than
dropping the row. A missing row reads as a forgotten surface.

Rename files with `git mv` so history follows:

```bash
git mv packages/core/src/old-name.ts packages/core/src/new-name.ts
```

Update the import specifiers and any barrel `index.ts` in the same pass.

### Step 7: Prove the old name is gone

```bash
rg -n --hidden -g '!node_modules' -g '!.git' '\bOldName\b' . || echo "no occurrences"
rg -n --hidden -g '!node_modules' -g '!.git' 'OLD_NAME' . || echo "no occurrences"
```

Paste the output. For every remaining occurrence, give a reason for keeping it,
in a table:

| Path and line | Why it stays |
|---|---|
| `CHANGELOG.md:88` | Historical entry describing the released name |

An occurrence with no reason is a miss, not an exception. Go back to Step 6.

Case variants are separate searches. Search the camelCase, PascalCase,
kebab-case and SCREAMING_SNAKE forms of the old name, because a rename that
misses `old-name` in a file path while fixing `oldName` in source still ships
broken imports.

### Step 8: Decide on the alias and the semver bump

| Package state | Deprecated alias | Release |
|---|---|---|
| Unpublished, or private in the workspace | None. Delete the old name outright. | No bump needed beyond the normal changeset |
| Published, name is exported publicly | Only if the user asks for one | Breaking change, major bump, state this in the changeset |
| Published, name is internal and not exported | None | Patch or minor, per the surrounding change |

Never leave a re-export or a `const oldName = newName` behind on unpublished
code "just in case". That is the house rule, and it turns one rename into two
names that both work.

Do not choose the release type unilaterally on a published package. State that
the rename is breaking and let the repo owner decide the bump.

### Step 9: Call verify

Call the `verify` skill and paste its report block. A rename touches imports,
type exports and docs builds, so typecheck and build are the checks that catch a
half-applied rename. The rename is not done until that block is present with no
`fail` row.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Presenting options with no recommendation | Every candidate table ends with exactly one **Recommendation:** line and a checkable reason |
| Two candidates that differ only in word order | Collapse them into one candidate, say so under the table, and generate a genuinely different third |
| A derived name that stutters, `SAMPLE_SAMPLE_...` | Expand the full derived name in every context before presenting; strip the qualifier the base already carries |
| Renaming source but not the docs site or the CLI help text | Walk the whole Step 6 surface table and write "none" for surfaces that do not exist |
| Leaving a deprecated alias on unpublished code | Delete the old name outright. Aliases are only for a published, exported, breaking rename the user asked to soften |
| Choosing a generic mechanism word like `truncate` | Name the purpose, not the mechanism, when a purpose word is available |
| Inventing a term the spec already fixes | Open the spec text, quote the term and cite the section; never quote from memory |
| Coining a new word where a sibling package already has one | Search `packages/`, `apps/` and `internal/` first and match the existing term |
| Renaming a file without `git mv` | Use `git mv`, then update imports and the barrel export in the same pass |
| Searching only the camelCase form of the old name | Search the camelCase, PascalCase, kebab-case and SCREAMING_SNAKE forms separately |
| Starting the rename off a name that was only proposed | Stop after Step 5 and wait for the user to pick a letter |
| Declaring the rename complete without running anything | Call `verify` and paste its report block |
