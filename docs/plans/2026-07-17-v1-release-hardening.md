# ecc-vsdd v1.0.0 Release Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the v1.0.0 release enforce explicit user PR consent across every worker, centralize GitHub mutations in a gated broker, automate release checks, and prove the exact release artifact with fresh-install Review and PR E2E runs.

**Architecture:** A global `UserPromptSubmit` hook materializes protected project-local workers because Claude Code ignores hooks in plugin subagents, and records a short-lived consent grant bound to `session_id`, canonical `cwd`, and `prompt_id` only for an exact `/vsdd-run ... --until pr` invocation; every other prompt clears it. PR launch consumes that grant idempotently by `tool_use_id`, `SubagentStart` binds the resulting capability to the real PR worker `agent_id`, and a dedicated broker performs push/PR creation after a fresh runtime preflight. The materialized PreToolUse guard rejects guard-observable direct and common wrapped outbound Git/GitHub mutations, including from the PR worker, so the broker is the only supported path.

**Tech Stack:** Python 3.10+, `unittest`, Claude Code plugin hooks, Git, GitHub CLI, GitHub Actions, Markdown/JSON.

---

### Task 1: Record explicit prompt-bound PR consent

**Files:**
- Modify: `hooks/hooks.json`
- Modify: `scripts/vsdd-model-guard.py`
- Test: `tests/test_vsdd_model_guard.py`

**Step 1: Write the failing tests**

Add tests that submit exact and non-exact `UserPromptSubmit` payloads and assert:

```python
def test_user_prompt_records_only_exact_until_pr_consent(): ...
def test_next_prompt_clears_pr_consent(): ...
def test_pr_launch_requires_matching_prompt_bound_consent(): ...
def test_pr_consent_is_one_shot_but_same_tool_hook_is_idempotent(): ...
```

The accepted forms are one-line `/ecc-vsdd:vsdd-run start|resume ... --until pr` and `/vsdd-run ... --until pr`. Bind the private record to sanitized session ID, canonical cwd, `prompt_id`, operation, SHA-256 of the exact prompt, and creation time.

**Step 2: Run the focused tests and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_vsdd_model_guard.ModelGuardTest.test_user_prompt_records_only_exact_until_pr_consent \
  tests.test_vsdd_model_guard.ModelGuardTest.test_next_prompt_clears_pr_consent \
  tests.test_vsdd_model_guard.ModelGuardTest.test_pr_launch_requires_matching_prompt_bound_consent \
  tests.test_vsdd_model_guard.ModelGuardTest.test_pr_consent_is_one_shot_but_same_tool_hook_is_idempotent -v
```

Expected: FAIL because `--user-prompt-submit` and consent records do not exist.

**Step 3: Implement the minimum consent lifecycle**

- Add a `UserPromptSubmit` plugin hook.
- Add `pr_consent_record_path`, exact prompt parsing, record creation, and clearing.
- Require Claude Code's documented `prompt_id` for consent and PR launch.
- Consume consent by launch `tool_use_id`; permit the second strict/global hook only when the same tool ID, slug, and worktree are presented.
- Remove the consent record during `SessionEnd`.

**Step 4: Run focused and full model-guard tests**

Expected: all new tests and existing guard tests PASS.

### Task 2: Bind authorization to the actual PR worker

**Files:**
- Modify: `hooks/hooks.json`
- Modify: `scripts/vsdd-model-guard.py`
- Test: `tests/test_vsdd_model_guard.py`

**Step 1: Write the failing tests**

```python
def test_pr_subagent_start_binds_real_agent_id_and_capability(): ...
def test_pr_worker_rejects_different_agent_id_or_capability(): ...
def test_pr_worker_rejects_expired_or_wrong_cwd_authorization(): ...
```

**Step 2: Verify RED**

Expected: current record accepts any non-empty PR worker `agent_id` and has no capability.

**Step 3: Implement binding**

- Add a `SubagentStart` hook invoking `--subagent-start`.
- Generate a cryptographically random PR action capability at launch.
- On PR-worker start, bind the authorization record to its actual `agent_id` and return the capability through `hookSpecificOutput.additionalContext`.
- Require exact session/cwd/prompt/agent/capability/worktree/slug/TTL matches for broker use.

**Step 4: Verify GREEN**

Expected: focused tests PASS and a different worker cannot reuse the record.

### Task 3: Reject direct external mutations from every worker

**Files:**
- Modify: `scripts/vsdd-model-guard.py`
- Test: `tests/test_vsdd_model_guard.py`

**Step 1: Write the failing tests**

Cover ordinary and wrapped commands:

```python
def test_non_pr_workers_cannot_push_or_create_pr(): ...
def test_pr_worker_must_use_bundled_action_broker(): ...
def test_external_action_detector_handles_git_c_env_and_shell_chains(): ...
def test_read_only_git_and_gh_commands_remain_allowed(): ...
```

Include `git push`, `git -C <repo> push`, `env X=1 git push`, `git send-pack`, `gh pr create`, `gh api`, GitHub API mutation via curl, and a chained `cd ... && git push`.

**Step 2: Verify RED**

Expected: non-PR pinned workers are currently auto-approved.

**Step 3: Implement fail-closed detection**

- Tokenize shell commands conservatively with `shlex` and shell punctuation.
- Deny recognized Git/GitHub mutations for all workers.
- Deny direct mutations from the PR worker and direct it to the bundled broker.
- Allow only an exact foreground invocation of the bundled broker for PR publication.
- Keep normal read-only Git/GitHub commands and implementation commands working.

**Step 4: Verify GREEN**

Expected: all detector and regression tests PASS.

### Task 4: Add the gated PR action broker

**Files:**
- Create: `scripts/vsdd-pr-action.py`
- Create: `tests/test_vsdd_pr_action.py`
- Modify: `agents/vsdd-pr-worker.md`
- Modify: `skills/vsdd-pr/SKILL.md`
- Modify: `skills/vsdd-run/SKILL.md`
- Modify: `skills/vsdd-run/references/runtime-contract.md`

**Step 1: Write broker integration tests with fake `git` and `gh` executables**

```python
def test_publish_rejects_missing_or_wrong_capability(): ...
def test_publish_rechecks_runtime_before_push_and_pr_create(): ...
def test_publish_blocks_changed_remote_base(): ...
def test_publish_pushes_creates_pr_and_writes_exact_evidence(): ...
def test_publish_recovers_existing_pr_without_duplicate_creation(): ...
```

**Step 2: Verify RED**

Expected: FAIL because the broker is absent.

**Step 3: Implement `publish`**

- Validate broker args without shell interpolation.
- Read and validate the private authorization/capability record.
- Verify the body file is inside the current spec root.
- Run runtime `preflight --phase pr` immediately before push and again before PR creation.
- Verify remote base with `git ls-remote`, push the exact integration HEAD, and create or reuse the PR with `gh` argument arrays.
- Verify `baseRefName/baseRefOid/headRefName/headRefOid/isDraft` from `gh pr view`.
- Atomically write the exact `pr-result.json` contract.

**Step 4: Update worker contracts**

Require the PR worker to create only the body file and call the broker once. Prohibit direct push/`gh pr create`.

**Step 5: Verify GREEN**

Expected: broker tests, model-guard tests, runtime tests, and full suite PASS.

### Task 5: Complete private-record negative coverage

**Files:**
- Modify: `scripts/vsdd-model-guard.py`
- Modify: `tests/test_vsdd_model_guard.py`

**Step 1: Add RED tests**

Test wrong mode, hard links, directories/FIFOs, absent records, expired records, wrong cwd, symlinked PR authorization, and cleanup after simulated crash/startup sweep.

**Step 2: Harden writes and cleanup**

- Create temporary records with `O_EXCL` and `O_NOFOLLOW` where supported.
- Reject all unsafe record forms through descriptor-based checks.
- Sweep expired records at session start without deleting live records.

**Step 3: Verify GREEN and coverage**

Expected: no skipped security behavior on macOS/Linux and line coverage remains at least 80% per runtime/control script.

### Task 6: Add v1 release automation and documentation

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `CHANGELOG.md`
- Create: `docs/release-checklist.md`
- Create: `requirements-dev.txt`
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`
- Modify: `docs/vsdd-workflow-usage.md`
- Modify: `skills/vsdd-run/SKILL.md`
- License: add only after the owner selects the license identifier.

**Step 1: Add CI**

Run unit/integration tests and coverage on Linux and macOS, compile Python, validate JSON, run `git diff --check`, and run `claude plugin validate . --strict`. Enforce the documented 80% line-coverage gate.

**Step 2: Add release metadata**

- Set the candidate version consistently to the current release candidate (`1.0.0-rc.11` after fixing the managed integration-worktree root).
- Add `$schema`, `displayName`, `repository`, and the selected `license` field to the manifest.
- Document macOS/Linux as supported and Windows as unsupported until its private-record guarantees are implemented and tested.
- Record all 0.3.x hardening work in `CHANGELOG.md`.

**Step 3: Add a release checklist**

Require clean checkout, CI, coverage, strict validation, two fresh Opus reviews within the documented threat model, isolated marketplace install, one start-to-PR E2E, one negative no-consent E2E, payload hash match, tag verification, and promotion of the same RC commit.

### Task 7: Perform release-candidate verification

**Files:**
- Evidence only; do not commit credentials, transcripts, or generated test repositories.

**Step 1: Run local gates**

```bash
python3 -m unittest discover -s tests -v
coverage run --branch -m unittest discover -s tests
coverage report --fail-under=80
python3 -m py_compile scripts/*.py
claude plugin validate . --strict
```

**Step 2: Run fresh Opus reviews**

Use separate Opus/xhigh read-only sessions for code and security. Require PASS with no P0/P1 inside the documented threat model; arbitrary custom-binary internals that require an OS sandbox are not hook-level release blockers.

**Step 3: Install the exact RC artifact in an isolated Claude config**

Verify manifest version, dependency installation, 15 agents, all skills/hooks, and cache payload hashes. Do not use `--plugin-dir` for release acceptance.

**Step 4: Run clean start-to-PR E2E**

Use a new disposable private GitHub repository and detailed self-contained brief. Issue one exact `start <slug> --until pr` prompt and verify Fable/worker routing, TASK commits, current Opus reviews, one-shot consent, broker-only push/PR creation, `pr-result.json`, and terminal `COMPLETE/pr`.

**Step 5: Run negative consent E2E**

Prove a resume/status prompt without `--until pr` cannot launch the broker or perform direct push/PR commands.

**Step 6: Audit every v1.0.0 requirement**

Promote `v1.0.0-rc.11` to `v1.0.0` only when the same commit and installed payload have passed all gates.
