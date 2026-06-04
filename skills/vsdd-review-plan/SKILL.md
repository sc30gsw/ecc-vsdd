# vsdd-review-plan

**Slash command**: `/vsdd-review-plan <slug>`
**Purpose**: Comprehensive pre-implementation review of requirements, design, and tasks. Writes "Traceability Coherence" and "Plan Review" findings to `review-results/plan-review.md`.

---

## Prerequisites

- `.claude/specs/<slug>/requirements.md` must exist
- `.claude/specs/<slug>/design.md` must exist
- `.claude/specs/<slug>/tasks.md` must exist
- `.claude/specs/<slug>/progress.md` must exist (used to read `mode`)
- `.claude/specs/<slug>/review-results/requirement-review.md` must exist (created by `vsdd-review-requirements`). If missing, abort: "Run `/vsdd-review-requirements <slug>` first."

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

### 4. CRITICAL gate — stop on any traceability failure

If ANY check is ❌, output the following and STOP. Do NOT output the PHASE COMPLETE gate.

```
⚠️ TRACEABILITY ERRORS FOUND — cannot proceed to implementation

The following issues must be fixed in the spec files before proceeding:

[list each ❌ with the specific IDs and how to fix]

Fix the issues listed above, then re-run /vsdd-review-plan <slug>.
```

Only continue to Step 5 if ALL checks (A–I) are ✅ (Check I may be ⚠️ skipped on old-format tech.md — recommend `/vsdd-steering` re-run).

### 5. Mode-specific plan review

**`--mode standard`**:

1. Invoke `ecc:docs-lookup` agent (stack documentation gathering)
   - Fetch current documentation for each technology from `.claude/specs/_steering/tech.md` §1 Stack that design.md references
   - Output: stack capability summary and known constraints to pass to subsequent agents
2. Invoke `ecc:planner` agent with the full requirements + design + tasks context
   - Focus: scope completeness, task ordering risks, dependency gaps, missing scenarios
3. Invoke `ecc:architect` agent with the full context + stack documentation from step 1
   - Focus: architectural soundness, technology fit, implementation risks, design section gaps
4. Collect all findings

**`--mode auto`**:

1. Invoke `ecc:architect` agent only (skip ecc:planner agent and ecc:docs-lookup agent)
2. Collect findings

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

## Technology Stack Review (standard mode only)

| 確認項目 | 結果 | 影響 |
| -------- | ---- | ---- |
| ...      | ...  | ...  |

## Recommended Actions Before Proceeding

- [ ] **HIGH**: <action 1>
- [ ] **HIGH**: <action 2>
- [ ] **MEDIUM**: <action 3>

## Sign-off Condition

All HIGH severity findings must be resolved before running `/vsdd-impl <slug>`.
```

---

## Output

```
.claude/specs/<slug>/review-results/plan-review.md    (created or overwritten)
```

---

## progress.md and change-log.md Update

After writing plan-review.md, update `.claude/specs/<slug>/progress.md`: change `vsdd-review-plan` from `⬜ not started` to `✅ complete`.

Append to `.claude/specs/<slug>/change-log.md`:

```
| <YYYY-MM-DD> | vsdd-review-plan | plan-review.md 作成 (Traceability: ✅/⚠️, <N> findings) |
```

---

## Phase Gate

Only output this block when ALL six traceability checks are ✅ AND plan review is complete:

```
== PHASE COMPLETE: vsdd-review-plan ==
Artifact: .claude/specs/<slug>/review-results/plan-review.md
Summary:
- All traceability coherence checks passed (A–I)
- Plan reviewed by ecc:architect agent (+ ecc:planner + ecc:docs-lookup agents in standard mode; docs-lookup runs first for stack context)
- Key risks and open questions documented in review-results/plan-review.md
- Spec is ready for implementation
- Run /vsdd-impl <slug> TASK-001 to begin

⏸ WAITING FOR CONFIRMATION
Type `CONFIRM vsdd-impl` to proceed with implementation, or describe changes needed.
```
