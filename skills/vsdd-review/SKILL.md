# vsdd-review — Post-Implementation Code Review

## Slash Command

```
/vsdd-review <slug>
```

## Purpose

Run code review and security review on all changes introduced by the feature branch. Write structured findings to `review-results/code-review.md`. Does NOT auto-apply fixes — only proposes them. Stack-agnostic: project-specific rules come from `.claude/specs/_steering/tech.md`.

---

## Prerequisites

- `vsdd-impl` has completed: all tasks in `progress.md` are `done` (or at least one is `done`; partial reviews are allowed).
- The feature branch must have at least one commit ahead of `main`.

---

## Input Files

| File                                                 | Purpose                                               |
| ---------------------------------------------------- | ----------------------------------------------------- |
| `.claude/specs/<slug>/requirements.md`               | Acceptance criteria to compare against implementation |
| `.claude/specs/<slug>/tasks.md`                      | Task scope (which files were changed)                 |
| `.claude/specs/<slug>/progress.md`                   | Task completion status and mode setting               |
| `.claude/specs/<slug>/review-results/plan-review.md` | Reference for plan context                            |
| `.claude/specs/_steering/tech.md`                    | §3 Conventions → project-layer checklist              |

---

## Mode Behavior

Both `standard` and `auto` modes run the same three reviews. The mode difference is in how findings are presented:

| Aspect                   | `standard` (engineer-led)                           | `auto` (AI-led)                                         |
| ------------------------ | --------------------------------------------------- | ------------------------------------------------------- |
| CRITICAL / HIGH findings | Listed in `code-review.md`, engineer decides action | Auto-fix proposals generated inline in `code-review.md` |
| MEDIUM / LOW findings    | Listed, engineer decides                            | Listed, no auto-proposals                               |
| Fix application          | Never auto-applied                                  | Never auto-applied                                      |

---

## Steps

### 1. Get the Feature Diff

```bash
git diff main...HEAD
git log main...HEAD --oneline
```

If the project uses a different base branch (e.g., `develop`), use that. The base branch defaults to `main` unless `progress.md` specifies otherwise.

Both the diff and the log serve as input for all three review steps.

### 2. Code Review (Step 1)

Invoke Claude Code's native `code-review` skill with `--effort xhigh`.

The checklist has two layers:

**Layer 1 — Process checks (fixed, stack-independent):**

| Area          | What to check                                                              |
| ------------- | --------------------------------------------------------------------------- |
| Correctness   | Logic matches acceptance criteria in `requirements.md`                      |
| Scope         | Diff stays within the File Structure Plan of `design.md` (no scope creep)   |
| Traceability  | Every commit references a TASK-XXX; no unexplained files in the diff        |
| Test coverage | Every file in design.md Test Strategy has its planned tests, and they pass  |
| Immutability  | No direct object mutation                                                   |
| Comments      | Non-obvious logic has comments explaining WHY, not WHAT                     |
| File size     | Source files under 800 lines; ideally 200–400 lines                        |
| Debug output  | No leftover debug logging in committed code                                 |

**Layer 2 — Project checks (dynamic, from tech.md):**

Read `.claude/specs/_steering/tech.md` §3 Conventions. For EACH rule listed there (error handling, validation, imports/exports, naming, test placement, ...), verify the diff complies, and cite the violated rule verbatim in the finding. If tech.md §3 links to rule files (e.g. `.claude/rules/*.md`), check against the linked files too.

If tech.md has no §3 Conventions section (old format), add a MEDIUM finding "project-layer checks skipped — re-run /vsdd-steering" and continue with Layer 1 only.

### 3. ECC Code Review (Step 2)

Invoke the `/ecc:code-review` command (local mode — no PR number) for a systematic 7-category review complementing the native review above:

| Category           | What to check                                                                    |
| ------------------ | --------------------------------------------------------------------------------- |
| Correctness        | Logic errors, off-by-ones, null handling, edge cases, race conditions             |
| Type Safety        | Type mismatches, unsafe casts, escape hatches (`any` etc.), missing generics      |
| Pattern Compliance | Matches tech.md §3 Conventions (naming, file structure, error handling, imports)  |
| Security           | Injection, auth gaps, secret exposure, SSRF, XSS, path traversal                  |
| Performance        | N+1 queries, unbounded loops, memory leaks, large payloads                        |
| Completeness       | Missing tests, missing error handling, missing docs                               |
| Maintainability    | Dead code, magic numbers, deep nesting, unclear naming, missing types             |

### 4. Security Review (Step 3)

Use the `ecc:security-review` skill for the security checklist. VSDD review targets application code — use `security-review`, not the `security-scan` command (which audits `.claude/` configuration via AgentShield, not application code).

Focus areas:

| Area                  | What to check                                                                             |
| --------------------- | ------------------------------------------------------------------------------------------ |
| Secrets               | No hardcoded API keys, tokens, or passwords                                                |
| Input validation      | User input validated at system boundaries per the validation policy in tech.md §3          |
| Authentication        | Auth handling confined to the project's designated auth layer (tech.md §3 / structure.md)  |
| Injection             | No unsanitized HTML rendering, SQL string interpolation, or shell command construction     |
| Sensitive data        | No PII/credentials in error messages, URLs, or logs                                        |
| Environment variables | Sensitive values loaded from environment configuration; fail fast if undefined             |

### 4.5. Steering Drift Check (both modes)

Cross-reference the diff against `.claude/specs/_steering/`:

| Check                                      | What to verify                                                                                                                        |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| New feature/module added                   | `.claude/specs/_steering/structure.md` lists the new module; if not, add a finding: "structure.md is stale — re-run `/vsdd-steering`"   |
| New exported types/schemas/functions       | They appear in `structure.md` for the relevant module                                                                                   |
| New domain term introduced                 | Term is registered in `.claude/specs/_steering/context.md` (not just used in code)                                                      |
| New library added to a dependency manifest | `.claude/specs/_steering/tech.md` §1 Stack lists it                                                                                     |
| Cross-cutting architectural change         | Either cites an ADR or carries a `> **ADR candidate**` flag in `design.md`                                                              |

Findings from this check go under a `## Steering Drift` section in `code-review.md` with severity `MEDIUM` (unless the drift indicates a coherence break — then `HIGH`).

If `.claude/specs/_steering/` is missing, abort with: "Run `/vsdd-steering` first to bootstrap the steering files."

### 5. Write to `review-results/code-review.md`

Merge findings from all three reviews (native code-review + ecc:code-review + ecc:security-review) into a single `code-review.md`. Tag each finding line with its source in brackets: `[code-review]`, `[ecc:code-review]`, or `[security-review]`. Deduplicate findings that appear in multiple reviews.

Create `.claude/specs/<slug>/review-results/code-review.md` with the following content:

```markdown
# Code Review: <slug>

**Date**: YYYY-MM-DD
**Reviewer**: vsdd-review skill
**Mode**: <standard|auto>
**Scope**: git diff main...HEAD — N files changed

## CRITICAL

- [ ] [FILE:LINE] [code-review | ecc:code-review | security-review] Description of critical issue

## HIGH

- [ ] [FILE:LINE] [code-review | ecc:code-review] Description of high-priority issue

## MEDIUM

- [ ] [FILE:LINE] [ecc:code-review] Description of medium-priority issue

## LOW

- [ ] [FILE:LINE] [code-review] Description of low-priority issue

## Passed Checks

- Process layer: scope, traceability, test coverage all green
- Project layer: all tech.md §3 conventions complied with
- (other passing items)

---

## Security Review

### CRITICAL

(none)

### HIGH

- [ ] [FILE:LINE] [security-review] Description of security issue

### MEDIUM

- [ ] [FILE:LINE] [security-review] Description of security issue

### LOW

(none)

### Passed Checks

- No hardcoded secrets found
- Input validation present at system boundaries
- (other passing items)
```

Use `YYYY-MM-DD` format for the date (e.g., `2026-05-26`).

If `code-review.md` already exists (re-run), append a new section `## Re-Review (YYYY-MM-DD)` at the bottom.

### 6. Auto-Fix Proposals (`auto` mode only)

For each CRITICAL or HIGH finding, append a proposal block immediately after the finding item:

````markdown
- [ ] [src/foo/service.ts:42] [ecc:code-review] Violates tech.md §3 error-handling convention

  **Proposed fix:**

  ```
  // Before
  <the offending code from the diff>

  // After
  <the same logic rewritten to match the convention cited from tech.md §3>
  ```
````

```

Do NOT apply the fix. The engineer applies it manually or addresses it before running `vsdd-pr`. In `standard` mode, no proposals are generated — the engineer reviews the diff directly.

---

## Output Files Modified

| File                                                 | Change                                                     |
| ---------------------------------------------------- | ---------------------------------------------------------- |
| `.claude/specs/<slug>/review-results/code-review.md` | Created with Code Review (native + ECC) + Security Review  |
| `.claude/specs/<slug>/change-log.md`                 | Phase completion event appended                            |

No source files are modified by this skill.

---

## Approval Gate

Update `.claude/specs/<slug>/progress.md`: change `vsdd-review` from `⬜ not started` to `✅ complete` in the Phase Status table.

Append to `.claude/specs/<slug>/change-log.md`:

```

| <YYYY-MM-DD> | vsdd-review | code-review.md 作成 (<N> findings: M CRITICAL, N HIGH, P MEDIUM, Q LOW) |

```

```

== PHASE COMPLETE: vsdd-review ==
Artifact: .claude/specs/<slug>/review-results/code-review.md
Summary:

- Code review complete (native + ECC): 0 CRITICAL, 2 HIGH, 3 MEDIUM, 1 LOW
- Security review complete: 0 CRITICAL, 1 HIGH, 0 MEDIUM
- Total open issues requiring action: 3 HIGH
- Auto-fix proposals generated for all HIGH findings (auto mode only)
- No source files were modified

⏸ WAITING FOR CONFIRMATION
Type `CONFIRM vsdd-pr` to proceed to PR creation, or describe changes needed.

```

> **Warning**: If any CRITICAL findings remain unresolved, the gate message will prominently flag this. Proceeding to `vsdd-pr` with open CRITICAL issues is strongly discouraged — resolve them first and re-run `/vsdd-review <slug>`.
```
