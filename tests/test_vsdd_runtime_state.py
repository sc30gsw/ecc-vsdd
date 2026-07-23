from __future__ import annotations

import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "vsdd-runtime-state.py"
SPEC = importlib.util.spec_from_file_location("vsdd_runtime_state", SCRIPT)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class RuntimeStateTest(unittest.TestCase):
    def managed_worktree(self, source: Path, slug: str = "sample") -> Path:
        worktree = runtime.managed_worktree_path(slug)
        runtime.MANAGED_WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
        if worktree.exists():
            self.skipTest(f"managed worktree fixture is already in use: {worktree}")

        def cleanup() -> None:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if worktree.exists():
                shutil.rmtree(worktree)

        self.addCleanup(cleanup)
        return worktree

    def make_repo(self, branch: str = "develop") -> Path:
        root = Path(tempfile.mkdtemp(prefix="ecc-vsdd-runtime-test-"))
        git(root.parent, "init", "-b", branch, str(root))
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
        return root

    def make_spec(self) -> tuple[Path, Path]:
        root = self.make_repo()
        spec = root / ".vsdd" / "specs" / "sample"
        steering = root / ".vsdd" / "specs" / "_steering"
        spec.mkdir(parents=True)
        steering.mkdir(parents=True)
        (steering / "tech.md").write_text("# Tech\n", encoding="utf-8")
        (steering / "structure.md").write_text("# Structure\n", encoding="utf-8")
        return root, spec

    def write_run_state(self, root: Path, spec: Path) -> None:
        head = git(root, "rev-parse", "HEAD")
        state = {
            "schema_version": 2,
            "slug": "sample",
            "status": "RUNNING",
            "base_ref": "develop",
            "base_branch": "develop",
            "base_sha": head,
            "integration_branch": "vsdd/sample",
            "integration_worktree": str(root),
            "phases": {},
            "artifact_hashes": {},
        }
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")

    def write_complete_steering(self, root: Path) -> None:
        steering = root / ".vsdd" / "specs" / "_steering"
        (steering / "tech.md").write_text("# Tech\n", encoding="utf-8")
        (steering / "structure.md").write_text("# Structure\n", encoding="utf-8")
        (steering / "context.md").write_text("# Context\n", encoding="utf-8")
        (steering / "open-questions.md").write_text("## Open\n\n", encoding="utf-8")

    def write_review(
        self,
        spec: Path,
        filename: str,
        review_type: str,
        target_commit: str,
        verdict: str = "PASS",
        attempt: int = 1,
    ) -> None:
        review_dir = spec / "review-results"
        review_dir.mkdir(exist_ok=True)
        high = 0 if verdict == "PASS" else 1
        (review_dir / filename).write_text(
            "---\n"
            f"review_type: {review_type}\n"
            f"target_commit: {target_commit}\n"
            f"verdict: {verdict}\n"
            "critical: 0\n"
            f"high: {high}\n"
            "medium: 0\n"
            "low: 0\n"
            "remediation_mode: none\n"
            "reviewer_model: opus\n"
            "reviewer_effort: xhigh\n"
            f"review_attempt: {attempt}\n"
            "---\n\n# Review\n",
            encoding="utf-8",
        )

    def write_completed_implementation(self, root: Path, spec: Path) -> str:
        head = git(root, "rev-parse", "HEAD")
        (spec / "tasks.md").write_text("### TASK-001 — One\n", encoding="utf-8")
        (spec / "progress.md").write_text(
            "| Task | Title | Status | Started | Completed |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| TASK-001 | One | done | — | now |\n",
            encoding="utf-8",
        )
        (spec / "implementation-ledger.md").write_text(
            "## TASK-to-SHA Mapping\n\n"
            "| TASK | Commit |\n| --- | --- |\n"
            f"| TASK-001 | {head} |\n",
            encoding="utf-8",
        )
        runtime.begin_attempt(root, "sample", "implementation-task", task_id="TASK-001")
        runtime.finish_attempt(
            root,
            "sample",
            "implementation-task",
            task_id="TASK-001",
            attempt=1,
            outcome="PASS",
        )
        return head

    def begin_review_attempt(self, root: Path, phase: str) -> None:
        state = runtime.read_state(root, "sample")
        scope = runtime.REVIEW_ATTEMPT_SCOPES[phase]
        if scope not in state.get("attempt_ledger", {}):
            runtime.begin_attempt(root, "sample", scope)

    def prepare_review_complete_run(self) -> tuple[Path, Path, str]:
        root, spec = self.make_spec()
        git(root, "branch", "-m", "vsdd/sample")
        self.write_run_state(root, spec)
        self.write_complete_steering(root)
        head = self.write_completed_implementation(root, spec)
        state = runtime.read_state(root, "sample")
        state["until"] = "review"
        state["phases"] = {"implementation": {"status": "COMPLETE"}}
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        review_specs = (
            ("requirements-review", "requirement-review.md", "requirements", "N/A"),
            ("plan-review", "plan-review.md", "plan", "N/A"),
            (
                "implementation-plan-review",
                "implementation-workflow-review.md",
                "implementation-workflow",
                "N/A",
            ),
            ("code-review", "code-review.md", "code", head),
            ("security-review", "security-review.md", "security", head),
        )
        for phase, filename, review_type, target in review_specs:
            self.write_review(spec, filename, review_type, target)
            self.begin_review_attempt(root, phase)
            runtime.snapshot_phase(root, "sample", phase)
        return root, spec, head

    def test_detect_base_uses_origin_head(self) -> None:
        repo = self.make_repo("develop")
        head = git(repo, "rev-parse", "HEAD")
        git(repo, "update-ref", "refs/remotes/origin/develop", head)
        git(
            repo,
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/develop",
        )

        detected = runtime.detect_base(repo, None)

        self.assertEqual(detected["base_ref"], "origin/develop")
        self.assertEqual(detected["base_branch"], "develop")
        self.assertEqual(detected["base_sha"], head)

    def test_detect_base_blocks_ambiguous_fallback(self) -> None:
        repo = self.make_repo("feature")
        git(repo, "branch", "main")
        git(repo, "branch", "master")

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "--base"):
            runtime.detect_base(repo, None)

    def test_detect_base_accepts_an_explicit_ref(self) -> None:
        repo = self.make_repo("release")

        detected = runtime.detect_base(repo, "release")

        self.assertEqual(detected["base_ref"], "release")
        self.assertEqual(detected["base_branch"], "release")

    def test_integration_gate_rejects_commits_on_default_branch(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)

        issues = runtime.integration_issues(
            root, "sample", runtime.read_state(root, "sample")
        )

        self.assertTrue(any("integration branch" in issue for issue in issues))

    def test_integration_gate_rejects_default_branch_even_when_state_claims_it(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)
        state = runtime.read_state(root, "sample")
        state["integration_branch"] = "develop"
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")

        issues = runtime.integration_issues(root, "sample", state)

        self.assertTrue(any("must record 'vsdd/sample'" in issue for issue in issues))

    def test_managed_bootstrap_accepts_only_the_precreated_run_state(self) -> None:
        root, spec = self.make_spec()
        git(root, "branch", "-m", "vsdd/sample")
        self.write_run_state(root, spec)
        self.write_complete_steering(root)
        state = runtime.read_state(root, "sample")
        state["bootstrap_status"] = "READY"
        state["phases"] = {
            "steering": {"status": "COMPLETE"},
            "init": {"status": "PENDING"},
        }
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")

        self.assertEqual(runtime.bootstrap_issues(root, "sample", state), [])
        self.assertEqual(
            runtime.preflight(root, "sample", "init"),
            {"status": "READY", "phase": "init"},
        )

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "Init outputs are missing"):
            runtime.snapshot_phase(root, "sample", "init")

        (spec / "review-results").mkdir()
        for name in (
            "progress.md",
            "change-log.md",
            "requirements.md",
            "design.md",
            "tasks.md",
        ):
            (spec / name).write_text("placeholder\n", encoding="utf-8")
        source = spec / "source-request.md"
        source.write_text("initial source\n", encoding="utf-8")
        runtime.snapshot_phase(root, "sample", "init")
        consumed = runtime.read_state(root, "sample")
        self.assertEqual(consumed["bootstrap_status"], "CONSUMED")
        self.assertEqual(
            consumed["source_paths"],
            [".vsdd/specs/sample/source-request.md"],
        )

        source.write_text("changed source\n", encoding="utf-8")
        invalidated = runtime.audit_state(root, "sample")
        self.assertEqual(invalidated["earliest_phase"], "requirements")

        (spec / "progress.md").write_text("collision\n", encoding="utf-8")
        issues = runtime.bootstrap_issues(root, "sample", state)

        self.assertTrue(any("unexpected pre-init artifact" in issue for issue in issues))

    def test_steering_gate_blocks_open_draft_and_glossary(self) -> None:
        root, spec = self.make_spec()
        steering = root / ".vsdd" / "specs" / "_steering"
        (steering / "open-questions.md").write_text(
            "## Open\n\n### Q-001: Meaning\n\n- Status: open\n",
            encoding="utf-8",
        )
        (steering / "context.md").write_text(
            "### Term\n\nMeaning\n\n<!-- DRAFT 2026-07-16 -->\n",
            encoding="utf-8",
        )
        (spec / "requirements.md").write_text(
            "> **Glossary pending**: Term\n", encoding="utf-8"
        )

        issues = runtime.steering_issues(root, "sample")

        self.assertTrue(any("Q-001" in issue for issue in issues))
        self.assertTrue(any("DRAFT" in issue for issue in issues))
        self.assertTrue(any("Glossary pending" in issue for issue in issues))

    def test_steering_gate_accepts_assumed_entries(self) -> None:
        root, spec = self.make_spec()
        steering = root / ".vsdd" / "specs" / "_steering"
        (steering / "open-questions.md").write_text(
            "## Open\n\n### Q-001: Technical choice\n\n"
            "- Status: assumed\n- Assumption: reversible\n",
            encoding="utf-8",
        )
        (steering / "context.md").write_text(
            "### Term\n\nMeaning\n\n<!-- ASSUMED 2026-07-16 source:src/model.py -->\n",
            encoding="utf-8",
        )
        (spec / "requirements.md").write_text("# Requirements\n", encoding="utf-8")

        self.assertEqual(runtime.steering_issues(root, "sample"), [])

    def test_preflight_rechecks_new_open_question_before_review(self) -> None:
        root, spec = self.make_spec()
        git(root, "branch", "-m", "vsdd/sample")
        self.write_run_state(root, spec)
        steering = root / ".vsdd" / "specs" / "_steering"
        (steering / "context.md").write_text("# Context\n", encoding="utf-8")
        (steering / "open-questions.md").write_text(
            "## Open\n\n### Q-002: New requirement term\n\n"
            "- Impact: product\n- Status: open\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "Q-002"):
            runtime.preflight(root, "sample", "requirements-review")

    def test_task_gate_requires_exact_progress_set(self) -> None:
        root, spec = self.make_spec()
        (spec / "tasks.md").write_text(
            "### TASK-001 — One\n\n### TASK-002 — Two\n", encoding="utf-8"
        )
        (spec / "progress.md").write_text(
            "| Task | Title | Status | Started | Completed |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| TASK-001 | One | pending | — | — |\n",
            encoding="utf-8",
        )

        issues = runtime.task_set_issues(root, "sample", require_ledger=False)

        self.assertTrue(any("TASK-002" in issue for issue in issues))

    def test_uncommitted_gate_checks_both_sides_of_a_rename(self) -> None:
        root, spec = self.make_spec()
        destination = spec / "moved-product.py"
        git(root, "mv", "README.md", str(destination.relative_to(root)))

        issues = runtime.uncommitted_non_spec_issues(root, "sample")

        self.assertTrue(any("README.md" in issue for issue in issues))

    def test_post_implementation_gate_requires_exact_ledger_mapping(self) -> None:
        root, spec = self.make_spec()
        (spec / "tasks.md").write_text(
            "### TASK-001 — One\n\n### TASK-002 — Two\n", encoding="utf-8"
        )
        (spec / "progress.md").write_text(
            "| Task | Title | Status | Started | Completed |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| TASK-001 | One | done | — | now |\n"
            "| TASK-002 | Two | done | — | now |\n",
            encoding="utf-8",
        )
        (spec / "implementation-ledger.md").write_text(
            "## TASK-to-SHA Mapping\n\n"
            "| TASK | Commit |\n| --- | --- |\n"
            "| TASK-001 | abcdef1 |\n",
            encoding="utf-8",
        )

        issues = runtime.task_set_issues(root, "sample", require_ledger=True)

        self.assertTrue(any("TASK-002" in issue for issue in issues))

    def test_post_implementation_gate_accepts_existing_commits(self) -> None:
        root, spec = self.make_spec()
        head = git(root, "rev-parse", "HEAD")
        (spec / "tasks.md").write_text("### TASK-001 — One\n", encoding="utf-8")
        (spec / "progress.md").write_text(
            "| Task | Title | Status | Started | Completed |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| TASK-001 | One | done | — | now |\n",
            encoding="utf-8",
        )
        (spec / "implementation-ledger.md").write_text(
            "## TASK-to-SHA Mapping\n\n"
            "| TASK | Commit |\n| --- | --- |\n"
            f"| TASK-001 | `{head}` |\n",
            encoding="utf-8",
        )

        self.assertEqual(
            runtime.task_set_issues(root, "sample", require_ledger=True), []
        )

        git(root, "branch", "-m", "vsdd/sample")
        self.write_run_state(root, spec)
        state = runtime.read_state(root, "sample")
        state.setdefault("attempt_ledger", {})["implementation-task:TASK-001"] = {
            "attempts_started": 1,
            "limit": 3,
            "last_finished_attempt": 1,
            "last_outcome": "PASS",
        }
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(
            runtime.task_gate(root, "sample"),
            {"status": "READY", "gate": "task-integrity"},
        )

    def test_post_implementation_gate_rejects_unmerged_commit_objects(self) -> None:
        root, spec = self.make_spec()
        git(root, "checkout", "-b", "task/one")
        (root / "task.txt").write_text("unmerged\n", encoding="utf-8")
        git(root, "add", "task.txt")
        git(
            root,
            "-c",
            "user.name=VSDD Test",
            "-c",
            "user.email=vsdd@example.invalid",
            "commit",
            "-m",
            "task commit",
        )
        task_commit = git(root, "rev-parse", "HEAD")
        git(root, "checkout", "develop")
        (spec / "tasks.md").write_text("### TASK-001 — One\n", encoding="utf-8")
        (spec / "progress.md").write_text(
            "| Task | Title | Status | Started | Completed |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| TASK-001 | One | done | — | now |\n",
            encoding="utf-8",
        )
        (spec / "implementation-ledger.md").write_text(
            "## TASK-to-SHA Mapping\n\n"
            "| TASK | Commit |\n| --- | --- |\n"
            f"| TASK-001 | {task_commit} |\n",
            encoding="utf-8",
        )

        issues = runtime.task_set_issues(root, "sample", require_ledger=True)

        self.assertTrue(any("not reachable from integration HEAD" in issue for issue in issues))

    def test_audit_invalidates_changed_artifact_and_downstream(self) -> None:
        root, spec = self.make_spec()
        requirements = spec / "requirements.md"
        requirements.write_text("# Requirements v1\n", encoding="utf-8")
        state = {
            "schema_version": 2,
            "slug": "sample",
            "status": "RUNNING",
            "phases": {
                phase: {"status": "COMPLETE"}
                for phase in ("steering", "init", "requirements", "requirements-review", "design")
            },
            "artifact_hashes": {},
        }
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        runtime.snapshot_phase(root, "sample", "requirements")
        requirements.write_text("# Requirements v2\n", encoding="utf-8")

        result = runtime.audit_state(root, "sample")
        updated = json.loads((spec / "run-state.json").read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "INVALIDATED")
        self.assertEqual(result["earliest_phase"], "requirements")
        self.assertEqual(updated["phases"]["steering"]["status"], "COMPLETE")
        self.assertEqual(updated["phases"]["requirements"]["status"], "PENDING")
        self.assertEqual(updated["phases"]["design"]["status"], "PENDING")
        self.assertEqual(runtime.audit_state(root, "sample")["status"], "VALID")
        self.assertNotIn(
            ".vsdd/specs/sample/requirements.md", updated["artifact_hashes"]
        )

    def test_source_change_invalidates_from_requirements(self) -> None:
        root, spec = self.make_spec()
        source = spec / "source-notion.md"
        source.write_text("source v1\n", encoding="utf-8")
        state = {
            "schema_version": 2,
            "slug": "sample",
            "status": "RUNNING",
            "phases": {"init": {"status": "COMPLETE"}, "requirements": {"status": "COMPLETE"}},
            "artifact_hashes": {},
        }
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        runtime.snapshot_phase(root, "sample", "source")
        source.write_text("source v2\n", encoding="utf-8")

        result = runtime.audit_state(root, "sample")

        self.assertEqual(result["earliest_phase"], "requirements")

    def test_resnapshot_changed_requirements_invalidates_only_dependents(self) -> None:
        root, spec = self.make_spec()
        requirements = spec / "requirements.md"
        requirements.write_text("# Requirements v1\n", encoding="utf-8")
        state = {
            "schema_version": 3,
            "slug": "sample",
            "status": "RUNNING",
            "phases": {
                phase: {"status": "COMPLETE"}
                for phase in (
                    "requirements",
                    "requirements-review",
                    "design",
                    "tasks",
                )
            },
            "artifact_hashes": {},
        }
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        runtime.snapshot_phase(root, "sample", "requirements")
        state = runtime.read_state(root, "sample")
        for phase in ("requirements-review", "design", "tasks"):
            state["phases"][phase]["status"] = "COMPLETE"
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        requirements.write_text("# Requirements v2\n", encoding="utf-8")

        runtime.snapshot_phase(root, "sample", "requirements")
        updated = runtime.read_state(root, "sample")

        self.assertEqual(updated["phases"]["requirements"]["status"], "COMPLETE")
        for phase in ("requirements-review", "design", "tasks"):
            self.assertEqual(updated["phases"][phase]["status"], "PENDING")

    def test_remediation_resnapshot_invalidates_both_reviews_and_pr(self) -> None:
        root, spec = self.make_spec()
        ledger = spec / "implementation-ledger.md"
        ledger.write_text("# Ledger v1\n", encoding="utf-8")
        state = {
            "schema_version": 3,
            "slug": "sample",
            "status": "RUNNING",
            "phases": {
                phase: {"status": "COMPLETE"}
                for phase in ("implementation", "code-review", "security-review", "pr")
            },
            "artifact_hashes": {},
        }
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        runtime.snapshot_phase(root, "sample", "implementation")
        state = runtime.read_state(root, "sample")
        for phase in ("code-review", "security-review", "pr"):
            state["phases"][phase]["status"] = "COMPLETE"
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        ledger.write_text("# Ledger v2 after remediation\n", encoding="utf-8")

        runtime.snapshot_phase(root, "sample", "remediation")
        updated = runtime.read_state(root, "sample")

        self.assertEqual(updated["phases"]["remediation"]["status"], "COMPLETE")
        for phase in ("code-review", "security-review", "pr"):
            self.assertEqual(updated["phases"][phase]["status"], "PENDING")

    def test_pr_snapshot_requires_structured_current_evidence(self) -> None:
        root, spec = self.make_spec()
        git(root, "branch", "-m", "vsdd/sample")
        self.write_run_state(root, spec)

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "pr-result.json"):
            runtime.snapshot_phase(root, "sample", "pr")

        head = git(root, "rev-parse", "HEAD")
        state = runtime.read_state(root, "sample")
        evidence = {
            "url": "https://github.com/sc30gsw/example/pull/42",
            "number": 42,
            "base_branch": state["base_branch"],
            "base_sha": state["base_sha"],
            "head_branch": "vsdd/sample",
            "head_sha": head,
            "target_commit": head,
        }
        (spec / "pr-result.json").write_text(json.dumps(evidence), encoding="utf-8")

        runtime.snapshot_phase(root, "sample", "pr")
        updated = runtime.read_state(root, "sample")

        self.assertEqual(updated["phases"]["pr"]["status"], "COMPLETE")
        self.assertEqual(updated["phases"]["pr"]["url"], evidence["url"])
        self.assertEqual(updated["phases"]["pr"]["target_commit"], head)

    def test_pr_snapshot_rejects_stale_head_evidence(self) -> None:
        root, spec = self.make_spec()
        git(root, "branch", "-m", "vsdd/sample")
        self.write_run_state(root, spec)
        state = runtime.read_state(root, "sample")
        evidence = {
            "url": "https://github.com/sc30gsw/example/pull/42",
            "number": 42,
            "base_branch": state["base_branch"],
            "base_sha": state["base_sha"],
            "head_branch": "vsdd/sample",
            "head_sha": "0" * 40,
            "target_commit": "0" * 40,
        }
        (spec / "pr-result.json").write_text(json.dumps(evidence), encoding="utf-8")

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "current integration HEAD"):
            runtime.snapshot_phase(root, "sample", "pr")

    def test_bootstrap_creates_only_managed_run_state_in_new_worktree(self) -> None:
        source = self.make_repo("develop")
        worktree = self.managed_worktree(source)

        result = runtime.bootstrap_run(
            source,
            "sample",
            worktree,
            request="Add a sample feature with tests",
            until="review",
            mode="auto",
            explicit_base=None,
        )

        self.assertEqual(git(source, "branch", "--show-current"), "develop")
        self.assertEqual(result["status"], "BOOTSTRAPPED")
        spec = worktree / ".vsdd" / "specs" / "sample"
        self.assertEqual({path.name for path in spec.iterdir()}, {"run-state.json"})
        state = json.loads((spec / "run-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["bootstrap_status"], "READY")
        self.assertEqual(state["integration_branch"], "vsdd/sample")
        self.assertEqual(state["phases"]["init"]["status"], "PENDING")

    def test_bootstrap_rejects_dirty_source_and_existing_branch(self) -> None:
        source = self.make_repo("develop")
        worktree = self.managed_worktree(source)
        (source / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "clean source checkout"):
            runtime.bootstrap_run(
                source,
                "sample",
                worktree,
                request="Feature",
                until="review",
                mode="auto",
                explicit_base=None,
            )

        (source / "dirty.txt").unlink()
        git(source, "branch", "vsdd/sample")
        with self.assertRaisesRegex(runtime.RuntimeBlocked, "branch already exists"):
            runtime.bootstrap_run(
                source,
                "sample",
                worktree,
                request="Feature",
                until="review",
                mode="auto",
                explicit_base=None,
            )

    def test_bootstrap_ignores_only_generated_project_agent_proxies(self) -> None:
        source = self.make_repo("develop")
        worktree = self.managed_worktree(source)
        agent = source / ".claude" / "agents" / "vsdd-status-worker.md"
        agent.parent.mkdir(parents=True)
        agent.write_text(
            "---\nname: vsdd-status-worker\n"
            "hooks:\n  PreToolUse:\n"
            "    - hooks:\n"
            "        - type: command\n"
            '          command: "python3 /plugin/scripts/vsdd-model-guard.py --project-agent"\n'
            "---\n"
            f"{runtime.PROJECT_AGENT_MARKER}\n",
            encoding="utf-8",
        )

        result = runtime.bootstrap_run(
            source,
            "sample",
            worktree,
            request="Feature",
            until="review",
            mode="auto",
            explicit_base=None,
        )

        self.assertEqual(result["status"], "BOOTSTRAPPED")

    def test_bootstrap_rejects_marker_only_project_agent_spoof(self) -> None:
        source = self.make_repo("develop")
        worktree = self.managed_worktree(source)
        agent = source / ".claude" / "agents" / "vsdd-status-worker.md"
        agent.parent.mkdir(parents=True)
        agent.write_text(
            "---\nname: vsdd-status-worker\n---\n"
            f"{runtime.PROJECT_AGENT_MARKER}\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "clean source checkout"):
            runtime.bootstrap_run(
                source,
                "sample",
                worktree,
                request="Feature",
                until="review",
                mode="auto",
                explicit_base=None,
            )

    def test_review_attempt_must_be_begun_and_increase_monotonically(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)
        self.write_review(spec, "requirement-review.md", "requirements", "N/A")

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "begin-attempt"):
            runtime.snapshot_phase(root, "sample", "requirements-review")

        first = runtime.begin_attempt(root, "sample", "requirements-review")
        self.assertEqual(first["attempt"], 1)
        runtime.snapshot_phase(root, "sample", "requirements-review")
        report = spec / "review-results" / "requirement-review.md"
        report.write_text(
            report.read_text(encoding="utf-8") + "changed in same attempt\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(runtime.RuntimeBlocked, "already snapshotted"):
            runtime.snapshot_phase(root, "sample", "requirements-review")

        second = runtime.begin_attempt(root, "sample", "requirements-review")
        self.assertEqual(second["attempt"], 2)
        self.write_review(
            spec,
            "requirement-review.md",
            "requirements",
            "N/A",
            attempt=2,
        )
        runtime.snapshot_phase(root, "sample", "requirements-review")

    def test_review_and_task_attempts_block_after_three_starts(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)
        (spec / "tasks.md").write_text("### TASK-001 — One\n", encoding="utf-8")

        for expected in (1, 2, 3):
            result = runtime.begin_attempt(root, "sample", "plan-review")
            self.assertEqual(result["attempt"], expected)
            runtime.finish_attempt(
                root,
                "sample",
                "plan-review",
                attempt=expected,
                outcome="FAIL",
            )
        self.assertEqual(runtime.read_state(root, "sample")["status"], "BLOCKED")
        with self.assertRaisesRegex(runtime.RuntimeBlocked, "exhausted"):
            runtime.begin_attempt(root, "sample", "plan-review")

        runtime.invalidate_state(root, "sample", "tasks", "approved tasks changed")
        for expected in (1, 2, 3):
            result = runtime.begin_attempt(
                root, "sample", "implementation-task", task_id="TASK-001"
            )
            self.assertEqual(result["attempt"], expected)
            runtime.finish_attempt(
                root,
                "sample",
                "implementation-task",
                task_id="TASK-001",
                attempt=expected,
                outcome="FAIL",
            )
        self.assertEqual(runtime.read_state(root, "sample")["status"], "BLOCKED")
        with self.assertRaisesRegex(runtime.RuntimeBlocked, "exhausted"):
            runtime.begin_attempt(
                root, "sample", "implementation-task", task_id="TASK-001"
            )

    def test_completed_tasks_require_mechanical_attempt_records(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)
        (spec / "tasks.md").write_text("### TASK-001 — One\n", encoding="utf-8")
        state = runtime.read_state(root, "sample")

        self.assertEqual(
            runtime.task_attempt_issues(state, {"TASK-001"}),
            ["TASK attempt was never begun: TASK-001"],
        )

        runtime.begin_attempt(root, "sample", "implementation-task", task_id="TASK-001")
        state = runtime.read_state(root, "sample")
        self.assertEqual(
            runtime.task_attempt_issues(state, {"TASK-001"}),
            ["TASK attempt has no successful finish: TASK-001"],
        )
        runtime.finish_attempt(
            root,
            "sample",
            "implementation-task",
            task_id="TASK-001",
            attempt=1,
            outcome="PASS",
        )
        state = runtime.read_state(root, "sample")
        self.assertEqual(runtime.task_attempt_issues(state, {"TASK-001"}), [])

    def test_attempt_requires_finish_and_rejects_conflicting_outcome(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)
        (spec / "tasks.md").write_text("### TASK-001 — One\n", encoding="utf-8")
        runtime.begin_attempt(
            root, "sample", "implementation-task", task_id="TASK-001"
        )

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "has not been finished"):
            runtime.begin_attempt(
                root, "sample", "implementation-task", task_id="TASK-001"
            )

        finished = runtime.finish_attempt(
            root,
            "sample",
            "implementation-task",
            task_id="TASK-001",
            attempt=1,
            outcome="PASS",
        )
        self.assertEqual(finished["outcome"], "PASS")
        self.assertEqual(
            runtime.finish_attempt(
                root,
                "sample",
                "implementation-task",
                task_id="TASK-001",
                attempt=1,
                outcome="PASS",
            )["status"],
            "ATTEMPT_FINISHED",
        )
        with self.assertRaisesRegex(runtime.RuntimeBlocked, "another outcome"):
            runtime.finish_attempt(
                root,
                "sample",
                "implementation-task",
                task_id="TASK-001",
                attempt=1,
                outcome="FAIL",
            )

    def test_third_revise_review_snapshot_blocks_the_run(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)
        for attempt in (1, 2):
            runtime.begin_attempt(root, "sample", "requirements-review")
            self.write_review(
                spec,
                "requirement-review.md",
                "requirements",
                "N/A",
                verdict="REVISE",
                attempt=attempt,
            )
            runtime.snapshot_phase(
                root,
                "sample",
                "requirements-review",
                phase_status="REVISE",
            )
        runtime.begin_attempt(root, "sample", "requirements-review")
        self.write_review(
            spec,
            "requirement-review.md",
            "requirements",
            "N/A",
            verdict="REVISE",
            attempt=3,
        )

        runtime.snapshot_phase(
            root,
            "sample",
            "requirements-review",
            phase_status="REVISE",
        )
        state = runtime.read_state(root, "sample")

        self.assertEqual(state["status"], "BLOCKED")
        self.assertIn("requirements-review", state["blocker"])
        with self.assertRaisesRegex(runtime.RuntimeBlocked, "run-state status"):
            runtime.preflight(root, "sample", "requirements-review")

    def test_pr_preflight_requires_all_review_gates(self) -> None:
        root, spec = self.make_spec()
        git(root, "branch", "-m", "vsdd/sample")
        self.write_run_state(root, spec)
        self.write_complete_steering(root)
        self.write_completed_implementation(root, spec)
        state = runtime.read_state(root, "sample")
        state["phases"] = {"implementation": {"status": "COMPLETE"}}
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "requirements-review"):
            runtime.preflight(root, "sample", "pr")

    def test_pr_preflight_rejects_reviews_for_an_old_commit(self) -> None:
        root, spec = self.make_spec()
        git(root, "branch", "-m", "vsdd/sample")
        self.write_run_state(root, spec)
        self.write_complete_steering(root)
        reviewed_head = self.write_completed_implementation(root, spec)
        state = runtime.read_state(root, "sample")
        state["phases"] = {
            "requirements-review": {"status": "COMPLETE"},
            "plan-review": {"status": "COMPLETE"},
            "implementation-plan-review": {"status": "COMPLETE"},
            "implementation": {"status": "COMPLETE"},
        }
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        review_specs = (
            ("requirements-review", "requirement-review.md", "requirements", "N/A"),
            ("plan-review", "plan-review.md", "plan", "N/A"),
            (
                "implementation-plan-review",
                "implementation-workflow-review.md",
                "implementation-workflow",
                "N/A",
            ),
            ("code-review", "code-review.md", "code", reviewed_head),
            ("security-review", "security-review.md", "security", reviewed_head),
        )
        for phase, filename, review_type, target in review_specs:
            self.write_review(spec, filename, review_type, target)
            self.begin_review_attempt(root, phase)
            runtime.snapshot_phase(root, "sample", phase)

        (root / "after-review.txt").write_text("new head\n", encoding="utf-8")
        git(root, "add", "after-review.txt")
        git(
            root,
            "-c",
            "user.name=VSDD Test",
            "-c",
            "user.email=vsdd@example.invalid",
            "commit",
            "-m",
            "change after review",
        )

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "target_commit"):
            runtime.preflight(root, "sample", "pr")

    def test_pr_preflight_accepts_current_snapshotted_pass_reviews(self) -> None:
        root, spec = self.make_spec()
        git(root, "branch", "-m", "vsdd/sample")
        self.write_run_state(root, spec)
        self.write_complete_steering(root)
        head = self.write_completed_implementation(root, spec)
        state = runtime.read_state(root, "sample")
        state["until"] = "pr"
        state["phases"] = {"implementation": {"status": "COMPLETE"}}
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        review_specs = (
            ("requirements-review", "requirement-review.md", "requirements", "N/A"),
            ("plan-review", "plan-review.md", "plan", "N/A"),
            (
                "implementation-plan-review",
                "implementation-workflow-review.md",
                "implementation-workflow",
                "N/A",
            ),
            ("code-review", "code-review.md", "code", head),
            ("security-review", "security-review.md", "security", head),
        )
        for phase, filename, review_type, target in review_specs:
            self.write_review(spec, filename, review_type, target)
            self.begin_review_attempt(root, phase)
            runtime.snapshot_phase(root, "sample", phase)

        self.assertEqual(
            runtime.preflight(root, "sample", "pr"),
            {"status": "READY", "phase": "pr"},
        )

        with self.assertRaisesRegex(
            runtime.RuntimeBlocked, "remediation requires at least one REVISE"
        ):
            runtime.preflight(root, "sample", "remediation")

    def test_review_completion_is_persisted_and_idempotent(self) -> None:
        root, _, _ = self.prepare_review_complete_run()

        completed = runtime.complete_run(root, "sample", "review")
        repeated = runtime.complete_run(root, "sample", "review")
        state = runtime.read_state(root, "sample")

        self.assertEqual(completed["status"], "COMPLETE")
        self.assertFalse(completed["idempotent"])
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(state["status"], "COMPLETE")
        self.assertEqual(state["reached"], "review")
        self.assertEqual(state["current_phase"], "security-review")
        self.assertIn("completed_at", state)

    def test_pr_preflight_requires_an_explicit_pr_boundary(self) -> None:
        root, _, _ = self.prepare_review_complete_run()

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "explicit until 'pr'"):
            runtime.preflight(root, "sample", "pr")

    def test_review_completion_rejects_drift_detected_by_preflight(self) -> None:
        root, spec, _ = self.prepare_review_complete_run()
        report = spec / "review-results" / "security-review.md"
        report.write_text(
            report.read_text(encoding="utf-8") + "\npost-snapshot drift\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            runtime.RuntimeBlocked, "completion preflight invalidated security-review"
        ):
            runtime.complete_run(root, "sample", "review")

        state = runtime.read_state(root, "sample")
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["current_phase"], "security-review")
        self.assertEqual(state["phases"]["security-review"]["status"], "PENDING")
        self.assertNotIn("reached", state)
        self.assertNotIn("completed_at", state)

    def test_idempotent_completion_reaudits_terminal_artifacts(self) -> None:
        root, spec, _ = self.prepare_review_complete_run()
        runtime.complete_run(root, "sample", "review")
        report = spec / "review-results" / "security-review.md"
        report.write_text(
            report.read_text(encoding="utf-8") + "\npost-completion drift\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            runtime.RuntimeBlocked, "run artifacts changed"
        ):
            runtime.complete_run(root, "sample", "review")

        state = runtime.read_state(root, "sample")
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["current_phase"], "security-review")
        self.assertNotIn("reached", state)
        self.assertNotIn("completed_at", state)

    def test_idempotent_completion_invalidates_reviews_for_a_new_head(self) -> None:
        root, _, _ = self.prepare_review_complete_run()
        runtime.complete_run(root, "sample", "review")
        (root / "after-review.txt").write_text("new head\n", encoding="utf-8")
        git(root, "add", "after-review.txt")
        git(
            root,
            "-c",
            "user.name=VSDD Test",
            "-c",
            "user.email=vsdd@example.invalid",
            "commit",
            "-m",
            "change after review",
        )

        with self.assertRaisesRegex(
            runtime.RuntimeBlocked, "terminal completion evidence invalidated code-review"
        ):
            runtime.complete_run(root, "sample", "review")

        state = runtime.read_state(root, "sample")
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["current_phase"], "code-review")
        self.assertEqual(state["phases"]["code-review"]["status"], "PENDING")
        self.assertEqual(state["phases"]["security-review"]["status"], "PENDING")
        self.assertNotIn("reached", state)
        self.assertNotIn("completed_at", state)

    def test_explicit_pr_extension_reopens_a_review_complete_run(self) -> None:
        root, _, _ = self.prepare_review_complete_run()
        runtime.complete_run(root, "sample", "review")

        extended = runtime.extend_run(root, "sample", "pr")
        state = runtime.read_state(root, "sample")

        self.assertEqual(extended["status"], "RUNNING")
        self.assertEqual(state["until"], "pr")
        self.assertEqual(state["current_phase"], "pr")
        self.assertNotIn("reached", state)
        self.assertIn("review_completed_at", state)
        self.assertEqual(
            runtime.preflight(root, "sample", "pr"),
            {"status": "READY", "phase": "pr"},
        )

    def test_pr_extension_invalidates_reviews_for_a_new_head(self) -> None:
        root, _, _ = self.prepare_review_complete_run()
        runtime.complete_run(root, "sample", "review")
        (root / "after-review.txt").write_text("new head\n", encoding="utf-8")
        git(root, "add", "after-review.txt")
        git(
            root,
            "-c",
            "user.name=VSDD Test",
            "-c",
            "user.email=vsdd@example.invalid",
            "commit",
            "-m",
            "change before extension",
        )

        with self.assertRaisesRegex(
            runtime.RuntimeBlocked, "review extension evidence invalidated code-review"
        ):
            runtime.extend_run(root, "sample", "pr")

        state = runtime.read_state(root, "sample")
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["until"], "review")
        self.assertEqual(state["current_phase"], "code-review")
        self.assertEqual(state["phases"]["code-review"]["status"], "PENDING")
        self.assertEqual(state["phases"]["security-review"]["status"], "PENDING")
        self.assertNotIn("reached", state)
        self.assertNotIn("completed_at", state)

    def test_pr_completion_requires_and_accepts_snapshotted_pr_evidence(self) -> None:
        root, spec, head = self.prepare_review_complete_run()
        runtime.complete_run(root, "sample", "review")
        runtime.extend_run(root, "sample", "pr")

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "pr-result.json"):
            runtime.complete_run(root, "sample", "pr")

        state = runtime.read_state(root, "sample")
        evidence = {
            "url": "https://github.com/sc30gsw/example/pull/42",
            "number": 42,
            "base_branch": state["base_branch"],
            "base_sha": state["base_sha"],
            "head_branch": "vsdd/sample",
            "head_sha": head,
            "target_commit": head,
        }
        (spec / "pr-result.json").write_text(json.dumps(evidence), encoding="utf-8")
        runtime.snapshot_phase(root, "sample", "pr")

        completed = runtime.complete_run(root, "sample", "pr")
        state = runtime.read_state(root, "sample")

        self.assertEqual(completed["status"], "COMPLETE")
        self.assertEqual(state["reached"], "pr")
        self.assertEqual(state["current_phase"], "pr")

    def test_pr_preflight_rejects_mixed_post_review_attempts(self) -> None:
        root, spec = self.make_spec()
        git(root, "branch", "-m", "vsdd/sample")
        self.write_run_state(root, spec)
        self.write_complete_steering(root)
        head = self.write_completed_implementation(root, spec)
        state = runtime.read_state(root, "sample")
        state["phases"] = {"implementation": {"status": "COMPLETE"}}
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        review_specs = (
            ("requirements-review", "requirement-review.md", "requirements", "N/A"),
            ("plan-review", "plan-review.md", "plan", "N/A"),
            (
                "implementation-plan-review",
                "implementation-workflow-review.md",
                "implementation-workflow",
                "N/A",
            ),
            ("code-review", "code-review.md", "code", head),
            ("security-review", "security-review.md", "security", head),
        )
        for phase, filename, review_type, target in review_specs:
            self.write_review(spec, filename, review_type, target)
            self.begin_review_attempt(root, phase)
            runtime.snapshot_phase(root, "sample", phase)

        runtime.begin_attempt(root, "sample", "post-implementation-review")
        self.write_review(spec, "code-review.md", "code", head, attempt=2)
        runtime.snapshot_phase(root, "sample", "code-review")

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "same review_attempt"):
            runtime.preflight(root, "sample", "pr")

    def test_review_snapshot_enforces_opus_and_verdict_status(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)
        self.write_review(
            spec,
            "requirement-review.md",
            "requirements",
            "N/A",
        )
        report = spec / "review-results" / "requirement-review.md"
        report.write_text(
            report.read_text(encoding="utf-8").replace(
                "reviewer_model: opus", "reviewer_model: sonnet"
            ),
            encoding="utf-8",
        )
        self.begin_review_attempt(root, "requirements-review")

        with self.assertRaisesRegex(runtime.RuntimeBlocked, "reviewer_model"):
            runtime.snapshot_phase(root, "sample", "requirements-review")

        self.write_review(
            spec,
            "requirement-review.md",
            "requirements",
            "N/A",
            verdict="REVISE",
        )
        with self.assertRaisesRegex(runtime.RuntimeBlocked, "phase status"):
            runtime.snapshot_phase(root, "sample", "requirements-review")

    def test_state_lock_serializes_concurrent_holders(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)
        original_timeout = runtime.LOCK_TIMEOUT_SECONDS
        runtime.LOCK_TIMEOUT_SECONDS = 0.2
        self.addCleanup(setattr, runtime, "LOCK_TIMEOUT_SECONDS", original_timeout)
        with runtime.state_lock(root, "sample"):
            with self.assertRaisesRegex(runtime.RuntimeBlocked, "timed out waiting"):
                with runtime.state_lock(root, "sample"):
                    pass
        # Released: a fresh acquisition now succeeds immediately.
        with runtime.state_lock(root, "sample"):
            pass

    def test_bootstrap_lock_serializes_same_slug(self) -> None:
        runtime.MANAGED_WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
        lock_path = runtime.MANAGED_WORKTREE_ROOT / ".lock-test-slug.bootstrap.lock"
        self.addCleanup(lock_path.unlink, missing_ok=True)
        original_timeout = runtime.LOCK_TIMEOUT_SECONDS
        runtime.LOCK_TIMEOUT_SECONDS = 0.2
        self.addCleanup(setattr, runtime, "LOCK_TIMEOUT_SECONDS", original_timeout)
        with runtime.bootstrap_lock("lock-test-slug"):
            with self.assertRaisesRegex(runtime.RuntimeBlocked, "timed out waiting"):
                with runtime.bootstrap_lock("lock-test-slug"):
                    pass

    def test_cli_dispatch_holds_state_lock_for_the_whole_subcommand(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)
        original_argv = sys.argv
        original_timeout = runtime.LOCK_TIMEOUT_SECONDS
        runtime.LOCK_TIMEOUT_SECONDS = 0.2
        self.addCleanup(setattr, sys, "argv", original_argv)
        self.addCleanup(setattr, runtime, "LOCK_TIMEOUT_SECONDS", original_timeout)
        sys.argv = [
            "vsdd-runtime-state.py",
            "begin-attempt",
            "--worktree",
            str(root),
            "--slug",
            "sample",
            "--scope",
            "requirements-review",
        ]
        with runtime.state_lock(root, "sample"):
            with self.assertRaises(SystemExit):
                runtime.main()
        # The CLI releases its lock once it exits; a direct call now succeeds,
        # proving the earlier failure came from lock contention, not a bug.
        runtime.begin_attempt(root, "sample", "requirements-review")

    def test_validate_worktree_root_tightens_permissions_and_rejects_symlink(
        self,
    ) -> None:
        directory = Path(tempfile.mkdtemp(prefix="ecc-vsdd-worktree-root-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        directory.chmod(0o777)
        runtime.validate_worktree_root(directory)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)

        parent = Path(tempfile.mkdtemp(prefix="ecc-vsdd-worktree-root-parent-"))
        self.addCleanup(shutil.rmtree, parent, ignore_errors=True)
        link = parent / "link"
        link.symlink_to(directory)
        with self.assertRaisesRegex(runtime.RuntimeBlocked, "not a private directory"):
            runtime.validate_worktree_root(link)

    def test_concurrent_cli_processes_do_not_lose_ledger_updates(self) -> None:
        root, spec = self.make_spec()
        self.write_run_state(root, spec)
        scopes = ("requirements-review", "plan-review")
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPT),
                    "begin-attempt",
                    "--worktree",
                    str(root),
                    "--slug",
                    "sample",
                    "--scope",
                    scope,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for scope in scopes
        ]
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, stdout + stderr)
        state = runtime.read_state(root, "sample")
        for scope in scopes:
            self.assertEqual(
                state["attempt_ledger"][scope]["attempts_started"],
                1,
                f"lost update for {scope}: {state['attempt_ledger']}",
            )

    def test_bootstrap_lock_creates_root_private_before_lock_file(self) -> None:
        original_root = runtime.MANAGED_WORKTREE_ROOT
        scratch = Path(tempfile.mkdtemp(prefix="ecc-vsdd-bootstrap-lock-root-"))
        runtime.MANAGED_WORKTREE_ROOT = scratch / "worktrees"
        self.addCleanup(setattr, runtime, "MANAGED_WORKTREE_ROOT", original_root)
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        with runtime.bootstrap_lock("sample"):
            pass
        self.assertEqual(
            stat.S_IMODE(runtime.MANAGED_WORKTREE_ROOT.stat().st_mode), 0o700
        )

    def test_bootstrap_validates_worktree_root_permissions(self) -> None:
        source = self.make_repo()
        worktree = self.managed_worktree(source)
        runtime.MANAGED_WORKTREE_ROOT.chmod(0o777)
        try:
            runtime.bootstrap_run(
                source, "sample", worktree, "fixture request", "review", "auto", None
            )
        finally:
            pass
        self.assertEqual(
            stat.S_IMODE(runtime.MANAGED_WORKTREE_ROOT.stat().st_mode), 0o700
        )


if __name__ == "__main__":
    unittest.main()
