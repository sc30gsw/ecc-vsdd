#!/usr/bin/env python3
"""Launch the independent Sonnet ultracode implementation session safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


MIN_CLAUDE_VERSION = (2, 1, 203)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STAGES = ("plan", "revise-plan", "implement", "remediate")
UNATTENDED_ALLOWED_TOOLS = (
    "Read",
    "Glob",
    "Grep",
    "Write",
    "Edit",
    "Workflow",
    "Bash(cat *)",
)
STAGE_PHASE = {
    "plan": "implementation-plan",
    "revise-plan": "implementation-plan",
    "implement": "implementation",
    "remediate": "remediation",
}


def fail(message: str) -> None:
    print(json.dumps({"status": "BLOCKED", "error": message}, ensure_ascii=False))
    raise SystemExit(1)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as error:
        fail(f"cannot read {path}: {error}")
    return value if isinstance(value, dict) else {}


def write_json_atomic(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    except OSError as error:
        fail(f"cannot persist {path}: {error}")


def process_alive(pid: object) -> bool:
    try:
        numeric_pid = int(pid)
        if numeric_pid <= 0:
            return False
        os.kill(numeric_pid, 0)
    except (TypeError, ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True
    return True


def running_supervisor(supervisors_dir: Path, stage: str) -> tuple[Path, dict] | None:
    """Return the one live supervisor for a stage, rejecting ambiguous state."""
    running: list[tuple[Path, dict]] = []
    for path in sorted(supervisors_dir.glob(f"{stage}-*.json")):
        record = read_json(path)
        if record.get("status") != "RUNNING":
            continue
        if process_alive(record.get("pid")):
            running.append((path, record))
            continue
        record.update(
            {
                "status": "BLOCKED",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "result": {
                    "status": "BLOCKED",
                    "error": "detached launcher supervisor exited without a result",
                },
            }
        )
        write_json_atomic(path, record)
    if len(running) > 1:
        fail(
            f"multiple live detached supervisors exist for {stage}: "
            f"{[str(path) for path, _ in running]}"
        )
    return running[0] if running else None


def parse_terminal_json(stdout: str, stderr: str) -> dict:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("status") in {"COMPLETE", "BLOCKED"}:
            return value
    return {
        "status": "BLOCKED",
        "error": "detached launcher returned no terminal structured result",
        "raw_stdout": stdout,
        "raw_stderr": stderr,
    }


def supervise_detached_launcher(evidence: Path) -> None:
    for _ in range(500):
        record = read_json(evidence)
        if record.get("status") == "RUNNING":
            break
        time.sleep(0.01)
    else:
        return

    command = record.get("command")
    worktree = record.get("worktree")
    if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
        result = {"status": "BLOCKED", "error": "invalid detached command record"}
        returncode = 1
        stdout = ""
        stderr = ""
    else:
        try:
            completed = subprocess.run(
                command,
                cwd=worktree,
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                check=False,
            )
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            result = parse_terminal_json(stdout, stderr)
        except OSError as error:
            returncode = 1
            stdout = ""
            stderr = str(error)
            result = {"status": "BLOCKED", "error": f"detached launcher failed: {error}"}

    current = read_json(evidence)
    current.update(
        {
            "status": (
                "COMPLETE"
                if returncode == 0 and result.get("status") == "COMPLETE"
                else "BLOCKED"
            ),
            "returncode": returncode,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "stdout": stdout,
            "stderr": stderr,
            "result": result,
        }
    )
    write_json_atomic(evidence, current)


def wait_for_detached_launcher(
    evidence: Path, worktree: Path, slug: str, wait_seconds: int
) -> None:
    supervisors = (
        worktree / ".claude" / "specs" / slug / "worker-supervisors"
    ).resolve()
    evidence = evidence.expanduser().resolve()
    try:
        evidence.relative_to(supervisors)
    except ValueError:
        fail(f"detached launcher evidence must be under {supervisors}")

    if not 0 <= wait_seconds <= 55:
        fail("--wait-seconds must be between 0 and 55")
    deadline = time.monotonic() + wait_seconds
    while True:
        record = read_json(evidence)
        if not record:
            fail(f"detached launcher evidence not found: {evidence}")
        if record.get("slug") != slug or Path(str(record.get("worktree"))).resolve() != worktree:
            fail("detached launcher evidence does not match slug/worktree")
        status = record.get("status")
        if status in {"COMPLETE", "BLOCKED"}:
            result = record.get("result")
            if not isinstance(result, dict):
                fail(f"detached launcher has no terminal result: {evidence}")
            output = dict(result)
            output["supervisor_evidence"] = str(evidence)
            print(json.dumps(output, ensure_ascii=False))
            if status == "BLOCKED":
                raise SystemExit(1)
            return
        if status != "RUNNING":
            fail(f"invalid detached launcher status {status!r}: {evidence}")
        if not process_alive(record.get("pid")):
            record.update(
                {
                    "status": "BLOCKED",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "result": {
                        "status": "BLOCKED",
                        "error": "detached launcher supervisor exited without a result",
                    },
                }
            )
            write_json_atomic(evidence, record)
            continue
        if time.monotonic() >= deadline:
            print(
                json.dumps(
                    {
                        "status": "RUNNING",
                        "stage": record.get("stage"),
                        "evidence": str(evidence),
                    },
                    ensure_ascii=False,
                )
            )
            return
        time.sleep(0.25)


def plugin_version_key(version: object) -> tuple[tuple[int, ...], int, str]:
    value = str(version or "")
    core = value.split("-", 1)[0]
    numbers = tuple(int(part) for part in re.findall(r"\d+", core))
    return numbers, int("-" not in value), value


def plugin_dirs_for_child(
    plugin_root: Path, *, config_root: Path | None = None
) -> list[Path]:
    """Resolve manifest dependencies for an isolated --plugin-dir child."""
    plugin_root = plugin_root.resolve()
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    manifest = read_json(manifest_path)
    raw_dependencies = manifest.get("dependencies", [])
    if not isinstance(raw_dependencies, list) or not all(
        isinstance(value, str) and value.strip() for value in raw_dependencies
    ):
        fail(f"invalid plugin dependencies in {manifest_path}")

    if config_root is None:
        configured = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
        config_root = (
            Path(configured).expanduser() if configured else Path.home() / ".claude"
        )
    else:
        config_root = config_root.expanduser()
    registry_path = config_root / "plugins" / "installed_plugins.json"
    registry = read_json(registry_path)
    installed = registry.get("plugins", {})
    if not isinstance(installed, dict):
        installed = {}

    resolved: list[Path] = []
    for dependency in raw_dependencies:
        candidates: list[tuple[tuple[tuple[int, ...], int, str], Path]] = []
        for key, entries in installed.items():
            if str(key).split("@", 1)[0] != dependency or not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                install_path = entry.get("installPath")
                if not isinstance(install_path, str) or not install_path.strip():
                    continue
                candidate = Path(install_path).expanduser().resolve()
                candidate_manifest = read_json(
                    candidate / ".claude-plugin" / "plugin.json"
                )
                if candidate.is_dir() and candidate_manifest.get("name") == dependency:
                    candidates.append(
                        (plugin_version_key(entry.get("version")), candidate)
                    )
        if not candidates:
            fail(
                f"required plugin dependency {dependency!r} is not installed in "
                f"{registry_path}; install the ecc-vsdd plugin dependency before launch"
            )
        candidates.sort(key=lambda item: item[0], reverse=True)
        selected = candidates[0][1]
        if selected not in resolved:
            resolved.append(selected)

    return [*resolved, plugin_root]


def workflows_disabled(worktree: Path) -> str | None:
    if os.environ.get("CLAUDE_CODE_DISABLE_WORKFLOWS") == "1":
        return "CLAUDE_CODE_DISABLE_WORKFLOWS=1"

    candidates = [
        Path.home() / ".claude" / "settings.json",
        worktree / ".claude" / "settings.json",
        worktree / ".claude" / "settings.local.json",
    ]
    for path in candidates:
        settings = read_json(path)
        if settings.get("disableWorkflows") is True:
            return f"disableWorkflows=true in {path}"
    return None


def claude_version(claude: str) -> tuple[int, int, int]:
    result = subprocess.run(
        [claude, "--version"], capture_output=True, text=True, check=False
    )
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout + result.stderr)
    if result.returncode or not match:
        fail("cannot determine Claude Code version")
    return tuple(int(part) for part in match.groups())


def git_output(worktree: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        fail(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    # Porcelain status uses a meaningful leading space for worktree-only changes.
    # Remove line endings only so callers such as changed_paths() keep that prefix.
    return result.stdout.rstrip("\r\n")


def changed_paths(worktree: Path) -> set[str]:
    output = git_output(worktree, "status", "--porcelain=v1", "--untracked-files=all")
    paths: set[str] = set()
    for line in output.splitlines():
        if len(line) < 4:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.add(value.strip('"'))
    return paths


def planning_guard_fingerprint(worktree: Path, slug: str) -> str:
    """Hash every working-tree change except the plan and launcher evidence."""
    spec_prefix = f".claude/specs/{slug}/"
    allowed = {
        f"{spec_prefix}implementation-workflow.md",
    }
    allowed_prefixes = {
        f"{spec_prefix}worker-sessions/",
        f"{spec_prefix}worker-supervisors/",
    }
    digest = hashlib.sha256()

    diff = subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "diff",
            "--binary",
            "HEAD",
            "--",
            ".",
            f":(exclude){spec_prefix}implementation-workflow.md",
            f":(exclude){spec_prefix}worker-sessions/**",
        ],
        capture_output=True,
        check=False,
    )
    if diff.returncode:
        fail(f"cannot fingerprint planning guard: {diff.stderr.decode(errors='replace')}")
    digest.update(diff.stdout)

    untracked = subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        capture_output=True,
        check=False,
    )
    if untracked.returncode:
        fail(f"cannot list untracked files: {untracked.stderr.decode(errors='replace')}")
    for raw_path in sorted(path for path in untracked.stdout.split(b"\0") if path):
        relative = raw_path.decode("utf-8", errors="surrogateescape")
        if relative in allowed or any(relative.startswith(prefix) for prefix in allowed_prefixes):
            continue
        path = worktree / relative
        digest.update(raw_path)
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def artifact_marker(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        content = path.read_bytes()
        stat = path.stat()
    except OSError as error:
        fail(f"cannot fingerprint planning artifact {path}: {error}")
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "mtime_ns": stat.st_mtime_ns,
    }


def planning_artifact_issue(
    stage: str,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> str | None:
    if after is None or after.get("size") == 0:
        return "implementation-workflow.md was not persisted"
    if stage in {"plan", "revise-plan"} and before is not None:
        if before.get("sha256") == after.get("sha256"):
            return (
                "current Dynamic Workflow did not produce new "
                "implementation-workflow.md content"
            )
    return None


def workflow_evidence_issue(path: Path, workflow_run_id: str) -> str | None:
    try:
        content = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError) as error:
        return f"cannot verify workflow_run_id in planning artifact: {error}"
    if workflow_run_id not in content:
        return "implementation-workflow.md does not record current workflow_run_id"
    return None


def parse_frontmatter(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(f"cannot read {path}: {error}")
    if not lines or lines[0] != "---":
        return {}
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def require_pass(path: Path) -> None:
    frontmatter = parse_frontmatter(path)
    if frontmatter.get("verdict") != "PASS":
        fail(f"required PASS verdict missing from {path}")
    if frontmatter.get("reviewer_model") != "opus":
        fail(f"reviewer_model must be opus in {path}")
    if frontmatter.get("reviewer_effort") != "xhigh":
        fail(f"reviewer_effort must be xhigh in {path}")


def stage_state_issues(stage: str, state: dict, session_id: str | None) -> list[str]:
    issues: list[str] = []
    if state.get("status") != "RUNNING":
        issues.append(f"run-state status must be RUNNING; got {state.get('status')!r}")
    phases = state.get("phases", {})
    bound_session = state.get("implementation_session_id")
    if stage == "plan":
        if bound_session:
            issues.append("implementation session is already bound in run-state")
        if phases.get("implementation-plan", {}).get("status") != "PENDING":
            issues.append("implementation-plan phase must be PENDING")
    elif stage == "revise-plan":
        if not session_id or bound_session != session_id:
            issues.append("implementation session_id does not match run-state")
        if phases.get("implementation-plan", {}).get("status") != "COMPLETE":
            issues.append("implementation-plan must be COMPLETE before revision")
        review = phases.get("implementation-plan-review", {})
        if review.get("status") != "REVISE" or review.get("verdict") != "REVISE":
            issues.append("implementation-plan-review must be REVISE")
    elif stage == "implement":
        if not session_id or bound_session != session_id:
            issues.append("implementation session_id does not match run-state")
        review = phases.get("implementation-plan-review", {})
        if review.get("status") != "COMPLETE" or review.get("verdict") != "PASS":
            issues.append("implementation-plan-review must be a snapshotted PASS")
        if phases.get("implementation", {}).get("status") != "PENDING":
            issues.append("implementation phase must be PENDING")
    elif stage == "remediate":
        if phases.get("remediation", {}).get("status") != "PENDING":
            issues.append("remediation phase must be PENDING")
    return issues


def require_runtime_preflight(
    plugin_root: Path,
    worktree: Path,
    slug: str,
    stage: str,
    session_id: str | None,
) -> dict:
    runtime = plugin_root / "scripts" / "vsdd-runtime-state.py"
    result = subprocess.run(
        [
            sys.executable,
            str(runtime),
            "preflight",
            "--worktree",
            str(worktree),
            "--slug",
            slug,
            "--phase",
            STAGE_PHASE[stage],
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        outcome = json.loads(result.stdout)
    except json.JSONDecodeError:
        fail(
            "deterministic preflight returned invalid output: "
            f"{result.stdout or result.stderr}"
        )
    if result.returncode or outcome.get("status") != "READY":
        detail = outcome.get("error") or outcome.get("status") or result.stderr.strip()
        fail(f"deterministic preflight blocked {stage}: {detail}")
    state_path = worktree / ".claude" / "specs" / slug / "run-state.json"
    state = read_json(state_path)
    issues = stage_state_issues(stage, state, session_id)
    if issues:
        fail(f"deterministic preflight blocked {stage}: {'; '.join(issues)}")
    return state


def task_integrity_issue(
    plugin_root: Path, worktree: Path, slug: str
) -> str | None:
    runtime = plugin_root / "scripts" / "vsdd-runtime-state.py"
    result = subprocess.run(
        [
            sys.executable,
            str(runtime),
            "task-gate",
            "--worktree",
            str(worktree),
            "--slug",
            slug,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        outcome = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "task-integrity gate returned invalid output"
    if result.returncode or outcome.get("status") != "READY":
        detail = outcome.get("error") or outcome.get("status") or result.stderr.strip()
        return f"task-integrity gate blocked completion: {detail}"
    return None


def bind_implementation_session(state_path: Path, session_id: str) -> None:
    state = read_json(state_path)
    current = state.get("implementation_session_id")
    if current not in {None, session_id}:
        fail("cannot replace the implementation session bound in run-state")
    state["implementation_session_id"] = session_id
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = state_path.with_name(f".{state_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, state_path)
    except OSError as error:
        fail(f"cannot persist implementation session binding: {error}")


def build_prompt(stage: str, slug: str, plugin_root: Path, worktree: Path) -> str:
    spec = worktree / ".claude" / "specs" / slug
    contract = plugin_root / "skills" / "vsdd-run" / "references" / "implementation-contract.md"
    common = (
        f"Work only in the integration worktree {worktree}. Feature slug: {slug}. "
        f"Read and obey {contract}. Never change models; every workflow agent must be Sonnet. "
        "This is unattended execution: never ask for permission or user input. Read persisted "
        "artifacts with Read, Glob, or Grep rather than shell cat/sed/head/tail. Ensure every "
        "Dynamic Workflow agent receives the same rule. If Workflow launches in the background, "
        "remain in this session until its completion notification, inspect its terminal result, "
        "and verify the persisted artifacts before returning the final structured result. "
        "Return BLOCKED on unavailable Dynamic Workflows, missing evidence, or exhausted retries. "
        "Return the exact current Workflow run ID (the wf_... value returned by the Workflow tool) "
        "as workflow_run_id in the final structured result. "
        f"In the structured result, set stage exactly to {stage!r}."
    )
    prompts = {
        "plan": (
            "ultracode: Create and run a Dynamic Workflow that reads the complete approved "
            f"{spec / 'tasks.md'}, {spec / 'progress.md'}, requirements, design, steering, and "
            "plan review. "
            f"Write {spec / 'implementation-workflow.md'} only. Infer the TASK DAG, parallel groups, "
            "worktrees, validation, commits, integration, and stop conditions. Do not edit product code, "
            "tests, requirements, design, or tasks. Even if the plan artifact already exists, never "
            "reuse it as completion evidence: run a new Workflow, overwrite it with newly generated "
            "content, and record the current Workflow run ID in the document. Stop when the plan "
            "artifact is complete so an "
            "independent Opus reviewer can inspect it. "
        ),
        "revise-plan": (
            "ultracode: Create and run a Dynamic Workflow to revise only "
            f"{spec / 'implementation-workflow.md'} for unresolved findings in "
            f"{spec / 'review-results' / 'implementation-workflow-review.md'}. "
            "Do not edit product code or tests. Stop after persisting the revised plan. "
        ),
        "implement": (
            "ultracode: Create and run a Dynamic Workflow that implements the complete approved "
            f"{spec / 'tasks.md'} according to {spec / 'implementation-workflow.md'}. "
            "The workflow decides dependency order, parallelism, TASK worktrees, and integration. "
            f"Keep {spec / 'implementation-workflow.md'} immutable. Use Red-Green-Refactor, enforce "
            f"three attempts per TASK, and write evidence plus the exact TASK-to-SHA mapping to "
            f"{spec / 'implementation-ledger.md'}. Integrate independent successes and run every "
            "steering verification command. Update every completed TASK row in progress.md to "
            "status done with its actual start and completion dates. Before returning COMPLETE, "
            "run the bundled runtime task-gate and require its READY result. "
        ),
        "remediate": (
            "ultracode: Create and run a Dynamic Workflow to fix only unresolved CRITICAL/HIGH "
            f"findings in {spec / 'review-results' / 'code-review.md'} and "
            f"{spec / 'review-results' / 'security-review.md'}. Use TDD, keep the approved workflow "
            f"immutable, update {spec / 'implementation-ledger.md'}, and run every steering "
            "verification command. Keep every completed TASK row in progress.md at status done, "
            "then run the bundled runtime task-gate and require READY before returning COMPLETE. "
            "Do not edit reviews. "
        ),
    }
    return prompts[stage] + common


def worker_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["CLAUDE_CODE_SUBAGENT_MODEL"] = "sonnet"
    # Print mode otherwise terminates still-running Dynamic Workflows after 600s.
    env["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"] = "0"
    env.pop("ANTHROPIC_DEFAULT_OPUS_MODEL", None)
    env.pop("ANTHROPIC_DEFAULT_HAIKU_MODEL", None)
    return env


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "_supervise":
        supervise_detached_launcher(Path(sys.argv[2]).expanduser().resolve())
        return

    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=(*STAGES, "wait"))
    parser.add_argument("--slug", required=True)
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--detach", action="store_true")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--wait-seconds", type=int, default=45)
    parser.add_argument("--synchronous", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if not SLUG_RE.fullmatch(args.slug):
        fail("slug must be lowercase kebab-case")

    worktree = args.worktree.expanduser().resolve()
    plugin_root = Path(__file__).resolve().parents[1]
    spec = worktree / ".claude" / "specs" / args.slug
    if not (worktree / ".git").exists():
        fail(f"not a Git checkout or worktree: {worktree}")
    if not (spec / "tasks.md").is_file():
        fail(f"missing tasks.md for {args.slug}")

    top_level = Path(git_output(worktree, "rev-parse", "--show-toplevel")).resolve()
    if top_level != worktree:
        fail(f"worktree path is not its Git top-level: {worktree}")
    branch = git_output(worktree, "branch", "--show-current")
    if branch != f"vsdd/{args.slug}":
        fail(f"implementation requires branch vsdd/{args.slug}; active branch is {branch!r}")

    if args.stage == "wait":
        if args.evidence is None:
            fail("wait requires --evidence")
        if args.detach or args.synchronous or args.session_id or args.dry_run:
            fail("wait accepts only --slug, --worktree, --evidence, and --wait-seconds")
        wait_for_detached_launcher(
            args.evidence, worktree, args.slug, args.wait_seconds
        )
        return
    if args.evidence is not None:
        fail("--evidence is valid only for wait")
    if args.synchronous and args.detach:
        fail("--synchronous and --detach cannot be combined")

    require_runtime_preflight(
        plugin_root, worktree, args.slug, args.stage, args.session_id
    )

    before_paths = changed_paths(worktree)
    before_head = git_output(worktree, "rev-parse", "HEAD")
    workflow_path = spec / "implementation-workflow.md"
    workflow_marker_before = (
        artifact_marker(workflow_path)
        if args.stage in {"plan", "revise-plan"}
        else None
    )
    planning_fingerprint = (
        planning_guard_fingerprint(worktree, args.slug)
        if args.stage in {"plan", "revise-plan"}
        else None
    )
    spec_prefix = f".claude/specs/{args.slug}/"
    allowed_spec_prefixes = (spec_prefix, ".claude/specs/_steering/")
    unsafe_before = sorted(
        path
        for path in before_paths
        if not any(path.startswith(prefix) for prefix in allowed_spec_prefixes)
    )
    if unsafe_before:
        fail(f"uncommitted non-spec changes exist before worker launch: {unsafe_before}")

    disabled = workflows_disabled(worktree)
    if disabled:
        fail(f"Dynamic Workflows unavailable: {disabled}")

    if args.stage in {"revise-plan", "implement"} and not args.session_id:
        fail(f"{args.stage} requires --session-id to preserve the Sonnet session")
    if args.stage == "implement":
        require_pass(spec / "review-results" / "implementation-workflow-review.md")
    if args.stage == "remediate":
        reports = [
            spec / "review-results" / "code-review.md",
            spec / "review-results" / "security-review.md",
        ]
        if not all(path.is_file() for path in reports):
            fail("remediation requires both code and security review artifacts")

    claude = os.environ.get("VSDD_CLAUDE_BIN") or shutil.which("claude")
    if not claude:
        fail("claude executable not found")
    version = claude_version(claude)
    if version < MIN_CLAUDE_VERSION:
        fail("Claude Code 2.1.203 or later is required for --effort ultracode")
    child_plugin_dirs = plugin_dirs_for_child(plugin_root)

    prompt = build_prompt(args.stage, args.slug, plugin_root, worktree)
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["COMPLETE", "BLOCKED"]},
            "stage": {"type": "string"},
            "summary": {"type": "string"},
            "blocked_tasks": {"type": "array", "items": {"type": "string"}},
            "workflow_run_id": {"type": "string", "pattern": "^wf_[A-Za-z0-9-]+$"},
        },
        "required": ["status", "stage", "summary", "workflow_run_id"],
    }
    command = [
        claude,
        "-p",
        "--model",
        "sonnet",
        "--effort",
        "ultracode",
        "--permission-mode",
        "auto",
        "--allowedTools",
        *UNATTENDED_ALLOWED_TOOLS,
    ]
    for child_plugin_dir in child_plugin_dirs:
        command.extend(["--plugin-dir", str(child_plugin_dir)])
    command.extend(
        [
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema, separators=(",", ":")),
        ]
    )
    launched_session_id = args.session_id or str(uuid.uuid4())
    if args.session_id:
        command.extend(["--resume", args.session_id])
    else:
        command.extend(
            [
                "--session-id",
                launched_session_id,
                "--agent",
                "ecc-vsdd:vsdd-implementation-driver",
            ]
        )
    command.append(prompt)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "DRY_RUN",
                    "stage": args.stage,
                    "model": "sonnet",
                    "effort": "ultracode",
                    "subagent_model": "sonnet",
                    "allowed_tools": list(UNATTENDED_ALLOWED_TOOLS),
                    "background_wait_ceiling_ms": "0",
                    "plugin_dirs": [str(path) for path in child_plugin_dirs],
                    "detach": args.detach,
                    "resume": bool(args.session_id),
                },
                ensure_ascii=False,
            )
        )
        return

    if args.detach and not args.synchronous:
        supervisors_dir = spec / "worker-supervisors"
        supervisors_dir.mkdir(parents=True, exist_ok=True)
        existing = running_supervisor(supervisors_dir, args.stage)
        if existing:
            supervisor_path, _ = existing
            print(
                json.dumps(
                    {
                        "status": "RUNNING",
                        "stage": args.stage,
                        "evidence": str(supervisor_path),
                        "reused": True,
                    },
                    ensure_ascii=False,
                )
            )
            return
        supervisor_id = uuid.uuid4().hex[:12]
        supervisor_path = supervisors_dir / f"{args.stage}-{supervisor_id}.json"
        child_command = [
            sys.executable,
            str(Path(__file__).resolve()),
            args.stage,
            "--slug",
            args.slug,
            "--worktree",
            str(worktree),
            "--synchronous",
        ]
        if args.session_id:
            child_command.extend(["--session-id", args.session_id])
        supervisor = {
            "status": "PREPARING",
            "stage": args.stage,
            "slug": args.slug,
            "worktree": str(worktree),
            "command": child_command,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json_atomic(supervisor_path, supervisor)
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "_supervise",
                    str(supervisor_path),
                ],
                cwd=worktree,
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as error:
            supervisor.update(
                {
                    "status": "BLOCKED",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "result": {
                        "status": "BLOCKED",
                        "error": f"cannot start detached launcher supervisor: {error}",
                    },
                }
            )
            write_json_atomic(supervisor_path, supervisor)
            fail(f"cannot start detached launcher supervisor: {error}")
        supervisor.update({"status": "RUNNING", "pid": process.pid})
        write_json_atomic(supervisor_path, supervisor)
        print(
            json.dumps(
                {
                    "status": "STARTED",
                    "stage": args.stage,
                    "evidence": str(supervisor_path),
                },
                ensure_ascii=False,
            )
        )
        return

    sessions_dir = spec / "worker-sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    record_path = sessions_dir / f"{args.stage}-{run_id}.json"
    record = {
        "status": "RUNNING",
        "stage": args.stage,
        "session_id": launched_session_id,
        "model": "sonnet",
        "effort": "ultracode",
        "subagent_model": "sonnet",
        "allowed_tools": list(UNATTENDED_ALLOWED_TOOLS),
        "background_wait_ceiling_ms": "0",
        "plugin_dirs": [str(path) for path in child_plugin_dirs],
        "started_from_session": args.session_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    env = worker_environment()
    try:
        result = subprocess.run(
            command,
            cwd=worktree,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except KeyboardInterrupt:
        record["status"] = "INTERRUPTED"
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        record_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        fail(
            "Claude worker interrupted; resume with session "
            f"{launched_session_id}; evidence: {record_path}"
        )
    except OSError as error:
        record["status"] = "FAILED"
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        record["error"] = str(error)
        record_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        fail(f"cannot launch Claude worker; evidence: {record_path}")

    unexpected: list[str] = []
    planning_head_changed = False
    planning_content_changed = False
    workflow_marker_after = None
    if args.stage in {"plan", "revise-plan"}:
        after_paths = changed_paths(worktree)
        newly_changed = after_paths - before_paths
        allowed = {
            f".claude/specs/{args.slug}/implementation-workflow.md",
            record_path.relative_to(worktree).as_posix(),
        }
        unexpected = sorted(newly_changed - allowed)
        planning_head_changed = git_output(worktree, "rev-parse", "HEAD") != before_head
        planning_content_changed = (
            planning_guard_fingerprint(worktree, args.slug) != planning_fingerprint
        )
        workflow_marker_after = artifact_marker(workflow_path)

    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError:
        response = {
            "raw_stdout": result.stdout,
            "raw_stderr": result.stderr,
        }
    record.update(
        {
            "status": "FINISHED" if result.returncode == 0 else "FAILED",
            "returncode": result.returncode,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "stderr": result.stderr,
            "unexpected_planning_changes": unexpected,
            "planning_head_changed": planning_head_changed,
            "planning_content_changed": planning_content_changed,
            "workflow_marker_before": workflow_marker_before,
            "workflow_marker_after": workflow_marker_after,
            "response": response,
        }
    )
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    def block_after_run(message: str) -> None:
        record["status"] = "BLOCKED"
        record["validation_error"] = message
        record_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        fail(f"{message}; evidence: {record_path}")

    session_id = response.get("session_id") if isinstance(response, dict) else None
    structured = response.get("structured_output") if isinstance(response, dict) else None
    if result.returncode != 0:
        fail(f"Claude worker failed; evidence: {record_path}")
    if unexpected or planning_head_changed or planning_content_changed:
        block_after_run("implementation planning modified prohibited files or commits")
    if not session_id:
        block_after_run("Claude worker returned no session_id")
    if session_id != launched_session_id:
        block_after_run("Claude worker session_id mismatch")
    if not isinstance(structured, dict):
        block_after_run("Claude worker returned no structured_output")
    workflow_run_id = structured.get("workflow_run_id")
    if not isinstance(workflow_run_id, str) or not re.fullmatch(
        r"wf_[A-Za-z0-9-]+", workflow_run_id
    ):
        block_after_run("Claude worker returned no valid current workflow_run_id")
    if structured.get("status") == "BLOCKED":
        block_after_run("Dynamic Workflow reported BLOCKED")
    if structured.get("status") != "COMPLETE" or structured.get("stage") != args.stage:
        block_after_run("Claude worker returned an invalid structured result")
    if args.stage in {"plan", "revise-plan"}:
        artifact_issue = planning_artifact_issue(
            args.stage, workflow_marker_before, workflow_marker_after
        )
        if artifact_issue:
            block_after_run(artifact_issue)
        evidence_issue = workflow_evidence_issue(workflow_path, workflow_run_id)
        if evidence_issue:
            block_after_run(evidence_issue)
    if args.stage in {"implement", "remediate"}:
        integrity_issue = task_integrity_issue(
            plugin_root, worktree, args.slug
        )
        if integrity_issue:
            block_after_run(integrity_issue)
    if args.stage == "plan":
        bind_implementation_session(spec / "run-state.json", session_id)

    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "stage": args.stage,
                "session_id": session_id,
                "evidence": str(record_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
