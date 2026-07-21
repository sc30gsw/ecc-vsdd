---
name: vsdd-pr
description: This skill should be used to generate, push, and create a VSDD pull request with requirement, design, task, commit, review, and verification traceability after every blocking gate passes.
---

# vsdd-pr — Create the gated VSDD pull request

## Invocation boundary

```text
/ecc-vsdd:vsdd-run resume <slug> --until pr
```

This phase is published only from a managed `vsdd-run` whose current, exact user prompt contains `--until pr`. A standalone Skill invocation, an earlier prompt, prose that mentions the command, or a persisted `until: pr` value is not current external-action authorization.

## Mandatory execution routing

Delegate PR body generation and broker invocation to a fresh `vsdd-pr-worker` (Sonnet, `medium`). When already running as that agent, execute the steps below inline and do not delegate again. Never let Fable or a reviewer author PR text or perform an external mutation.

## Prerequisites

Require:

- completed requirements, design, tasks, and TASK-to-commit mapping;
- deterministic `pr` preflight proving TASK equality, all statuses `done`, and all mapped commits exist;
- `review-results/requirement-review.md` with `verdict: PASS`;
- `review-results/plan-review.md` with `verdict: PASS`;
- `review-results/implementation-workflow-review.md` with `verdict: PASS`;
- `review-results/code-review.md` with `verdict: PASS`;
- `review-results/security-review.md` with `verdict: PASS`;
- code and security reports target the exact current integration commit;
- every steering verification command passes at that commit;
- the integration branch is not the base branch;
- `gh` is installed and authenticated and a push remote exists.

Stop without exception when either post-implementation report has unresolved CRITICAL/HIGH, is `BLOCKED`, targets another commit, or is missing. A human confirmation does not waive this validation gate.

## Build the PR body

Create a complete body containing:

1. concise change summary;
2. REQ → Design → TASK → commit traceability table;
3. acceptance-criteria test checklist;
4. verification commands and results;
5. code and security review severity counts with links to persisted artifacts;
6. unresolved MEDIUM findings and manual follow-up items;
7. immutable implementation workflow summary, implementation-ledger evidence, and worktree/integration notes.

Derive every claim from disk and Git. Do not fabricate commands, results, commits, or review outcomes. Flag any TASK or commit without traceability and block rather than omitting it.

## Select ready or draft state

- Create a ready PR when both reviews pass, unresolved MEDIUM=0, and no manual follow-up remains.
- Create a draft PR when both reviews pass but a MEDIUM finding or manual follow-up remains.
- Do not create any PR when CRITICAL/HIGH remains.

## Publish through the broker

Write the complete body to the absolute path `.vsdd/specs/<slug>/pr-body.md`. Do not push, call `gh pr create`, call `gh api`, or write `pr-result.json` directly. Read the one-time values injected into this worker's `SubagentStart` context:

- `VSDD_PR_ACTION_CAPABILITY`
- `VSDD_PR_ACTION_SESSION_ID`
- `VSDD_PR_ACTION_AGENT_ID`

Invoke only this foreground command, substituting literal values from that context and the current run. Do not use environment-variable expansion for the injected values:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-pr-action.py" publish \
  --worktree "<absolute-integration-worktree>" \
  --slug "<slug>" \
  --session-id "<injected-session-id>" \
  --agent-id "<injected-agent-id>" \
  --capability "<injected-capability>" \
  --title "<one-line-title>" \
  --body-file "<absolute-spec-path>/pr-body.md" \
  [--draft]
```

The broker revalidates the private authorization, current PR preflight, recorded base branch/SHA, exact integration branch/HEAD, and remote base. It pushes only the exact integration ref, rechecks preflight, creates or reuses the PR, validates GitHub's base/head identity and draft state, and atomically persists the completion authority below. Never assume `main` or redetect a different base at PR time.

The broker persists `.vsdd/specs/<slug>/pr-result.json` with exactly these current fields:

```json
{
  "url": "https://github.com/owner/repo/pull/123",
  "number": 123,
  "draft": false,
  "base_branch": "develop",
  "base_sha": "<run-state.base_sha>",
  "head_branch": "vsdd/<slug>",
  "head_sha": "<current-full-integration-HEAD>",
  "target_commit": "<same-current-full-integration-HEAD>",
  "created_at": "<ISO-8601>"
}
```

Return the broker's structured result to Fable. Then have the Status worker run `vsdd-runtime-state.py snapshot --phase pr`. The snapshot validates the GitHub URL/number, recorded base identity, exact integration branch, and both head fields against current `HEAD` before copying evidence into `run-state.json`. A PR worker message, `progress.md` row, or stale URL never completes the phase. If authorization, preflight, push, authentication, remote detection, `gh`, evidence persistence, or snapshot fails, return `VSDD RUN BLOCKED` and never fabricate a URL or bypass the broker.

## Completion output

```text
== PHASE COMPLETE: vsdd-pr ==
PR: <url>
State: <ready|draft>
Base: <ref>@<sha>
Head: vsdd/<slug>@<sha>
Reviews: code=PASS security=PASS
```
