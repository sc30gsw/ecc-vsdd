# vsdd-workflow — Workflow Status Dashboard

## Slash Command

```
/vsdd-workflow [slug]
```

## Purpose

Read-only meta skill. Displays the current state of the VSDD workflow — which phases are complete, which is next, and any blockers. Does NOT modify any files.

---

## This Skill is Read-Only

`vsdd-workflow` never writes to or modifies any file. It only reads spec files and git history to report status. There is no approval gate for this skill.

---

## Usage: Specific Feature

```
/vsdd-workflow <slug>
```

Reads `.claude/specs/<slug>/` and displays the full phase chain with status:

```
VSDD Workflow: <slug>
Mode: standard | auto
Branch: feature/<slug> (12 commits ahead of main)

Phase Chain:
[✅] vsdd-init              — source-notion.md archived
[✅] vsdd-requirements      — requirements.md: 5 REQs defined
[✅] vsdd-review-requirements — requirement-review.md: Requirements Review present
[✅] vsdd-design            — design.md: 8 sections
[✅] vsdd-tasks             — tasks.md: 12 TASKs defined
[✅] vsdd-review-plan       — plan-review.md: Plan Review + Traceability ✅
[🔄] vsdd-impl              — progress: 3/12 done, TASK-004 in-progress
[⏳] vsdd-review            — waiting for vsdd-impl to complete
[⏳] vsdd-pr                — waiting

Next action: /vsdd-impl <slug> TASK-004   (resume in-progress task)
       or:   CONFIRM vsdd-impl            (if paused at a gate)
```

Status icons:

| Icon | Meaning               |
| ---- | --------------------- |
| ✅   | Phase complete        |
| 🔄   | Phase in progress     |
| ⚠️   | Phase has a blocker   |
| ⏳   | Phase not yet started |

---

## Usage: All Features

```
/vsdd-workflow
```

Lists all spec directories under `.claude/specs/` and shows each feature's current phase:

```
VSDD Workflow Overview
Specs directory: .claude/specs/

slug                     | current phase  | status
-------------------------|----------------|-----------------------------------
user-authentication      | vsdd-impl       | 🔄 3/8 tasks done
mail-group-bulk-delete   | vsdd-pr         | ✅ PR #42 open
supplier-csv-export      | vsdd-design     | ⏳ not started
```

If `.claude/specs/` is empty or does not exist:

```
No spec directories found under .claude/specs/
Run /vsdd-init <slug> to start a new feature.
```

---

## Phase Detection Logic

Each phase is detected by inspecting files inside `.claude/specs/<slug>/`. Detection is sequential: if a phase's condition is not met, all subsequent phases show `⏳`.

| Phase                     | Detected When                                                                           |
| ------------------------- | --------------------------------------------------------------------------------------- |
| `vsdd-init`                | `source-notion.md` exists OR the `<slug>` directory itself exists                       |
| `vsdd-requirements`        | `requirements.md` exists AND contains at least one `## REQ-` heading                    |
| `vsdd-review-requirements` | `review-results/requirement-review.md` exists                                           |
| `vsdd-design`              | `design.md` exists (any non-empty content)                                              |
| `vsdd-tasks`               | `tasks.md` exists AND contains at least one `### TASK-` heading                         |
| `vsdd-review-plan`         | `review-results/plan-review.md` exists AND contains no `❌` in its Traceability section |
| `vsdd-impl`                | `progress.md` has at least one task marked `done`                                       |
| `vsdd-review`              | `review-results/code-review.md` exists                                                  |
| `vsdd-pr`                  | `progress.md` contains a `## PR` section with a URL                                     |

---

## Progress Metrics (vsdd-impl)

When `vsdd-impl` is the current phase, show task completion metrics by parsing `progress.md`:

```
[🔄] vsdd-impl — progress: 3/12 done (25%), 1 in-progress, 8 pending
     In-progress: TASK-004 (Create supplier CSV export hook)
     Last completed: TASK-003 (Add export button to supplier table)
```

Count tasks by status by reading the `## Tasks` table in `progress.md`:

- `done`: table rows with `| done |` in the Status column
- `in-progress`: table rows with `| in-progress |` in the Status column
- `pending`: table rows with `| pending |` in the Status column

---

## Blocker Detection

For the currently active or blocked phase, surface known blockers:

| Phase        | Blocker Condition                                                               | Warning Message                                         |
| ------------ | ------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `vsdd-impl`   | `review-results/plan-review.md` does not exist                                  | ⚠️ Run /vsdd-review-plan \<slug\> before implementing    |
| `vsdd-review` | `progress.md` has tasks still `pending`                                         | ⚠️ N tasks still pending — run /vsdd-impl \<slug\> first |
| `vsdd-pr`     | `review-results/code-review.md` has unchecked `- [ ]` items under `## CRITICAL` | ⚠️ Resolve all CRITICAL issues before creating PR       |
| `vsdd-pr`     | `review-results/code-review.md` does not exist                                  | ⚠️ Run /vsdd-review \<slug\> before creating PR          |

Blockers appear with ⚠️ next to the phase name and a `Blocker:` line in the output.

---

## Git Branch Detection

Display the current branch and commit count:

```bash
git branch --show-current
git log main...HEAD --oneline | wc -l
```

Output:

```
Branch: feature/user-authentication (12 commits ahead of main)
```

If the current branch does not match the slug:

```
⚠️ Current branch (feature/other-thing) does not match slug (user-authentication)
   Switch to the correct branch before running implementation or review skills.
```

---

## Full Phase Chain Reference

The complete VSDD skill chain in order:

```
1. vsdd-init                — Archive Notion source, create spec directory
2. vsdd-requirements        — Write requirements.md from source-notion.md
3. vsdd-review-requirements — Review requirements, write to review-results/requirement-review.md
4. vsdd-design              — Write design.md (architecture, components, API)
5. vsdd-tasks               — Write tasks.md (TASK-xxx breakdown)
6. vsdd-review-plan         — Review plan, verify traceability, write to review-results/plan-review.md
7. vsdd-impl                — TDD implementation, one commit per task
8. vsdd-review              — Code + security review, write to review-results/code-review.md
9. vsdd-pr                  — Create GitHub PR with traceability and test plan
```

---

## Example: Fully Complete Feature

```
VSDD Workflow: user-authentication
Mode: auto
Branch: feature/user-authentication (12 commits ahead of main)

Phase Chain:
[✅] vsdd-init              — source-notion.md archived
[✅] vsdd-requirements      — requirements.md: 5 REQs (REQ-001 through REQ-005)
[✅] vsdd-review-requirements — requirement-review.md: Requirements Review present
[✅] vsdd-design            — design.md: 6 sections
[✅] vsdd-tasks             — tasks.md: 12 TASKs defined
[✅] vsdd-review-plan       — plan-review.md: Plan Review, Traceability ✅
[✅] vsdd-impl              — progress: 12/12 done
[✅] vsdd-review            — code-review.md: Code Review (2026-05-26), 0 CRITICAL, 2 HIGH open
[⏳] vsdd-pr                — waiting

Next action: /vsdd-pr user-authentication
```
