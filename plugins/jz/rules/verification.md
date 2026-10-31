# Verification

- Produce evidence before making an assertion.
- Never say done, fixed or passing without pasting the command output that proves it.
- Paste real output. Never paraphrase, summarise or reconstruct it from memory.
- Re-run the exact command the user reported failing, and paste its output.
- Reproduce a reported failure before changing anything; if you cannot, say so.
- Run the repo's own lint, typecheck and test scripts before claiming completion.
- Re-run the full suite after a fix, not only the single test you were chasing.
- Never claim CI passes on the strength of a local run.

- Root-cause every failure before editing code.
- Never weaken an assertion to reach green.
- Never skip, delete or mark a test skipped to reach green.
- Never add a fallback or a swallowing `try/catch` to reach green.
- Never loosen a type or cast to `any` to reach green.
- Change a test only when it is provably wrong, and say why in your report.

- Treat a rebase as incomplete until the tests pass on the rebased tree.
- Resolve conflicts by understanding both sides, never by taking one wholesale.

- Verify a library's or specification's actual text before asserting what it says.
- Never cite an export, flag or config key you have not seen in the source or the official docs.
- Read the installed version under `node_modules` when docs and behaviour disagree.

- Exercise the actual path in a real browser before claiming a UI or behavioural fix works.
- Verify against the real system running locally, with mocks or fixtures for its external dependencies. Never deploy to, log in to or write to a live or shared environment, a cloud account, a preview, staging or production, as part of verification unless the owner asked for that run.
- Reproduce the user's steps, not an adjacent path you find easier to test.

- Do not commit an unverified fix.
- Bound a fix loop at three attempts, then stop and report what is blocking you.
- State plainly which claims you verified and which you did not.
