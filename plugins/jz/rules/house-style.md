# House code style

- Write TypeScript in strict mode.
- Author ESM first; add CommonJS output only when a consumer requires it.
- Never use `any`. Use a precise type, or `unknown` plus narrowing.
- Never use `enum`. Use a string literal union.
- Prefer `type` over `interface`.
- Prefer static imports. Use dynamic import only for real lazy loading.
- Inject dependencies through parameters. Never declare or read global variables.
- Put braces on every `if`, including single-statement bodies.
- Give each function one responsibility.
- Do not add fallbacks, defaults or optional parameters that no caller needs.
- Do not duplicate logic across packages. Extract it once and import it.
- Name things for what they do. Avoid `data`, `info`, `handler`, `utils`.
- Keep comments minimal and explain why, never what.
- Use readable test values. Prefer strings over byte arrays.
- Delete replaced code outright on unpublished packages (why: nothing depends on it yet).
- Keep a deprecated alias only when the package is published and the change is breaking.
- Never call a non-public or internal API of a dependency.

- Prefer adding no new dependency.
- Prefer a package already present in the workspace over a new one.
- Before proposing a dependency, check its maintenance activity and last release date.
- Before proposing a dependency, confirm its license is compatible with MIT and ISC.
- State those findings when you propose it.

- Detect the package manager from the lock file. Never assume one.
- Run the scripts declared in the repo's `package.json`.
- Never invent an ad-hoc command in place of a declared script.
- Read the script before running it, so you pass the flags it expects.

- Never put secrets, tokens or credentials in code, tests or examples.
- Use `example.com` for every domain in examples and fixtures.
