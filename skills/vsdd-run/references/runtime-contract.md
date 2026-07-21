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

The global `UserPromptSubmit` hook atomically materializes the 13 delegated workers as unscoped project agents under `.claude/agents/`, with the literal installed guard path in their PreToolUse frontmatter. Claude Code ignores hooks in plugin subagents and fixes the project-agent registry before prompt submission, so the first parent Fable is restricted to exact capability-protected relay start and wait commands. The start command consumes a private session/cwd/prompt-bound record and detaches one child Fable with the same exact prompt after the proxies exist; the unchanged wait command polls at most 45 seconds per call until terminal. Replay, command modification, and replacing polling with one long call fail closed. The child may launch only the registered unscoped workers and never plugin-scoped copies. The guard binds generated file hashes to session ID, canonical cwd, and prompt ID, rejects collisions with user-owned agents, permits only those exact definitions, and removes unchanged generated files on `SessionEnd`. Managed bootstrap ignores only those exact marked proxy paths when checking source cleanliness.

The same hook records PR consent only for the exact current one-line `/ecc-vsdd:vsdd-run start|resume ... --until pr` (or `/vsdd-run`) prompt. Every later prompt clears it. The strict control-plane hook consumes that consent by launch tool-use ID, independently parses the PR worker's `VSDD_RUN_CONTEXT`, runs `preflight --phase pr`, and stores a private launch authorization. `SubagentStart` injects literal installed-plugin paths into every VSDD worker and binds a random capability to the actual PR worker agent ID. Subagent PreToolUse payloads expose the pinned `agent_type`; `agent_id` availability varies by Claude Code version and is intentionally not an authentication input there. The worker-local hook revalidates session/cwd/prompt/type/capability and preflight, while the broker invocation must separately present the exact agent ID recorded by `SubagentStart`. The runtime requires top-level `until: pr` plus current review, commit, steering, and TASK evidence. Missing consent, replay by another worker, or stale evidence must prevent the external worker from starting or performing push/PR commands.

For guard-observable direct commands and common shell/interpreter wrappers, all workers are denied `git push`, `git send-pack`, `gh pr` mutations, mutation-capable `gh api`, and recognized GitHub HTTP mutations. Dynamic shell subcommands and unclassified Git/gh commands fail closed. The PR worker creates only `pr-body.md` and invokes the exact bundled `vsdd-pr-action.py publish` broker with the injected literal capability/session/agent values. The broker revalidates authorization and preflight, verifies the unchanged remote base, pushes the exact integration ref, rechecks preflight, creates or reuses the PR through argument-array subprocess calls, validates GitHub base/head/draft identity, and atomically writes `pr-result.json`.

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

Managed bootstrap persists `bootstrap_status: READY`, Init `PENDING`, request/source metadata, and no feature-spec file other than `run-state.json`. Phase 1 Init consumes it only after `preflight --phase init`; before its snapshot, persist at least one `source-notion.md` or `source-request.md`. The Init snapshot hashes those files with Requirements ownership, records `source_paths`, and changes the bootstrap status to `CONSUMED`, so any later initial-source edit invalidates Requirements and downstream phases. Do not apply the normal existing-directory collision rule to this exact managed shape.

Use the dedicated command for `operation: bootstrap`:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" bootstrap \
  --repo <absolute-clean-source-checkout> --slug <slug> \
  --worktree /tmp/vsdd-worktrees/<slug> \
  --request <persisted-feature-brief-or-source-reference> \
  --mode <auto|standard> --until <review|pr> [--base <explicit-ref>]
```

It detects the real base, rejects dirty/colliding state, mechanically rejects every worktree path except `/tmp/vsdd-worktrees/<slug>`, creates `vsdd/<slug>` there, leaves the source checkout branch unchanged, and writes only `run-state.json`. Do not choose a sibling worktree path or manually reproduce these mutations.

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

At the same boundary, reject every uncommitted path outside the feature spec and Steering directories. Reviews target the exact integration commit, so uncommitted product changes are never reviewable completion evidence.

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

The PR action broker must write `.vsdd/specs/<slug>/pr-result.json` with `url`, positive integer `number`, `draft`, `base_branch`, `base_sha`, `head_branch`, `head_sha`, `target_commit`, and `created_at`. Snapshot phase `pr` only after the broker writes it. The runtime requires the recorded base identity, `head_branch: vsdd/<slug>`, and both head fields equal to the current integration `HEAD`.
