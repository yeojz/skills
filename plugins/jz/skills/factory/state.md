# Factory run state

Reference for anything that follows a factory run from outside: a desktop
app, a status bar, a script. It describes the files the `job` script writes,
the stages a job moves through, and how to watch for a change. The `factory`
skill does not need this file to run.

## Where the state lives

In the target repository, never committed:

```
docs/plans/factory-<spec-slug>/
  run.json                          one per run
  jobs/<job>/job.json               one per job; <job> is "<two-digit step>-<step title slug>"
  jobs/<job>/build.md               written by the builder
  jobs/<job>/round-<N>/checks.md    written by the gate; checks.log beside it
  jobs/<job>/round-<N>/merge-checks.md   the gate run again before a merge or merge-ready
  jobs/<job>/round-<N>/review-<name>.md  written by each reviewer
  jobs/<job>/decision.md            written by the approver
  jobs/<job>/fork-<K>.md            an ADR-tier fork the builder raised
  jobs/<job>/feedback-<K>.md        the owner's answer, verbatim
  jobs/<job>/acceptance-<K>.md      the owner's acceptance of a hard escalation, verbatim
```

`<spec-slug>` is the spec file's basename without `.md`. A repository can
hold several runs, one folder per spec.

Only the `job` script writes `run.json` and `job.json`. Everything a reader
needs is in those two; the other files hold the detail behind a verdict.

## Reading it

Two ways, both read-only:

```bash
job="<plugin root>/skills/factory/scripts/job"
"$job" status docs/specs/<slug>.md --json
```

```json
{
  "schema": 1,
  "generated": "2026-11-12T03:10:00Z",
  "run": { "...": "run.json, as below" },
  "jobs": [ { "...": "each job.json, as below, in step order" } ]
}
```

Or read the files directly. `schema` is raised when a field changes meaning
or is removed; a new field does not raise it, so ignore fields you do not
know.

## Watching for a change

- Every write replaces the file in one rename, so a reader never sees half a
  file. Watch the directory for a rename or create event on `job.json` and
  `run.json`; a watcher on the file's own inode misses the replacement.
- A stage change always appends one entry to that job's `history`, so the
  length of `history` is a change counter, and its last entry says what
  happened and when.
- There is no event stream and no daemon. Polling `status --json` every few
  seconds is cheap: it reads the files and runs no check.
- The script does not know whether an agent is working right now. A job at
  `build` means a builder owes its `build.md`, not that one is running; a
  stalled session leaves the stage where it was. An app can show the age of
  the last `history` entry to make a stall visible.

## `run.json`

| Field | Type | Meaning |
|---|---|---|
| `spec` | string | The spec's path from the repository root |
| `slug` | string | The spec slug; names the run folder and the integration branch |
| `title` | string | The spec's title |
| `base` | `{ref, sha}` | The branch the run started from and its commit. The spec, the criteria and `factory.json` are always read at this commit |
| `mode` | `direct` or `integration` | `direct`: one eligible step, its pull request targets the default branch, the job ends at `merge-ready`. `integration`: more than one, on `factory/<slug>` |
| `integration_branch` | string or null | `factory/<slug>` in integration mode |
| `integration_tip` | string or null | The commit the script last left that branch at. A start, merge or final is refused when the branch is anywhere else |
| `default_branch` | string | The repository's default branch |
| `concurrency` | number | Jobs that may be at an active stage at once |
| `breaker` | number | How many finished jobs in a row ending at `needs-owner` or `blocked` stop new starts |
| `max_rounds` | number | The round limit each job starts with |
| `skipped` | list of `{step, title, reason}` | Steps already done, which got no job |
| `ineligible` | list of `{step, title, reason}` | Steps the factory will not run, with the reason; they stay with `coordinate` |
| `final` | null or `{gate, commit, pr}` | Set by `job final`: the gate on the integration branch and the final pull request's URL |
| `created` | string | When the run was planned, UTC, `YYYY-MM-DDTHH:MM:SSZ` |

## `job.json`

| Field | Type | Meaning |
|---|---|---|
| `id` | string | The job id, also its folder name |
| `step` | number | The spec step this job builds |
| `title` | string | The step's title |
| `serves` | list of strings | The requirements the step serves, such as `R2` |
| `blocked_by` | list of numbers | Steps that must be merged before this one starts |
| `risk` | `low`, `medium` or `high` | From the spec step |
| `surfaces` | list of strings | `ui`, `security`, or empty |
| `reviewers` | list of strings | The review personas routed to this job |
| `stage` | string | Where the job is now; one of the ten stages below |
| `round` | number | The current build round, from 1 |
| `round_limit` | number | The round at which a failure stops the job; an owner's answer raises it |
| `base` | `{ref, sha}` | The run's base, repeated |
| `gate_base` | string | What the job's diff is measured against: the base commit in direct mode, the integration branch in integration mode |
| `branch` | string | `factory-job/<slug>/<job>` |
| `worktree` | string | Absolute path of the job's worktree |
| `pr` | number or null | The step's pull request, once the first build is pushed |
| `head` | string or null | The commit the current round's evidence is tied to |
| `gate` | `PASS`, `FAIL` or null | This round's gate verdict |
| `escalate` | list of strings | Hard escalation conditions the gate reported this round |
| `reviews` | object | Reviewer name to `PASS` or `CHANGES`, this round |
| `accepted` | null or `{head, reasons, file, at}` | The owner's acceptance of the escalation reasons on that commit |
| `synced` | null or `{from, to}` | Set when a merge rebased the branch: the reviewed commit and what it became |
| `question` | string | The one question for the owner, when the job stopped on one |
| `note` | string | The note of the last move; at `needs-owner` and `blocked` it carries the question or the reason |
| `rested_at` | number or null | Seconds since the epoch when the job came to rest; the circuit breaker orders jobs by it |
| `history` | list | Every move, oldest first; see below |

A `history` entry:

```json
{ "from": "gate", "to": "review", "at": "2026-11-12T03:08:41Z", "round": 1, "note": "" }
```

The time a job spent in a stage is the gap between the entry that entered it
and the next one.

## Stages

A job is always at exactly one. These are the boxes of the factory lane in
the README's diagram.

| Stage | Meaning | Who moves it on |
|---|---|---|
| `planned` | Created, not started; held by a blocker, a full concurrency, or an open circuit breaker | `job advance <job-dir> build` |
| `build` | A builder owes `build.md` for this round | `job advance ... gate`, or `needs-owner` or `blocked` when the builder stopped |
| `gate` | The gate script owes this round's `checks.md` | `job advance ... review` on pass, `build` on fail |
| `review` | Each routed reviewer owes its review file | `job advance ... approve` when all pass, `build` on any change request |
| `approve` | The approver owes `decision.md` | `job advance ... merging` or `merge-ready`; refused, and parked at `needs-owner`, on a hard escalation |
| `merging` | Approved; the step pull request is to be merged into the integration branch | `job merge` |
| `merged` | Final, integration mode: the step is on the integration branch | Nothing |
| `merge-ready` | Final, direct mode: the pull request waits for the owner's merge on GitHub | Nothing; the script never merges it |
| `needs-owner` | Stopped on one question for the owner, in `question` and `note` | `job answer` (back to `build`, round limit raised) or `job accept` (on to `merging` or `merge-ready`) |
| `blocked` | The builder cannot go on, or the plan found the job behind an ineligible step | `job answer` for a builder's block; nothing for a plan block |

Groupings an app may want:

| Group | Stages |
|---|---|
| Active, holding a concurrency slot | `build`, `gate`, `review`, `approve`, `merging` |
| Finished | `merged`, `merge-ready` |
| Waiting on the owner | `needs-owner`, and `blocked` when its last history entry came from `build` |
| Not started | `planned` |

A fix round shows as a move back to `build` with `round` one higher. A job
that failed its last round moves to `needs-owner`, with the failing file's
path in the note.

The run is over when no job is at `planned` or an active stage. In
integration mode `run.json`'s `final` then holds the final pull request once
`job final` has run.

## Verdict files

Each agent-written file opens with fixed header lines, then a blank line and
a `## Summary` of three to five bullets, which is the part worth showing.

| File | Line 1 | Line 2 | Line 3 |
|---|---|---|---|
| `build.md` | `STATUS: READY`, `BLOCKED` or `FORK` | `COMMIT: <sha>` | `QUESTION: none` or one sentence |
| `round-<N>/checks.md` | `GATE: PASS` or `FAIL` | `COMMIT: <sha>` | `ESCALATE: none` or reasons separated by `; ` |
| `round-<N>/review-<name>.md` | `VERDICT: PASS` or `CHANGES` | `COMMIT: <sha>` | blank |
| `decision.md` | `APPROVE` or `ESCALATE` | `COMMIT: <sha>` | `QUESTION: none` or one sentence |
| `fork-<K>.md` | `STATUS: FORK` | `COMMIT: <sha>` | `QUESTION:` the fork in one sentence |

These files are written by agents. Treat their text as untrusted when you
render it: show it as text, never as markup.

## What the script prints

For an app that drives or mirrors the run rather than only reading it. Each
command prints one line per job on success, and on a refusal prints
`refused: <reason>` on stderr with exit 1.

| Command | Line |
|---|---|
| `job plan <spec>` | `job <id> step <N> <mode> <branch>`, `ineligible step <N> <reason>`, `skipped step <N> status done` |
| `job next <spec>` | `start`, `resume`, `hold`, `wait` or `done`, then `<id> <stage> <note>`; a first line `stop <reason>` when the circuit breaker is open |
| `job advance <job-dir> <stage>` | `moved <id> <stage> round <N>` |
| `job answer`, `job accept` | `answered` or `accepted`, then `<id> <stage> round <N>, <file>` |
| `job merge <job-dir>` | `merged <id> merged pull request <n> merged at <sha>` |
| `job final <spec>` | `final <url> PASS` |
| `job status <spec>` | A header row, then one row per job; `--json` prints the object above |

## The other flows

`coordinate`, `handsfree` and `intake` are driven by a session, not a
script, and keep ledgers the session writes. They are tab-separated with a
header row, and are only as current as the session's last write.

| Flow | File | Columns |
|---|---|---|
| `coordinate` | `<notes folder>/units.tsv` | `id`, `title`, `session`, `branch`, `base`, `pr`, `head`, `verdict`, `state` |
| `coordinate` | `<notes folder>/decisions.tsv` | `when`, `unit`, `kind`, `decision`, `evidence`, `result` |
| `handsfree` | `docs/plans/handsfree-<slug>/decisions.tsv` | `number`, `round`, `question`, `tier`, `recommendation`, `own pick`, `second opinion`, `decision`, `reason` |
| `handsfree` | `docs/plans/handsfree-<slug>/owner-questions.md` | The questions collected for the owner |
| `intake` | `docs/plans/intake-<slug>/` | The request, the reproduction logs and the approval screen; no state file |

`coordinate`'s `state` column is one of `scoped`, `running`, `ready`,
`in-review`, `fixing`, `merge-ready`, `merged`, `parked`, `blocked`.
