from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


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
    def assert_blocked(self, operation) -> str:
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit):
            operation()
        return output.getvalue()

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

    def test_plan_prompt_enforces_permission_safe_unattended_workflow(self) -> None:
        root, spec = self.make_repo()

        prompt = launcher.build_prompt("plan", "sample", ROOT, root)

        self.assertIn(str(spec / "progress.md"), prompt)
        self.assertIn("never ask for permission or user input", prompt)
        self.assertIn("Read, Glob, or Grep rather than shell cat/sed/head/tail", prompt)
        self.assertIn("remain in this session until its completion notification", prompt)
        self.assertIn("workflow_run_id", prompt)
        self.assertIn("never reuse it as completion evidence", prompt)

    def test_unattended_tools_allow_safe_artifact_reads(self) -> None:
        self.assertIn("Read", launcher.UNATTENDED_ALLOWED_TOOLS)
        self.assertIn("Glob", launcher.UNATTENDED_ALLOWED_TOOLS)
        self.assertIn("Grep", launcher.UNATTENDED_ALLOWED_TOOLS)
        self.assertIn("Bash(cat *)", launcher.UNATTENDED_ALLOWED_TOOLS)
        self.assertNotIn("Bash(*)", launcher.UNATTENDED_ALLOWED_TOOLS)

    def test_worker_environment_waits_for_background_workflow_without_ceiling(self) -> None:
        env = launcher.worker_environment()

        self.assertEqual(env["CLAUDE_CODE_SUBAGENT_MODEL"], "sonnet")
        self.assertEqual(env["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"], "0")

    def test_implement_prompt_requires_progress_sync_and_task_gate(self) -> None:
        root, _ = self.make_repo()

        prompt = launcher.build_prompt("implement", "sample", ROOT, root)

        self.assertIn("progress.md", prompt)
        self.assertIn("status done", prompt)
        self.assertIn("runtime task-gate", prompt)

    def test_plan_artifact_rejects_stale_content(self) -> None:
        marker = {"sha256": "same", "size": 10, "mtime_ns": 1}

        self.assertIn(
            "did not produce new",
            launcher.planning_artifact_issue("plan", marker, marker) or "",
        )
        self.assertIsNone(
            launcher.planning_artifact_issue(
                "plan",
                marker,
                {"sha256": "new", "size": 11, "mtime_ns": 2},
            )
        )

    def test_plan_artifact_must_record_current_workflow_run_id(self) -> None:
        root, spec = self.make_repo()
        path = spec / "implementation-workflow.md"
        path.write_text("# Plan\n\nWorkflow: wf_old\n", encoding="utf-8")

        self.assertIn(
            "does not record current",
            launcher.workflow_evidence_issue(path, "wf_current") or "",
        )
        self.assertIsNone(launcher.workflow_evidence_issue(path, "wf_old"))

    def test_plan_launch_calls_runtime_preflight_before_claude(self) -> None:
        root, _ = self.make_repo()

        result = subprocess.run(
            [
                sys.executable,
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

    def test_io_process_and_terminal_helpers_fail_closed(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ecc-vsdd-launch-helpers-"))
        invalid = root / "invalid.json"
        invalid.write_text("{", encoding="utf-8")
        self.assertIn("cannot read", self.assert_blocked(lambda: launcher.read_json(invalid)))

        with mock.patch.object(launcher.os, "replace", side_effect=OSError("denied")):
            self.assertIn(
                "cannot persist",
                self.assert_blocked(
                    lambda: launcher.write_json_atomic(root / "record.json", {})
                ),
            )

        self.assertFalse(launcher.process_alive(0))
        self.assertFalse(launcher.process_alive("not-a-pid"))
        with mock.patch.object(launcher.os, "kill", side_effect=PermissionError):
            self.assertTrue(launcher.process_alive(123))

        terminal = launcher.parse_terminal_json(
            "noise\n{\"status\": \"COMPLETE\", \"value\": 1}\n", ""
        )
        self.assertEqual(terminal["value"], 1)
        fallback = launcher.parse_terminal_json("noise\n", "failure")
        self.assertEqual(fallback["status"], "BLOCKED")
        self.assertEqual(fallback["raw_stderr"], "failure")

    def test_supervisor_helpers_reject_stale_and_ambiguous_state(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="ecc-vsdd-supervisors-"))
        stale = directory / "plan-stale.json"
        stale.write_text(
            json.dumps({"status": "RUNNING", "pid": 999999}), encoding="utf-8"
        )
        with mock.patch.object(launcher, "process_alive", return_value=False):
            self.assertIsNone(launcher.running_supervisor(directory, "plan"))
        self.assertEqual(launcher.read_json(stale)["status"], "BLOCKED")

        for name in ("plan-one.json", "plan-two.json"):
            (directory / name).write_text(
                json.dumps({"status": "RUNNING", "pid": 1}), encoding="utf-8"
            )
        with mock.patch.object(launcher, "process_alive", return_value=True):
            output = self.assert_blocked(
                lambda: launcher.running_supervisor(directory, "plan")
            )
        self.assertIn("multiple live detached supervisors", output)

    def test_wait_helper_validates_and_reports_every_terminal_shape(self) -> None:
        worktree = Path(tempfile.mkdtemp(prefix="ecc-vsdd-wait-helper-")).resolve()
        supervisors = worktree / ".claude/specs/sample/worker-supervisors"
        supervisors.mkdir(parents=True)
        evidence = supervisors / "plan-run.json"

        self.assertIn(
            "must be under",
            self.assert_blocked(
                lambda: launcher.wait_for_detached_launcher(
                    worktree / "outside.json", worktree, "sample", 0
                )
            ),
        )
        self.assertIn(
            "between 0 and 55",
            self.assert_blocked(
                lambda: launcher.wait_for_detached_launcher(
                    evidence, worktree, "sample", 56
                )
            ),
        )
        self.assertIn(
            "evidence not found",
            self.assert_blocked(
                lambda: launcher.wait_for_detached_launcher(
                    evidence, worktree, "sample", 0
                )
            ),
        )

        base = {"slug": "sample", "worktree": str(worktree), "pid": 123}
        evidence.write_text(
            json.dumps({**base, "slug": "other", "status": "RUNNING"}),
            encoding="utf-8",
        )
        self.assertIn(
            "does not match",
            self.assert_blocked(
                lambda: launcher.wait_for_detached_launcher(
                    evidence, worktree, "sample", 0
                )
            ),
        )

        evidence.write_text(
            json.dumps({**base, "status": "COMPLETE"}), encoding="utf-8"
        )
        self.assertIn(
            "no terminal result",
            self.assert_blocked(
                lambda: launcher.wait_for_detached_launcher(
                    evidence, worktree, "sample", 0
                )
            ),
        )

        evidence.write_text(
            json.dumps({**base, "status": "UNKNOWN"}), encoding="utf-8"
        )
        self.assertIn(
            "invalid detached launcher status",
            self.assert_blocked(
                lambda: launcher.wait_for_detached_launcher(
                    evidence, worktree, "sample", 0
                )
            ),
        )

        evidence.write_text(
            json.dumps({**base, "status": "RUNNING"}), encoding="utf-8"
        )
        with mock.patch.object(launcher, "process_alive", return_value=False):
            self.assert_blocked(
                lambda: launcher.wait_for_detached_launcher(
                    evidence, worktree, "sample", 0
                )
            )
        self.assertEqual(launcher.read_json(evidence)["status"], "BLOCKED")

        evidence.write_text(
            json.dumps({**base, "status": "RUNNING", "stage": "plan"}),
            encoding="utf-8",
        )
        with mock.patch.object(launcher, "process_alive", return_value=True):
            output = io.StringIO()
            with redirect_stdout(output):
                launcher.wait_for_detached_launcher(
                    evidence, worktree, "sample", 0
                )
        self.assertEqual(json.loads(output.getvalue())["status"], "RUNNING")

        evidence.write_text(
            json.dumps(
                {
                    **base,
                    "status": "COMPLETE",
                    "result": {"status": "COMPLETE", "stage": "plan"},
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()
        with redirect_stdout(output):
            launcher.wait_for_detached_launcher(evidence, worktree, "sample", 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "COMPLETE")

    def test_configuration_git_and_review_helpers_fail_closed(self) -> None:
        worktree = Path(tempfile.mkdtemp(prefix="ecc-vsdd-config-helper-"))
        with mock.patch.dict(
            os.environ, {"CLAUDE_CODE_DISABLE_WORKFLOWS": "1"}, clear=False
        ):
            self.assertEqual(
                launcher.workflows_disabled(worktree),
                "CLAUDE_CODE_DISABLE_WORKFLOWS=1",
            )
        settings = worktree / ".claude/settings.json"
        settings.parent.mkdir()
        settings.write_text('{"disableWorkflows": true}', encoding="utf-8")
        self.assertIn("settings.json", launcher.workflows_disabled(worktree) or "")

        invalid_version = subprocess.CompletedProcess(
            ["claude", "--version"], 1, stdout="", stderr="broken"
        )
        with mock.patch.object(launcher.subprocess, "run", return_value=invalid_version):
            self.assertIn(
                "cannot determine",
                self.assert_blocked(lambda: launcher.claude_version("claude")),
            )
        self.assertIn(
            "git status failed",
            self.assert_blocked(lambda: launcher.git_output(worktree, "status")),
        )
        with mock.patch.object(
            launcher,
            "git_output",
            return_value='?? one.txt\nR  old.txt -> new.txt\nx',
        ):
            self.assertEqual(launcher.changed_paths(worktree), {"one.txt", "new.txt"})

        review = worktree / "review.md"
        review.write_text(
            "---\nverdict: PASS\nreviewer_model: opus\n"
            "reviewer_effort: xhigh\n---\n",
            encoding="utf-8",
        )
        self.assertEqual(launcher.parse_frontmatter(review)["verdict"], "PASS")
        launcher.require_pass(review)
        for key, value, expected in (
            ("verdict", "REVISE", "PASS verdict"),
            ("reviewer_model", "sonnet", "reviewer_model"),
            ("reviewer_effort", "high", "reviewer_effort"),
        ):
            text = review.read_text(encoding="utf-8").replace(
                f"{key}: " + launcher.parse_frontmatter(review)[key],
                f"{key}: {value}",
            )
            review.write_text(text, encoding="utf-8")
            self.assertIn(
                expected,
                self.assert_blocked(lambda path=review: launcher.require_pass(path)),
            )
            review.write_text(
                "---\nverdict: PASS\nreviewer_model: opus\n"
                "reviewer_effort: xhigh\n---\n",
                encoding="utf-8",
            )

    def test_state_and_gate_helpers_cover_rejection_paths(self) -> None:
        invalid_state = {
            "status": "STOPPED",
            "implementation_session_id": "already-bound",
            "phases": {},
        }
        self.assertGreaterEqual(
            len(launcher.stage_state_issues("plan", invalid_state, None)), 3
        )
        self.assertGreaterEqual(
            len(launcher.stage_state_issues("revise-plan", invalid_state, "wrong")),
            4,
        )
        self.assertGreaterEqual(
            len(launcher.stage_state_issues("implement", invalid_state, "wrong")), 4
        )
        self.assertIn(
            "remediation phase must be PENDING",
            launcher.stage_state_issues("remediate", invalid_state, None),
        )

        invalid_json = subprocess.CompletedProcess(
            ["runtime"], 0, stdout="not-json", stderr=""
        )
        with mock.patch.object(launcher.subprocess, "run", return_value=invalid_json):
            self.assertIn(
                "invalid output",
                self.assert_blocked(
                    lambda: launcher.require_runtime_preflight(
                        ROOT, Path("/tmp"), "sample", "plan", None
                    )
                ),
            )
            self.assertEqual(
                launcher.task_integrity_issue(ROOT, Path("/tmp"), "sample"),
                "task-integrity gate returned invalid output",
            )

        blocked = subprocess.CompletedProcess(
            ["runtime"], 1, stdout='{"status":"BLOCKED","error":"stale"}', stderr=""
        )
        with mock.patch.object(launcher.subprocess, "run", return_value=blocked):
            self.assertIn(
                "stale",
                launcher.task_integrity_issue(ROOT, Path("/tmp"), "sample") or "",
            )

        state_path = Path(tempfile.mkdtemp(prefix="ecc-vsdd-bind-helper-")) / "state.json"
        state_path.write_text(
            json.dumps({"implementation_session_id": "first"}), encoding="utf-8"
        )
        self.assertIn(
            "cannot replace",
            self.assert_blocked(
                lambda: launcher.bind_implementation_session(state_path, "second")
            ),
        )

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
            "    print('2.1.214')\n"
            "    raise SystemExit(0)\n"
            "session_id = sys.argv[sys.argv.index('--session-id') + 1]\n"
            "time.sleep(0.2)\n"
            "path = Path('.claude/specs/sample/implementation-workflow.md')\n"
            "path.write_text('# Approved workflow candidate\\n\\nWorkflow: wf_test-plan\\n', encoding='utf-8')\n"
            "print(json.dumps({'session_id': session_id, 'structured_output': "
            "{'status': 'COMPLETE', 'stage': 'plan', 'summary': 'planned', "
            "'workflow_run_id': 'wf_test-plan'}}))\n",
            encoding="utf-8",
        )
        fake_claude.chmod(0o755)
        env = os.environ.copy()
        env["VSDD_CLAUDE_BIN"] = str(fake_claude)
        config_root, _ = self.make_dependency_config(root)
        env["CLAUDE_CONFIG_DIR"] = str(config_root)

        result = subprocess.run(
            [
                sys.executable,
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
                sys.executable,
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
                    sys.executable,
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
