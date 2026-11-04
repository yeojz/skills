# Model tiers

- Tiers, strongest first: top, strong, standard, light. Name the tier and the host's model for it in every brief.
- On Claude: top is fable, strong is opus, standard is sonnet at effort medium, light is haiku.
- On Codex: top is the strongest model offered at its highest reasoning effort, strong is the default model at high effort, standard is the default model at medium effort, light is the smallest model offered at low effort.
- The other family is Codex from a Claude session and Claude Code from a Codex session, where its plugin or CLI is present.

- Grilling a plan or spec with the owner: strong; top when it is cross-cutting or carries several ADR-tier decisions.
- Coordinating a multi-phase program, or a session that starts other sessions: strong.
- Implementing a step under a coordinator: the coordinator's tier. A scoped unit with named files and a done condition outside a coordinated program: standard.
- A large or cross-cutting task: strong.
- Reviewing a change or verifying a branch independently: the other family where present; otherwise a fresh session on strong, or top for a subtle or security-sensitive change, one that needed an escalated fix round, or one that touches an ADR-tier decision. Never the author's session.
- Scanning files, running a declared script and reporting its output, or a lookup: light.
- Pick the tier by the job, never by the model the current session runs on.
- Raise one tier for a subtle or security-sensitive implementation.
- A fix round after one whose findings came back not fixed runs one tier above the last round's, up to top.
- A second opinion on a contested design runs on the family the first reviewer did not.
