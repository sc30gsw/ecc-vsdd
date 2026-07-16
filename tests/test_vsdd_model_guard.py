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
                "CLAUDE_PLUGIN_DATA": data_root,
            }
        )
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

    def orchestrator_launch(self) -> dict:
        return {
            "agent_type": "ecc-vsdd:vsdd-orchestrator",
            "session_id": "orchestrator-session",
            "effort": {"level": "high"},
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "ecc-vsdd:vsdd-code-reviewer"},
        }

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
            "effort": {"level": "xhigh"},
            "tool_name": "Read",
            "tool_input": {},
        }
        result = self.run_guard(payload, data_root=data_root)

        self.assertEqual(result.returncode, 0, result.stderr)

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

        self.assertEqual(result.returncode, 0, result.stderr)

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

                self.assertEqual(result.returncode, 0, result.stderr)

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

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
