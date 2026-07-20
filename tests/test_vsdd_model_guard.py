from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "vsdd-model-guard.py"
GUARD_SPEC = importlib.util.spec_from_file_location("vsdd_model_guard", SCRIPT)
assert GUARD_SPEC and GUARD_SPEC.loader
guard = importlib.util.module_from_spec(GUARD_SPEC)
GUARD_SPEC.loader.exec_module(guard)


class ModelGuardTest(unittest.TestCase):
    def run_guard(
        self,
        payload: dict,
        *arguments: str,
        data_root: str | None = None,
        plugin_root: Path = ROOT,
        **environment: str,
    ) -> subprocess.CompletedProcess[str]:
        data_root = data_root or tempfile.mkdtemp(prefix="ecc-vsdd-model-guard-")
        env = os.environ.copy()
        env.update(
            {
                "CLAUDE_PLUGIN_ROOT": str(plugin_root),
                "TMPDIR": data_root,
                guard.PROJECT_AGENTS_READY_ENV: "1",
            }
        )
        env.pop("CLAUDE_PLUGIN_DATA", None)
        env.pop("CLAUDE_CODE_SUBAGENT_MODEL", None)
        env.update(environment)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *(arguments or ("--strict",))],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def run_global_guard(
        self, payload: dict, *, data_root: str, plugin_root: Path = ROOT
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "CLAUDE_PLUGIN_ROOT": str(plugin_root),
                "TMPDIR": data_root,
            }
        )
        env.pop("CLAUDE_PLUGIN_DATA", None)
        env.pop("CLAUDE_CODE_SUBAGENT_MODEL", None)
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def orchestrator_launch(self) -> dict:
        return {
            "agent_type": "ecc-vsdd:vsdd-orchestrator",
            "session_id": "orchestrator-session",
            "prompt_id": "prompt-1",
            "cwd": str(ROOT),
            "effort": {"level": "high"},
            "tool_name": "Read",
            "tool_use_id": "tool-launch-1",
            "tool_input": {"file_path": str(ROOT / "README.md")},
        }

    def user_prompt(self, prompt: str, **overrides: object) -> dict:
        payload: dict[str, object] = {
            "session_id": "orchestrator-session",
            "prompt_id": "prompt-1",
            "cwd": tempfile.mkdtemp(prefix="ecc-vsdd-user-prompt-project-"),
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        }
        payload.update(overrides)
        return payload

    def make_pr_gate_fixture(self) -> tuple[Path, Path, Path]:
        fixture = Path(tempfile.mkdtemp(prefix="ecc-vsdd-pr-gate-"))
        plugin_root = fixture / "plugin"
        worktree = fixture / "worktree"
        (plugin_root / "agents").mkdir(parents=True)
        (plugin_root / "scripts").mkdir()
        worktree.mkdir()
        run_state = worktree / ".claude" / "specs" / "sample" / "run-state.json"
        run_state.parent.mkdir(parents=True)
        run_state.write_text("{}\n", encoding="utf-8")
        for source in (ROOT / "agents").glob("*.md"):
            filename = source.name
            (plugin_root / "agents" / filename).write_text(
                source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        (plugin_root / "scripts" / "vsdd-runtime-state.py").write_text(
            "import json\nprint(json.dumps({'status': 'READY', 'phase': 'pr'}))\n",
            encoding="utf-8",
        )
        (plugin_root / "scripts" / "vsdd-pr-action.py").write_text(
            (ROOT / "scripts" / "vsdd-pr-action.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (plugin_root / "scripts" / "vsdd-model-guard.py").write_text(
            SCRIPT.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return plugin_root, worktree, run_state

    def pr_launch_payload(self, worktree: Path, run_state: Path) -> dict:
        payload = self.orchestrator_launch()
        payload["cwd"] = str(worktree)
        payload["tool_name"] = "Agent"
        payload["tool_input"] = {
            "subagent_type": "vsdd-pr-worker",
            "prompt": (
                "VSDD_RUN_CONTEXT\n"
                "schema_version: 1\n"
                "execution_mode: unattended\n"
                "operation: phase\n"
                "slug: sample\n"
                f"integration_worktree: {worktree}\n"
                f"run_state: {run_state}\n"
                "phase: pr\n"
                "attempt: 1\n"
                "source_paths: none\n"
                "END_VSDD_RUN_CONTEXT\n"
            ),
        }
        return payload

    def bind_pr_worker(
        self,
        launch: dict,
        *,
        data_root: str,
        plugin_root: Path,
        agent_id: str = "pr-worker-1",
    ) -> str:
        started = {
            "session_id": launch["session_id"],
            "prompt_id": launch["prompt_id"],
            "cwd": launch["cwd"],
            "hook_event_name": "SubagentStart",
            "agent_type": "vsdd-pr-worker",
            "agent_id": agent_id,
        }
        result = self.run_guard(
            started,
            "--subagent-start",
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        match = re.search(
            r"VSDD_PR_ACTION_CAPABILITY:\s*([A-Za-z0-9_-]+)", context
        )
        self.assertIsNotNone(match)
        return match.group(1)

    def assert_strict_allow(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        decision = output["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "allow")

    def test_orchestrator_cli_examples_require_explicit_high_effort(self) -> None:
        expected = "claude --agent ecc-vsdd:vsdd-orchestrator --effort high"
        for relative_path in (
            "README.md",
            "docs/vsdd-workflow-usage.md",
            "skills/vsdd-run/SKILL.md",
        ):
            with self.subTest(path=relative_path):
                command_lines = [
                    line
                    for line in (ROOT / relative_path)
                    .read_text(encoding="utf-8")
                    .splitlines()
                    if line.startswith("claude ")
                    and "--agent ecc-vsdd:vsdd-orchestrator" in line
                ]
                self.assertTrue(command_lines)
                self.assertIn(expected, command_lines)
                for command in command_lines:
                    self.assertIn("--effort high", command)

    def test_rejects_per_invocation_model_override(self) -> None:
        payload = self.orchestrator_launch()
        payload["tool_name"] = "Agent"
        payload["tool_input"] = {
            "subagent_type": "vsdd-code-reviewer",
            "model": "sonnet",
        }

        result = self.run_guard(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("model override", result.stderr)

    def test_rejects_global_subagent_model_override(self) -> None:
        payload = self.orchestrator_launch()
        payload["tool_name"] = "Agent"
        payload["tool_input"] = {"subagent_type": "vsdd-code-reviewer"}
        result = self.run_guard(
            payload, CLAUDE_CODE_SUBAGENT_MODEL="sonnet"
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("CLAUDE_CODE_SUBAGENT_MODEL", result.stderr)

    def test_parent_session_model_is_not_applied_to_a_subagent(self) -> None:
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-model-record-")
        session_start = {
            "hook_event_name": "SessionStart",
            "agent_type": "ecc-vsdd:vsdd-orchestrator",
            "session_id": "shared-parent-session",
            "model": "claude-fable-1",
        }
        recorded = self.run_guard(
            session_start, "--session-start", data_root=data_root
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)

        payload = {
            "agent_type": "ecc-vsdd:vsdd-code-reviewer",
            "session_id": "shared-parent-session",
            "cwd": str(ROOT),
            "effort": {"level": "xhigh"},
            "tool_name": "Read",
            "tool_input": {},
        }
        result = self.run_guard(payload, data_root=data_root)

        self.assert_strict_allow(result)

    def test_session_start_without_optional_model_does_not_block_tools(self) -> None:
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-model-optional-")
        session_start = {
            "hook_event_name": "SessionStart",
            "agent_type": "ecc-vsdd:vsdd-orchestrator",
            "session_id": "actual-payload-session",
            "source": "startup",
        }
        recorded = self.run_guard(
            session_start, "--session-start", data_root=data_root
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        self.assertNotIn("VSDD RUN BLOCKED", recorded.stdout)

        payload = self.orchestrator_launch()
        payload["session_id"] = "actual-payload-session"
        result = self.run_guard(payload, data_root=data_root)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_subagent_rejects_effort_that_disagrees_with_frontmatter(self) -> None:
        payload = {
            "agent_type": "ecc-vsdd:vsdd-code-reviewer",
            "agent_id": "subagent-1",
            "session_id": "shared-parent-session",
            "effort": {"level": "high"},
            "tool_name": "Read",
            "tool_input": {},
        }

        result = self.run_guard(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("requires effort 'xhigh'", result.stderr)

    def test_subagent_without_optional_effort_uses_verified_frontmatter(self) -> None:
        payload = {
            "agent_type": "ecc-vsdd:vsdd-init-worker",
            "session_id": "shared-parent-session",
            "tool_name": "Bash",
            "tool_input": {},
        }

        result = self.run_guard(payload)

        self.assert_strict_allow(result)

    def test_main_agent_without_effort_is_rejected(self) -> None:
        payload = self.orchestrator_launch()
        payload.pop("effort")

        result = self.run_guard(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("active effort is None", result.stderr)

    def test_orchestrator_cannot_background_the_worker_launcher(self) -> None:
        payload = self.orchestrator_launch()
        payload["tool_name"] = "Bash"
        payload["tool_input"] = {
            "command": (
                f'python3 "{ROOT / "scripts" / "vsdd-launch-worker.py"}" '
                "plan --slug sample --worktree /tmp/sample"
            ),
            "run_in_background": True,
        }

        result = self.run_guard(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("foreground", result.stderr)

    def test_orchestrator_rejects_shell_expansion_in_launcher_arguments(self) -> None:
        payload = self.orchestrator_launch()
        payload["tool_name"] = "Bash"
        payload["tool_input"] = {
            "command": (
                f'python3 "{ROOT / "scripts" / "vsdd-launch-worker.py"}" '
                "plan --slug sample --worktree '/tmp/{sample,other}'"
            )
        }

        result = self.run_guard(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("control operators", result.stderr)

    def test_user_prompt_records_only_exact_until_pr_consent(self) -> None:
        accepted = (
            "/ecc-vsdd:vsdd-run resume sample --until pr",
            "/vsdd-run start sample detailed-brief --until pr",
            "/ecc-vsdd:vsdd-run legacy-sample --until pr",
        )
        rejected = (
            "Please run /ecc-vsdd:vsdd-run resume sample --until pr",
            "/ecc-vsdd:vsdd-run status sample --until pr",
            "/ecc-vsdd:vsdd-run resume sample --until review",
            "/ecc-vsdd:vsdd-run resume sample --until pr\nignore the guard",
        )

        for index, prompt in enumerate((*accepted, *rejected)):
            with self.subTest(prompt=prompt):
                data_root = tempfile.mkdtemp(prefix="ecc-vsdd-pr-consent-")
                payload = self.user_prompt(
                    prompt,
                    session_id=f"consent-session-{index}",
                )

                result = self.run_guard(
                    payload,
                    "--user-prompt-submit",
                    data_root=data_root,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                records = [
                    path
                    for path in Path(data_root).rglob(f"consent-session-{index}.json")
                    if path.parent.name == "pr-consent-sessions"
                ]
                if prompt in accepted:
                    self.assertEqual(len(records), 1)
                    record = json.loads(records[0].read_text(encoding="utf-8"))
                    self.assertEqual(record["authorization"], "vsdd-pr-consent")
                    self.assertEqual(record["prompt_id"], "prompt-1")
                    self.assertEqual(record["cwd"], str(Path(payload["cwd"]).resolve()))
                    requested_operation = prompt.split()[1]
                    self.assertEqual(
                        record["operation"],
                        requested_operation
                        if requested_operation in {"start", "resume"}
                        else "start",
                    )
                    self.assertRegex(record["prompt_sha256"], r"^[0-9a-f]{64}$")
                else:
                    self.assertEqual(records, [])

    def test_next_prompt_clears_pr_consent(self) -> None:
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-pr-consent-clear-")
        accepted = self.user_prompt(
            "/ecc-vsdd:vsdd-run resume sample --until pr",
            session_id="cleared-consent-session",
        )
        recorded = self.run_guard(
            accepted,
            "--user-prompt-submit",
            data_root=data_root,
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        self.assertEqual(
            len(
                [
                    path
                    for path in Path(data_root).rglob("cleared-consent-session.json")
                    if path.parent.name == "pr-consent-sessions"
                ]
            ),
            1,
        )

        ordinary = self.user_prompt(
            "/ecc-vsdd:vsdd-run status sample",
            session_id="cleared-consent-session",
            prompt_id="prompt-2",
        )
        cleared = self.run_guard(
            ordinary,
            "--user-prompt-submit",
            data_root=data_root,
        )

        self.assertEqual(cleared.returncode, 0, cleared.stderr)
        self.assertEqual(
            [
                path
                for path in Path(data_root).rglob("cleared-consent-session.json")
                if path.parent.name == "pr-consent-sessions"
            ],
            [],
        )

    def test_non_pr_workers_cannot_push_or_create_pr(self) -> None:
        commands = (
            "git push origin HEAD",
            f"git -C {ROOT} push origin HEAD",
            "env TRACE=1 git push origin HEAD",
            "git send-pack origin HEAD",
            "gh pr create --fill",
            "gh api repos/example/project/pulls -f title=test",
            "cd /tmp && git push origin HEAD",
            "bash -c 'git push origin HEAD'",
            "sh -lc 'gh pr create --fill'",
            (
                'python3 -c "import subprocess; '
                "subprocess.run(['git','push','origin','HEAD'])\""
            ),
            "x=push; git $x origin HEAD",
            "git $(printf push) origin HEAD",
            "git -c alias.publish=push publish origin HEAD",
            "curl -X DELETE https://api.github.com/repos/example/project/pulls/1",
            "wget --method=POST https://api.github.com/repos/example/project/pulls",
            "echo hi\ngit push origin HEAD",
            "git status --short\ngit push origin HEAD",
            "echo origin | xargs git push",
            "git-push origin HEAD",
            "printf 'git push origin HEAD' | sh",
            "{ git push origin HEAD; }",
            "{ gh pr create --fill; }",
            ">/dev/null git push origin HEAD",
            "2>/dev/null gh pr create --fill",
            "env -u PATH git push origin HEAD",
            "env -C /tmp git push origin HEAD",
            "env -S 'git push origin HEAD'",
            "exec -a foo git push origin HEAD",
            "sudo -u root git push origin HEAD",
            "env -u PATH gh pr create --fill",
        )
        for command in commands:
            with self.subTest(command=command):
                payload = {
                    "agent_type": "ecc-vsdd:vsdd-status-worker",
                    "agent_id": "status-worker-1",
                    "session_id": "external-action-session",
                    "prompt_id": "prompt-1",
                    "cwd": tempfile.mkdtemp(prefix="ecc-vsdd-boundary-project-"),
                    "effort": {"level": "low"},
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                }

                result = self.run_global_guard(
                    payload,
                    data_root=tempfile.mkdtemp(prefix="ecc-vsdd-external-action-"),
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn("external Git/GitHub mutation", result.stderr)

    def test_read_only_git_and_gh_commands_remain_allowed(self) -> None:
        for command in (
            "git status --short",
            f"git -C {ROOT} rev-parse HEAD",
            "gh pr view --json number,url",
        ):
            with self.subTest(command=command):
                payload = {
                    "agent_type": "ecc-vsdd:vsdd-status-worker",
                    "agent_id": "status-worker-1",
                    "session_id": "read-only-command-session",
                    "prompt_id": "prompt-1",
                    "cwd": tempfile.mkdtemp(prefix="ecc-vsdd-boundary-project-"),
                    "effort": {"level": "low"},
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                }

                result = self.run_global_guard(
                    payload,
                    data_root=tempfile.mkdtemp(prefix="ecc-vsdd-read-only-command-"),
                )

                self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_pr_boundary_changes_require_current_prompt_consent(self) -> None:
        cases = (
            (
                "ecc-vsdd:vsdd-status-worker",
                "low",
                "resume",
                f'python3 "{ROOT / "scripts" / "vsdd-runtime-state.py"}" '
                f'extend --worktree "{ROOT}" --slug sample --until pr',
            ),
            (
                "ecc-vsdd:vsdd-init-worker",
                "low",
                "start",
                f'python3 "{ROOT / "scripts" / "vsdd-runtime-state.py"}" '
                f'bootstrap --repo "{ROOT}" --slug sample --worktree /tmp/sample '
                '--request "sample" --until pr',
            ),
            (
                "ecc-vsdd:vsdd-status-worker",
                "low",
                "resume",
                (
                    "bash -c 'python3 \""
                    f'{ROOT / "scripts" / "vsdd-runtime-state.py"}'
                    "\" extend --worktree \""
                    f'{ROOT}'
                    "\" --slug sample --until pr'"
                ),
            ),
        )
        for index, (agent_type, effort, operation, command) in enumerate(cases):
            with self.subTest(operation=operation):
                data_root = tempfile.mkdtemp(prefix="ecc-vsdd-boundary-consent-")
                payload = {
                    "agent_type": agent_type,
                    "agent_id": f"boundary-worker-{index}",
                    "session_id": f"boundary-session-{index}",
                    "prompt_id": f"boundary-prompt-{index}",
                    "cwd": tempfile.mkdtemp(prefix="ecc-vsdd-boundary-project-"),
                    "effort": {"level": effort},
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                }

                missing = self.run_global_guard(payload, data_root=data_root)
                self.assertEqual(missing.returncode, 2)
                self.assertIn("prompt-bound PR consent", missing.stderr)

                prompt = self.user_prompt(
                    f"/ecc-vsdd:vsdd-run {operation} sample --until pr",
                    session_id=payload["session_id"],
                    prompt_id=payload["prompt_id"],
                    cwd=payload["cwd"],
                )
                recorded = self.run_guard(
                    prompt,
                    "--user-prompt-submit",
                    data_root=data_root,
                )
                self.assertEqual(recorded.returncode, 0, recorded.stderr)

                allowed = self.run_global_guard(payload, data_root=data_root)
                self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_pr_launch_requires_matching_prompt_bound_consent(self) -> None:
        plugin_root, worktree, run_state = self.make_pr_gate_fixture()
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-pr-no-consent-")
        launch = self.pr_launch_payload(worktree, run_state)
        materialized = self.user_prompt(
            "/ecc-vsdd:vsdd-run status sample",
            session_id=launch["session_id"],
            prompt_id=launch["prompt_id"],
            cwd=launch["cwd"],
        )
        self.assertEqual(
            self.run_guard(
                materialized,
                "--user-prompt-submit",
                data_root=data_root,
                plugin_root=plugin_root,
            ).returncode,
            0,
        )

        missing = self.run_guard(
            launch,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("prompt-bound PR consent", missing.stderr)

        consent = self.user_prompt(
            "/ecc-vsdd:vsdd-run resume sample --until pr",
            session_id=launch["session_id"],
            prompt_id="different-prompt",
            cwd=launch["cwd"],
        )
        recorded = self.run_guard(
            consent,
            "--user-prompt-submit",
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)

        mismatched = self.run_guard(
            launch,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(mismatched.returncode, 2)
        self.assertIn("materialized project agent record", mismatched.stderr)

    def test_pr_consent_is_one_shot_but_same_tool_hook_is_idempotent(self) -> None:
        plugin_root, worktree, run_state = self.make_pr_gate_fixture()
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-pr-one-shot-")
        launch = self.pr_launch_payload(worktree, run_state)
        consent = self.user_prompt(
            "/ecc-vsdd:vsdd-run resume sample --until pr",
            session_id=launch["session_id"],
            prompt_id=launch["prompt_id"],
            cwd=launch["cwd"],
        )
        recorded = self.run_guard(
            consent,
            "--user-prompt-submit",
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)

        consent_path = next(
            path
            for path in Path(data_root).rglob(f"{launch['session_id']}.json")
            if path.parent.name == "pr-consent-sessions"
        )
        consent_record = json.loads(consent_path.read_text(encoding="utf-8"))
        valid_prompt_hash = consent_record["prompt_sha256"]
        consent_record["prompt_sha256"] = "invalid"
        consent_path.write_text(json.dumps(consent_record), encoding="utf-8")
        consent_path.chmod(0o600)
        invalid_hash = self.run_guard(
            launch,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(invalid_hash.returncode, 2)
        self.assertIn("prompt-bound PR consent", invalid_hash.stderr)
        consent_record["prompt_sha256"] = valid_prompt_hash
        consent_path.write_text(json.dumps(consent_record), encoding="utf-8")
        consent_path.chmod(0o600)

        first = self.run_guard(
            launch,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assert_strict_allow(first)
        repeated_hook = self.run_guard(
            launch,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assert_strict_allow(repeated_hook)

        another_launch = dict(launch)
        another_launch["tool_use_id"] = "tool-launch-2"
        consumed = self.run_guard(
            another_launch,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(consumed.returncode, 2)
        self.assertIn("already consumed", consumed.stderr)

    def test_pr_subagent_start_binds_real_agent_id_and_capability(self) -> None:
        plugin_root, worktree, run_state = self.make_pr_gate_fixture()
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-pr-agent-bind-")
        launch = self.pr_launch_payload(worktree, run_state)
        consent = self.user_prompt(
            "/ecc-vsdd:vsdd-run resume sample --until pr",
            session_id=launch["session_id"],
            prompt_id=launch["prompt_id"],
            cwd=launch["cwd"],
        )
        self.assertEqual(
            self.run_guard(
                consent,
                "--user-prompt-submit",
                data_root=data_root,
                plugin_root=plugin_root,
            ).returncode,
            0,
        )
        self.assert_strict_allow(
            self.run_guard(
                launch,
                data_root=data_root,
                plugin_root=plugin_root,
            )
        )

        capability = self.bind_pr_worker(
            launch,
            data_root=data_root,
            plugin_root=plugin_root,
            agent_id="bound-pr-worker",
        )

        record_path = next(
            path
            for path in Path(data_root).rglob(f"{launch['session_id']}.json")
            if path.parent.name == "pr-authorized-sessions"
        )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["agent_id"], "bound-pr-worker")
        self.assertEqual(record["capability"], capability)
        self.assertEqual(record["prompt_id"], launch["prompt_id"])

    def test_pr_worker_rejects_unbound_or_expired_authorization(self) -> None:
        plugin_root, worktree, run_state = self.make_pr_gate_fixture()
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-pr-agent-reject-")
        launch = self.pr_launch_payload(worktree, run_state)
        consent = self.user_prompt(
            "/ecc-vsdd:vsdd-run resume sample --until pr",
            session_id=launch["session_id"],
            prompt_id=launch["prompt_id"],
            cwd=launch["cwd"],
        )
        self.assertEqual(
            self.run_guard(
                consent,
                "--user-prompt-submit",
                data_root=data_root,
                plugin_root=plugin_root,
            ).returncode,
            0,
        )
        self.assert_strict_allow(
            self.run_guard(
                launch,
                data_root=data_root,
                plugin_root=plugin_root,
            )
        )
        self.bind_pr_worker(
            launch,
            data_root=data_root,
            plugin_root=plugin_root,
            agent_id="bound-pr-worker",
        )
        worker = {
            "agent_type": "ecc-vsdd:vsdd-pr-worker",
            "session_id": launch["session_id"],
            "prompt_id": launch["prompt_id"],
            "cwd": launch["cwd"],
            "effort": {"level": "medium"},
            "tool_name": "Bash",
            "tool_input": {"command": "git status --short"},
        }

        record_path = next(
            path
            for path in Path(data_root).rglob(f"{launch['session_id']}.json")
            if path.parent.name == "pr-authorized-sessions"
        )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["agent_id"] = None
        record_path.write_text(json.dumps(record), encoding="utf-8")
        record_path.chmod(0o600)
        unbound = self.run_global_guard(
            worker,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(unbound.returncode, 2)
        self.assertIn("invalid or expired", unbound.stderr)

        record["agent_id"] = "bound-pr-worker"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        record_path.chmod(0o600)
        worker["cwd"] = str(ROOT.parent)
        wrong_cwd = self.run_global_guard(
            worker,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(wrong_cwd.returncode, 2)
        self.assertIn("invalid or expired", wrong_cwd.stderr)
        worker["cwd"] = launch["cwd"]

        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["created_at"] = 1
        record_path.write_text(json.dumps(record), encoding="utf-8")
        record_path.chmod(0o600)

        expired = self.run_global_guard(
            worker,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(expired.returncode, 2)
        self.assertIn("invalid or expired", expired.stderr)

    def test_only_bound_pr_worker_can_invoke_the_action_broker(self) -> None:
        plugin_root, worktree, run_state = self.make_pr_gate_fixture()
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-pr-broker-guard-")
        launch = self.pr_launch_payload(worktree, run_state)
        consent = self.user_prompt(
            "/ecc-vsdd:vsdd-run resume sample --until pr",
            session_id=launch["session_id"],
            prompt_id=launch["prompt_id"],
            cwd=launch["cwd"],
        )
        self.assertEqual(
            self.run_guard(
                consent,
                "--user-prompt-submit",
                data_root=data_root,
                plugin_root=plugin_root,
            ).returncode,
            0,
        )
        self.assert_strict_allow(
            self.run_guard(
                launch,
                data_root=data_root,
                plugin_root=plugin_root,
            )
        )
        capability = self.bind_pr_worker(
            launch,
            data_root=data_root,
            plugin_root=plugin_root,
            agent_id="bound-pr-worker",
        )
        body = run_state.with_name("pr-body.md")
        body.write_text("PR body\n", encoding="utf-8")
        broker_command = (
            f'python3 "{plugin_root / "scripts" / "vsdd-pr-action.py"}" publish '
            f'--worktree "{worktree}" --slug sample '
            f'--session-id {launch["session_id"]} --agent-id bound-pr-worker '
            f'--capability {capability} --title "Test PR" --body-file "{body}"'
        )
        pr_worker = {
            "agent_type": "ecc-vsdd:vsdd-pr-worker",
            "session_id": launch["session_id"],
            "prompt_id": launch["prompt_id"],
            "cwd": launch["cwd"],
            "effort": {"level": "medium"},
            "tool_name": "Bash",
            "tool_input": {"command": broker_command},
        }

        allowed = self.run_global_guard(
            pr_worker,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assert_strict_allow(allowed)

        direct_pr_worker = dict(pr_worker)
        direct_pr_worker.update(
            {
                "hook_event_name": "PreToolUse",
                "tool_input": {"command": "gh pr create --fill"},
            }
        )
        direct = self.run_global_guard(
            direct_pr_worker,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(direct.returncode, 0)
        decision = json.loads(direct.stdout)["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn(
            "direct external Git/GitHub mutation",
            decision["permissionDecisionReason"],
        )

        status_worker = dict(pr_worker)
        status_worker.update(
            {
                "agent_type": "ecc-vsdd:vsdd-status-worker",
                "agent_id": "status-worker-1",
                "effort": {"level": "low"},
                "tool_input": {"command": broker_command},
            }
        )
        wrong_worker = self.run_global_guard(
            status_worker,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(wrong_worker.returncode, 2)
        self.assertIn("PR action broker", wrong_worker.stderr)

    def test_broker_invocation_must_match_bound_capability_and_context(self) -> None:
        plugin_root, worktree, run_state = self.make_pr_gate_fixture()
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-pr-broker-context-")
        launch = self.pr_launch_payload(worktree, run_state)
        consent = self.user_prompt(
            "/ecc-vsdd:vsdd-run resume sample --until pr",
            session_id=launch["session_id"],
            prompt_id=launch["prompt_id"],
            cwd=launch["cwd"],
        )
        self.assertEqual(
            self.run_guard(
                consent,
                "--user-prompt-submit",
                data_root=data_root,
                plugin_root=plugin_root,
            ).returncode,
            0,
        )
        self.assert_strict_allow(
            self.run_guard(
                launch,
                data_root=data_root,
                plugin_root=plugin_root,
            )
        )
        self.bind_pr_worker(
            launch,
            data_root=data_root,
            plugin_root=plugin_root,
            agent_id="bound-pr-worker",
        )
        worker = {
            "agent_type": "ecc-vsdd:vsdd-pr-worker",
            "agent_id": "bound-pr-worker",
            "session_id": launch["session_id"],
            "prompt_id": launch["prompt_id"],
            "cwd": launch["cwd"],
            "effort": {"level": "medium"},
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    f'python3 "{plugin_root / "scripts" / "vsdd-pr-action.py"}" '
                    f'publish --worktree "{worktree}" --slug sample '
                    f'--session-id {launch["session_id"]} '
                    "--agent-id bound-pr-worker --capability wrong-capability "
                    f'--title "Test PR" --body-file "{run_state.with_name("pr-body.md")}"'
                )
            },
        }

        result = self.run_global_guard(
            worker,
            data_root=data_root,
            plugin_root=plugin_root,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("broker invocation does not match", result.stderr)

    def test_pr_worker_launch_requires_context_and_ready_preflight(self) -> None:
        missing = self.orchestrator_launch()
        missing["tool_name"] = "Agent"
        missing["cwd"] = tempfile.mkdtemp(prefix="ecc-vsdd-missing-context-")
        materialized = self.user_prompt(
            "/ecc-vsdd:vsdd-run status sample",
            session_id=missing["session_id"],
            prompt_id=missing["prompt_id"],
            cwd=missing["cwd"],
        )
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-missing-context-state-")
        self.run_guard(materialized, "--user-prompt-submit", data_root=data_root)
        missing["tool_input"] = {"subagent_type": "vsdd-pr-worker"}
        rejected = self.run_guard(missing, data_root=data_root)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("VSDD_RUN_CONTEXT", rejected.stderr)

        plugin_root, worktree, run_state = self.make_pr_gate_fixture()
        allowed = self.pr_launch_payload(worktree, run_state)
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-pr-session-")
        consent = self.user_prompt(
            "/ecc-vsdd:vsdd-run resume sample --until pr",
            session_id=allowed["session_id"],
            prompt_id=allowed["prompt_id"],
            cwd=allowed["cwd"],
        )
        recorded = self.run_guard(
            consent,
            "--user-prompt-submit",
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)

        self.assert_strict_allow(
            self.run_guard(
                allowed,
                data_root=data_root,
                plugin_root=plugin_root,
            )
        )
        self.bind_pr_worker(
            allowed,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        worker = {
            "agent_type": "ecc-vsdd:vsdd-pr-worker",
            "session_id": allowed["session_id"],
            "prompt_id": allowed["prompt_id"],
            "cwd": allowed["cwd"],
            "effort": {"level": "medium"},
            "tool_name": "Bash",
            "tool_input": {"command": "git status --short"},
        }
        self.assert_strict_allow(
            self.run_global_guard(
                worker,
                data_root=data_root,
                plugin_root=plugin_root,
            )
        )

        (plugin_root / "scripts" / "vsdd-runtime-state.py").write_text(
            "import sys\nprint('stale review evidence', file=sys.stderr)\nsys.exit(1)\n",
            encoding="utf-8",
        )
        stale = self.run_global_guard(
            worker,
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(stale.returncode, 2)
        self.assertIn("PR worker preflight failed", stale.stderr)

        ended = self.run_guard(
            allowed,
            "--session-end",
            data_root=data_root,
            plugin_root=plugin_root,
        )
        self.assertEqual(ended.returncode, 0, ended.stderr)
        self.assertEqual(
            list(Path(data_root).rglob("orchestrator-session.json")), []
        )

    def test_orchestrator_allows_detached_launcher_poll_protocol(self) -> None:
        launcher_path = ROOT / "scripts" / "vsdd-launch-worker.py"
        commands = [
            (
                f'python3 "{launcher_path}" plan --slug sample '
                "--worktree /tmp/sample --detach"
            ),
            (
                f'python3 "{launcher_path}" wait --slug sample '
                "--worktree /tmp/sample --evidence "
                "/tmp/sample/.claude/specs/sample/worker-supervisors/plan-abc.json "
                "--wait-seconds 45"
            ),
        ]

        for command in commands:
            with self.subTest(command=command):
                payload = self.orchestrator_launch()
                payload["tool_name"] = "Bash"
                payload["tool_input"] = {
                    "command": command,
                    "run_in_background": False,
                }

                result = self.run_guard(payload)

                self.assert_strict_allow(result)

    def test_strict_orchestrator_launch_auto_approves_after_validation(self) -> None:
        self.assert_strict_allow(self.run_guard(self.orchestrator_launch()))

    def test_strict_hook_works_without_plugin_data_environment(self) -> None:
        runtime_root = tempfile.mkdtemp(prefix="ecc-vsdd-runtime-root-")
        result = self.run_guard(
            self.orchestrator_launch(), data_root=runtime_root
        )

        self.assert_strict_allow(result)
        records = list(Path(runtime_root).rglob("orchestrator-session.json"))
        self.assertEqual(len(records), 1)

    @unittest.skipIf(os.name == "nt", "POSIX directory modes are not portable")
    def test_guard_runtime_root_and_record_directory_are_private(self) -> None:
        runtime_root = tempfile.mkdtemp(prefix="ecc-vsdd-runtime-mode-")
        result = self.run_guard(
            self.orchestrator_launch(), data_root=runtime_root
        )

        self.assert_strict_allow(result)
        record = next(Path(runtime_root).rglob("orchestrator-session.json"))
        guard_root = record.parents[1]
        self.assertEqual(guard_root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(record.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(record.stat().st_mode & 0o777, 0o600)

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics are required")
    def test_private_record_write_rejects_preplanted_temporary_symlink(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ecc-vsdd-private-write-")) / "guard"
        record = root / "authorized-sessions" / "sample.json"
        record.parent.mkdir(parents=True, mode=0o700)
        sentinel = root / "sentinel.txt"
        sentinel.write_text("sentinel\n", encoding="utf-8")
        temporary = record.with_name(f".{record.name}.4242.tmp")
        temporary.symlink_to(sentinel)

        with mock.patch.object(guard, "guard_runtime_root", return_value=root):
            with mock.patch.object(guard.os, "getpid", return_value=4242):
                with self.assertRaises(OSError):
                    guard.write_private_json(record, {"authorization": "test"})

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "sentinel\n")

    @unittest.skipIf(os.name == "nt", "POSIX file security semantics are required")
    def test_private_record_read_rejects_unsafe_file_forms(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ecc-vsdd-private-read-")) / "guard"
        records = root / "pr-authorized-sessions"
        records.mkdir(parents=True, mode=0o700)
        root.chmod(0o700)
        records.chmod(0o700)

        with mock.patch.object(guard, "guard_runtime_root", return_value=root):
            wrong_mode = records / "wrong-mode.json"
            wrong_mode.write_text("{}\n", encoding="utf-8")
            wrong_mode.chmod(0o644)
            self.assertIsNone(guard.read_private_json(wrong_mode))

            hard_link = records / "hard-link.json"
            hard_link.write_text("{}\n", encoding="utf-8")
            hard_link.chmod(0o600)
            os.link(hard_link, records / "hard-link-copy.json")
            self.assertIsNone(guard.read_private_json(hard_link))

            directory = records / "directory.json"
            directory.mkdir(mode=0o700)
            self.assertIsNone(guard.read_private_json(directory))

            fifo = records / "fifo.json"
            os.mkfifo(fifo, mode=0o600)
            self.assertIsNone(guard.read_private_json(fifo))

            symlink = records / "symlink.json"
            target = records / "symlink-target.json"
            target.write_text("{}\n", encoding="utf-8")
            target.chmod(0o600)
            symlink.symlink_to(target)
            self.assertIsNone(guard.read_private_json(symlink))

    def test_session_start_sweeps_expired_authorization_records(self) -> None:
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-expired-sweep-")
        payload = self.orchestrator_launch()
        payload["session_id"] = "expired-sweep-session"
        self.assert_strict_allow(self.run_guard(payload, data_root=data_root))
        record = next(Path(data_root).rglob("expired-sweep-session.json"))
        value = json.loads(record.read_text(encoding="utf-8"))
        value["created_at"] = 1
        record.write_text(json.dumps(value), encoding="utf-8")
        record.chmod(0o600)

        started = self.run_guard(
            {
                "session_id": "new-session",
                "cwd": str(ROOT),
                "hook_event_name": "SessionStart",
                "source": "startup",
            },
            "--session-start",
            data_root=data_root,
        )

        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertEqual(
            list(Path(data_root).rglob("expired-sweep-session.json")), []
        )

    @unittest.skipIf(os.name == "nt", "POSIX directory modes are not portable")
    def test_owned_legacy_runtime_root_is_migrated_to_private_mode(self) -> None:
        runtime_root = tempfile.mkdtemp(prefix="ecc-vsdd-runtime-migration-")
        guard_root = Path(runtime_root) / f"ecc-vsdd-guard-{os.getuid()}"
        guard_root.mkdir(mode=0o755)
        guard_root.chmod(0o755)

        result = self.run_guard(
            self.orchestrator_launch(), data_root=runtime_root
        )

        self.assert_strict_allow(result)
        self.assertEqual(guard_root.stat().st_mode & 0o777, 0o700)

    def test_hook_configs_do_not_require_plugin_data_in_skill_scope(self) -> None:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        prompt_args = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["args"]
        session_args = hooks["hooks"]["SessionStart"][0]["hooks"][0]["args"]
        global_args = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["args"]
        subagent = hooks["hooks"]["SubagentStart"][0]
        end_args = hooks["hooks"]["SessionEnd"][0]["hooks"][0]["args"]
        self.assertEqual(prompt_args[-1], "--user-prompt-submit")
        self.assertEqual(session_args[-1], "--session-start")
        self.assertEqual(len(global_args), 1)
        self.assertNotIn("matcher", subagent)
        self.assertEqual(subagent["hooks"][0]["args"][-1], "--subagent-start")
        self.assertEqual(end_args[-1], "--session-end")
        self.assertNotIn("CLAUDE_PLUGIN_DATA", json.dumps(hooks))

        skill = (ROOT / "skills" / "vsdd-run" / "SKILL.md").read_text()
        self.assertNotIn("CLAUDE_PLUGIN_DATA", skill)
        self.assertNotIn("--data-root", skill)

    def test_user_prompt_materializes_and_cleans_protected_project_workers(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-protected-agents-"))
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-protected-agent-state-")
        payload = {
            "session_id": "protected-agent-session",
            "prompt_id": "prompt-12345678",
            "cwd": str(project),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/ecc-vsdd:vsdd-run start sample BRIEF.md --until review",
        }

        created = self.run_guard(
            payload,
            "--user-prompt-submit",
            data_root=data_root,
        )

        self.assertEqual(created.returncode, 0, created.stderr)
        context = json.loads(created.stdout)["hookSpecificOutput"][
            "additionalContext"
        ]
        self.assertIn("protected project workers", context)
        agent_dir = project / ".claude" / "agents"
        expected_names = {
            f"{name.split(':', 1)[1]}.md" for name in guard.ORCHESTRATOR_AGENTS
        }
        self.assertEqual({path.name for path in agent_dir.glob("*.md")}, expected_names)
        for path in agent_dir.glob("*.md"):
            content = path.read_text(encoding="utf-8")
            with self.subTest(agent=path.name):
                self.assertIn(guard.PROJECT_AGENT_MARKER, content)
                self.assertIn(str(SCRIPT), content)
                self.assertIn("--project-agent", content)
                self.assertNotIn("          args:\n", content)
                self.assertIn("hooks:\n  PreToolUse:", content)

        ended = self.run_guard(
            {
                **payload,
                "hook_event_name": "SessionEnd",
                "reason": "clear",
            },
            "--session-end",
            data_root=data_root,
        )
        self.assertEqual(ended.returncode, 0, ended.stderr)
        self.assertEqual(list(agent_dir.glob("*.md")), [])

    def test_parent_session_requires_exact_relay_before_phase_work(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-relay-parent-"))
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-relay-parent-state-")
        prompt = {
            "session_id": "relay-parent-session",
            "prompt_id": "prompt-12345678",
            "cwd": str(project),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/ecc-vsdd:vsdd-run status sample",
        }
        created = self.run_guard(
            prompt,
            "--user-prompt-submit",
            data_root=data_root,
            ECC_VSDD_PROJECT_AGENTS_READY="",
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        context = json.loads(created.stdout)["hookSpecificOutput"][
            "additionalContext"
        ]
        relay_command = context.split("start command: ", 1)[1].split(
            ". Then invoke", 1
        )[0]
        wait_command = context.split("wait command: ", 1)[1].split(
            ". Repeat", 1
        )[0]
        self.assertIn("--relay-start", relay_command)
        self.assertIn("--relay-wait", wait_command)
        launch = self.orchestrator_launch()
        launch.update(
            {
                "session_id": prompt["session_id"],
                "prompt_id": prompt["prompt_id"],
                "cwd": prompt["cwd"],
                "tool_name": "Read",
                "tool_input": {"file_path": str(project / "README.md")},
            }
        )
        denied = self.run_guard(
            launch,
            data_root=data_root,
            ECC_VSDD_PROJECT_AGENTS_READY="",
        )
        self.assertEqual(denied.returncode, 2)
        self.assertIn("protected orchestrator relay", denied.stderr)

        launch["tool_name"] = "Bash"
        launch["tool_input"] = {"command": relay_command}
        allowed = self.run_guard(
            launch,
            data_root=data_root,
            ECC_VSDD_PROJECT_AGENTS_READY="",
        )
        self.assert_strict_allow(allowed)

    def test_relay_supervisor_runs_ready_child_and_wait_returns_result(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-relay-runner-"))
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-relay-runner-state-")
        payload = {
            "session_id": "relay-runner-session",
            "prompt_id": "prompt-12345678",
            "cwd": str(project),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/ecc-vsdd:vsdd-run status sample",
        }
        with mock.patch.dict(
            os.environ,
            {
                "CLAUDE_PLUGIN_ROOT": str(ROOT),
                "TMPDIR": data_root,
                guard.PROJECT_AGENTS_READY_ENV: "",
            },
            clear=False,
        ):
            guard.ACTIVE_HOOK_EVENT = "UserPromptSubmit"
            start_command, wait_command = guard.create_orchestrator_relay(payload)
            start_tokens = shlex.split(start_command)
            wait_tokens = shlex.split(wait_command)
            capability = start_tokens[-1]
            completed = subprocess.CompletedProcess(
                args=["claude"], returncode=0, stdout="child complete\n", stderr=""
            )
            supervisor = mock.Mock(pid=4321)
            with mock.patch.object(
                guard.subprocess, "Popen", return_value=supervisor
            ) as detached, mock.patch(
                "pathlib.Path.cwd", return_value=project
            ), mock.patch("sys.stdout", new_callable=io.StringIO) as start_stdout:
                guard.ACTIVE_HOOK_EVENT = ""
                guard.start_orchestrator_relay(start_tokens[3:])
            self.assertEqual(detached.call_count, 1)
            self.assertIn('"status": "STARTED"', start_stdout.getvalue())

            with mock.patch.object(
                guard.time, "monotonic", side_effect=[0.0, 46.0]
            ), mock.patch("pathlib.Path.cwd", return_value=project), mock.patch(
                "sys.stdout", new_callable=io.StringIO
            ) as running_stdout:
                guard.wait_orchestrator_relay(wait_tokens[3:])
            self.assertIn('"status": "RUNNING"', running_stdout.getvalue())

            with mock.patch.object(
                guard.shutil, "which", return_value="/usr/bin/claude"
            ), mock.patch.object(
                guard.subprocess, "run", return_value=completed
            ) as launched, mock.patch("pathlib.Path.cwd", return_value=project):
                guard.supervise_orchestrator_relay(
                    [
                        "--session-id",
                        payload["session_id"],
                        "--capability",
                        capability,
                    ]
                )
            child_env = launched.call_args.kwargs["env"]
            self.assertEqual(child_env[guard.PROJECT_AGENTS_READY_ENV], "1")
            child_command = launched.call_args.args[0]
            self.assertIn("ecc-vsdd:vsdd-orchestrator", child_command)
            self.assertIn("acceptEdits", child_command)
            self.assertEqual(
                child_command[child_command.index("--add-dir") + 1],
                str(guard.MANAGED_WORKTREE_ROOT.resolve()),
            )

            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout, mock.patch(
                "pathlib.Path.cwd", return_value=project
            ):
                with self.assertRaisesRegex(SystemExit, "0"):
                    guard.wait_orchestrator_relay(wait_tokens[3:])
            self.assertIn("child complete", stdout.getvalue())
            self.assertIn('"status": "COMPLETE"', stdout.getvalue())
            record_path = guard.orchestrator_relay_record_path(payload["session_id"])
            self.assertIsNotNone(record_path)
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertIsInstance(record["consumed_at"], int)

    def test_relay_parser_and_start_fail_closed(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-relay-errors-"))
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-relay-errors-state-")
        payload = {
            "session_id": "relay-errors-session",
            "prompt_id": "prompt-12345678",
            "cwd": str(project),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/ecc-vsdd:vsdd-run status sample",
        }
        malformed = (
            "python3 guard.py --relay-start\n--session-id bad",
            "python3 $(command -v guard.py) --relay-start",
            "'unterminated",
            "python3",
            "python3 /wrong/guard.py --relay-start --session-id s --prompt-id p --capability c",
        )
        with mock.patch.dict(
            os.environ,
            {
                "CLAUDE_PLUGIN_ROOT": str(ROOT),
                "TMPDIR": data_root,
                guard.PROJECT_AGENTS_READY_ENV: "",
            },
            clear=False,
        ):
            for command in malformed:
                with self.subTest(command=command):
                    self.assertIsNone(guard.relay_invocation(command))
            guard.ACTIVE_HOOK_EVENT = "UserPromptSubmit"
            start_command, wait_command = guard.create_orchestrator_relay(payload)
            start_tokens = shlex.split(start_command)
            wait_tokens = shlex.split(wait_command)
            guard.ACTIVE_HOOK_EVENT = ""
            with mock.patch("pathlib.Path.cwd", return_value=project):
                with self.assertRaisesRegex(SystemExit, "2"):
                    guard.wait_orchestrator_relay(wait_tokens[3:])
                with mock.patch.object(
                    guard.subprocess, "Popen", side_effect=OSError("boom")
                ):
                    with self.assertRaisesRegex(SystemExit, "2"):
                        guard.start_orchestrator_relay(start_tokens[3:])
            record_path = guard.orchestrator_relay_record_path(payload["session_id"])
            self.assertIsNotNone(record_path)
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(record["status"], "BLOCKED")
            self.assertIn("cannot start protected orchestrator supervisor", record["error"])

    def test_project_worker_materialization_refuses_user_agent_collision(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-agent-collision-"))
        agent_dir = project / ".claude" / "agents"
        agent_dir.mkdir(parents=True)
        existing = agent_dir / "vsdd-status-worker.md"
        existing.write_text("---\nname: vsdd-status-worker\n---\nuser file\n")

        result = self.run_guard(
            {
                "session_id": "collision-session",
                "prompt_id": "prompt-12345678",
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "/ecc-vsdd:vsdd-run status sample",
            },
            "--user-prompt-submit",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("refuses to overwrite existing project agent", result.stderr)
        self.assertEqual(existing.read_text(), "---\nname: vsdd-status-worker\n---\nuser file\n")

    def test_project_worker_materialization_refuses_spoofed_generated_marker(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-agent-marker-spoof-"))
        agent_dir = project / ".claude" / "agents"
        agent_dir.mkdir(parents=True)
        existing = agent_dir / "vsdd-status-worker.md"
        original = (
            "---\nname: vsdd-status-worker\n---\n"
            f"{guard.PROJECT_AGENT_MARKER}\nuser file\n"
        )
        existing.write_text(original, encoding="utf-8")

        result = self.run_guard(
            {
                "session_id": "marker-spoof-session",
                "prompt_id": "prompt-12345678",
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "/ecc-vsdd:vsdd-run status sample",
            },
            "--user-prompt-submit",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("refuses to overwrite existing project agent", result.stderr)
        self.assertEqual(existing.read_text(encoding="utf-8"), original)

    def test_new_session_adopts_recorded_proxies_and_cleanup_preserves_owners(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-agent-adoption-"))
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-agent-adoption-state-")
        first = {
            "session_id": "first-proxy-session",
            "prompt_id": "prompt-12345678",
            "cwd": str(project),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/ecc-vsdd:vsdd-run start sample BRIEF.md --until review",
        }
        second = {
            **first,
            "session_id": "second-proxy-session",
            "prompt_id": "prompt-87654321",
            "prompt": "/ecc-vsdd:vsdd-run resume sample",
        }

        self.assertEqual(
            self.run_guard(
                first, "--user-prompt-submit", data_root=data_root
            ).returncode,
            0,
        )
        adopted = self.run_guard(
            second, "--user-prompt-submit", data_root=data_root
        )
        self.assertEqual(adopted.returncode, 0, adopted.stderr)
        agent_dir = project / ".claude" / "agents"
        self.assertEqual(len(list(agent_dir.glob("*.md"))), 13)

        self.assertEqual(
            self.run_guard(
                {**second, "hook_event_name": "SessionEnd"},
                "--session-end",
                data_root=data_root,
            ).returncode,
            0,
        )
        self.assertEqual(len(list(agent_dir.glob("*.md"))), 13)
        self.assertEqual(
            self.run_guard(
                {**first, "hook_event_name": "SessionEnd"},
                "--session-end",
                data_root=data_root,
            ).returncode,
            0,
        )
        self.assertEqual(list(agent_dir.glob("*.md")), [])

    def test_session_start_removes_expired_recorded_proxies(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-agent-expiry-"))
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-agent-expiry-state-")
        prompt = {
            "session_id": "expired-proxy-session",
            "prompt_id": "prompt-12345678",
            "cwd": str(project),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/ecc-vsdd:vsdd-run status sample",
        }
        self.assertEqual(
            self.run_guard(
                prompt, "--user-prompt-submit", data_root=data_root
            ).returncode,
            0,
        )
        record = next(
            path
            for path in Path(data_root).rglob("expired-proxy-session.json")
            if path.parent.name == "materialized-agent-sessions"
        )
        value = json.loads(record.read_text(encoding="utf-8"))
        value["created_at"] = 0
        record.write_text(json.dumps(value), encoding="utf-8")
        record.chmod(0o600)

        started = self.run_guard(
            {
                "session_id": "replacement-session",
                "cwd": str(project),
                "hook_event_name": "SessionStart",
                "model": "fable",
                "effort": {"level": "high"},
                "agent_type": "ecc-vsdd:vsdd-orchestrator",
            },
            "--session-start",
            data_root=data_root,
        )

        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertFalse(record.exists())
        self.assertEqual(list((project / ".claude" / "agents").glob("*.md")), [])

    def test_subagent_start_injects_literal_plugin_root_for_every_worker(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-subagent-start-"))
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-subagent-start-state-")
        self.run_guard(
            {
                "session_id": "shared-session",
                "prompt_id": "prompt-12345678",
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "/ecc-vsdd:vsdd-run status sample",
            },
            "--user-prompt-submit",
            data_root=data_root,
        )
        payload = {
            "session_id": "shared-session",
            "prompt_id": "prompt-12345678",
            "cwd": str(project),
            "hook_event_name": "SubagentStart",
            "agent_type": "vsdd-steering-worker",
            "agent_id": "steering-worker-1",
        }

        result = self.run_guard(
            payload,
            "--subagent-start",
            data_root=data_root,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn(f"VSDD_PLUGIN_ROOT: {ROOT}", context)
        self.assertIn(
            f"VSDD_RUNTIME_STATE: {ROOT / 'scripts' / 'vsdd-runtime-state.py'}",
            context,
        )

    def test_subagent_start_rejects_empty_plugin_root(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-empty-root-"))
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-empty-root-state-")
        self.run_guard(
            {
                "session_id": "shared-session",
                "prompt_id": "prompt-12345678",
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "/ecc-vsdd:vsdd-run status sample",
            },
            "--user-prompt-submit",
            data_root=data_root,
        )
        payload = {
            "session_id": "shared-session",
            "prompt_id": "prompt-12345678",
            "cwd": str(project),
            "hook_event_name": "SubagentStart",
            "agent_type": "vsdd-steering-worker",
            "agent_id": "steering-worker-1",
        }

        result = self.run_guard(
            payload,
            "--subagent-start",
            data_root=data_root,
            CLAUDE_PLUGIN_ROOT="",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot resolve the installed plugin root", result.stderr)

    def test_orchestrator_rejects_unprotected_plugin_scoped_worker(self) -> None:
        launch = self.orchestrator_launch()
        launch["tool_name"] = "Agent"
        launch["tool_input"] = {
            "subagent_type": "ecc-vsdd:vsdd-code-reviewer"
        }

        result = self.run_guard(launch)

        self.assertEqual(result.returncode, 2)
        self.assertIn("project-local protected worker", result.stderr)

    def test_project_worker_hook_allows_only_an_untampered_materialized_agent(self) -> None:
        project = Path(tempfile.mkdtemp(prefix="ecc-vsdd-project-hook-"))
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-project-hook-state-")
        prompt = {
            "session_id": "project-hook-session",
            "prompt_id": "prompt-12345678",
            "cwd": str(project),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/ecc-vsdd:vsdd-run status sample",
        }
        created = self.run_guard(
            prompt,
            "--user-prompt-submit",
            data_root=data_root,
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        launch = self.orchestrator_launch()
        launch.update(
            {
                "session_id": prompt["session_id"],
                "prompt_id": prompt["prompt_id"],
                "cwd": prompt["cwd"],
            }
        )
        self.assert_strict_allow(self.run_guard(launch, data_root=data_root))
        worker = {
            "agent_type": "vsdd-status-worker",
            "session_id": prompt["session_id"],
            "prompt_id": prompt["prompt_id"],
            "cwd": prompt["cwd"],
            "hook_event_name": "PreToolUse",
            "effort": {"level": "low"},
            "tool_name": "Write",
            "tool_input": {"file_path": str(project / "status.txt")},
        }

        allowed = self.run_guard(
            worker,
            "--project-agent",
            data_root=data_root,
            CLAUDE_PLUGIN_ROOT="",
        )
        self.assert_strict_allow(allowed)

        proxy = project / ".claude" / "agents" / "vsdd-status-worker.md"
        proxy.write_text(proxy.read_text() + "tampered\n", encoding="utf-8")
        denied = self.run_guard(
            worker,
            "--project-agent",
            data_root=data_root,
            CLAUDE_PLUGIN_ROOT="",
        )
        self.assertEqual(denied.returncode, 0)
        decision = json.loads(denied.stdout)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("materialized project agent", decision["permissionDecisionReason"])

    def test_pr_preflight_rejects_empty_plugin_root_before_execution(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": ""}):
            with self.assertRaisesRegex(
                SystemExit,
                "2",
            ):
                guard.run_pr_preflight(ROOT, "sample")

    def test_pr_worker_contract_requires_the_bundled_broker(self) -> None:
        agent = (ROOT / "agents" / "vsdd-pr-worker.md").read_text(encoding="utf-8")
        skill = (ROOT / "skills" / "vsdd-pr" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("vsdd-pr-action.py", agent)
        self.assertIn("vsdd-pr-action.py", skill)
        self.assertIn("Never run `git push`", agent)
        self.assertIn("Do not push", skill)
        self.assertIn("VSDD_PR_ACTION_CAPABILITY", skill)

    def test_non_strict_global_hook_does_not_auto_approve_worker_tools(self) -> None:
        payload = {
            "agent_type": "ecc-vsdd:vsdd-status-worker",
            "session_id": "shared-parent-session",
            "effort": {"level": "low"},
            "tool_name": "Bash",
            "tool_input": {"command": "python3 runtime.py preflight"},
        }
        result = self.run_global_guard(
            payload,
            data_root=tempfile.mkdtemp(prefix="ecc-vsdd-model-guard-global-"),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_strict_orchestrator_authorizes_pinned_worker_in_shared_session(self) -> None:
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-model-guard-authorized-")
        orchestrator = self.orchestrator_launch()
        orchestrator["session_id"] = "shared-authorized-session"
        self.assert_strict_allow(
            self.run_guard(orchestrator, data_root=data_root)
        )
        worker = {
            "agent_type": "ecc-vsdd:vsdd-status-worker",
            "session_id": "shared-authorized-session",
            "cwd": str(ROOT),
            "effort": {"level": "low"},
            "tool_name": "Bash",
            "tool_input": {"command": "python3 runtime.py preflight"},
        }

        self.assert_strict_allow(
            self.run_global_guard(worker, data_root=data_root)
        )

    @unittest.skipIf(os.name == "nt", "symlink semantics differ on Windows")
    def test_symlinked_authorization_record_is_not_trusted(self) -> None:
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-symlink-record-")
        orchestrator = self.orchestrator_launch()
        orchestrator["session_id"] = "symlinked-session"
        self.assert_strict_allow(
            self.run_guard(orchestrator, data_root=data_root)
        )
        record = next(Path(data_root).rglob("symlinked-session.json"))
        replacement = record.with_name("replacement.json")
        replacement.write_text(record.read_text(encoding="utf-8"), encoding="utf-8")
        replacement.chmod(0o600)
        record.unlink()
        record.symlink_to(replacement)
        worker = {
            "agent_type": "ecc-vsdd:vsdd-status-worker",
            "agent_id": "subagent-1",
            "session_id": "symlinked-session",
            "cwd": str(ROOT),
            "effort": {"level": "low"},
            "tool_name": "Read",
            "tool_input": {},
        }

        result = self.run_global_guard(worker, data_root=data_root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_authorization_is_bound_to_the_orchestrator_cwd(self) -> None:
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-cwd-bound-")
        orchestrator = self.orchestrator_launch()
        orchestrator["session_id"] = "cwd-bound-session"
        self.assert_strict_allow(
            self.run_guard(orchestrator, data_root=data_root)
        )
        worker = {
            "agent_type": "ecc-vsdd:vsdd-status-worker",
            "agent_id": "subagent-1",
            "session_id": "cwd-bound-session",
            "cwd": str(ROOT.parent),
            "effort": {"level": "low"},
            "tool_name": "Read",
            "tool_input": {},
        }

        result = self.run_global_guard(worker, data_root=data_root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_session_end_removes_authorization_and_model_records(self) -> None:
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-session-end-")
        payload = self.orchestrator_launch()
        payload["session_id"] = "ending-session"
        payload["model"] = "claude-fable-5"
        started = self.run_guard(
            payload, "--session-start", data_root=data_root
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assert_strict_allow(self.run_guard(payload, data_root=data_root))
        self.assertGreaterEqual(
            len(list(Path(data_root).rglob("ending-session.json"))), 2
        )

        ended = self.run_guard(payload, "--session-end", data_root=data_root)

        self.assertEqual(ended.returncode, 0, ended.stderr)
        self.assertEqual(
            list(Path(data_root).rglob("ending-session.json")), []
        )

    def test_ultracode_main_session_uses_launcher_effort_not_frontmatter(self) -> None:
        data_root = tempfile.mkdtemp(prefix="ecc-vsdd-ultracode-record-")
        session_start = {
            "hook_event_name": "SessionStart",
            "agent_type": "ecc-vsdd:vsdd-implementation-driver",
            "session_id": "implementation-session",
            "model": "claude-sonnet-5",
        }
        recorded = self.run_guard(
            session_start, "--session-start", data_root=data_root
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)

        payload = {
            "agent_type": "ecc-vsdd:vsdd-implementation-driver",
            "session_id": "implementation-session",
            "effort": {"level": "xhigh"},
            "tool_name": "Read",
            "tool_input": {},
        }
        result = self.run_guard(payload, data_root=data_root)

        self.assert_strict_allow(result)


if __name__ == "__main__":
    unittest.main()
