---
name: design-critique
description: Use when a UI needs judging, redesigning or fixing visually, and after every visual change before reporting it. Triggers on requests like "this looks AI generated", "the design is ugly", "redesign this", "improve the contrast", "it is not aligned on mobile", "horizontal scroll on mobile", "critique this UI", "looks very plain", "the fonts look small", or when a visual fix is about to be called done.
---

# design-critique

## Overview

The frontend iteration loop. It runs a fixed checklist over a real running page
instead of offering an impression, holds every proposal against the design
document already agreed, and proves a visual fix by loading the page in a
browser and measuring rather than by looking at it.

Three modes, used in this order when they all apply:

| Mode | When | Output |
|---|---|---|
| 1 Critique | "this looks AI generated", "looks plain", "critique this" | Findings list against the checklist, then lettered directions |
| 2 Design-doc iteration | A design document exists for this surface | Each proposal marked aligned or deviation, before building |
| 3 Verify | After every visual change, always | Measured evidence block from a loaded page |

Mode 3 is not optional and is not skipped because the change looks obviously
correct. `rules/ui-conventions.md` holds the standing constraints; this skill is
how they get checked.

## Workflow

### Step 1: Get the page running and loaded

Never critique from source alone. Find the dev command from the repo's scripts,
start it, and load the actual URL.

```bash
cat package.json | jq -r '.scripts | to_entries[] | "\(.key)\t\(.value)"'
```

Start it with the browser tooling rather than a bare shell, so the preview stays
attached:

- `mcp__Claude_Browser__preview_start` with a `.claude/launch.json` entry, or
  with `url` when the server already runs.
- `mcp__Claude_Browser__navigate` to the exact route under discussion.

If no dev server exists and the surface is a static file, load the file URL. If
the page cannot be loaded at all, say so and stop; do not substitute a reading
of the JSX for a critique.

### Step 2: Mode 1, critique against the fixed checklist

Walk every row. Each row gets a verdict of `pass`, `finding` or `n/a`, and every
`finding` names the file and the selector or component it lives in. A vague
impression such as "feels generic" is not a finding.

**Generic AI aesthetic tells**

| Tell | What to look for |
|---|---|
| Thick coloured accent border | Selected card or tab marked by a 3px+ accent border, especially `border-r` |
| Default palette | Indigo, violet or teal, including a gradient between two of them |
| Uniform card grid | Every item the same box, same weight, same size, no hierarchy |
| Full-viewport sections | `100vh`, `min-h-screen`, `h-dvh` on stacked sections |
| Block-by-block reveal | Scroll-triggered fade or slide applied per section, so it "appears block by block" |
| Centred hero, two-button row | Centred headline, sub, and a primary plus ghost button side by side |
| Emoji as iconography | Emoji standing in for an icon in UI chrome |
| Inline hand-drawn SVG | A literal `<svg><path d=...>` where the icon library already has it |

Grep for the mechanical ones rather than eyeballing:

```bash
rg -n "min-h-screen|100vh|h-dvh" src/
rg -n "indigo|violet|teal" src/
rg -n "<svg" src/ --glob '!*icon*'
rg -n "border-(r|l|t|b)-[48]|border-[48]" src/
```

**Hierarchy.** Is it obvious what the user is meant to do first on this screen.
Name the single primary action. A settings surface with no primary action, or a
screen where three controls carry equal visual weight, is a finding. When a
viewer cannot tell what to do first on a screen, the underlying defect is a
missing primary action, not a styling preference.

**Type.** Sizes anchored on `rem`, never a base below the browser default. UI
text at 16px or larger. A limited scale, roughly five to seven steps, not a
dozen arbitrary values. Read the real computed values in Step 4, since a `text-sm`
under a shrunk root is smaller than it looks in the source.

**Spacing.** One consistent rhythm from a spacing scale, not ad-hoc pixel values.
Enough separation between a row and its background: if a row's background and the
page background differ by a barely perceptible amount and no border or shadow
separates them, that is a row-separation finding, and the row does not read as
distinct from the surface behind it.

**Contrast.** Measured in Step 4, in both light and dark. Never judged by eye.

**Responsive.** Measured in Step 4 at a mobile width. No horizontal overflow,
nothing clipped.

**Icons.** From `react-icons/lu` for interface icons and `react-icons/si` for
brand marks. Any inline SVG icon is a finding with a named replacement.

### Step 3: Mode 2, hold every proposal against the design document

Before proposing or building anything, find the document.

```bash
ls docs/plans/*design*.md docs/design/*.md 2>/dev/null
rg -l "design|redesign" docs/ --glob '*.md'
```

If one exists, read it in full and produce this table before writing code:

| Proposal | Design doc says | Verdict |
|---|---|---|
| Sidebar collapses to icon rail | Sidebar stays fixed at 240px | deviation |
| Neutral warm palette | Neutral warm palette | aligned |

Rules:

- Every deviation is stated and its reason given **before** it is implemented,
  never discovered afterwards.
- A deviation needs an explicit yes. Do not fold it into a larger change.
- The named failure is producing something unrelated to what was agreed. If the
  build has already drifted, list the drifted items against the document and
  offer to bring them back, rather than defending the drift.

If no design document exists, say so once, and treat the critique findings as
the reference for the rest of the session.

### Step 4: Mode 3, verify in a real browser by measuring

Run this every time a visual change is made, before reporting anything. Claiming
a visual fix works without loading the page is forbidden.

**Widths.** Check both.

```
mcp__Claude_Browser__resize_window  preset: mobile   (375x812)
mcp__Claude_Browser__resize_window  preset: desktop
```

**Horizontal overflow, measured not looked at.** Compare document scroll width
to viewport width, then name the offending element:

```js
// mcp__Claude_Browser__javascript_tool
(() => {
  const vw = document.documentElement.clientWidth;
  const overflow = document.documentElement.scrollWidth > vw;
  const culprits = [...document.querySelectorAll('*')]
    .map((el) => ({ el, r: el.getBoundingClientRect() }))
    .filter(({ r }) => r.right > vw + 1 || r.left < -1)
    .slice(0, 10)
    .map(({ el, r }) => ({
      tag: el.tagName,
      cls: el.className?.toString().slice(0, 80),
      left: Math.round(r.left),
      right: Math.round(r.right),
    }));
  return { vw, scrollWidth: document.documentElement.scrollWidth, overflow, culprits };
})();
```

A report of "no horizontal scroll" without these numbers is not evidence.

**Clipping.** An element whose `scrollWidth` exceeds its `clientWidth` with a
`text-overflow` or `overflow: hidden` is clipped. That measurement is what a
report of truncated or cut-off text resolves to:

```js
[...document.querySelectorAll('h1,h2,h3,button,[class*=title]')]
  .filter((el) => el.scrollWidth > el.clientWidth + 1)
  .map((el) => ({ tag: el.tagName, text: el.textContent.trim().slice(0, 40) }));
```

**Contrast, computed.** Read the real resolved colours and compute the ratio.
Do this in light and in dark; use `resize_window` with `colorScheme` to switch,
or toggle the app's own theme control.

```js
(() => {
  const lum = (c) => {
    const [r, g, b] = c.match(/[\d.]+/g).slice(0, 3).map(Number)
      .map((v) => (v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const bgOf = (el) => {
    for (let n = el; n; n = n.parentElement) {
      const bg = getComputedStyle(n).backgroundColor;
      if (bg && !/rgba\(0, 0, 0, 0\)|transparent/.test(bg)) return bg;
    }
    return 'rgb(255, 255, 255)';
  };
  return [...document.querySelectorAll('p,span,a,button,label,h1,h2,h3,td,th')]
    .filter((el) => el.textContent.trim())
    .slice(0, 40)
    .map((el) => {
      const s = getComputedStyle(el);
      const fg = s.color, bg = bgOf(el);
      const [l1, l2] = [lum(fg), lum(bg)].sort((a, b) => b - a);
      const ratio = +((l1 + 0.05) / (l2 + 0.05)).toFixed(2);
      const px = parseFloat(s.fontSize);
      const large = px >= 24 || (px >= 18.66 && +s.fontWeight >= 700);
      return { text: el.textContent.trim().slice(0, 30), fg, bg, px, ratio, pass: ratio >= (large ? 3 : 4.5) };
    })
    .filter((r) => !r.pass);
})();
```

Report the failing pairs with their measured ratios. AA is 4.5:1 for body text
and 3:1 for large text.

**Type scale, computed.** Catch UI text below 16px and a scale that sprawled:

```js
[...new Set([...document.querySelectorAll('*')]
  .filter((el) => el.children.length === 0 && el.textContent.trim())
  .map((el) => parseFloat(getComputedStyle(el).fontSize)))].sort((a, b) => a - b);
```

**Interaction.** Actually drive it. A toggle must be observed toggling, a
dialog observed opening and closing, a menu observed closing on Escape and on
outside click. Use `computer` clicks plus `read_page`, and check focus lands
where it should.

**Console.** Read it and report errors:

```
mcp__Claude_Browser__read_console_messages  onlyErrors: true
```

**Cross-browser.** When the report names Safari, Chrome or Firefox
specifically, the fix is not verified until it is exercised in the named
browser. If only one engine is available, say which one was tested and which
were not, rather than implying all three.

**The reproduction path.** Exercise the exact steps the user reported, at the
width they reported, not an adjacent path that is easier to reach. A blink, a
jitter or a flash of unstyled content is verified by reproducing the trigger,
not by reasoning that the cause was removed.

Then emit this block:

```markdown
## Visual verification

URL: http://localhost:5173/settings
Widths: 375x812, 1440x900

| Check | Measured | Result |
|---|---|---|
| Horizontal overflow @375 | scrollWidth 375, clientWidth 375 | pass |
| Clipped text @375 | none | pass |
| Contrast, light | worst 4.62:1 on muted label | pass |
| Contrast, dark | worst 3.10:1 on muted label | fail |
| Min UI font size | 16px | pass |
| Interaction | dialog opens, Escape closes, focus returns | pass |
| Console errors | 0 | pass |
| Browsers | Chromium only; Safari and Firefox not tested | partial |
```

The words fixed, done and working may not appear before this block exists, and
not at all while a row says `fail`.

### Step 5: Bound iteration on a single visual bug at 3 attempts

Count out loud: attempt 1 of 3, attempt 2 of 3, attempt 3 of 3. One attempt is
one hypothesis, one change, one verified reload with measurements.

After the third failed attempt, stop editing and report:

- The hypothesis of each attempt and what the measurement ruled out.
- What was actually observed each time, from Step 4, not what was expected.
- The exact reproduction path still failing.

Then present the options, with reverting as a real one:

```markdown
Three attempts, still reproducing. Options:

A. Revert to the state before attempt 1. The original behaviour returns, the
   bug returns with it, and nothing else has shifted.  (recommended)
B. Keep attempt 3 and box the problem: <named narrower change>.
C. Change approach entirely: <named different mechanism>.
```

Reverting is a legitimate outcome, not a failure. The original behaviour with a
known jitter is often worth more than three speculative fixes stacked on top of
each other. Offer it plainly, and give the exact command:

```bash
git diff HEAD -- <paths>
git restore --source=HEAD -- <paths>
```

Do not begin a fourth attempt on the same bug unless the user picks B or C, or
supplies new information.

### Step 6: Offer directions before redesigning

Any redesign, palette change or layout rework is proposed as two or three
lettered directions with a recommendation, before implementation:

```markdown
A. Editorial. Asymmetric layout, one serif display face, generous whitespace,
   warm neutral ground, accent used once per screen.  (recommended: reads as
   deliberate and is furthest from the default look)
B. Dense enterprise. Compact rows, 13px-equivalent metadata at 16px minimum,
   strong table hierarchy, restrained slate palette, tuned for scanning.
C. Keep the structure, replace the surface. Same layout, new palette and type
   scale only. Cheapest, but keeps the uniform-grid rhythm.
```

Each direction names its palette, its type pairing and its layout rhythm. "A
better design" or "enterprise grade" is not a direction until those three are
named. Wait for the pick. Then apply Step 3, then Step 4.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Claiming a visual fix works without loading the page | Load the URL in the browser tooling, measure, paste the verification block |
| Judging contrast by eye or from the source colour tokens | Read `getComputedStyle` colours and compute the ratio, in light and in dark |
| Reporting "no horizontal scroll" from a screenshot | Compare `documentElement.scrollWidth` against `clientWidth` at 375px and name the culprit element |
| Stacking a fourth attempt on a failing visual bug | Stop at 3, report each observation, offer the revert as option A |
| Treating a revert as a failure | Present it as a legitimate outcome with the exact `git restore` command |
| Drifting from the agreed design document | Read the document first, table every proposal as aligned or deviation, raise deviations before building |
| Hand-writing an inline SVG icon | Take it from `react-icons/lu`, or `react-icons/si` for brand marks |
| Answering "looks AI generated" with a palette swap alone | Walk the whole tells table: borders, grid rhythm, 100vh, reveals, hero shape, icons |
| Offering "a better design" and implementing straight away | Two or three lettered directions naming palette, type and rhythm, with a recommendation |
| Verifying at desktop width only | Check 375px and desktop; a mobile complaint is verified at mobile |
| Saying it works in Safari after testing Chromium | Name which engine was tested and which were not |
| Reasoning that a blink is gone because the cause was removed | Re-run the exact reproduction steps and report what was observed |
| Calling a settings screen fine because it renders | Name its primary action; no primary action is a finding |
| Leaving a finding as "feels generic" | Name the file, the component and the specific tell |
