# Structured review contract

Write each review as Markdown with this YAML frontmatter:

```yaml
---
review_type: requirements|plan|implementation-workflow|code|security
target_commit: <full-sha-or-N/A>
verdict: PASS|REVISE|BLOCKED
critical: <integer>
high: <integer>
medium: <integer>
low: <integer>
remediation_mode: none|standard|workflow
reviewer_model: opus
reviewer_effort: xhigh
review_attempt: <1..3>
---
```

Use stable finding IDs and include severity, affected REQ/TASK IDs, evidence with file and line, and a concrete acceptance condition. Set `PASS` only when CRITICAL and HIGH are both zero. Set `REVISE` when a blocking finding is actionable. Set `BLOCKED` when evidence cannot be obtained or the required review cannot complete.

Use `remediation_mode: workflow` only when blocking fixes span multiple independent components or require parallel investigation. Otherwise use `standard`. MEDIUM findings remain visible but do not block; LOW findings are optional.

The orchestrator may read only the fixed frontmatter fields to choose transitions. It must not reinterpret prose, downgrade severity, or modify the report.

The Status worker must snapshot every report through `vsdd-runtime-state.py snapshot`. The runtime validates the review type, Opus/xhigh routing fields, attempt range, severity integers, PASS/REVISE consistency, and target commit before persisting `verdict`, `target_commit`, and output hash into `run-state.json`. A review is not a valid prerequisite without that snapshot. Code and security reports bind to the exact current full integration `HEAD`; any later commit makes both stale for PR and requires fresh Opus reviews.

Before launching a reviewer, the Status worker must atomically obtain the attempt number with `vsdd-runtime-state.py begin-attempt`. Use scope `requirements-review`, `plan-review`, or `implementation-plan-review` for those phases. For each paired Code/Security round, call it once with scope `post-implementation-review` and write the same returned number to both reports. Never invent or reuse an attempt number. Snapshot finishes that review attempt; replacing a snapshotted report requires beginning the next attempt. The third `REVISE`, any `BLOCKED`, or an attempt beyond the limit blocks the run mechanically.
