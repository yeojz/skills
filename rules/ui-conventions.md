# UI conventions

- Take icons from an icon library. Never hand-write an inline SVG icon.
- Use `react-icons/lu` for interface icons.
- Use `react-icons/si` for brand and product logos.
- Build interactive components on Radix primitives.
- Do not pull in a themed component kit for styling defaults.

- Express type sizes in `rem`, anchored on the browser default.
- Keep UI text at 16px or larger.

- Avoid the default indigo and violet palettes.
- Avoid a uniform grid of identical cards.

- Follow the agreed design document.

- Check mobile widths before calling a layout done.
- Check for horizontal overflow at the narrowest supported width.
- Check contrast in light mode and in dark mode.
- Check focus states and keyboard traversal on every interactive element.

- Write labels, empty states and errors in vocabulary a non-technical reader understands when the product targets one.
- Say what happened and what to do next in an error message.
