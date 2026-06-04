# vsdd-pr — Create Pull Request

## Slash Command

```
/vsdd-pr <slug>
```

## Purpose

Create a GitHub Pull Request enriched with VSDD-specific content: a REQ → TASK → commit traceability table, review summary, and an acceptance-criteria-derived test plan checklist. Builds the full PR body and creates the PR directly via `gh pr create`.

---

## Prerequisites

- `vsdd-review` has been run: `review-results/code-review.md` must exist.
- No unresolved CRITICAL findings in `review-results/code-review.md` (see Warning below).

---

## Input Files

| File                                                 | Purpose                                   |
| ---------------------------------------------------- | ----------------------------------------- |
| `.claude/specs/<slug>/requirements.md`               | REQ definitions and acceptance criteria   |
| `.claude/specs/<slug>/tasks.md`                      | TASK definitions with REQ references      |
| `.claude/specs/<slug>/design.md`                     | Architecture summary for PR context       |
| `.claude/specs/<slug>/progress.md`                   | Task completion status and mode setting   |
| `.claude/specs/<slug>/review-results/code-review.md` | Review findings to surface in the PR body |

---

## Mode Behavior

Both `standard` and `auto` modes produce the same PR content.

| Aspect                   | `standard`                             | `auto`                                |
| ------------------------ | -------------------------------------- | ------------------------------------- |
| Before creating PR       | Show draft PR body, wait for `CONFIRM` | Create PR immediately                 |
| If CRITICAL issues exist | Stop and require user decision         | Stop and require user decision (same) |

---

## Steps

### 1. Pre-flight: Check for CRITICAL Issues

Read `.claude/specs/<slug>/review-results/code-review.md`. Search for unchecked CRITICAL findings:

```markdown
## CRITICAL

- [ ] ... ← unchecked = still open
- [x] ... ← checked = resolved
```

If any unchecked CRITICAL findings exist, output:

```
WARNING: Open CRITICAL issues found in code-review.md:
  - [src/features/foo/api/mutations.ts:42] Description of issue

Resolve all CRITICAL issues before creating the PR.
After fixing, re-run /vsdd-review <slug> to update code-review.md.
```

Stop. Do not proceed until the user explicitly confirms they want to continue (exceptional case only, e.g., known false positive).

### 2. Build the Traceability Table

Collect commits on the feature branch that reference task IDs:

```bash
git log main...HEAD --oneline --grep="TASK-"
```

Parse each `### TASK-xxx` block in `tasks.md` for its linked REQ ID (look for `REQ-xxx` references in the task description or metadata).

Build the table:

```markdown
| REQ        | Description                         | Tasks              | Key Commits                              |
| ---------- | ----------------------------------- | ------------------ | ---------------------------------------- |
| REQ-001    | User can log in with email/password | TASK-001, TASK-002 | feat(TASK-001): Create login schema      |
| REQ-002    | Show validation errors inline       | TASK-003           | feat(TASK-003): Add inline error display |
| (Untraced) | —                                   | TASK-012           | feat(TASK-012): Fix loading state        |
```

Tasks with no REQ reference appear in an `(Untraced)` row at the bottom.

### 3. Build the Test Plan Checklist

Extract acceptance criteria from `requirements.md`. Each `### REQ-xxx` section typically contains an "Acceptance Criteria" or "AC" subsection. Convert each criterion into a checklist item:

```markdown
## Test Plan

- [ ] REQ-001: Login with valid credentials redirects to dashboard
- [ ] REQ-001: Login with wrong password shows "メールアドレスまたはパスワードが正しくありません"
- [ ] REQ-002: Empty email field shows inline validation error before submit
- [ ] REQ-002: Invalid email format shows the validation error message
- [ ] Regression: test command from tech.md §4 passes (all existing tests green)
- [ ] Build: all Verification Commands from tech.md §4 pass (lint / format / type check)
```

### 4. Build the PR Body Sections

**Review summary** — extract from `review-results/code-review.md`:

```markdown
## Review Summary

| Severity | Code Review | Security Review |
| -------- | ----------- | --------------- |
| CRITICAL | 0 open      | 0 open          |
| HIGH     | 2 open      | 1 open          |
| MEDIUM   | 3 open      | 0 open          |

> Outstanding HIGH issues (must resolve before merge):
>
> - [src/features/foo/components/foo-form.tsx:15] Using relative import path
> - [src/lib/api-client.ts:88] Missing input validation at boundary
```

Count open (unchecked `- [ ]`) vs resolved (checked `- [x]`) findings per severity.

**Spec reference** — link to all spec documents:

```markdown
## Spec Reference

| Document                | Path                                                        |
| ----------------------- | ----------------------------------------------------------- |
| Source (Notion archive) | `.claude/specs/<slug>/source-notion.md`                     |
| Requirements            | `.claude/specs/<slug>/requirements.md`                      |
| Design                  | `.claude/specs/<slug>/design.md`                            |
| Tasks                   | `.claude/specs/<slug>/tasks.md`                             |
| Requirements Review     | `.claude/specs/<slug>/review-results/requirement-review.md` |
| Plan Review             | `.claude/specs/<slug>/review-results/plan-review.md`        |
| Code Review             | `.claude/specs/<slug>/review-results/code-review.md`        |
| Change Log              | `.claude/specs/<slug>/change-log.md`                        |
| Progress                | `.claude/specs/<slug>/progress.md`                          |
```

### 5. Create the Pull Request

Push the branch and create the PR directly:

```bash
git push -u origin HEAD
```

Then create the PR:

```bash
gh pr create --title "<feature title>" --body "$(cat <<'EOF'
## Summary

<3-5 bullet points: what changed and why>

## Spec Reference

<built in Step 4>

## Traceability

<built in Step 2>

## Review Summary

<built in Step 4>

## Test Plan

<built in Step 3>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

> **Optional**: Run `/git-pr -u` after PR creation to add Review Attention Score and Mermaid diagram to the PR body.

### 6. Record the PR URL and update Phase Status

After the PR is created, update `.claude/specs/<slug>/progress.md`: change `vsdd-pr` from `⬜ not started` to `✅ complete` in the Phase Status table.

Then append to `.claude/specs/<slug>/progress.md`:

```markdown
## PR

- URL: https://github.com/<org>/<repo>/pull/42
- Created: 2026-05-26
- Status: open
```

Date format: `YYYY-MM-DD`. This entry allows `vsdd-workflow` to detect that the PR phase is complete.

### 7. Update change-log.md

Append to `.claude/specs/<slug>/change-log.md`:

```
| <YYYY-MM-DD> | vsdd-pr | PR 作成 (<PR URL>) |
```

---

## Notes

- Notion status update is out of scope — update the Notion card manually after the PR is reviewed and merged.
- The PR body intentionally surfaces open HIGH issues so reviewers are aware; this does not block PR creation.
- Only CRITICAL open issues block PR creation.

---

## Output Files Modified

| File                                 | Change                                          |
| ------------------------------------ | ----------------------------------------------- |
| `.claude/specs/<slug>/progress.md`   | `## PR` section appended with URL, date, status |
| `.claude/specs/<slug>/change-log.md` | Phase completion event appended                 |
| GitHub                               | New PR created                                  |

---

## Approval Gate

```
== PHASE COMPLETE: vsdd-pr ==
Artifact: .claude/specs/<slug>/progress.md
Summary:
- PR created: https://github.com/<org>/<repo>/pull/42
- Traceability table: 3 REQs traced across 12 TASKs and 12 commits
- Test plan: 8 checklist items derived from acceptance criteria
- Review summary: 0 CRITICAL, 3 HIGH open (surfaced in PR body for reviewers)
- PR URL recorded in progress.md
- change-log.md updated

Optional: run `/git-pr -u` to add Review Attention Score + Mermaid to the PR.

⏸ WAITING FOR CONFIRMATION
Type `CONFIRM vsdd-workflow` to view final workflow status, or describe changes needed.
```
