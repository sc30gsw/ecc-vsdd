---
name: vsdd-impl
description: This skill should be used to plan and implement the complete approved VSDD tasks.md through a dedicated Sonnet ultracode Dynamic Workflow with TDD, traceability, retries, worktrees, and an independent Opus plan gate.
---

# vsdd-impl — Dynamic Workflow implementation

## Invocation

```text
/vsdd-impl <slug>
```

Do not accept a single `task-id` in automated mode. Read the complete approved `tasks.md`; the Dynamic Workflow decides dependencies, parallelism, worktrees, integration, and execution order.

## Mandatory execution routing

Never implement inline in the invoking model and never pass TASKs individually to subagents. Use a dedicated Claude Code main session pinned to Sonnet with `--effort ultracode` and `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`.

Read and obey:

```text
${CLAUDE_PLUGIN_ROOT}/skills/vsdd-run/references/implementation-contract.md
```

The `ecc-vsdd:vsdd-implementation-driver` agent executes inside that independent session. Fable and Opus may never take over implementation.

## Prerequisites

Require:

- `.claude/specs/<slug>/requirements.md`;
- `.claude/specs/<slug>/design.md`;
- `.claude/specs/<slug>/tasks.md` with at least one `TASK-NNN`;
- exact, duplicate-free equality between all `tasks.md` TASK headings and all `progress.md` Tasks rows; require deterministic `plan-review` preflight for managed runs;
- `.claude/specs/<slug>/review-results/plan-review.md` with `verdict: PASS` and no failed A–I check;
- `.claude/specs/_steering/tech.md` with §3 conventions and §4 verification commands;
- a dedicated integration worktree and non-base integration branch;
- Claude Code 2.1.203 or later with Dynamic Workflows enabled.

Stop with `VSDD RUN BLOCKED` when any prerequisite, exact model, effort, or capability is unavailable. Never use a fallback model, `inherit`, or `max`.

## Stage 1: Persist the implementation workflow

Launch:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-launch-worker.py" plan --slug <slug> --worktree <absolute-integration-worktree>
```

The Sonnet ultracode session must create and run a Dynamic Workflow that reads all approved tasks and writes only:

```text
.claude/specs/<slug>/implementation-workflow.md
```

Require the artifact to record the inferred TASK DAG, parallel groups, worktree assignments, validation commands, Red → Green → Refactor checkpoints, commit/integration order, stop conditions, and retry policy. Do not change code during this stage. Persist the returned session ID.

## Stage 2: Independent workflow-plan gate

Launch a new `ecc-vsdd:vsdd-implementation-workflow-reviewer` (Opus, `xhigh`) with disk-only context. It writes:

```text
.claude/specs/<slug>/review-results/implementation-workflow-review.md
```

Use the structured review contract. On `REVISE`, resume the same Sonnet session with launcher stage `revise-plan`, then use a new Opus reviewer. Allow at most three Opus reviews total. On the third failure, block without Fable repair or waiver.

## Stage 3: Resume implementation

Only after `verdict: PASS`, launch:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-launch-worker.py" implement --slug <slug> --worktree <absolute-integration-worktree> --session-id <id>
```

The Dynamic Workflow owns runtime decomposition. For every TASK:

Keep the approved `implementation-workflow.md` immutable and persist all runtime evidence to `implementation-ledger.md`.

1. Atomically run bundled runtime `begin-attempt --scope implementation-task --task-id TASK-NNN` and record the returned number.
2. Write or update a failing test and record Red evidence.
3. Implement the minimum change and record Green evidence.
4. Refactor while keeping tests green.
5. Run the TASK validation commands and applicable `tech.md` §4 commands.
6. Commit implementation for exactly one `TASK-NNN` and record the SHA.
7. Integrate according to the approved workflow plan.
8. Run matching `finish-attempt --attempt <n> --outcome PASS`; on failure use `FAIL` before deciding whether another attempt is available.
9. Update the TASK row in `progress.md` to `done` with actual start and completion dates after integration and PASS.

Allow at most three attempts per TASK. Do not overlap unfinished attempts. The runtime changes the run to BLOCKED on the third FAIL. After exhaustion, mark the TASK blocked, do not start dependents, allow independent TASKs to continue, and append every attempt's cause, change, and evidence to `implementation-ledger.md`.

Do not mix multiple TASK implementations in one commit. Integration commits may reference multiple TASKs. Require a complete TASK → commit mapping under `implementation-ledger.md` heading `## TASK-to-SHA Mapping`.

## Completion gate

Require:

- every approved TASK completed, or explicitly blocked with all dependents stopped;
- no blocked TASK when the requested scope is to proceed to PR;
- every required verification command passes;
- the integration worktree is clean after committed spec and implementation updates;
- `progress.md`, `change-log.md`, immutable `implementation-workflow.md`, `implementation-ledger.md`, and `run-state.json` reflect the exact target commit.
- deterministic preflight for `code-review` proves exact TASK equality, every TASK status `done`, and every mapped commit exists.
- bundled runtime `task-gate` returns `status: READY` before the launcher accepts implementation or remediation `COMPLETE`.

Print `VSDD RUN BLOCKED` with the TASK ID and evidence when the gate fails. On success, continue to separate fresh Opus code and security reviews.
