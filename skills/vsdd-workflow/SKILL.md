---
name: vsdd-workflow
description: This skill should be used to inspect VSDD run state, phase validity, hashes, retries, blockers, worktrees, review verdicts, and resume instructions without performing implementation work.
---

# vsdd-workflow — State dashboard

## Invocation

```text
/vsdd-workflow [slug]
```

## Routing and scope

Return a purely read-only display directly when no persisted state must change. Delegate hash recomputation, invalidation, retry bookkeeping, cancellation state, or cleanup bookkeeping to a fresh `vsdd-status-worker` (Haiku, `low`).

Never author or revise Steering, requirements, design, tasks, implementation, reviews, commits, or PR text.

Read the run-state contract:

```text
${CLAUDE_PLUGIN_ROOT}/skills/vsdd-run/references/run-state-contract.md
${CLAUDE_PLUGIN_ROOT}/skills/vsdd-run/references/runtime-contract.md
```

## List view

Without a slug, enumerate `.claude/specs/*/run-state.json` except `_steering` and display:

| Slug | Status | Current phase | Attempt | Branch | Updated | Next action |
| --- | --- | --- | --- | --- | --- | --- |

If a legacy spec has no `run-state.json`, label it `legacy/unmanaged` and suggest starting or migrating through `vsdd-run`; do not fabricate state.

## Detail view

With a slug, read `run-state.json`, current Git state, artifacts, and structured review frontmatter. Recompute hashes only through the Status worker.

Display:

1. run status: RUNNING, BLOCKED, CANCELLED, or COMPLETE;
2. base ref/SHA, integration branch/worktree, current head;
3. current phase and retry budget;
4. each phase's pinned agent/model/effort;
5. persisted input/output hash validity;
6. review verdicts and target commits;
7. implementation session ID and worker evidence;
8. immutable implementation plan and `implementation-ledger.md` evidence;
9. exact `tasks.md` / `progress.md` / ledger TASK-set status;
10. blocked TASKs and dependent TASKs not started;
11. exact resume, source-update resume, cancel, and cleanup commands.

Use this phase table:

```text
0  Steering
1  Init
2  Requirements
3  Requirements Review
4  Design
5  Tasks
6  Plan Review
7a Implementation Plan
7b Implementation Workflow Review
7c Implementation
8a Code Review
8b Security Review
8c Remediation, when required
9  PR
```

## Validity rules

- A file's existence never proves phase completion.
- Before displaying a resumable next phase, have the Status worker run deterministic `preflight`; show `INVALIDATED` from its earliest phase instead of stale completion state.
- A review is valid only when its structured frontmatter is parseable, its reviewer model/effort match the contract, and its artifact hash or target commit is current.
- Code and security reviews must target the same current full SHA.
- CRITICAL/HIGH requires `REVISE`; MEDIUM may proceed; `BLOCKED` stops.
- An input hash change invalidates its owning phase and every downstream phase.
- Any unresolved Steering `Status: open`, `DRAFT`, or `Glossary pending` marker blocks every downstream phase.
- Before Plan Review, the TASK ID sets in `tasks.md` and the `progress.md` Tasks table must be exactly equal.
- Before Code Review and later phases, every TASK must additionally be `done` and map exactly once to an existing commit in `implementation-ledger.md`.
- `base_ref`, `base_branch`, and `base_sha` are persisted at Start; never substitute `main` or silently redetect another base on resume.
- Retry counters remain on resume unless upstream invalidation legitimately resets the owning phase.
- PR completion requires a persisted GitHub URL and matching head SHA.

## Output example

```text
VSDD STATUS: mail-groups-filter
Status: BLOCKED
Phase: implementation-plan-review
Attempt: 3/3
Branch: vsdd/mail-groups-filter
Worktree: /absolute/path
Implementation session: <uuid>
Reviews: requirements=PASS plan=PASS implementation-workflow=REVISE code=not-run security=not-run
Evidence: .claude/specs/mail-groups-filter/review-results/implementation-workflow-review.md
Resume: /ecc-vsdd:vsdd-run resume mail-groups-filter
Cancel: /ecc-vsdd:vsdd-run cancel mail-groups-filter
Cleanup: /ecc-vsdd:vsdd-run cleanup mail-groups-filter
```
