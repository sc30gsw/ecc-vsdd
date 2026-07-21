---
name: vsdd-review
description: This skill should be used to run separate independent Opus code and security reviews against the exact VSDD implementation commit and produce structured blocking verdicts without modifying code.
---

# vsdd-review — Independent code and security gates

## Invocation

```text
/vsdd-review <slug>
```

## Mandatory execution routing

Launch two new disk-only agents against the same full commit SHA:

- `vsdd-code-reviewer` — Opus, `xhigh`;
- `vsdd-security-reviewer` — Opus, `xhigh`.

Run them independently, preferably concurrently. Never reuse implementation context, pass one reviewer's findings to the other, merge them into one author context, or let either reviewer modify source files. Direct invocation from another model must still delegate to these pinned agents.

Read and obey:

```text
${CLAUDE_PLUGIN_ROOT}/skills/vsdd-run/references/review-contract.md
```

## Prerequisites

Require the approved requirements, design, tasks, plan review, immutable implementation workflow, implementation-workflow PASS review, `implementation-ledger.md`, completed TASK-to-SHA mapping, successful mechanical TASK attempt records, and passing `tech.md` §4 commands. Require deterministic `code-review` preflight before launching reviewers. Have the Status worker call `begin-attempt --scope post-implementation-review` exactly once, then pass its returned number and the same exact integration target SHA to both reviewers.

## Code review

Write only:

```text
.vsdd/specs/<slug>/review-results/code-review.md
```

Check correctness, acceptance-criteria coverage, scope, traceability, tests, regressions, type safety, performance, maintainability, steering conventions, architecture boundaries, and drift. Every finding must cite evidence and affected REQ/TASK IDs.

## Security review

Write only:

```text
.vsdd/specs/<slug>/review-results/security-review.md
```

Check secrets, trust boundaries, authentication, authorization, input validation, injection, SSRF, XSS, path traversal, unsafe deserialization, dependency risks, sensitive data, abuse cases, and project-specific security rules. Every finding must cite evidence and affected REQ/TASK IDs.

## Gate

Both reports must use the structured review frontmatter and name the same `target_commit`.

- `PASS`: CRITICAL=0 and HIGH=0.
- `REVISE`: at least one actionable CRITICAL/HIGH finding.
- `BLOCKED`: required evidence or review capability unavailable.

MEDIUM findings remain visible and may proceed. LOW findings are optional. Any unresolved CRITICAL/HIGH in either report blocks PR.

Set `remediation_mode: workflow` only for cross-cutting or independently parallelizable remediation; otherwise set `standard`. Do not apply fixes in review agents.

## Re-review

After remediation, have the Status worker begin the next shared `post-implementation-review` attempt, launch two new Opus reviewers against the new target commit, and overwrite the current verdict files while preserving prior attempts in clearly labeled history sections or attempt-specific evidence files. Allow the initial review plus at most two remediation/re-review rounds. The third `REVISE` snapshot blocks mechanically.

Update `run-state.json` only through the Haiku status worker after validating both persisted reports.
