# Dynamic implementation contract

## Planning stage

Start a dedicated Sonnet session with `--effort ultracode` and `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` through the bundled detached launcher. Poll its exact supervisor evidence in foreground calls until terminal; reuse a live supervisor for the same stage after compaction or resume. Read the complete approved `tasks.md` and use a Dynamic Workflow to write `.claude/specs/<slug>/implementation-workflow.md` before changing code.

The dedicated session and every Dynamic Workflow agent run unattended. They must never ask for permission or user input, must use Read/Glob/Grep instead of shell `cat`/`sed`/`head`/`tail` for persisted `.claude/specs` artifacts, and must remain alive until a background Workflow sends its completion notification. A running background Workflow is not a `BLOCKED` result. Inspect its terminal result and required files before returning the single final structured result.

Every launcher stage must return the exact current Workflow tool run ID as `workflow_run_id`. Plan and plan-revision stages must persist newly generated content; an unchanged pre-existing `implementation-workflow.md` is never completion evidence. Record the current `wf_...` ID in the plan so the launcher can reject stale artifact reuse.

Record:

- inferred TASK dependency DAG;
- parallel groups and integration order;
- TASK worktree and branch assignments;
- validation commands per TASK;
- Red → Green → Refactor checkpoints;
- commit order and integration rules;
- stopping conditions and retry policy.

Pause after the planning workflow. A fresh Opus `xhigh` agent must review the file. Allow the initial review and at most two Sonnet plan revisions, for at most three Opus reviews. Block after the third failed review.

## Implementation stage

Resume the same Sonnet session only after `verdict: PASS`. Let the Dynamic Workflow decide execution order, parallelism, and worktree use from the approved plan. Do not pass TASKs individually from Fable.

Treat the approved `implementation-workflow.md` as immutable. Create `.claude/specs/<slug>/implementation-ledger.md` for runtime state with Red/Green/Refactor evidence, attempt history, validation results, integration evidence, and an exact `## TASK-to-SHA Mapping` table.

Allow at most three attempts per TASK. After the third failure:

- mark the TASK blocked;
- do not start dependent TASKs;
- allow independent TASKs to continue;
- append retry cause, change, and evidence to `implementation-ledger.md`.

Before each TASK attempt, call the bundled runtime `begin-attempt --scope implementation-task --task-id TASK-NNN`. Use its returned attempt number in the ledger. After validation, call `finish-attempt` with the same number and `--outcome PASS` or `FAIL`. Do not start another attempt until the previous one is finished. A TASK is not eligible for Code Review until its current mechanical attempt record ends in PASS; the third FAIL changes the run to `BLOCKED` immediately.

Require each implementation commit to name one `TASK-NNN`. Do not mix implementation for multiple TASKs in one commit. Allow integration commits to cite multiple TASKs. Record every TASK-to-SHA mapping in `implementation-ledger.md` under the exact heading `## TASK-to-SHA Mapping`.

## Review remediation

Use a fresh Sonnet `high` ordinary remediation worker first. Use Sonnet `ultracode` immediately when either Opus report says `remediation_mode: workflow`, or on the second remediation round when blocking findings remain. Run fresh code and security Opus reviews after every round. Block after the initial review plus two remediation/re-review rounds.

The Status worker begins each paired Code/Security round once with scope `post-implementation-review`. Remediation changes invalidate both prior report snapshots but preserve this counter so the next pair is monotonically numbered. A genuine upstream plan or implementation invalidation resets it.
