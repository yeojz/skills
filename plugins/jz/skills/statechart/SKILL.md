---
name: statechart
description: Use when a system that moves between states, such as a checkout flow, a protocol, a job queue, a retry loop or a UI with modes, needs its behaviour checked against rules or drawn as a statechart, or a bug shown as a path through states. Triggers on requests like "/statechart", "model this flow", "draw the state machine", "can this ever double charge", "is there a state we cannot get out of", "show me how this bug happens step by step", "check the protocol for deadlocks", or when a race or ordering bug is hard to explain in prose.
---

# statechart

## Overview

Models a system as a small TypeScript state machine, checks every reachable
state against rules the reader agrees to, and draws a Mermaid statechart in
the reader's words. The report gives the shortest path to each broken rule.
The checker is `statechart.ts` beside this file: plain TypeScript with no
dependencies, run by Node 22.18+, Bun or Deno. No Java and no TLC.

Requirements: Node 22.18 or later, Bun 1.1.5 or later, or Deno 2.0 or later
on `PATH`. The skill installs nothing. When none is found, stop and give the
user the command to run themselves, such as `mise use -g node@22`.

The reader is the person who decides whether the behaviour is right. The
chart and the rules are written for them, not for the code.

## Workflow

### Step 1: Agree the rules with the reader

Before writing the model, list the rules in the reader's words: "you are
charged at most once", "a paid order always has a receipt", "you can always
get back to the start". Ask the reader to confirm or correct them. A rule is
the thing the chart proves or breaks, so never weaken one to make it hold.

### Step 2: Write the model

Work in a scratch folder outside the repository. One `.ts` module holds the
model and the view. Use erasable TypeScript only (types, no `enum` or
`namespace`), since Node strips types without compiling. A complete example:

```ts
type S = { phase: "cart" | "paying" | "paid" | "failed"; charged: number; retried: boolean };

export const title = "Checkout";
export const init: S = { phase: "cart", charged: 0, retried: false };

export const actions = {
  Pay: (s: S) => (s.phase === "cart" ? { ...s, phase: "paying" } : null),
  BankOk: (s: S) => (s.phase === "paying" ? { ...s, phase: "paid", charged: s.charged + 1 } : null),
  Timeout: (s: S) => (s.phase === "paying" && !s.retried ? { ...s, charged: s.charged + 1, retried: true } : null),
  BankDeclines: (s: S) => (s.phase === "paying" ? { ...s, phase: "failed" } : null),
  Retry: (s: S) => (s.phase === "failed" ? { ...s, phase: "cart" } : null),
};

export const invariants = { "You are charged at most once": (s: S) => s.charged <= 1 };
export const canReach = { "You can always still finish paying": (s: S) => s.phase === "paid" };
export const final = (s: S) => s.phase === "paid";

export const state = (s: S) =>
  s.phase === "paying" ? (s.retried ? "Paying, retried" : "Paying") : { cart: "In cart", paid: "Paid", failed: "Payment failed" }[s.phase];
export const step = (a: string) =>
  ({ Pay: "you press pay", BankOk: "the bank approves", Timeout: "the bank times out",
     BankDeclines: "the bank declines", Retry: "you try again" })[a] ?? a;
```

| Export | Required | Meaning |
|---|---|---|
| `init` | yes | A start state (a plain object), an array of them, or a function returning either |
| `actions` | yes | Name to `(s) => next`; return a state, an array of states (a choice), or `null` when the action cannot happen |
| `invariants` | no | Reader's sentence to `(s) => boolean`, true in every reachable state |
| `canReach` | no | Reader's sentence to a goal predicate; from every reachable state a goal must still be reachable |
| `final` | no | True in correct end states, so they do not count as dead ends |
| `constraint` | no | States where it is false are checked against invariants but not explored or checked for dead ends; the report counts them, and a `canReach` rule whose goal is reachable only through them reads NOT CHECKED |
| `state` | no | The chart label for a state: a non-empty string, an array of them for parent states, or an object of them for parallel regions; one shape for every state, or the run stops |
| `step` | no | `(action, from, to) => label` for the arrow, or `null` to hide that step |
| `group`, `colors` | no | Phase name per state, and phase name to Mermaid style such as `fill:#d1e7dd,stroke:#0f5132` |
| `title` | no | Chart title |

Model rules:

- Keep only the data a rule or a label needs. Every extra field multiplies the states.
- A state is a plain object of plain data: objects, arrays, strings, finite numbers, booleans, `null`, Sets and Maps. A `Date`, `NaN`, a bigint, a class instance or a top-level array stops the run.
- Keep counters and queues bounded. Prefer a cap in the action guard: past a `constraint` nothing is searched, so a stuck loop there can hide.
- Actions get a copy of the state, so mutating it is harmless, but return a new object.
- Make every function depend only on its arguments. The checker calls each once per state or step.
- A state with no step out breaks the built-in dead-end rule unless `final` covers it. A step back to the same state does not count as a way out.
- `canReach` says a goal is still possible, not that it will happen; there is no fairness.

### Step 3: Run the checker

Node runs the model without checking its types, so type-check it first when a
checker is on `PATH`, and fix every error:

```bash
deno check model.ts
<skill dir>/statechart model.ts --out out-1
```

With no `deno`, use `tsc --noEmit --strict model.ts` if `tsc` is installed;
otherwise skip the type-check. The checker also reports any field a hook
reads that no reachable state has, which catches most misspellings.

`<skill dir>` is the directory holding this SKILL.md. Flags: `--max-states N`
stops the search (default 100000), `--budget N` is the chart limit (default
500 chart states, after `state()` merges them). Exit codes: 0 every rule
holds, 1 a rule breaks (even when the search is incomplete), 2 the report has
`## Model warnings`, no rule broke but something was not checked, or the model
or a flag is invalid. The run replaces `report.md` and `chart.mmd` in the
`--out` folder and prints the report.

An action or rule that throws stops the run with the state it threw on. Fix the
model and run again, at most three times; then show the reader the error and
the model rather than guessing further.

### Step 4: Read the report

- `BREAKS (path N)` names a broken rule; `## Path N` lists each step with the arrow label, the chart label and the raw state values. Paths are shortest first.
- In the chart, class `breaks` means every model state behind that chart state breaks a rule, `mayBreak` means only some do. The Legend says which state breaks which rule.
- `## Model warnings` lists actions that never fired and fields read that no state has. Either means the model is wrong; fix it before trusting any result.
- `NOT CHECKED (reason)` or `holds in the states searched` means part of the graph was not searched: the search hit `--max-states`, or a goal lies only past `constraint`. Shrink constants or move the cap into the action guards; the result is not a proof.
- Past `--budget` chart states the chart draws only the bug paths, and its `[when X]` conditions come from those paths alone. With no bug and no chart, coarsen `state()` or raise `--budget`.
- The checker explores past a broken state, so the chart shows what happens after a bug too.

### Step 5: Shape the chart

Aim for about 20 arrows. In order:

1. Coarsen `state()`: one label for values that act the same; drop detail the reader does not need.
2. Never merge two states that break different rules, and keep every state on a bug path. The report warns when a bug path step stays inside one label or is hidden; split that label or unhide the step.
3. Only then hide steps with `step()` returning `null`, such as a reset every state has. Hide all steps of an arrow or none, keep every chart state reachable from a start state, and keep one arrow out of every state that has a step out. On flat and parent charts `## Chart warnings` reports breaches of the last two; on a regions chart check them by eye.

Label states with what the reader sees ("Paying, retried"), never variable
names. Label arrows as the reader sees them happen ("the bank times out"),
never the action name. Two actions that look the same to the reader get the
same label and share an arrow. When a step only happens under a condition no
label shows, end the label with it in brackets: `you press play [while it loads]`.
In a regions chart the checker adds `[when X]` for conditions on other regions
itself, so do not write those. A label that already ends in `]` gets no
`[when X]`, so write the whole condition yourself there. The checker reads each
other region on its own, so a condition on two regions at once shows looser
than it is; when that matters, say the real condition in the hand-off.

Rerun with a new `--out` folder after each change.

### Step 6: Hand off

Show `chart.mmd` as a `mermaid` code block. Then give:

- One line per broken rule: the rule's sentence, and its path as the report numbers it.
- What the model leaves out (timeouts, other users, persistence, whatever was simplified).
- Which steps the chart hides, from `## Steps hidden from the chart`.
- The command that regenerates it, with a new `--out` folder.

When the model describes real code, replay each bug path against that code,
as a test or a live repro, one step per action. If the bug does not happen,
assume the model is wrong until shown otherwise, and say so.

## Limits

| Not covered | Instead |
|---|---|
| Temporal properties beyond "a goal is still reachable", such as "eventually" under fairness | Say the check is missing in the hand-off; TLA+ with TLC covers it but needs Java |
| Large state spaces (millions of states) | Shrink the model; this checker is breadth-first in memory, about 60k states a second |
| Symmetry reduction | Model one representative process, or canonicalise the state in the actions |

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing rules after the model, then fitting them to what holds | Agree the rules with the reader first, in their words |
| Labels that leak variable names, such as `phase=paying` | Use what the reader sees: "Paying" |
| Trusting "holds" while an action never fired | A dead guard hides behaviour; fix it and rerun |
| Unbounded counters, so the run stops at `--max-states` | Cap in the guard or add `constraint` |
| A correct end state reported as a dead end | Export `final` for it |
| Hiding a step on a bug path to cut arrows | Keep every bug path state and step visible |
| Claiming the code has the bug from the model alone | Replay the path against the real code first |
| Writing `[when ...]` on a regions chart | The checker adds conditions on other regions itself |
