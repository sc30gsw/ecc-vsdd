---
name: vsdd-run
description: This skill should be used when the user asks to start, resume, inspect, cancel, clean up, or fully automate the complete ecc-vsdd workflow with pinned Claude models, Dynamic Workflow implementation, independent Opus reviews, validation gates, and pull request creation.
version: 1.0.0-rc.8
argument-hint: start <request-or-slug> [source] [--mode auto|standard] [--base ref] [--until review|pr] | resume <slug> [source] [--until pr] | status|cancel|cleanup <slug>
disable-model-invocation: true
hooks:
  PreToolUse:
    - matcher: ""
      hooks:
        - type: command
          command: python3
          args:
            - "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-model-guard.py"
            - "--strict"
---

# vsdd-run — Pinned, resumable VSDD orchestration

## Invocation

```text
/ecc-vsdd:vsdd-run start <request-or-slug> [source] [--mode auto|standard] [--base <ref>] [--until review|pr]
/ecc-vsdd:vsdd-run resume <slug> [source] [--until pr]
/ecc-vsdd:vsdd-run status <slug>
/ecc-vsdd:vsdd-run cancel <slug>
/ecc-vsdd:vsdd-run cleanup <slug>
```

Treat the legacy `/ecc-vsdd:vsdd-run <slug> ...` form as `start <slug> ...`. Accept deprecated `--approval none` as a no-op; reject `critical` and `all` because independent automated reviews are mandatory gates.

Default to `--until review`. Treat only an exact, current one-line `start|resume ... --until pr` user prompt as authorization to push the integration branch and create a PR. The hook binds it to the current session, canonical cwd, and prompt ID; the next user prompt clears it. It never authorizes bypassing a failed gate.

Default a new run to `--mode auto`. Preserve the recorded mode on resume. Mode changes presentation and interaction style only; it never changes model routing, review coverage, severity gates, or retry limits.

## Control-plane preflight

Require the current session to run the plugin agent `ecc-vsdd:vsdd-orchestrator` with explicit CLI effort `high`. The agent definition pins Fable, but Claude Code can retain the caller's default effort for a top-level `--agent` session, so never omit `--effort high`. If the required agent or effort is not active, stop before tools or mutations and print:

```text
claude --agent ecc-vsdd:vsdd-orchestrator --effort high
```

The scoped hook mechanically prevents Fable from writing files, running arbitrary Bash, or launching unpinned agents. Never weaken or work around it.

Read these contracts before starting or resuming:

- `${CLAUDE_PLUGIN_ROOT}/skills/vsdd-run/references/model-routing.md`
- `${CLAUDE_PLUGIN_ROOT}/skills/vsdd-run/references/run-state-contract.md`
- `${CLAUDE_PLUGIN_ROOT}/skills/vsdd-run/references/review-contract.md`
- `${CLAUDE_PLUGIN_ROOT}/skills/vsdd-run/references/implementation-contract.md`
- `${CLAUDE_PLUGIN_ROOT}/skills/vsdd-run/references/runtime-contract.md`

When the trusted `UserPromptSubmit` context supplies exact protected orchestrator relay start and wait commands, invoke start before any repository inspection or worker launch, then invoke the unchanged wait command in the foreground and repeat it on `RUNNING` until terminal. Return the child session's terminal result and do nothing else in the parent session. Each call is bounded to 45 seconds; never replace polling with one long foreground command. The child starts after the project-agent registry exists and executes this skill normally. Never construct or modify a relay command.

Require Claude Code 2.1.214 or later, every named project-local protected worker materialized by the `UserPromptSubmit` hook, the exact pinned models and efforts, Dynamic Workflows for Phase 7, ECC dependency skills, Git, and `gh` when `--until pr` is selected. Launch workers only by their unscoped `vsdd-*-worker` or `vsdd-*-reviewer` names. Claude Code ignores `hooks`, `mcpServers`, and `permissionMode` in plugin subagents, so never launch the `ecc-vsdd:vsdd-*` plugin-scoped worker definitions. Never use `inherit`, `max`, a fallback model, or Fable for worker work. Return `VSDD RUN BLOCKED` when a requirement is unavailable.

## Lifecycle commands

### Start

1. Obtain a lowercase kebab-case slug. When the first argument is a feature brief instead, delegate deterministic slug selection to a fresh `vsdd-init-worker`.
2. Require sufficient source material: a detailed brief, source file, or supported URL.
3. Delegate Git setup to a fresh Init worker:
   - pass a context envelope with `operation: bootstrap`; this runs before Phase 0 and is not the Phase 1 Init execution;
   - require the current checkout to be clean;
   - use `vsdd-runtime-state.py bootstrap` as the sole mutation path; it resolves explicit `--base` or the actual repository default branch;
   - record the exact `base_ref`, `base_branch`, and `base_sha`; never default to `main`;
   - create branch `vsdd/<slug>` and a dedicated integration worktree outside the current checkout;
   - create `.claude/specs/<slug>/run-state.json` as the only feature-spec file, with `bootstrap_status: READY`, `init: PENDING`, and the original request/source metadata;
   - block if the branch, worktree, spec directory, or run state already existed before this managed bootstrap.
4. Require the bootstrap command to leave the user's current checkout and branch unchanged, then invoke Steering with `operation: phase`.
5. Enter the phase loop.

### Resume

When a source argument is supplied, first delegate source-update mode to a fresh Init worker. Require successful persistence, invalidate Requirements and downstream phases, and snapshot the new source as specified by the runtime contract. Never recreate or overwrite the existing spec skeleton.

When and only when the user explicitly supplies `--until pr` for a run already completed at `review`, have a fresh Status worker run deterministic `extend --until pr` before PR preflight. This records the new external-action boundary and reopens the run. Never infer this authorization from an earlier default, a status request, or the existence of review evidence.

Delegate state verification to a fresh `vsdd-status-worker`. Run the deterministic runtime preflight, invalidate the earliest stale phase and all downstream phases, then continue at the first incomplete valid phase. Preserve retry counters unless their owning phase was invalidated by changed upstream input.

### Status

Delegate read-only inspection to `vsdd-status-worker`. Print phase, attempts, pinned routing, current blockers, worktree paths, implementation session ID, review verdicts, and exact resume command. Do not enter the phase loop.

### Cancel and cleanup

Delegate both operations to `vsdd-init-worker`.

- `cancel`: stop new work, mark the run cancelled, and preserve all changes and worktrees.
- `cleanup`: remove only safely integrated TASK worktrees. Keep the integration worktree after PR creation unless explicitly authorized to remove it. Never delete unmerged changes.

## Phase loop

Use only persisted artifacts and fixed verdict fields to choose transitions. Prefix every worker task with the exact `VSDD_RUN_CONTEXT` envelope from the runtime contract, including the explicit `operation`. Before every worker, delegate deterministic `preflight` to a fresh Status worker. Before every review and implementation TASK attempt, use the atomic attempt protocol. After every worker passes its completion gate, delegate deterministic `snapshot` and `run-state.json` bookkeeping to a fresh Status worker. Never create, revise, review, implement, commit, or author PR content in Fable.

| Order | Phase | Fresh pinned agent | Completion gate |
| --- | --- | --- | --- |
| 0 | Steering | `vsdd-steering-worker` | required files exist, contain no unresolved blocking decision, record reversible assumptions, and repository fingerprint is current |
| 1 | Init | `vsdd-init-worker` | consume the exact managed bootstrap, create the spec skeleton and mode, snapshot Init, and set `bootstrap_status: CONSUMED` |
| 2 | Requirements | `vsdd-requirements-worker` | EARS `REQ-NNN` blocks and acceptance criteria exist |
| 3 | Requirements review | `vsdd-requirements-reviewer` | structured `verdict: PASS` |
| 4 | Design | `vsdd-design-worker` | design satisfies every approved REQ and steering viewpoint |
| 5 | Tasks | `vsdd-tasks-worker` | traceable `TASK-NNN` blocks exist and TASK IDs exactly equal the `progress.md` Tasks table |
| 6 | Plan review | `vsdd-plan-reviewer` | checks A–I pass and structured `verdict: PASS` |
| 7a | Implementation plan | independent Sonnet ultracode session | `implementation-workflow.md` exists and no code was changed |
| 7b | Implementation plan review | `vsdd-implementation-workflow-reviewer` | structured `verdict: PASS` |
| 7c | Implementation | resume Sonnet ultracode session | all TASKs are done, all required checks pass, and `implementation-ledger.md` maps every TASK to an existing commit |
| 8a | Code review | `vsdd-code-reviewer` | structured verdict against exact target commit |
| 8b | Security review | `vsdd-security-reviewer` | structured verdict against the same target commit |
| 8c | Remediation | Sonnet high or ultracode | fresh code and security reviews both `PASS` |
| 9 | PR | `vsdd-pr-worker` | persisted GitHub PR URL and target commit |

For each Requirements, Plan, and Implementation Workflow review, have the Status worker run `begin-attempt` with that phase scope before launching Opus. For each paired Code/Security round, run it once with scope `post-implementation-review` and pass the same returned number to both fresh Opus agents. Never accept a self-selected attempt number.

Run Steering only when `_steering/` is missing or its repository fingerprint is stale. Otherwise record reuse with validated hashes. Even when Steering is reused, deterministic preflight must reject every remaining Open question, DRAFT marker, or Glossary-pending marker before downstream work. Phase 6 already reviews Requirements, Design, and Tasks together; never move it before Tasks.

During `start` or `resume`, `execution_mode: unattended` disables every phase-local interview, `WAITING FOR CONFIRMATION`, `CONFIRM ...`, approval prompt, and overwrite question. Workers derive routine answers from persisted source evidence. This never overrides the unattended decision boundary or a `BLOCKED` verdict.

The existing integration worktree and feature spec directory are expected during Phase 1 only when they are the exact managed bootstrap: active and recorded branch `vsdd/<slug>`, recorded worktree equal to the active Git top-level, `bootstrap_status: READY`, Init still pending, and no feature-spec entry other than `run-state.json`. Any additional file or identity mismatch is a collision and blocks; the managed bootstrap itself is never treated as one.

## Review and revision loops

Run every review in a new Opus `xhigh` agent using disk-only context. Pass only the integration worktree, slug, expected artifact, exact target commit when applicable, and attempt number. Never pass author conversation or conclusions.

For Requirements, Plan, and Implementation Workflow reviews:

1. Run the author once and a fresh reviewer once.
2. On `REVISE`, return findings to the same phase model in a fresh author/revision agent.
3. Run a new Opus reviewer after each revision.
4. Allow at most three reviews total; then block.

Treat `BLOCKED` as an immediate blocker. Treat unresolved CRITICAL/HIGH as `REVISE`. MEDIUM may proceed and remains visible; LOW is optional.

## Dynamic implementation

Never pass individual TASKs from Fable to subagents. Launch the dedicated Sonnet main session through only:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-launch-worker.py" plan --slug <slug> --worktree <absolute-integration-worktree> --detach
```

The start result is `status: STARTED` plus an evidence path, or `status: RUNNING` with `reused: true` when the same stage already has a live supervisor. Poll that exact detached supervisor until terminal:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-launch-worker.py" wait --slug <slug> --worktree <absolute-integration-worktree> --evidence <exact-started-evidence> --wait-seconds 45
```

Invoke every start and wait command in the foreground (`run_in_background: false`). On `status: RUNNING`, call `wait` again; never end the Fable session or advance a phase until `COMPLETE` or `BLOCKED`. The launcher-owned supervisor survives shell timeout, compaction, and session restart. Resume must discover and poll an existing RUNNING supervisor instead of starting a duplicate. The launcher runs deterministic phase preflight itself, resolves every plugin manifest dependency for the isolated child, and binds the returned session ID into `run-state.json` only after a completed plan. After the implementation-workflow Opus review passes, resume it with:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-launch-worker.py" implement --slug <slug> --worktree <absolute-integration-worktree> --session-id <id> --detach
```

For plan revisions use `revise-plan --detach` with the same session ID and poll its returned evidence. The launcher pins the main session and every workflow agent to Sonnet, sets `--effort ultracode`, omits fallback models, and blocks when workflows are disabled.

Apply the TASK retry and traceability rules in the implementation contract. Do not let Fable or Opus take over implementation after a failure.

## Post-implementation review and remediation

Launch code and security reviews independently, preferably concurrently, against the same full commit SHA. Require both reports.

- Both `PASS`: continue.
- Either `BLOCKED`: stop.
- Either has CRITICAL/HIGH: start remediation.

Use a fresh `vsdd-remediation-worker` at Sonnet `high` for the first ordinary fix. Use the ultracode launcher with stage `remediate` immediately when either report says `remediation_mode: workflow`, or for the second remediation round when blocking findings remain. After every fix, launch two new Opus reviewers. Allow the initial review and at most two remediation/re-review rounds; then block.

Never create a PR with unresolved CRITICAL/HIGH. If MEDIUM or a manual follow-up remains, have the PR worker request a draft PR; otherwise request a ready PR. Launch it only with the exact Phase 9 `VSDD_RUN_CONTEXT`; the strict hook must consume the current prompt-bound consent, parse that envelope, and receive `READY` from runtime PR preflight before the Agent call is allowed. `SubagentStart` binds a random capability to the actual PR worker agent ID. Its session-bound authorization and current preflight must remain valid before every PR-worker Bash command.

Every worker, including the PR worker, is forbidden from direct `git push`, `git send-pack`, and GitHub mutation commands. Require the PR worker to write only `pr-body.md` and invoke the bundled capability-gated `vsdd-pr-action.py publish` broker. The broker alone may push the exact integration ref, create or reuse the PR, validate remote/GitHub identity, and persist `pr-result.json` with URL/number, recorded base branch/SHA, integration head branch/SHA, and target commit. The Status worker must snapshot phase `pr`; without this current structured evidence the run is not complete.

After both current Code and Security reviews are snapshotted `PASS`, have the Status worker run deterministic `complete --reached review` when `until: review`. After a current PR snapshot, run `complete --reached pr` when `until: pr`. Do not print `VSDD RUN COMPLETE` until this terminal command returns `status: COMPLETE`; it atomically sets the top-level status, reached boundary, current phase, and completion timestamp.

## Unattended decision boundary

Allow workers to document and proceed with reversible technical assumptions. Block instead of guessing when an unresolved choice affects product behavior, data loss, security, compatibility, destructive operations, or external authority.

Allow independent TASKs to continue after another TASK exhausts its retries, but never start its dependents. A partially successful implementation remains blocked from PR until the approved scope is complete or explicitly respecified upstream.

## Completion and blocker output

Print a self-contained final record:

```text
VSDD RUN COMPLETE: <slug>
Reached: <review|pr>
Integration branch: vsdd/<slug>
Integration worktree: <absolute path>
Target commit: <sha>
Reviews: requirements=PASS plan=PASS implementation-workflow=PASS code=PASS security=PASS
PR: <URL|not requested>
```

On any failure print:

```text
VSDD RUN BLOCKED: <slug>
Phase: <phase>
Attempt: <n>/<limit>
Evidence: <artifact, finding IDs, command, or capability>
Preserved state: <run-state path and worktree>
Resume: /ecc-vsdd:vsdd-run resume <slug>
```

Never claim completion unless the target phase's persisted gate is valid for the current hashes and commit and top-level `status` is `COMPLETE` with the requested `reached` boundary.
