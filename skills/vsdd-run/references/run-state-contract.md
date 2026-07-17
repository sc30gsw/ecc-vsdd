# Run state contract

Persist `.claude/specs/<slug>/run-state.json` atomically with this logical shape:

```json
{
  "schema_version": 4,
  "slug": "feature-slug",
  "status": "RUNNING|BLOCKED|CANCELLED|COMPLETE",
  "execution_mode": "unattended",
  "request": "original feature brief or source URL",
  "source_paths": [".claude/specs/feature-slug/source-notion.md"],
  "until": "review|pr",
  "reached": "review|pr",
  "completed_at": "ISO-8601 timestamp",
  "review_completed_at": "ISO-8601 timestamp preserved while extending review to PR",
  "base_ref": "origin/develop",
  "base_branch": "develop",
  "base_sha": "full SHA",
  "integration_branch": "vsdd/feature-slug",
  "integration_worktree": "/absolute/path",
  "bootstrap_status": "READY|CONSUMED",
  "current_phase": "steering|init|requirements|requirements-review|design|tasks|plan-review|implementation-plan|implementation-plan-review|implementation|code-review|security-review|remediation|pr",
  "implementation_session_id": null,
  "phases": {
    "steering": {"status": "PENDING"},
    "init": {"status": "PENDING"}
  },
  "artifact_hashes": {},
  "attempt_ledger": {
    "requirements-review": {"attempts_started": 1, "limit": 3, "last_finished_attempt": 1, "last_outcome": "PASS"},
    "post-implementation-review": {"attempts_started": 1, "limit": 3},
    "implementation-task:TASK-001": {"attempts_started": 1, "limit": 3, "last_finished_attempt": 1, "last_outcome": "PASS"}
  },
  "invalidation_history": [],
  "blocker": null
}
```

For every phase, record its agent, model, effort, attempt number, start/end timestamps, input hashes, output hashes, target commit, verdict, and evidence paths. Never record a phase complete from a worker message alone. Use `scripts/vsdd-runtime-state.py snapshot` after validating the persisted artifact.

Before every phase and on resume, run `scripts/vsdd-runtime-state.py preflight`. It atomically compares recorded artifact hashes, invalidates the earliest owner phase and every downstream phase, validates phase prerequisites, structured review snapshots, Steering markers and TASK sets, and protects the recorded base/integration branch. Invalidation removes the stale hash records owned by invalidated phases so the earliest phase can run again; the next audit must not repeat the same invalidation. Never reuse a review against a different artifact hash or commit. Never reuse an author/reviewer session after invalidation.

Snapshotting a legitimately regenerated artifact compares it with the prior owned hash before replacement. When it changed, keep the current phase at its new status and invalidate only its dependents. Requirements/Design/Tasks changes invalidate all affected downstream artifacts; Remediation changes invalidate both Code and Security reviews plus PR without resetting the shared post-review counter.

Managed Start bootstrap creates the integration worktree and `.claude/specs/<slug>/run-state.json` before Phase 0. Phase 1 Init may consume that existing path only when `bootstrap_status` is `READY`, Init is pending, both recorded and active branch are exactly `vsdd/<slug>`, the recorded worktree equals the active Git top-level, and the feature spec contains no other entry. Snapshotting Init changes the status to `CONSUMED`. This narrow exception is not an overwrite path.

Create that state only with the bundled `bootstrap` command and a context envelope containing `operation: bootstrap`. Phase 1 uses a separate worker invocation with `operation: phase` and `phase: init`. Bootstrap bypasses Steering because it precedes Phase 0; Phase 1 never bypasses Steering.

Use these retry ceilings independently:

- Requirements review: initial + two revisions/reviews.
- Plan review: initial + two revisions/reviews.
- Implementation-workflow review: initial + two revisions/reviews.
- Each implementation TASK: initial + two retries.
- Post-implementation code/security review: initial + two remediation/re-review rounds.

After exhaustion, set `status: BLOCKED`, preserve every worktree and session record, and record exact evidence. Never reset counters on resume unless an upstream input changed and invalidated the corresponding phase.

Use `begin-attempt` before every review round and TASK attempt. Reviews are finished by a validated report snapshot; TASKs require an explicit matching `finish-attempt --outcome PASS|FAIL`. Rewriting a snapshotted report with the same number, overlapping unfinished attempts, a fourth attempt, or a third failing outcome is rejected mechanically.

PR completion additionally requires a snapshotted `.claude/specs/<slug>/pr-result.json`. Its GitHub URL/number, recorded base branch/SHA, integration head branch/SHA, and target commit must all match the current run state and integration `HEAD`; a worker completion message alone cannot complete PR.

After the requested boundary is fully snapshotted, use the bundled `complete --reached review|pr` command. It is the only path that sets top-level `status: COMPLETE`, `reached`, `completed_at`, and the terminal `current_phase`. A review-complete run remains closed until the user explicitly requests `resume <slug> --until pr`; then use `extend --until pr` to preserve the review completion timestamp, set `until: pr`, and reopen at Phase 9. Any artifact invalidation clears terminal completion markers.
