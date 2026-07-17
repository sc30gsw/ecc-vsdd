from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "vsdd-model-guard.py"


class ModelGuardTest(unittest.TestCase):
    def run_guard(
        self,
        payload: dict,
        *arguments: str,
        data_root: str | None = None,
        **environment: str,
    ) -> subprocess.CompletedProcess[str]:
        data_root = data_root or tempfile.mkdtemp(prefix="ecc-vsdd-model-guard-")
        env = os.environ.copy()
        env.update(
            {
                "CLAUDE_PLUGIN_ROOT": str(ROOT),
                "TMPDIR": data_root,
            }
        )
        env.pop("CLAUDE_PLUGIN_DATA", None)
        env.pop("CLAUDE_CODE_SUBAGENT_MODEL", None)
        env.update(environment)
        return subprocess.run(
            ["python3", str(SCRIPT), *(arguments or ("--strict",))],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def run_global_guard(
        self, payload: dict, *, data_root: str
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "CLAUDE_PLUGIN_ROOT": str(ROOT),
                "TMPDIR": data_root,
            }
        )
        env.pop("CLAUDE_PLUGIN_DATA", None)
        env.pop("CLAUDE_CODE_SUBAGENT_MODEL", None)
        return subprocess.run(
            ["python3", str(SCRIPT)],
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
            "cwd": str(ROOT),
            "effort": {"level": "high"},
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "ecc-vsdd:vsdd-code-reviewer"},
        }

    def assert_strict_allow(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        decision = output["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "allow")

    def test_rejects_per_invocation_model_override(self) -> None:
        payload = self.orchestrator_launch()
        payload["tool_input"]["model"] = "sonnet"

        result = self.run_guard(payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn("model override", result.stderr)

    def test_rejects_global_subagent_model_override(self) -> None:
        result = self.run_guard(
            self.orchestrator_launch(), CLAUDE_CODE_SUBAGENT_MODEL="sonnet"
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
            "agent_id": "subagent-1",
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
        session_args = hooks["hooks"]["SessionStart"][0]["hooks"][0]["args"]
        global_args = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["args"]
        end_args = hooks["hooks"]["SessionEnd"][0]["hooks"][0]["args"]
        self.assertEqual(session_args[-1], "--session-start")
        self.assertEqual(len(global_args), 1)
        self.assertEqual(end_args[-1], "--session-end")
        self.assertNotIn("CLAUDE_PLUGIN_DATA", json.dumps(hooks))

        skill = (ROOT / "skills" / "vsdd-run" / "SKILL.md").read_text()
        self.assertNotIn("CLAUDE_PLUGIN_DATA", skill)
        self.assertNotIn("--data-root", skill)

    def test_non_strict_global_hook_does_not_auto_approve_worker_tools(self) -> None:
        payload = {
            "agent_type": "ecc-vsdd:vsdd-status-worker",
            "agent_id": "subagent-1",
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
            "agent_id": "subagent-1",
            "session_id": "shared-authorized-session",
            "cwd": str(ROOT),
            "effort": {"level": "low"},
            "tool_name": "Bash",
            "tool_input": {"command": "python3 runtime.py preflight"},
        }

        self.assert_strict_allow(
            self.run_global_guard(worker, data_root=data_root)
        )

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
