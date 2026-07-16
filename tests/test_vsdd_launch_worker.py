from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "vsdd-launch-worker.py"
SPEC = importlib.util.spec_from_file_location("vsdd_launch_worker", SCRIPT)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)
RUNTIME_SCRIPT = ROOT / "scripts" / "vsdd-runtime-state.py"
RUNTIME_SPEC = importlib.util.spec_from_file_location("vsdd_runtime_state", RUNTIME_SCRIPT)
assert RUNTIME_SPEC and RUNTIME_SPEC.loader
runtime = importlib.util.module_from_spec(RUNTIME_SPEC)
RUNTIME_SPEC.loader.exec_module(runtime)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class LaunchWorkerTest(unittest.TestCase):
    def make_repo(self) -> tuple[Path, Path]:
        root = Path(tempfile.mkdtemp(prefix="ecc-vsdd-launch-test-"))
        git(root.parent, "init", "-b", "vsdd/sample", str(root))
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        git(root, "add", "README.md")
        git(
            root,
            "-c",
            "user.name=VSDD Test",
            "-c",
            "user.email=vsdd@example.invalid",
            "commit",
            "-m",
            "fixture",
        )
        spec = root / ".claude" / "specs" / "sample"
        spec.mkdir(parents=True)
        (spec / "tasks.md").write_text(
            "<!-- Artifact not yet generated. Run the corresponding vsdd-* skill. -->\n",
            encoding="utf-8",
        )
        head = git(root, "rev-parse", "HEAD")
        state = {
            "schema_version": 4,
            "slug": "sample",
            "status": "RUNNING",
            "base_ref": "vsdd/sample",
            "base_branch": "develop",
            "base_sha": head,
            "integration_branch": "vsdd/sample",
            "integration_worktree": str(root),
            "phases": {"implementation-plan": {"status": "PENDING"}},
            "artifact_hashes": {},
            "attempt_ledger": {},
        }
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        return root, spec

    def make_dependency_config(self, root: Path) -> tuple[Path, Path]:
        config_root = root.parent / f"{root.name}-claude-config"
        ecc_root = root.parent / f"{root.name}-ecc-plugin"
        (ecc_root / ".claude-plugin").mkdir(parents=True)
        (ecc_root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "ecc", "version": "2.0.0"}), encoding="utf-8"
        )
        (config_root / "plugins").mkdir(parents=True)
        (config_root / "plugins" / "installed_plugins.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "plugins": {
                        "ecc@ecc": [
                            {
                                "scope": "project",
                                "projectPath": str(root),
                                "installPath": str(ecc_root),
                                "version": "2.0.0",
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        return config_root, ecc_root

    def test_child_plugin_dirs_include_manifest_dependency(self) -> None:
        root, _ = self.make_repo()
        config_root, ecc_root = self.make_dependency_config(root)

        plugin_dirs = launcher.plugin_dirs_for_child(ROOT, config_root=config_root)

        self.assertEqual(plugin_dirs, [ecc_root.resolve(), ROOT.resolve()])

    def test_plan_launch_calls_runtime_preflight_before_claude(self) -> None:
        root, _ = self.make_repo()

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "plan",
                "--slug",
                "sample",
                "--worktree",
                str(root),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("deterministic preflight", result.stdout)
        self.assertNotIn("claude executable not found", result.stdout)

    def test_implement_requires_current_bound_session_and_pending_phase(self) -> None:
        state = {
            "status": "RUNNING",
            "implementation_session_id": "expected-session",
            "phases": {
                "implementation-plan-review": {
                    "status": "COMPLETE",
                    "verdict": "PASS",
                },
                "implementation": {"status": "PENDING"},
            },
        }

        self.assertEqual(
            launcher.stage_state_issues("implement", state, "wrong-session"),
            ["implementation session_id does not match run-state"],
        )
        self.assertEqual(
            launcher.stage_state_issues("implement", state, "expected-session"), []
        )
        state["phases"]["implementation"]["status"] = "COMPLETE"
        self.assertIn(
            "implementation phase must be PENDING",
            launcher.stage_state_issues("implement", state, "expected-session"),
        )

    def test_revise_plan_requires_a_revise_snapshot(self) -> None:
        state = {
            "status": "RUNNING",
            "implementation_session_id": "expected-session",
            "phases": {
                "implementation-plan": {"status": "COMPLETE"},
                "implementation-plan-review": {
                    "status": "COMPLETE",
                    "verdict": "PASS",
                },
            },
        }

        issues = launcher.stage_state_issues(
            "revise-plan", state, "expected-session"
        )

        self.assertIn("implementation-plan-review must be REVISE", issues)

    def test_detached_plan_can_be_polled_to_completion_and_binds_session(self) -> None:
        root, spec = self.make_repo()
        steering = root / ".claude" / "specs" / "_steering"
        steering.mkdir()
        for name in ("tech.md", "structure.md", "context.md"):
            (steering / name).write_text(f"# {name}\n", encoding="utf-8")
        (steering / "open-questions.md").write_text("## Open\n\n", encoding="utf-8")
        (spec / "tasks.md").write_text("### TASK-001 — One\n", encoding="utf-8")
        (spec / "progress.md").write_text(
            "| Task | Title | Status | Started | Completed |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| TASK-001 | One | pending | — | — |\n",
            encoding="utf-8",
        )
        state = runtime.read_state(root, "sample")
        state["phases"].update(
            {
                "steering": {"status": "COMPLETE"},
                "init": {"status": "COMPLETE"},
                "requirements": {"status": "COMPLETE"},
                "requirements-review": {"status": "COMPLETE"},
                "design": {"status": "COMPLETE"},
                "tasks": {"status": "COMPLETE"},
                "plan-review": {"status": "PENDING"},
                "implementation-plan": {"status": "PENDING"},
            }
        )
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        review_dir = spec / "review-results"
        review_dir.mkdir()
        (review_dir / "plan-review.md").write_text(
            "---\n"
            "review_type: plan\n"
            "target_commit: N/A\n"
            "verdict: PASS\n"
            "critical: 0\n"
            "high: 0\n"
            "medium: 0\n"
            "low: 0\n"
            "remediation_mode: none\n"
            "reviewer_model: opus\n"
            "reviewer_effort: xhigh\n"
            "review_attempt: 1\n"
            "---\n\n# Review\n",
            encoding="utf-8",
        )
        runtime.begin_attempt(root, "sample", "plan-review")
        runtime.snapshot_phase(root, "sample", "plan-review")

        fake_claude = root.parent / f"{root.name}-fake-claude"
        fake_claude.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys, time\n"
            "from pathlib import Path\n"
            "if '--version' in sys.argv:\n"
            "    print('2.1.203')\n"
            "    raise SystemExit(0)\n"
            "session_id = sys.argv[sys.argv.index('--session-id') + 1]\n"
            "time.sleep(0.2)\n"
            "path = Path('.claude/specs/sample/implementation-workflow.md')\n"
            "path.write_text('# Approved workflow candidate\\n', encoding='utf-8')\n"
            "print(json.dumps({'session_id': session_id, 'structured_output': "
            "{'status': 'COMPLETE', 'stage': 'plan', 'summary': 'planned'}}))\n",
            encoding="utf-8",
        )
        fake_claude.chmod(0o755)
        env = os.environ.copy()
        env["VSDD_CLAUDE_BIN"] = str(fake_claude)
        config_root, _ = self.make_dependency_config(root)
        env["CLAUDE_CONFIG_DIR"] = str(config_root)

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "plan",
                "--slug",
                "sample",
                "--worktree",
                str(root),
                "--detach",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        started = json.loads(result.stdout)
        self.assertEqual(started["status"], "STARTED")

        duplicate = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "plan",
                "--slug",
                "sample",
                "--worktree",
                str(root),
                "--detach",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(duplicate.returncode, 0, duplicate.stdout + duplicate.stderr)
        reused = json.loads(duplicate.stdout)
        self.assertEqual(reused["status"], "RUNNING")
        self.assertTrue(reused["reused"])
        self.assertEqual(reused["evidence"], started["evidence"])

        output: dict = {}
        for _ in range(10):
            waited = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "wait",
                    "--slug",
                    "sample",
                    "--worktree",
                    str(root),
                    "--evidence",
                    started["evidence"],
                    "--wait-seconds",
                    "1",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(waited.returncode, 0, waited.stdout + waited.stderr)
            output = json.loads(waited.stdout)
            if output["status"] == "COMPLETE":
                break

        self.assertEqual(output["status"], "COMPLETE")
        updated = runtime.read_state(root, "sample")
        self.assertEqual(updated["implementation_session_id"], output["session_id"])
        self.assertTrue((spec / "implementation-workflow.md").is_file())


if __name__ == "__main__":
    unittest.main()
