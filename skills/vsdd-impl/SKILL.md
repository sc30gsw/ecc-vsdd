# vsdd-impl — Implement Tasks (TDD)

## Slash Command

```
/vsdd-impl <slug> [task-id]
```

## Purpose

Implement one task (or all pending tasks) for a spec using strict Test-Driven Development. Delegates test/implementation cycles to the `/ecc:tdd-workflow` skill and keeps `progress.md` up to date throughout. Stack-agnostic: conventions and commands come from `.claude/specs/_steering/tech.md`.

---

## Prerequisites

Before running this skill, confirm:

- `vsdd-review-plan` has been run: `review-results/plan-review.md` must exist and contain no `❌` in the Traceability section.
- `tasks.md` exists and has at least one task in `pending` status.
- `.claude/specs/_steering/tech.md` exists with §3 Conventions and §4 Verification Commands. If the sections are missing (old format), pause and recommend re-running `/vsdd-steering`; continue only on explicit user approval, falling back to generic best practices.

If the plan review is missing, stop and instruct the user to run `/vsdd-review-plan <slug>` first.

---

## Input Files

| File                                                 | Purpose                                           |
| ---------------------------------------------------- | ------------------------------------------------- |
| `.claude/specs/<slug>/tasks.md`                      | Task definitions and acceptance criteria          |
| `.claude/specs/<slug>/progress.md`                   | Current task statuses and mode setting            |
| `.claude/specs/<slug>/design.md`                     | Architecture decisions guiding implementation     |
| `.claude/specs/<slug>/review-results/plan-review.md` | Checked for Plan Review completion                |
| `.claude/specs/_steering/tech.md`                    | §3 Conventions (rules) + §4 Verification Commands |

---

## Mode Behavior

Read `mode` from `progress.md` by extracting the `**Mode**:` value:

```markdown
**Mode**: standard
```

| Aspect                          | `standard` (engineer-led)                       | `auto` (AI-led)                                           |
| ------------------------------- | ----------------------------------------------- | --------------------------------------------------------- |
| After RED phase                 | Pause — show failing test, wait for `CONFIRM`   | Proceed automatically                                     |
| After GREEN phase               | Pause — show implementation, wait for `CONFIRM` | Proceed automatically                                     |
| After REFACTOR phase            | Pause — show final state, wait for `CONFIRM`    | Post summary and proceed to next task                     |
| On verification command failure | Stop, show error, ask for guidance              | Attempt self-fix up to 3 iterations, then stop and report |

---

## Steps

### 1. Determine Which Task to Implement

```
If [task-id] is provided:
  - Locate that task in tasks.md
  - Verify its status in progress.md is "pending" (or "in-progress" if resuming)
  - Warn if the task is already "done"

Otherwise:
  - Find the first task with status "in-progress" in progress.md (resume case)
  - If none, find the first task with status "pending"
  - If all tasks are "done", report completion and skip to the gate
```

### 2. Mark Task as In-Progress

Update the task row in the `## Tasks` table in `progress.md`:

```markdown
<!-- Before -->

| TASK-001 | Create user schema | pending | — | — |

<!-- After -->

| TASK-001 | Create user schema | in-progress | <YYYY-MM-DD> | — |
```

### 3. TDD Cycle via `/ecc:tdd-workflow`

Invoke the `/ecc:tdd-workflow` skill for the selected task. Pass the task's acceptance criteria as the specification. Throughout the cycle, use the commands from **tech.md §4 Verification Commands** — referred to below as `<test command>` and `<all verification commands>`.

**RED phase — Write failing test:**

- Place the test file per the project's test placement convention (tech.md §3; e.g. co-located with source, or under a parallel `spec/` / `test/` tree)
- Target the acceptance criteria from `tasks.md` directly
- Run `<test command>` — confirm the test fails for the right reason
- In `standard` mode: pause and display the failing test output

**GREEN phase — Minimal implementation:**

- Write the minimum code to make the test pass
- Apply every rule from tech.md §3 Conventions (see below)
- Run `<test command>` — confirm the test passes
- In `standard` mode: pause and display the passing test output

**REFACTOR phase — Clean up:**

- Remove duplication, improve naming, add comments per project conventions (explain WHY, not WHAT)
- Run `<all verification commands>` (lint / format / type check / test) — all must pass with no errors
- In `standard` mode: pause and display the final state

### 4. Commit

After each task completes its TDD cycle:

```bash
git add <changed files>
git commit -m "feat(TASK-001): <task title from tasks.md>"
```

Use the exact task ID and title from `tasks.md`. Follow Conventional Commits format.

### 5. Update `progress.md`

Update the task row in the `## Tasks` table:

```markdown
<!-- After completion -->

| TASK-001 | Create user schema | done | <YYYY-MM-DD> | <YYYY-MM-DD> |
```

### 6. Repeat

If no `[task-id]` was given (`auto` mode or batch run), loop back to Step 1 and pick the next `pending` task. Continue until all tasks are `done` or the user interrupts.

---

## Project Constraints (Enforced at Every Commit)

**The constraint list lives in `.claude/specs/_steering/tech.md` — not here.**

At the start of every task:

1. Read **tech.md §3 Conventions** — every rule there (error handling, validation, imports/exports, naming, test placement, etc.) is non-negotiable for the diff being committed.
2. Read **tech.md §4 Verification Commands** — run ALL of them before every commit; a failing command blocks the commit.
3. If tech.md §3 links to rule files (e.g. `.claude/rules/*.md`), read the linked files for the precise patterns and apply them.

If a task cannot satisfy a convention, do NOT silently deviate — stop and surface the conflict to the user (it may be an ADR candidate).

---

## Session Resume

If the session was interrupted mid-task, re-run:

```
/vsdd-impl <slug>
```

The skill reads the `## Tasks` table in `progress.md`, finds any row with `| in-progress |` in the Status column, and resumes from the appropriate TDD phase. If no `in-progress` row exists, it picks the first row with `| pending |`.

---

## Output Files Modified

| File                                 | Change                             |
| ------------------------------------ | ---------------------------------- |
| `.claude/specs/<slug>/progress.md`   | Task statuses updated              |
| `.claude/specs/<slug>/change-log.md` | Phase completion event appended    |
| Source tree (per design.md §3)       | New/modified source and test files |
| `git history`                        | One commit per completed task      |

---

## Approval Gate

After all specified tasks complete (or a single task if `[task-id]` was given):

Update `.claude/specs/<slug>/progress.md`: change `vsdd-impl` from `⬜ not started` to `✅ complete` in the Phase Status table.

Append to `.claude/specs/<slug>/change-log.md`:

```
| <YYYY-MM-DD> | vsdd-impl | 実装完了 (<N> tasks, <M> commits) |
```

```
== PHASE COMPLETE: vsdd-impl ==
Artifact: .claude/specs/<slug>/progress.md
Summary:
- Implemented TASK-001 through TASK-003 (3 tasks)
- All tests pass (tech.md §4 test command green)
- All verification commands pass (lint / format / type check)
- Commits: feat(TASK-001), feat(TASK-002), feat(TASK-003)
- Remaining pending tasks: TASK-004 through TASK-012

⏸ WAITING FOR CONFIRMATION
Type `CONFIRM vsdd-review` to proceed to code review, or describe changes needed.
```
