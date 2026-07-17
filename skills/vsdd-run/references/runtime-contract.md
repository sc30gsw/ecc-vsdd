# Unattended runtime contract

## Worker context envelope

Prefix every worker task with this exact machine-readable envelope:

```text
VSDD_RUN_CONTEXT
schema_version: 1
execution_mode: unattended
operation: bootstrap|phase|source-update
slug: <slug>
integration_worktree: <absolute-path>
run_state: <absolute-path-to-run-state.json>
phase: <phase>
attempt: <integer>
source_paths: <comma-separated-persisted-paths-or-none>
END_VSDD_RUN_CONTEXT
```

Pass persisted paths, never raw source content or another agent's conclusions. Require the worker to read source artifacts from disk.

`execution_mode: unattended` overrides every phase-local interview, confirmation, approval, overwrite question, and optional pause. Derive routine answers from persisted source material and repository evidence. Record reversible technical assumptions. Return `BLOCKED` with one exact decision request when product behavior, data loss, security, compatibility, destructive operations, or external authority cannot be resolved from evidence.

`operation` is mandatory. `bootstrap` is the only operation that runs before Steering and before the integration worktree exists; it must execute only the bundled `bootstrap` command below and return immediately. `phase` executes exactly the named phase and must obey Steering/preflight. `source-update` preserves the initialized skeleton, updates only the supplied source, invalidates Requirements and downstream, and returns. Never infer an operation from prose.

The `auto|standard` mode changes presentation only. It never changes unattended execution, model routing, gates, or review coverage.

## Deterministic transition protocol

Use a fresh `vsdd-status-worker` to execute the bundled runtime. Fable never calls it through Bash directly.

Before every phase:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" preflight \
  --worktree <absolute-integration-worktree> --slug <slug> --phase <phase>
```

- `READY`: launch the phase worker with the context envelope.
- `INVALIDATED`: return to `earliest_phase`; never launch the originally requested phase.
- `BLOCKED`: stop and report the exact evidence.

Preflight also requires every direct prerequisite phase to be `COMPLETE`. Review prerequisites require a deterministic artifact snapshot with `verdict: PASS`; code and security review snapshots must target the current integration `HEAD`, carry the same `review_attempt`, and match the current finished `post-implementation-review` ledger entry. PR preflight requires Requirements, Plan, Implementation Workflow, Code, and Security reviews all to remain PASS and current. A new commit after review therefore returns `BLOCKED` until fresh Opus reviews are snapshotted.

After the requested terminal evidence is current, close the run deterministically:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" complete \
  --worktree <absolute-integration-worktree> --slug <slug> \
  --reached <review|pr>
```

To continue a review-complete run to PR, require an explicit user `--until pr` and record it before PR preflight:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" extend \
  --worktree <absolute-integration-worktree> --slug <slug> --until pr
```

The strict control-plane hook independently parses the PR worker's `VSDD_RUN_CONTEXT`, runs `preflight --phase pr`, and stores a private session-bound PR authorization before allowing that agent launch. The global hook revalidates the same authorization and preflight immediately before every PR-worker Bash command. The runtime requires top-level `until: pr` plus current review, commit, steering, and TASK evidence. Missing consent or stale evidence must prevent the external worker from starting or performing push/PR commands.

After a phase artifact passes its completion gate:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" snapshot \
  --worktree <absolute-integration-worktree> --slug <slug> --phase <phase>
```

Use `--phase-status REVISE|BLOCKED` for non-passing review attempts. Never accept a phase without a deterministic snapshot of its primary artifact.

## Base branch protocol

Before creating an integration worktree, have the Init worker run:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" detect-base \
  --repo <absolute-source-checkout> [--base <explicit-ref>]
```

Persist all returned fields: `base_ref`, `base_branch`, and `base_sha`. The detector uses `origin/HEAD` first, then an unambiguous conventional or sole local branch. It never guesses `main`; ambiguity returns `BLOCKED`. Create `vsdd/<slug>` from the returned `base_ref`, leave the source checkout unchanged, and persist the dedicated integration worktree path.

Managed bootstrap persists `bootstrap_status: READY`, Init `PENDING`, request/source metadata, and no feature-spec file other than `run-state.json`. Phase 1 Init consumes it only after `preflight --phase init`; its snapshot changes the status to `CONSUMED`. Do not apply the normal existing-directory collision rule to this exact managed shape.

Use the dedicated command for `operation: bootstrap`:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" bootstrap \
  --repo <absolute-clean-source-checkout> --slug <slug> \
  --worktree <new-absolute-integration-worktree> \
  --request <persisted-feature-brief-or-source-reference> \
  --mode <auto|standard> --until <review|pr> [--base <explicit-ref>]
```

It detects the real base, rejects dirty/colliding state, creates `vsdd/<slug>` in the dedicated worktree, leaves the source checkout branch unchanged, and writes only `run-state.json`. Do not manually reproduce these mutations.

## Steering integrity

Every `Status: open` question, `<!-- DRAFT ... -->` marker, and `Glossary pending` marker blocks downstream phases. An unattended worker may convert a reversible technical conclusion to:

```text
- Status: assumed
- Assumption: <decision>
- Evidence: <path or manifest>
```

Use `<!-- ASSUMED <date> source:<path> -->` for inferred glossary entries. Never relabel a product, security, compatibility, data-loss, destructive, or external-authority question as assumed.

## Source update on resume

Accept `resume <slug> [source]`. When source is supplied, run the Init worker in source-update mode without recreating the skeleton. A requested URL fetch failure is `BLOCKED`, not a warning. After the new source is persisted:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" invalidate \
  --worktree <worktree> --slug <slug> --from-phase requirements \
  --reason "source updated on resume"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" snapshot \
  --worktree <worktree> --slug <slug> --phase source
```

Then resume from Requirements.

## TASK integrity

Before Plan Review, require exact TASK ID equality between `tasks.md` and the `progress.md` Tasks table. Before Code Review, Security Review, Remediation, and PR, additionally require every TASK to be `done` and an exact TASK-to-commit mapping under `implementation-ledger.md` heading `## TASK-to-SHA Mapping`. Every mapped commit must both exist and be an ancestor of integration `HEAD`; an object that exists only in an unmerged TASK worktree is invalid.

## Mechanical attempt protocol

Before launching a Requirements, Plan, or Implementation Workflow reviewer, atomically run `begin-attempt` with that review phase as the scope. Before each paired Code/Security review round, run it once with scope `post-implementation-review`; both reports use the returned attempt number.

Before every TASK attempt, run:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" begin-attempt \
  --worktree <worktree> --slug <slug> \
  --scope implementation-task --task-id TASK-NNN
```

After that TASK attempt, run `finish-attempt` with the returned `--attempt` and `--outcome PASS|FAIL`. A TASK is not complete without a persisted PASS outcome. The runtime rejects unfinished overlapping attempts, report attempt rewrites, non-monotonic numbers, and every attempt beyond three. A third REVISE/FAIL or any review `BLOCKED` sets the run to `BLOCKED` immediately. Only an upstream artifact invalidation resets the affected downstream counters; resume alone never resets them.

## PR completion evidence

The PR worker must write `.claude/specs/<slug>/pr-result.json` with `url`, positive integer `number`, `base_branch`, `base_sha`, `head_branch`, `head_sha`, and `target_commit`. Snapshot phase `pr` only after writing it. The runtime requires the recorded base identity, `head_branch: vsdd/<slug>`, and both head fields equal to the current integration `HEAD`.
