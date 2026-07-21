---
name: vsdd-init
description: This skill should be used to initialize a VSDD feature specification, source material, progress tracking, and change log after steering is current.
---

# Skill: vsdd-init

## Mandatory execution routing

Before initialization, inspect Steering availability and its saved artifact gate. If missing, delegate Steering to a fresh `vsdd-steering-worker` (Opus, `xhigh`). If the repository stack, conventions, or verification commands changed, refresh Steering explicitly with `--force`. Then delegate initialization to a fresh `vsdd-init-worker` (Haiku, `low`). When already running as the Init worker, execute the steps below inline and do not delegate again.

When `VSDD_RUN_CONTEXT` says `execution_mode: unattended`, do not ask questions or wait on `CONFIRM`. Require its explicit `operation` field; never infer lifecycle intent from prose. A new Start has two distinct operations: `operation: bootstrap` creates the integration branch/worktree and only `run-state.json`; later `operation: phase` with `phase: init` consumes that exact bootstrap. Block on anything that existed before bootstrap or any extra pre-Init artifact, but do not reject the managed worktree/spec created by the immediately preceding bootstrap. For `operation: source-update`, preserve the skeleton and replace only the explicitly supplied source plus its metadata.

## Invocation

```
/vsdd-init <slug> [source] [--mode standard|auto] [--update-source]
```

**Arguments:**

- `<slug>` — kebab-case identifier for the feature (e.g. `user-invitation`, `supplier-csv-import`)
- `[source]` — optional Notion page URL, source file, or detailed feature brief
- `[--mode standard|auto]` — workflow mode (default: `standard`)
  - `standard`: engineer-led — AI assists, human drives decisions
  - `auto`: AI-led — suitable for non-engineers; AI asks questions and makes decisions autonomously
- `--update-source` — internal resume mode; preserve the existing skeleton and update source only

---

## Purpose

Initialize a spec directory for a new feature under `.vsdd/specs/<slug>/`. This is always the first step in the VSDD workflow. It creates the directory structure, optionally fetches a Notion page as source material, and records the chosen mode in `progress.md`.

---

## Execution Steps

### Managed Bootstrap operation (before Step 0)

When and only when `VSDD_RUN_CONTEXT.operation` is `bootstrap`, do not inspect or require Steering and do not create the Phase 1 skeleton. Run exactly:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py" bootstrap \
  --repo <absolute-clean-source-checkout> --slug <slug> \
  --worktree <new-absolute-integration-worktree> \
  --request <persisted-feature-brief-or-source-reference> \
  --mode <auto|standard> --until <review|pr> [--base <explicit-ref>]
```

Return the command result immediately. This path is complete only when the source checkout branch is unchanged and the new feature spec contains exactly `run-state.json` with `bootstrap_status: READY`. Do not continue to Step 0 in the same invocation.

For all remaining steps require `operation: phase` with `phase: init`, or `operation: source-update`. A missing/unknown operation is `BLOCKED`.

### Step 0: Validate the Steering gate

Do not generate or refresh Steering in the Haiku Init worker. Require the Opus Steering worker to have produced `.vsdd/specs/_steering/` artifacts whose saved hashes and decision markers pass deterministic preflight. Read the `⚠ NEW OPEN QUESTIONS: <count>` state from its persisted output.

**Gate**:

- `count == 0` → continue to Step 1.
- Standalone invocation with `count >= 1` → STOP. Present new `Q-XXX` entries from `.vsdd/specs/_steering/open-questions.md` and ask the user to either grill them (run `/grill-with-docs` or resolve manually) or explicitly type `dismiss <Q-id>` to acknowledge and proceed.
- Orchestrated `vsdd-run` with `count >= 1` → classify each question using the unattended decision boundary. Record reversible technical assumptions and continue; STOP only for unresolved product behavior, data loss, security, compatibility, destructive operations, or external authority.

If Steering is missing, its saved hash changed, or its decision markers fail, return `BLOCKED` and require the caller to launch `vsdd-steering-worker`. A repository stack/convention change requires an explicit `--force` refresh. This guarantees coherence without letting Haiku author Steering.

### Step 1: Validate inputs

- Confirm `<slug>` is kebab-case (lowercase letters, digits, hyphens only).
- If `--mode` is not provided, default to `standard`.
- Announce to the user: "Initializing spec for `<slug>` in `--mode <mode>`."
- In unattended mode, read `base_ref`, `base_branch`, `base_sha`, integration branch, and worktree from `run-state.json`; block if any is missing.
- Before creating the Phase 1 skeleton, run deterministic `preflight --phase init`. Require `bootstrap_status: READY`, Init `PENDING`, recorded and active branch exactly `vsdd/<slug>`, the active Git top-level equal to `integration_worktree`, and `run-state.json` as the only entry under the feature spec directory.

When `--update-source` is set, require an existing spec and skip Steps 2 and 4 except for source metadata updates. Never recreate placeholders or reset progress.

### Step 2: Create directory structure

Create the following empty directories and files under `.vsdd/specs/<slug>/`:

```
.vsdd/specs/<slug>/
├── review-results/      ← subdirectory for review output files
├── progress.md          ← created in this step
├── change-log.md        ← created in this step
├── requirements.md      ← placeholder (created by vsdd-requirements)
├── design.md            ← placeholder (created by vsdd-design)
└── tasks.md             ← placeholder (created by vsdd-tasks)
```

Run:

```bash
mkdir -p .vsdd/specs/<slug>/review-results/
```

Write placeholder files with a single comment line:

```
<!-- Artifact not yet generated. Run the corresponding vsdd-* skill. -->
```

### Step 3: Persist source material

If a Notion URL is given:

1. Extract the page ID from the URL (last 32-character hex segment, with or without hyphens).
2. Call `mcp__claude_ai_Notion__notion-fetch` with the page ID.
3. Write the raw Markdown content to `.vsdd/specs/<slug>/source-notion.md`.
4. If the fetch fails, return `VSDD RUN BLOCKED`; never continue after an explicitly requested external source failed.

If a source file or detailed brief is given, persist its normalized content to `.vsdd/specs/<slug>/source-request.md`. If no source is given during a new unattended run, require the request already persisted in `run-state.json` to be sufficiently detailed; otherwise block.

For `--update-source`, update `**Source**:` in `progress.md`, update `request` and `source_paths` in `run-state.json`, invalidate from Requirements, then snapshot phase `source` using the bundled runtime commands. Stop after this update so Resume can restart at Requirements.

For a new run, the Init checkpoint must snapshot the persisted `source-notion.md` or `source-request.md` as Requirements-owned input evidence. A later source edit must therefore invalidate Requirements and every downstream phase.

### Step 4: Write progress.md and change-log.md

Write `.vsdd/specs/<slug>/progress.md` with the following structure:

```markdown
# Spec Progress: <slug>

**Mode**: <standard|auto>
**Initialized**: <YYYY-MM-DD>
**Source**: <source URL/path/brief or "none">
**Base ref**: <detected ref>
**Base branch**: <detected branch>
**Base SHA**: <full SHA>
**Integration branch**: vsdd/<slug>
**Integration worktree**: <absolute path>

## Phase Status

| Phase | Skill                   | Status         |
| ----- | ----------------------- | -------------- |
| 0     | vsdd-steering            | ✅ current     |
| 1     | vsdd-init                | ✅ complete    |
| 2     | vsdd-requirements        | ⬜ not started |
| 3     | vsdd-review-requirements | ⬜ not started |
| 4     | vsdd-design              | ⬜ not started |
| 5     | vsdd-tasks               | ⬜ not started |
| 6     | vsdd-review-plan         | ⬜ not started |
| 7     | vsdd-impl                | ⬜ not started |
| 8     | vsdd-review              | ⬜ not started |
| 9     | vsdd-pr                  | ⬜ not started |

## Files

| File                                   | Description                            |
| -------------------------------------- | -------------------------------------- |
| `requirements.md`                      | EARS-format requirements               |
| `design.md`                            | Architecture and design decisions      |
| `tasks.md`                             | Task breakdown (TASK-xxx)              |
| `implementation-workflow.md`           | Dynamic Workflow runtime decision plan |
| `implementation-ledger.md`             | TDD evidence, retries, and TASK-to-SHA mapping |
| `review-results/requirement-review.md` | Requirements Review findings           |
| `review-results/plan-review.md`        | Plan Review + Traceability findings    |
| `review-results/implementation-workflow-review.md` | Implementation Workflow Review |
| `review-results/code-review.md`        | Independent Code Review findings       |
| `review-results/security-review.md`    | Independent Security Review findings   |
| `run-state.json`                       | Model, hash, commit, retry, resume state |
| `change-log.md`                        | Phase completion event log             |
```

Write `.vsdd/specs/<slug>/change-log.md` with the following structure:

```markdown
# Change Log: <slug>

| Date         | Skill    | Event          |
| ------------ | -------- | -------------- |
| <YYYY-MM-DD> | vsdd-init | スペック初期化 |
```

### Step 5: Print confirmation

Print a summary of what was created, including:

- Directory path
- Mode recorded
- Whether a Notion source was fetched
- `change-log.md` initialized with first row
- The next step to take

---

## Mode Behavior Summary

| Aspect       | `--mode standard`          | `--mode auto`              |
| ------------ | -------------------------- | -------------------------- |
| Who drives   | Engineer                   | AI                         |
| AI role      | Assist + review            | Ask + decide               |
| Notion fetch | Optional                   | Optional                   |
| Next skill   | `/vsdd-requirements <slug>` | `/vsdd-requirements <slug>` |

---

## Notes

- The `progress.md` file is the single source of truth for the mode. Subsequent skills MUST read mode from `progress.md` rather than accepting a `--mode` flag themselves.
- If `.vsdd/specs/<slug>/` already exists, ask whether to overwrite only in standalone mode. In unattended Phase 1, accept only the deterministic managed-bootstrap shape described above; return `BLOCKED` for every other existing shape. In source-update mode preserve the initialized skeleton.
- The `slug` is used as-is in all file paths. Choose descriptive, stable slugs.

---

== PHASE COMPLETE: vsdd-init ==
Artifact: .vsdd/specs/<slug>/progress.md
Summary:

- Created spec directory structure under .vsdd/specs/<slug>/
- Recorded mode (standard|auto) in progress.md
- Persisted the requested source artifact, if provided
- All placeholder artifacts initialized

[Standalone invocation only]
⏸ WAITING FOR CONFIRMATION
Type `CONFIRM vsdd-requirements` to proceed. Or describe changes needed.

Omit the standalone confirmation lines entirely when `execution_mode: unattended`; return the completion artifact to the orchestrator immediately.
