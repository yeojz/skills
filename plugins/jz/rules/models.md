# Model tiers

- Grilling a plan or spec with the owner: opus; fable when it is cross-cutting or carries several ADR-tier decisions.
- Coordinating a multi-phase program, or a session that starts other sessions: opus.
- Implementing a step under a coordinator: the coordinator's model. A scoped unit with named files and a done condition outside a coordinated program: sonnet, effort medium.
- A large or cross-cutting task: opus.
- Reviewing a change or verifying a branch independently: a model that wrote none of the change, never below sonnet. Prefer another family through Codex where its plugin is present; for a subtle or security-sensitive change, a tier above the author's.
- Scanning files, running a declared script and reporting its output, or a lookup: haiku.
- Pick the tier by the job, never by the model the current session runs on, and name the tier in the brief.
- Raise one tier for a subtle or security-sensitive implementation.
- A fix round after one whose findings came back not fixed runs one tier above the model that wrote the last round, up to fable. When that lands on the reviewer's model, the re-check goes to a fresh reviewer on another model.
- A second opinion on a contested design runs on a different model family, through Codex where its plugin is present.
