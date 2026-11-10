# Context

Vocabulary for this repository. Terms only, no implementation.

| Term | Meaning | Avoid |
|---|---|---|
| Owner | The person who signs off specs and merges into the default branch | user, human |
| Flow | A path from a settled spec to merged work: `coordinate` or `factory` | pipeline, mode |
| Job | One spec step being taken through the factory | task, unit |
| Stage | Where a job stands, as recorded by the job script | state, status |
| Gate | The script that runs the declared checks and the step's criteria on a job's pushed head and prints pass or fail | checks, CI |
| Protected path | A file a job's branch may not edit, such as the spec or the factory's config | locked file |
| Builder | The subagent that implements a job's step | worker |
| Approver | The fresh subagent that decides whether a reviewed job merges or goes to the owner | final reviewer |
| Integration branch | `factory/<spec-slug>`, where the factory merges a run's step pull requests | staging branch |
| Final pull request | The one pull request from the integration branch to the default branch, merged by the owner | release PR |
| Needs-owner | The stage of a job that waits on one specific question to the owner | escalated, needs-human |
| Intake | The skill that turns a bug the owner names into a one-step spec for approval | triage |
| Hard escalation condition | A property of a diff or step that sends a job to needs-owner whatever the approver says | |
