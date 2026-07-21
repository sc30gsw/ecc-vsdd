from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "vsdd-pr-action.py"
BROKER_SPEC = importlib.util.spec_from_file_location("vsdd_pr_action", SCRIPT)
assert BROKER_SPEC and BROKER_SPEC.loader
broker = importlib.util.module_from_spec(BROKER_SPEC)
BROKER_SPEC.loader.exec_module(broker)


def run(*argv: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def git(repo: Path, *args: str) -> str:
    result = run("git", "-C", str(repo), *args)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


class PrActionTest(unittest.TestCase):
    def make_fixture(self) -> dict[str, object]:
        self.assertTrue(SCRIPT.is_file(), "PR action broker is not implemented")
        root = Path(tempfile.mkdtemp(prefix="ecc-vsdd-pr-action-"))
        plugin = root / "plugin"
        scripts = plugin / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(SCRIPT, scripts / SCRIPT.name)
        shutil.copy2(
            ROOT / "scripts" / "vsdd-model-guard.py",
            scripts / "vsdd-model-guard.py",
        )
        runtime_counter = root / "runtime-count.txt"
        (scripts / "vsdd-runtime-state.py").write_text(
            """#!/usr/bin/env python3
import json, os, pathlib, sys
path = pathlib.Path(os.environ['FAKE_RUNTIME_COUNTER'])
count = int(path.read_text() or '0') if path.exists() else 0
count += 1
path.write_text(str(count))
if count == int(os.environ.get('FAKE_RUNTIME_FAIL_ON', '0')):
    print('simulated stale evidence', file=sys.stderr)
    raise SystemExit(1)
print(json.dumps({'status': 'READY', 'phase': 'pr'}))
""",
            encoding="utf-8",
        )

        remote = root / "remote.git"
        source = root / "source"
        self.assertEqual(run("git", "init", "--bare", str(remote)).returncode, 0)
        self.assertEqual(run("git", "init", "-b", "main", str(source)).returncode, 0)
        (source / "README.md").write_text("base\n", encoding="utf-8")
        git(source, "add", "README.md")
        git(
            source,
            "-c",
            "user.name=VSDD Test",
            "-c",
            "user.email=vsdd@example.invalid",
            "commit",
            "-m",
            "base",
        )
        base_sha = git(source, "rev-parse", "HEAD")
        git(source, "remote", "add", "origin", str(remote))
        git(source, "push", "-u", "origin", "main")
        git(source, "switch", "-c", "vsdd/sample")
        (source / "feature.txt").write_text("feature\n", encoding="utf-8")
        git(source, "add", "feature.txt")
        git(
            source,
            "-c",
            "user.name=VSDD Test",
            "-c",
            "user.email=vsdd@example.invalid",
            "commit",
            "-m",
            "feature",
        )
        head_sha = git(source, "rev-parse", "HEAD")
        spec = source / ".vsdd" / "specs" / "sample"
        spec.mkdir(parents=True)
        state = {
            "schema_version": 4,
            "slug": "sample",
            "status": "RUNNING",
            "until": "pr",
            "base_branch": "main",
            "base_sha": base_sha,
            "integration_branch": "vsdd/sample",
            "integration_worktree": str(source.resolve()),
        }
        (spec / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
        body = spec / "pr-body.md"
        body.write_text("# Test PR\n", encoding="utf-8")

        bin_dir = root / "bin"
        bin_dir.mkdir()
        gh_state = root / "gh-pr-created"
        gh_log = root / "gh.log"
        (bin_dir / "gh").write_text(
            """#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
log = pathlib.Path(os.environ['FAKE_GH_LOG'])
with log.open('a') as stream:
    stream.write(json.dumps(args) + '\\n')
state = pathlib.Path(os.environ['FAKE_GH_STATE'])
if args[:2] == ['pr', 'view']:
    if not state.exists():
        raise SystemExit(1)
    print(json.dumps({
        'number': 42,
        'url': 'https://github.com/sc30gsw/example/pull/42',
        'baseRefName': 'main',
        'baseRefOid': os.environ['FAKE_BASE_SHA'],
        'headRefName': 'vsdd/sample',
        'headRefOid': os.environ['FAKE_HEAD_SHA'],
        'isDraft': os.environ.get('FAKE_DRAFT') == '1',
    }))
elif args[:2] == ['pr', 'create']:
    state.write_text('created')
    print('https://github.com/sc30gsw/example/pull/42')
else:
    print('unexpected gh invocation', file=sys.stderr)
    raise SystemExit(2)
""",
            encoding="utf-8",
        )
        (bin_dir / "gh").chmod(0o755)

        session_id = "broker-session"
        agent_id = "pr-worker-42"
        capability = "A" * 43
        data_root = root / "tmp"
        guard_root = data_root / f"ecc-vsdd-guard-{os.getuid()}"
        auth_dir = guard_root / "pr-authorized-sessions"
        auth_dir.mkdir(parents=True, mode=0o700)
        guard_root.chmod(0o700)
        auth_dir.chmod(0o700)
        auth = {
            "schema_version": 2,
            "authorization": "vsdd-pr",
            "session_id": session_id,
            "cwd": str(source.resolve()),
            "prompt_id": "prompt-broker-1",
            "launch_tool_use_id": "tool-launch-broker",
            "slug": "sample",
            "integration_worktree": str(source.resolve()),
            "capability": capability,
            "agent_id": agent_id,
            "created_at": int(time.time()),
        }
        auth_path = auth_dir / f"{session_id}.json"
        auth_path.write_text(json.dumps(auth), encoding="utf-8")
        auth_path.chmod(0o600)

        env = os.environ.copy()
        env.update(
            {
                "CLAUDE_PLUGIN_ROOT": str(plugin),
                "TMPDIR": str(data_root),
                "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
                "FAKE_RUNTIME_COUNTER": str(runtime_counter),
                "FAKE_GH_STATE": str(gh_state),
                "FAKE_GH_LOG": str(gh_log),
                "FAKE_BASE_SHA": base_sha,
                "FAKE_HEAD_SHA": head_sha,
                "FAKE_DRAFT": "0",
            }
        )
        command = [
            sys.executable,
            str(scripts / SCRIPT.name),
            "publish",
            "--worktree",
            str(source),
            "--slug",
            "sample",
            "--session-id",
            session_id,
            "--agent-id",
            agent_id,
            "--capability",
            capability,
            "--title",
            "Test PR",
            "--body-file",
            str(body),
        ]
        return {
            "root": root,
            "plugin": plugin,
            "source": source,
            "remote": remote,
            "spec": spec,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "runtime_counter": runtime_counter,
            "gh_state": gh_state,
            "gh_log": gh_log,
            "auth_path": auth_path,
            "env": env,
            "command": command,
        }

    def publish(self, fixture: dict[str, object], *extra: str) -> subprocess.CompletedProcess[str]:
        return run(
            *fixture["command"],
            *extra,
            cwd=fixture["source"],
            env=fixture["env"],
        )

    def publish_direct(self, fixture: dict[str, object]) -> dict:
        scripts = fixture["plugin"] / "scripts"
        old_cwd = Path.cwd()
        try:
            os.chdir(fixture["source"])
            with mock.patch.dict(os.environ, fixture["env"], clear=True):
                with mock.patch.object(
                    tempfile, "tempdir", str(fixture["root"] / "tmp")
                ):
                    with mock.patch.object(
                        broker, "RUNTIME", scripts / "vsdd-runtime-state.py"
                    ), mock.patch.object(
                        broker, "GUARD", scripts / "vsdd-model-guard.py"
                    ), mock.patch.object(
                        sys, "argv", list(fixture["command"])[1:]
                    ):
                        return broker.publish(broker.parse_args())
        finally:
            os.chdir(old_cwd)

    def test_publish_rejects_wrong_capability(self) -> None:
        fixture = self.make_fixture()
        command = list(fixture["command"])
        capability_index = command.index("--capability") + 1
        command[capability_index] = "wrong-capability"

        result = run(
            *command,
            cwd=fixture["source"],
            env=fixture["env"],
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("capability", result.stderr)
        self.assertFalse(fixture["gh_state"].exists())

    def test_publish_blocks_changed_remote_base(self) -> None:
        fixture = self.make_fixture()
        state_path = fixture["spec"] / "run-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["base_sha"] = "0" * 40
        state_path.write_text(json.dumps(state), encoding="utf-8")

        with self.assertRaises(broker.ActionBlocked) as caught:
            self.publish_direct(fixture)

        self.assertIn("remote base", str(caught.exception))
        self.assertFalse(fixture["gh_state"].exists())

    def test_publish_rechecks_runtime_between_push_and_pr_creation(self) -> None:
        fixture = self.make_fixture()
        fixture["env"]["FAKE_RUNTIME_FAIL_ON"] = "2"

        with self.assertRaises(broker.ActionBlocked) as caught:
            self.publish_direct(fixture)

        self.assertIn("preflight", str(caught.exception))
        self.assertEqual(fixture["runtime_counter"].read_text(), "2")
        self.assertEqual(
            git(fixture["remote"], "rev-parse", "refs/heads/vsdd/sample"),
            fixture["head_sha"],
        )
        self.assertFalse(fixture["gh_state"].exists())

    def test_publish_pushes_creates_pr_and_writes_exact_evidence(self) -> None:
        fixture = self.make_fixture()

        output = self.publish_direct(fixture)

        self.assertEqual(output["status"], "CREATED")
        self.assertEqual(output["url"], "https://github.com/sc30gsw/example/pull/42")
        self.assertEqual(fixture["runtime_counter"].read_text(), "2")
        self.assertEqual(
            git(fixture["remote"], "rev-parse", "refs/heads/vsdd/sample"),
            fixture["head_sha"],
        )
        evidence = json.loads(
            (fixture["spec"] / "pr-result.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            evidence,
            {
                "url": "https://github.com/sc30gsw/example/pull/42",
                "number": 42,
                "draft": False,
                "base_branch": "main",
                "base_sha": fixture["base_sha"],
                "head_branch": "vsdd/sample",
                "head_sha": fixture["head_sha"],
                "target_commit": fixture["head_sha"],
                "created_at": evidence["created_at"],
            },
        )

    def test_publish_reuses_existing_pr_without_duplicate_creation(self) -> None:
        fixture = self.make_fixture()
        fixture["gh_state"].write_text("already-created", encoding="utf-8")

        result = self.publish_direct(fixture)

        self.assertEqual(result["status"], "EXISTING")
        calls = [json.loads(line) for line in fixture["gh_log"].read_text().splitlines()]
        self.assertFalse(any(call[:2] == ["pr", "create"] for call in calls))
        self.assertTrue((fixture["spec"] / "pr-result.json").is_file())


if __name__ == "__main__":
    unittest.main()
