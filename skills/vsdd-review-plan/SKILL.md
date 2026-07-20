---
name: vsdd-review-plan
description: This skill should be used to independently review the complete VSDD requirements, design, tasks, viewpoints, and REQ-to-TASK traceability before implementation.
---

# vsdd-review-plan

## Mandatory execution routing

Delegate each review attempt to a new `vsdd-plan-reviewer` (Opus, `xhigh`) with disk-only context. When already running as that reviewer, execute the checks below inline and do not delegate again. Never edit requirements, design, or tasks; write only the plan review artifact.

**Slash command**: `/vsdd-review-plan <slug>`
**Purpose**: Comprehensive pre-implementation review of requirements, design, and tasks. Writes "Traceability Coherence" and "Plan Review" findings to `review-results/plan-review.md`.

---

## Prerequisites

- `.claude/specs/<slug>/requirements.md` must exist
- `.claude/specs/<slug>/design.md` must exist
- `.claude/specs/<slug>/tasks.md` must exist
- `.claude/specs/<slug>/progress.md` must exist (used to read `mode`)
- `.claude/specs/<slug>/review-results/requirement-review.md` must exist (created by `vsdd-review-requirements`). If missing, abort: "Run `/vsdd-review-requirements <slug>` first."
- The set of every `TASK-NNN` heading in `tasks.md` must exactly equal the set of TASK rows in the `progress.md` Tasks table. Duplicate, missing, or extra IDs are a blocking traceability failure. In an orchestrated run, require the Status worker's deterministic `plan-review` preflight before launching this reviewer.

---

## Steps

### 1. Read all spec inputs

```
.claude/specs/<slug>/requirements.md
.claude/specs/<slug>/design.md
.claude/specs/<slug>/tasks.md
.claude/specs/<slug>/progress.md    (read mode: standard | auto)
.claude/specs/<slug>/review-results/requirement-review.md  (required — abort if missing)
.claude/specs/_steering/tech.md     (read §2 Design Viewpoints for Check I)
```

Build three indexes in memory:

- **REQ index**: all `REQ-XXX` IDs found in requirements.md
- **Design section index**: all `§X.X <title>` headings found in design.md
- **TASK index**: all `TASK-XXX` IDs found in tasks.md
- **Progress TASK index**: all `TASK-XXX` IDs found in the `progress.md` Tasks table

Before Check A, compare the TASK and Progress TASK indexes as sets and also reject duplicates in either source. On mismatch, write the structured review artifact with `verdict: REVISE`, name every missing/extra/duplicate ID, and stop. A non-empty table or a single matching row is never sufficient.

### 2. Run traceability coherence check (BOTH modes)

Run all checks below (A–I). For each check, record either ✅ (pass) or ❌ (fail) with specific IDs.

#### Check A — REQ → Design coverage

Every REQ-XXX in the REQ index appears in at least one `Satisfies:` line in design.md.

Failure example:

```
❌ REQ-004 has no Satisfies: line in design.md
   Fix: add "Satisfies: REQ-004" to the relevant design section
```

#### Check B — REQ → Task coverage

Every REQ-XXX in the REQ index appears in at least one `Implements:` line in tasks.md.

Failure example:

```
❌ REQ-006 has no Implements: entry in tasks.md
   Fix: add REQ-006 to an existing task's Implements field, or create TASK-NNN
```

#### Check C — Design → Task coverage

Every design section §X.X in the design section index appears in at least one `Design ref:` line in tasks.md.

Failure example:

```
❌ §7 Error Handling Strategy has no Design ref: entry in tasks.md
   Fix: add "Design ref: §7 Error Handling Strategy" to the relevant task
```

#### Check D — Task → REQ completeness

Every TASK-XXX in tasks.md has at least one `Implements:` entry (not empty).

Failure example:

```
❌ TASK-005 has no Implements: field
   Fix: add "Implements: REQ-XXX" to TASK-005
```

#### Check E — Dangling references

All REQ-XXX IDs referenced in `Satisfies:` or `Implements:` fields actually exist in the REQ index.
All §X.X references in `Design ref:` fields actually exist in the design section index.

Failure example:

```
❌ tasks.md TASK-003 references "Design ref: §9 Deployment" but §9 does not exist in design.md
   Fix: correct the section reference or add §9 to design.md
```

#### Check F — Duplicate IDs

No repeated REQ-XXX IDs in requirements.md.
No repeated TASK-XXX IDs in tasks.md.

Failure example:

```
❌ TASK-002 appears twice in tasks.md
   Fix: renumber the second occurrence
```

#### Check G — Structure Adherence

Every file path referenced in `design.md` File Structure Plan either:

- exists under an existing feature listed in `.claude/specs/_steering/structure.md`, OR
- is justified in the design as a new feature with a one-line responsibility note.

Failure example:

```
❌ design.md introduces src/features/foo/ but neither structure.md lists it nor design.md explains its responsibility
   Fix: either re-use an existing feature, or add a "New feature: foo — <responsibility>" section to design.md
```

#### Check H — ADR Citation

Every cross-cutting design decision (error handling, auth, state management) cites the relevant ADR via `Satisfies: ADR-NNNN` OR is itself flagged with `> **ADR candidate**: <rationale>` for follow-up.

Failure example:

```
❌ design.md §7 Error Handling Strategy does not cite ADR-0001 (error design)
   Fix: add "Satisfies: ADR-0001" to §7
```

#### Check I — Viewpoint coverage

Every Design Viewpoint listed in `.claude/specs/_steering/tech.md` §2 has a corresponding section in design.md.

Failure example:

```
❌ tech.md §2 lists "Data Model & Migration" but design.md has no such section
   Fix: add the missing viewpoint section to design.md (re-run /vsdd-design), or remove the viewpoint from tech.md via /vsdd-steering
```

If `tech.md` has no §2 Design Viewpoints section (old format), record Check I as ⚠️ skipped and recommend re-running `/vsdd-steering`.

If `.claude/specs/_steering/structure.md` is missing, abort with: "Run `/vsdd-steering` first to bootstrap the steering files."

### 3. Write Traceability Coherence table to `review-results/plan-review.md`

Write to `.claude/specs/<slug>/review-results/plan-review.md`:

```markdown
---
review_type: plan
target_commit: N/A
verdict: PASS|REVISE|BLOCKED
critical: <integer>
high: <integer>
medium: <integer>
low: <integer>
remediation_mode: none
reviewer_model: opus
reviewer_effort: xhigh
review_attempt: <1..3>
---

# Plan Review: <slug>

**Date**: <YYYY-MM-DD>
**Reviewer**: vsdd-review-plan skill
**Mode**: <standard|auto>
**Traceability**: ✅ All checks passed (or ⚠️ N failures)

## Traceability Coherence

| Check            | Result  | Details                               |
| ---------------- | ------- | ------------------------------------- |
| A: REQ → Design  | ✅ / ❌ | <!-- IDs or "all covered" -->         |
| B: REQ → Task    | ✅ / ❌ | <!-- IDs or "all covered" -->         |
| C: Design → Task | ✅ / ❌ | <!-- sections or "all covered" -->    |
| D: Task → REQ    | ✅ / ❌ | <!-- IDs or "all have Implements" --> |
| E: Dangling refs | ✅ / ❌ | <!-- broken refs or "none" -->        |
| F: Duplicate IDs | ✅ / ❌ | <!-- duplicates or "none" -->         |
| G: Structure     | ✅ / ❌ | <!-- unjustified new modules or "none" --> |
| H: ADR citation  | ✅ / ❌ | <!-- uncited cross-cutting decisions or "none" --> |
| I: Viewpoints    | ✅ / ❌ / ⚠️ | <!-- missing viewpoint sections or "all covered" --> |
```

### 4. Blocking gate — stop on any traceability failure

If ANY check is ❌, output the following and STOP. Do NOT output the PHASE COMPLETE gate.

```
⚠️ TRACEABILITY ERRORS FOUND — cannot proceed to implementation

The following issues must be fixed in the spec files before proceeding:

[list each ❌ with the specific IDs and how to fix]

Fix the issues listed above, then re-run /vsdd-review-plan <slug>.
```

Only continue to Step 5 if ALL checks (A–I) are ✅. Treat an old-format or skipped Check I as `REVISE`; Steering must be refreshed before implementation.

### 5. Independent plan review

Execute architecture, task-breakdown, scope, dependency, feasibility, and stack checks inside the single fresh pinned Opus reviewer. Consult authoritative stack documentation only when a current external fact is material. Do not spawn inherited or ECC default reviewers whose model and effort are not pinned. Mode changes presentation only, not review coverage or gating.

### 6. Write Plan Review to `review-results/plan-review.md`

Write findings to plan-review.md after the Traceability Coherence section:

```markdown
## Architecture & Design Review

| Section / 横断 | Issue | Severity | Suggestion |
| -------------- | ----- | -------- | ---------- |
| ...            | ...   | ...      | ...        |

## Task Breakdown Review

| Task / 横断 | Issue | Severity | Suggestion |
| ----------- | ----- | -------- | ---------- |
| ...         | ...   | ...      | ...        |

## Technology Stack Review (when relevant)

| 確認項目 | 結果 | 影響 |
| -------- | ---- | ---- |
| ...      | ...  | ...  |

## Recommended Actions Before Proceeding

- [ ] **HIGH**: <action 1>
- [ ] **HIGH**: <action 2>
- [ ] **MEDIUM**: <action 3>

## Sign-off Condition

All CRITICAL/HIGH findings and every failed A–I check must be resolved before `/vsdd-impl <slug>`.
```

---

## Output

```
.claude/specs/<slug>/review-results/plan-review.md    (created or overwritten)
```

---

## progress.md and change-log.md Update

After writing plan-review.md, set `vsdd-review-plan` to `✅ complete` only for `verdict: PASS`; otherwise record `🔄 revise` or `⛔ blocked` with the attempt number.

Append to `.claude/specs/<slug>/change-log.md`:

```
| <YYYY-MM-DD> | vsdd-review-plan | plan-review.md 作成 (Traceability: ✅/⚠️, <N> findings) |
```

---

## Phase Gate

Only output this block when all A–I traceability checks are ✅, CRITICAL/HIGH are zero, and `verdict: PASS`:

```
== PHASE COMPLETE: vsdd-review-plan ==
Artifact: .claude/specs/<slug>/review-results/plan-review.md
Summary:
- All traceability coherence checks passed (A–I)
- Plan reviewed by a fresh independent Opus xhigh reviewer
- Key risks and open questions documented in review-results/plan-review.md
- Spec is ready for implementation
- Run /vsdd-impl <slug> to begin the whole-task Dynamic Workflow

Gate: continue automatically only for `verdict: PASS`; otherwise revise with the owning pinned author and obtain a new fresh Opus review, up to three reviews total.
```
