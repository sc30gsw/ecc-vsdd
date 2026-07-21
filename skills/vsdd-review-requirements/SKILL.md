---
name: vsdd-review-requirements
description: This skill should be used to independently review VSDD requirements for EARS quality, completeness, ambiguity, feasibility, acceptance criteria, and terminology drift.
---

# Skill: vsdd-review-requirements

## Mandatory execution routing

Delegate each review attempt to a new `vsdd-requirements-reviewer` (Opus, `xhigh`) with disk-only context. When already running as that reviewer, execute the checks below inline and do not delegate again. Never edit `requirements.md`; write only the review artifact.

## Invocation

```
/vsdd-review-requirements <slug>
```

**Arguments:**

- `<slug>` — kebab-case feature identifier matching an existing `.vsdd/specs/<slug>/` directory

---

## Purpose

Review `requirements.md` for completeness, clarity, EARS compliance, ambiguity, feasibility, terminology, and missing edge cases. Write a structured verdict to `.vsdd/specs/<slug>/review-results/requirement-review.md`. Mode changes presentation only; the pinned Opus reviewer and gate never change.

---

## Execution Steps

### Step 1: Read mode and validate prerequisites

Read `.vsdd/specs/<slug>/progress.md`:

- Extract `**Mode**:` value (`standard` or `auto`).
- Check that `vsdd-requirements` phase is marked `✅ complete`. If not, abort and instruct the user to run `/vsdd-requirements <slug>` first.
- If `progress.md` does not exist, abort and instruct the user to run `/vsdd-init <slug>` first.
- Create `.vsdd/specs/<slug>/review-results/` directory if it does not exist.

### Step 2: Load requirements.md

Read `.vsdd/specs/<slug>/requirements.md` in full.

- If the file contains only the placeholder comment (`<!-- Artifact not yet generated... -->`), abort and instruct the user to run `/vsdd-requirements <slug>` first.
- Count the number of REQ blocks for the review summary.

### Step 3: Independent review execution

Execute all checks in this file inside the single fresh pinned Opus reviewer. Consult authoritative stack documentation only when technical feasibility depends on a current external fact. Do not spawn inherited or ECC default reviewers whose model and effort are not pinned. Keep the review independent from the requirements author.

---

## Checks Performed

Run all checks below regardless of mode. Flag each finding with the REQ ID and severity.

### Check 1: EARS Format Compliance

- Each REQ block must contain: a User Story, a `When ... the system shall ...` clause, and at least 2 Acceptance Criteria.
- Missing any element → **HIGH**
- Using EARS keywords incorrectly (e.g. "Where" used instead of "When" for event-driven behavior) → **MEDIUM**

### Check 2: Ambiguous Terms

Scan all requirement text for vague qualifiers. Flag occurrences as **MEDIUM**:

- Adjectives: "fast", "slow", "easy", "simple", "appropriate", "reasonable", "sufficient"
- Quantities: "some", "many", "few", "several", "various", "etc.", "and so on"
- Time: "soon", "quickly", "immediately" (unless a specific duration is given)
- Replace suggestion: "Replace with a measurable criterion (e.g. 'within 2 seconds', 'up to 100 items')."

### Check 3: Missing Elements

- Missing actor (role) in User Story → **HIGH**
- Missing triggering event (When clause) → **HIGH**
- Missing system response (shall clause) → **HIGH**
- Requirement describes implementation, not behavior (e.g. "the database will store...") → **MEDIUM**

### Check 4: Testability

- Each Acceptance Criterion must be binary (pass/fail) and observable without access to internals.
- Subjective criteria ("looks good", "feels intuitive") → **HIGH**
- Criteria requiring knowledge of internal state not exposed to users → **MEDIUM**

### Check 5: Completeness

- No obvious error paths covered (e.g. what happens when an API call fails) → **MEDIUM**
- No empty state handling (e.g. what the user sees when the list is empty) → **MEDIUM**
- No permission / role boundary specified when the feature involves restricted access → **HIGH**
- No pagination or data limit stated for list-type features → **LOW**

### Check 6: REQ ID Numbering

- IDs must be sequential with no gaps → **LOW**
- Duplicate IDs → **HIGH**

### Check 7: Technical Feasibility (all modes)

- REQ requiring a non-existent API endpoint or interface → **HIGH**
- REQ assuming a capability (e.g. real-time push, background processing) not present in `tech.md` §1 Stack → **MEDIUM**
- REQ whose acceptance criteria would require bypassing the project's validation policy (`tech.md` §3 Conventions) → **MEDIUM**

### Check 8: Term Drift against Steering (both modes)

Cross-reference every domain term used in `requirements.md` against `.vsdd/specs/_steering/context.md`.

- Term used in REQ but not registered in `context.md` → **MEDIUM** (suggest: define the term in `context.md` via grill-with-docs, OR replace with a registered term)
- Term registered in `context.md` but used with a meaning that conflicts with the registered definition → **HIGH**
- New term flagged with `> **Glossary pending**: <term>` by `vsdd-requirements` → **MEDIUM** (must be resolved before `/vsdd-design`)

If `.vsdd/specs/_steering/context.md` is missing, abort the review with: "Run `/vsdd-steering` first to bootstrap the steering files."

---

## Output Format

Write the following to `.vsdd/specs/<slug>/review-results/requirement-review.md`:

```markdown
---
review_type: requirements
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

# Requirements Review: <slug>

**Date**: <YYYY-MM-DD>
**Reviewer**: vsdd-review-requirements skill
**Mode**: <standard|auto>
**Requirements reviewed**: <N> REQs (REQ-001 through REQ-NNN)

## Overall Assessment

<!-- 2-4 sentences: Is this requirements doc ready to proceed? What is the most critical concern? -->

## Findings

| REQ     | Issue               | Severity | Suggestion          |
| ------- | ------------------- | -------- | ------------------- |
| REQ-001 | <issue description> | HIGH     | <corrective action> |
| REQ-002 | <issue description> | MEDIUM   | <corrective action> |
| REQ-003 | <issue description> | LOW      | <corrective action> |

_Severity: CRITICAL/HIGH blocks the next phase; MEDIUM may proceed and remains visible; LOW is optional._

## Recommended Actions Before Proceeding

- [ ] **HIGH**: <action 1>
- [ ] **HIGH**: <action 2>
- [ ] **MEDIUM**: <action 3>

## Sign-off Condition

All CRITICAL/HIGH findings must be resolved before running `/vsdd-design <slug>`.
```

---

## change-log.md Update

After writing findings to requirement-review.md, append to `.vsdd/specs/<slug>/change-log.md`:

```
| <YYYY-MM-DD> | vsdd-review-requirements | requirement-review.md 作成 (<N> findings: M HIGH, N MEDIUM, P LOW) |
```

Also update `.vsdd/specs/<slug>/progress.md`:

```
## Phase: vsdd-review-requirements

**Status**: Complete
**Date**: <YYYY-MM-DD>
**Mode**: <standard|auto>
**Findings**: <N> total (M HIGH, N MEDIUM, P LOW)
```

Change `vsdd-review-requirements` status to `✅ complete` only for `verdict: PASS`; otherwise record `🔄 revise` or `⛔ blocked` with the attempt number.

---

## Notes

- Do not modify `requirements.md`. This skill is read-only with respect to requirements. The user must update requirements separately and rerun this skill if needed.
- Set `PASS` only when CRITICAL and HIGH are both zero.
- In `--mode auto`, present findings in plain language without jargon. Label each finding with its business impact rather than technical category (e.g. "Users won't know what to do if the upload fails" instead of "Missing error path for REQ-003").
- If `review-results/requirement-review.md` already exists, overwrite it with the new review (each run replaces the prior review). The prior review is preserved in `change-log.md`.

---

== PHASE COMPLETE: vsdd-review-requirements ==
Artifact: .vsdd/specs/<slug>/review-results/requirement-review.md
Summary:

- Mode read from progress.md
- requirements.md loaded and analyzed (N REQs)
- Checks run: EARS compliance, ambiguity, missing elements, testability, completeness, numbering, technical feasibility (standard only)
- Reviewer: fresh independent `vsdd-requirements-reviewer` (Opus xhigh)
- Findings written to review-results/requirement-review.md
- change-log.md updated with finding count
- progress.md updated: vsdd-review-requirements → complete

Gate: continue automatically only for `verdict: PASS`; otherwise revise with the Opus author and obtain a new fresh Opus review, up to three reviews total.
