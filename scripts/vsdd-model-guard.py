#!/usr/bin/env python3
"""Deny control-plane work and enforce pinned VSDD agent effort levels."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


EXPECTED_EFFORT = {
    "ecc-vsdd:vsdd-orchestrator": "high",
    "ecc-vsdd:vsdd-steering-worker": "xhigh",
    "ecc-vsdd:vsdd-init-worker": "low",
    "ecc-vsdd:vsdd-requirements-worker": "xhigh",
    "ecc-vsdd:vsdd-requirements-reviewer": "xhigh",
    "ecc-vsdd:vsdd-design-worker": "xhigh",
    "ecc-vsdd:vsdd-tasks-worker": "high",
    "ecc-vsdd:vsdd-plan-reviewer": "xhigh",
    "ecc-vsdd:vsdd-implementation-driver": "xhigh",
    "ecc-vsdd:vsdd-implementation-workflow-reviewer": "xhigh",
    "ecc-vsdd:vsdd-code-reviewer": "xhigh",
    "ecc-vsdd:vsdd-security-reviewer": "xhigh",
    "ecc-vsdd:vsdd-remediation-worker": "high",
    "ecc-vsdd:vsdd-pr-worker": "medium",
    "ecc-vsdd:vsdd-status-worker": "low",
}

EXPECTED_MODEL = {
    "ecc-vsdd:vsdd-orchestrator": "fable",
    "ecc-vsdd:vsdd-steering-worker": "opus",
    "ecc-vsdd:vsdd-init-worker": "haiku",
    "ecc-vsdd:vsdd-requirements-worker": "opus",
    "ecc-vsdd:vsdd-requirements-reviewer": "opus",
    "ecc-vsdd:vsdd-design-worker": "opus",
    "ecc-vsdd:vsdd-tasks-worker": "sonnet",
    "ecc-vsdd:vsdd-plan-reviewer": "opus",
    "ecc-vsdd:vsdd-implementation-driver": "sonnet",
    "ecc-vsdd:vsdd-implementation-workflow-reviewer": "opus",
    "ecc-vsdd:vsdd-code-reviewer": "opus",
    "ecc-vsdd:vsdd-security-reviewer": "opus",
    "ecc-vsdd:vsdd-remediation-worker": "sonnet",
    "ecc-vsdd:vsdd-pr-worker": "sonnet",
    "ecc-vsdd:vsdd-status-worker": "haiku",
}

WORKERS = set(EXPECTED_EFFORT) - {"ecc-vsdd:vsdd-orchestrator"}
ORCHESTRATOR_TOOLS = {"Read", "Grep", "Glob", "LS", "Skill", "Agent", "Task"}
ORCHESTRATOR_AGENTS = WORKERS - {"ecc-vsdd:vsdd-implementation-driver"}
PROJECT_WORKER_NAMES = {
    agent_type.split(":", 1)[1]: agent_type for agent_type in ORCHESTRATOR_AGENTS
}
ORCHESTRATOR_SKILLS = {"ecc-vsdd:vsdd-run", "vsdd-run"}
AUTHORIZATION_TTL_SECONDS = 7 * 24 * 60 * 60
PR_CONSENT_TTL_SECONDS = 24 * 60 * 60
ORCHESTRATOR_RELAY_TTL_SECONDS = 60 * 60
PROJECT_AGENT_MARKER = "<!-- ecc-vsdd-generated-agent-proxy:v1 -->"
PROJECT_AGENTS_READY_ENV = "ECC_VSDD_PROJECT_AGENTS_READY"
VSDD_ENTRY_POINTS = {
    "vsdd-run",
    "vsdd-steering",
    "vsdd-init",
    "vsdd-requirements",
    "vsdd-review-requirements",
    "vsdd-design",
    "vsdd-tasks",
    "vsdd-review-plan",
    "vsdd-workflow",
    "vsdd-review",
    "vsdd-pr",
}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PROMPT_ID_RE = re.compile(r"^[a-zA-Z0-9-]{8,128}$")
SAFE_GIT_SUBCOMMANDS = {
    "add",
    "am",
    "apply",
    "archive",
    "bisect",
    "blame",
    "branch",
    "bundle",
    "cat-file",
    "check-attr",
    "check-ignore",
    "check-ref-format",
    "checkout",
    "cherry",
    "cherry-pick",
    "clean",
    "clone",
    "commit",
    "config",
    "describe",
    "diff",
    "diff-tree",
    "fetch",
    "for-each-ref",
    "format-patch",
    "fsck",
    "grep",
    "hash-object",
    "help",
    "init",
    "log",
    "ls-files",
    "ls-remote",
    "ls-tree",
    "merge",
    "merge-base",
    "merge-tree",
    "mv",
    "notes",
    "pull",
    "range-diff",
    "rebase",
    "reflog",
    "remote",
    "reset",
    "restore",
    "revert",
    "rev-list",
    "rev-parse",
    "rm",
    "show",
    "show-ref",
    "sparse-checkout",
    "status",
    "submodule",
    "switch",
    "tag",
    "update-index",
    "update-ref",
    "version",
    "worktree",
}
SAFE_GH_COMMANDS = {
    ("--version",),
    ("auth", "status"),
    ("help",),
    ("issue", "list"),
    ("issue", "status"),
    ("issue", "view"),
    ("pr", "checks"),
    ("pr", "diff"),
    ("pr", "list"),
    ("pr", "status"),
    ("pr", "view"),
    ("release", "list"),
    ("release", "view"),
    ("repo", "list"),
    ("repo", "view"),
    ("run", "list"),
    ("run", "view"),
    ("run", "watch"),
    ("search", "code"),
    ("search", "commits"),
    ("search", "issues"),
    ("search", "prs"),
    ("search", "repos"),
    ("status",),
    ("workflow", "list"),
    ("workflow", "view"),
}
SHELL_INTERPRETERS = {"bash", "dash", "ksh", "sh", "zsh"}
SHELL_COMMAND_WRAPPERS = {"command", "env", "exec", "nohup", "sudo"}
CODE_INTERPRETERS = {"node", "nodejs", "perl", "python", "python3", "ruby"}
ACTIVE_HOOK_EVENT = ""
ACTIVE_PROJECT_AGENT = False


def deny(message: str) -> None:
    if ACTIVE_HOOK_EVENT == "PreToolUse":
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            f"VSDD control-plane guard: {message}"
                        ),
                    }
                }
            )
        )
        raise SystemExit(0)
    print(f"VSDD control-plane guard: {message}", file=sys.stderr)
    raise SystemExit(2)


def installed_plugin_root() -> Path:
    raw_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if not raw_plugin_root and ACTIVE_PROJECT_AGENT:
        raw_plugin_root = str(Path(__file__).resolve().parents[1])
    if not raw_plugin_root:
        deny("cannot resolve the installed plugin root")
    plugin_root = Path(raw_plugin_root).resolve()
    if not plugin_root.is_dir():
        deny("cannot resolve the installed plugin root")
    return plugin_root


def allow_validated_tool(authorized: bool) -> None:
    """Skip prompts only for a validated strict or orchestrator-authorized call."""
    if not authorized:
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": (
                        "ecc-vsdd validated the pinned agent, model, effort, and tool scope"
                    ),
                }
            }
        )
    )


def guard_runtime_root() -> Path:
    """Return a user-private, session-lifetime state root shared by hook types."""
    user_id = str(os.getuid()) if hasattr(os, "getuid") else "current-user"
    return Path(tempfile.gettempdir()) / f"ecc-vsdd-guard-{user_id}"


def ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        deny(f"guard runtime path is not a private directory: {path}")
    if os.name != "nt":
        details = path.stat()
        if hasattr(os, "getuid") and details.st_uid != os.getuid():
            deny(f"guard runtime directory has a different owner: {path}")
        if stat.S_IMODE(details.st_mode) & 0o077:
            try:
                path.chmod(0o700)
            except OSError as error:
                deny(f"cannot restrict guard runtime directory permissions: {error}")
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                deny(f"guard runtime directory permissions are too broad: {path}")


def write_private_json(path: Path, record: dict) -> None:
    root = guard_runtime_root()
    try:
        path.relative_to(root)
    except ValueError:
        deny(f"guard runtime record escapes its private root: {path}")
    ensure_private_directory(root)
    ensure_private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def read_private_json(path: Path) -> dict | None:
    root = guard_runtime_root()
    try:
        path.relative_to(root)
        ensure_private_directory(root)
        ensure_private_directory(path.parent)
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
    except (ValueError, FileNotFoundError, OSError):
        return None
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            return None
        if os.name != "nt":
            if hasattr(os, "getuid") and details.st_uid != os.getuid():
                return None
            if stat.S_IMODE(details.st_mode) & 0o077 or details.st_nlink != 1:
                return None
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = -1
            value = json.load(stream)
    except (json.JSONDecodeError, OSError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return value if isinstance(value, dict) else None


def safe_session_id(session_id: object) -> str:
    return re.sub(r"[^a-zA-Z0-9-]", "", str(session_id or ""))


def normalized_cwd(payload: dict) -> str | None:
    raw = str(payload.get("cwd") or "")
    if not raw or not Path(raw).is_absolute():
        return None
    return str(Path(raw).resolve())


def authorization_record_path(session_id: object) -> Path | None:
    safe_id = re.sub(r"[^a-zA-Z0-9-]", "", str(session_id or ""))
    if not safe_id:
        return None
    return guard_runtime_root() / "authorized-sessions" / f"{safe_id}.json"


def pr_authorization_record_path(session_id: object) -> Path | None:
    safe_id = safe_session_id(session_id)
    if not safe_id:
        return None
    return guard_runtime_root() / "pr-authorized-sessions" / f"{safe_id}.json"


def pr_consent_record_path(session_id: object) -> Path | None:
    safe_id = safe_session_id(session_id)
    if not safe_id:
        return None
    return guard_runtime_root() / "pr-consent-sessions" / f"{safe_id}.json"


def materialized_agents_record_path(session_id: object) -> Path | None:
    safe_id = safe_session_id(session_id)
    if not safe_id:
        return None
    return guard_runtime_root() / "materialized-agent-sessions" / f"{safe_id}.json"


def orchestrator_relay_record_path(session_id: object) -> Path | None:
    safe_id = safe_session_id(session_id)
    if not safe_id:
        return None
    return guard_runtime_root() / "orchestrator-relay-sessions" / f"{safe_id}.json"


def remove_private_record(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as error:
        deny(f"cannot clear guard session state: {error}")


def exact_pr_consent_operation(prompt: object) -> str | None:
    raw = str(prompt or "")
    if not raw or "\n" in raw or "\r" in raw or raw != raw.strip():
        return None
    try:
        argv = shlex.split(raw)
    except ValueError:
        return None
    if len(argv) < 4 or argv[0] not in {
        "/ecc-vsdd:vsdd-run",
        "/vsdd-run",
    }:
        return None
    operation = argv[1]
    if operation not in {"start", "resume"}:
        if operation in {"status", "cancel", "cleanup"} or not SLUG_RE.fullmatch(
            operation
        ):
            return None
        operation = "start"
    until_values: list[str] = []
    index = 2
    while index < len(argv):
        token = argv[index]
        if token == "--until":
            if index + 1 >= len(argv):
                return None
            until_values.append(argv[index + 1])
            index += 2
            continue
        if token.startswith("--until="):
            until_values.append(token.split("=", 1)[1])
        index += 1
    if until_values != ["pr"]:
        return None
    return operation


def is_exact_vsdd_entry_prompt(prompt: object) -> bool:
    raw = str(prompt or "")
    if not raw or "\n" in raw or "\r" in raw or raw != raw.strip():
        return False
    try:
        argv = shlex.split(raw)
    except ValueError:
        return False
    if not argv or not argv[0].startswith("/"):
        return False
    command = argv[0][1:]
    if command.startswith("ecc-vsdd:"):
        command = command.split(":", 1)[1]
    return command in VSDD_ENTRY_POINTS


def project_agent_directory(cwd: str) -> Path:
    root = Path(cwd)
    claude_dir = root / ".claude"
    agent_dir = claude_dir / "agents"
    for directory in (claude_dir, agent_dir):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            deny(f"project agent directory is unsafe: {directory}")
        try:
            directory.mkdir(exist_ok=True)
        except OSError as error:
            deny(f"cannot create project agent directory {directory}: {error}")
    return agent_dir


def rendered_project_agent(agent_type: str) -> str:
    source = agent_definition_path(agent_type)
    try:
        content = source.read_text(encoding="utf-8")
    except OSError as error:
        deny(f"cannot read project agent template {source}: {error}")
    parts = content.split("---", 2)
    if len(parts) != 3 or parts[0].strip() or "\nhooks:" in parts[1]:
        deny(f"project agent template has unsupported frontmatter: {source}")
    guard_script = installed_plugin_root() / "scripts" / "vsdd-model-guard.py"
    guard_command = shlex.join(["python3", str(guard_script), "--project-agent"])
    hook = (
        "\nhooks:\n"
        "  PreToolUse:\n"
        "    - matcher: \"\"\n"
        "      hooks:\n"
        "        - type: command\n"
        f"          command: {json.dumps(guard_command)}\n"
    )
    return f"---{parts[1].rstrip()}{hook}---{parts[2].rstrip()}\n\n{PROJECT_AGENT_MARKER}\n"


def atomic_write_project_agent(path: Path, content: str) -> None:
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=".ecc-vsdd-agent-", dir=path.parent
        )
        temporary = Path(raw_temporary)
        if os.name != "nt":
            os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # The target was checked before rendering, but another session could
        # create it before this write. Link without replacement so a project
        # agent is never overwritten across that race.
        os.link(temporary, path)
        temporary.unlink()
        temporary = None
    except OSError as error:
        deny(f"cannot materialize protected project agent {path}: {error}")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def recorded_project_agent_exists(
    cwd: str, name: str, target: Path, content_hash: str
) -> bool:
    directory = guard_runtime_root() / "materialized-agent-sessions"
    if not directory.exists():
        return False
    now_value = time.time()
    for record_path in directory.glob("*.json"):
        record = read_private_json(record_path)
        created_at = record.get("created_at") if record else None
        files = record.get("files") if record else None
        entry = files.get(name) if isinstance(files, dict) else None
        if (
            record
            and record.get("schema_version") == 1
            and record.get("authorization") == "vsdd-project-agents"
            and record.get("cwd") == cwd
            and isinstance(created_at, int)
            and 0 <= now_value - created_at <= AUTHORIZATION_TTL_SECONDS
            and isinstance(entry, dict)
            and entry.get("path") == str(target)
            and entry.get("sha256") == content_hash
        ):
            return True
    return False


def remove_recorded_project_agent_files(record: dict) -> None:
    files = record.get("files")
    if not isinstance(files, dict):
        return
    for name, entry in files.items():
        if name not in PROJECT_WORKER_NAMES or not isinstance(entry, dict):
            continue
        target = Path(str(entry.get("path") or ""))
        if target.is_symlink() or not target.is_file():
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except OSError:
            continue
        if hashlib.sha256(content.encode("utf-8")).hexdigest() == entry.get("sha256"):
            try:
                target.unlink()
            except OSError:
                continue


def materialize_project_agents(payload: dict) -> list[str]:
    cwd = normalized_cwd(payload)
    path = materialized_agents_record_path(payload.get("session_id"))
    prompt_id = str(payload.get("prompt_id") or "")
    if cwd is None or path is None or not PROMPT_ID_RE.fullmatch(prompt_id):
        deny("protected project agents require session_id, cwd, and prompt_id")
    agent_dir = project_agent_directory(cwd)
    rendered: dict[str, tuple[Path, str, bool]] = {}
    for name, agent_type in sorted(PROJECT_WORKER_NAMES.items()):
        target = agent_dir / f"{name}.md"
        content = rendered_project_agent(agent_type)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        adopted = False
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_file():
                deny(f"refuses to overwrite existing project agent: {target}")
            try:
                existing = target.read_text(encoding="utf-8")
            except OSError as error:
                deny(f"cannot inspect existing project agent {target}: {error}")
            if (
                hashlib.sha256(existing.encode("utf-8")).hexdigest() != content_hash
                or not recorded_project_agent_exists(
                    cwd, name, target, content_hash
                )
            ):
                deny(f"refuses to overwrite existing project agent: {target}")
            adopted = True
        rendered[name] = (target, content, adopted)
    files: dict[str, dict[str, str]] = {}
    created: set[str] = set()
    try:
        for name, (target, content, adopted) in rendered.items():
            if not adopted:
                atomic_write_project_agent(target, content)
                created.add(name)
            files[name] = {
                "path": str(target),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        write_private_json(
            path,
            {
                "schema_version": 1,
                "authorization": "vsdd-project-agents",
                "session_id": safe_session_id(payload.get("session_id")),
                "cwd": cwd,
                "prompt_id": prompt_id,
                "files": files,
                "created_at": int(time.time()),
            },
        )
    except BaseException:
        # Roll back only files whose bytes still match this generation. This
        # also handles a record-write failure after all proxies were created.
        for name, entry in files.items():
            if name not in created:
                continue
            target = Path(entry["path"])
            if target.is_symlink() or not target.is_file():
                continue
            try:
                content = target.read_text(encoding="utf-8")
                if hashlib.sha256(content.encode("utf-8")).hexdigest() == entry["sha256"]:
                    target.unlink()
            except OSError:
                pass
        raise
    return sorted(files)


def materialized_agents_record(payload: dict) -> dict:
    path = materialized_agents_record_path(payload.get("session_id"))
    record = read_private_json(path) if path is not None else None
    created_at = record.get("created_at") if record else None
    age = time.time() - created_at if isinstance(created_at, int) else -1
    if not (
        record
        and record.get("schema_version") == 1
        and record.get("authorization") == "vsdd-project-agents"
        and record.get("session_id") == safe_session_id(payload.get("session_id"))
        and record.get("cwd") == normalized_cwd(payload)
        and record.get("prompt_id") == str(payload.get("prompt_id") or "")
        and isinstance(record.get("files"), dict)
        and 0 <= age <= AUTHORIZATION_TTL_SECONDS
    ):
        deny("VSDD worker lacks a valid materialized project agent record")
    return record


def check_materialized_project_agent(
    payload: dict, raw_agent_type: object, agent_type: str
) -> None:
    expected_name = agent_type.split(":", 1)[1]
    if str(raw_agent_type or "") != expected_name:
        deny(
            f"launch the project-local protected worker {expected_name!r}; "
            "plugin-scoped worker hooks are ignored by Claude Code"
        )
    record = materialized_agents_record(payload)
    entry = record["files"].get(expected_name)
    cwd = normalized_cwd(payload)
    expected_path = (
        Path(cwd) / ".claude" / "agents" / f"{expected_name}.md"
        if cwd
        else None
    )
    if not isinstance(entry, dict) or expected_path is None:
        deny("materialized project agent record is incomplete")
    path = Path(str(entry.get("path") or ""))
    if path != expected_path or path.is_symlink() or not path.is_file():
        deny("materialized project agent path is invalid")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        deny(f"cannot read materialized project agent {path}: {error}")
    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if (
        PROJECT_AGENT_MARKER not in content
        or entry.get("sha256") != actual_hash
        or str(installed_plugin_root() / "scripts" / "vsdd-model-guard.py")
        not in content
        or "--project-agent" not in content
    ):
        deny(f"materialized project agent was modified: {expected_name}")


def cleanup_materialized_agents(payload: dict) -> None:
    path = materialized_agents_record_path(payload.get("session_id"))
    record = read_private_json(path) if path is not None else None
    if record is None or not isinstance(record.get("files"), dict):
        return
    directory = guard_runtime_root() / "materialized-agent-sessions"
    now_value = time.time()
    if directory.exists():
        for other_path in directory.glob("*.json"):
            if other_path == path:
                continue
            other = read_private_json(other_path)
            created_at = other.get("created_at") if other else None
            if (
                other
                and other.get("cwd") == record.get("cwd")
                and isinstance(created_at, int)
                and 0 <= now_value - created_at <= AUTHORIZATION_TTL_SECONDS
            ):
                return
    remove_recorded_project_agent_files(record)
    cwd = str(record.get("cwd") or "")
    if cwd:
        for directory_path in (
            Path(cwd) / ".claude" / "agents",
            Path(cwd) / ".claude",
        ):
            try:
                directory_path.rmdir()
            except OSError:
                pass


def relay_command(record: dict, action: str) -> str:
    command = [
        "python3",
        str(installed_plugin_root() / "scripts" / "vsdd-model-guard.py"),
        action,
        "--session-id",
        str(record["session_id"]),
        "--prompt-id",
        str(record["prompt_id"]),
        "--capability",
        str(record["capability"]),
    ]
    if action == "--relay-wait":
        command.extend(["--wait-seconds", "45"])
    return shlex.join(command)


def create_orchestrator_relay(payload: dict) -> tuple[str, str]:
    path = orchestrator_relay_record_path(payload.get("session_id"))
    cwd = normalized_cwd(payload)
    prompt_id = str(payload.get("prompt_id") or "")
    prompt = str(payload.get("prompt") or "")
    if path is None or cwd is None or not PROMPT_ID_RE.fullmatch(prompt_id):
        deny("orchestrator relay requires session_id, cwd, and prompt_id")
    capability = secrets.token_urlsafe(32)
    record = {
        "schema_version": 1,
        "authorization": "vsdd-orchestrator-relay",
        "session_id": safe_session_id(payload.get("session_id")),
        "cwd": cwd,
        "prompt_id": prompt_id,
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "capability": capability,
        "created_at": int(time.time()),
        "status": "READY",
    }
    start_command = relay_command(record, "--relay-start")
    wait_command = relay_command(record, "--relay-wait")
    record["start_command"] = start_command
    record["wait_command"] = wait_command
    try:
        write_private_json(path, record)
    except OSError as error:
        deny(f"cannot persist orchestrator relay authorization: {error}")
    return start_command, wait_command


def current_orchestrator_relay(payload: dict) -> tuple[Path, dict] | None:
    path = orchestrator_relay_record_path(payload.get("session_id"))
    record = read_private_json(path) if path is not None else None
    if record is None or path is None:
        return None
    created_at = record.get("created_at")
    age = time.time() - created_at if isinstance(created_at, int) else -1
    if not (
        record.get("schema_version") == 1
        and record.get("authorization") == "vsdd-orchestrator-relay"
        and record.get("session_id") == safe_session_id(payload.get("session_id"))
        and record.get("cwd") == normalized_cwd(payload)
        and record.get("prompt_id") == str(payload.get("prompt_id") or "")
        and re.fullmatch(r"[A-Za-z0-9_-]{32,128}", str(record.get("capability") or ""))
        and record.get("status") in {"READY", "RUNNING", "COMPLETE", "BLOCKED"}
        and 0 <= age <= ORCHESTRATOR_RELAY_TTL_SECONDS
    ):
        deny("orchestrator relay authorization is invalid or expired")
    return path, record


def relay_invocation(command: object) -> dict[str, str] | None:
    raw_command = str(command or "")
    if any(character in raw_command for character in "\r\n;|&<>{}*?[]~"):
        return None
    if "$(" in raw_command or "`" in raw_command:
        return None
    try:
        argv = shlex.split(raw_command)
    except ValueError:
        return None
    if len(argv) not in {9, 11} or Path(argv[0]).name not in {"python", "python3"}:
        return None
    guard_script = (installed_plugin_root() / "scripts" / "vsdd-model-guard.py").resolve()
    if Path(argv[1]).resolve() != guard_script or argv[2] not in {
        "--relay-start",
        "--relay-wait",
    }:
        return None
    if argv[3] != "--session-id" or argv[5] != "--prompt-id" or argv[7] != "--capability":
        return None
    if argv[2] == "--relay-start" and len(argv) != 9:
        return None
    if argv[2] == "--relay-wait" and (
        len(argv) != 11 or argv[9:] != ["--wait-seconds", "45"]
    ):
        return None
    return {
        "action": argv[2],
        "session_id": argv[4],
        "prompt_id": argv[6],
        "capability": argv[8],
    }


def check_orchestrator_relay(payload: dict, command: object) -> None:
    parsed = relay_invocation(command)
    current = current_orchestrator_relay(payload)
    if parsed is None or current is None:
        deny("Fable must invoke the exact protected orchestrator relay command")
    _, record = current
    expected = {
        "session_id": safe_session_id(payload.get("session_id")),
        "prompt_id": str(payload.get("prompt_id") or ""),
        "capability": str(record.get("capability") or ""),
    }
    if any(
        not secrets.compare_digest(parsed[key], value)
        for key, value in expected.items()
    ):
        deny("orchestrator relay invocation does not match its authorization")
    status = record.get("status")
    if parsed["action"] == "--relay-start" and status != "READY":
        deny("orchestrator relay start is not ready")
    if parsed["action"] == "--relay-wait" and status not in {
        "RUNNING",
        "COMPLETE",
        "BLOCKED",
    }:
        deny("orchestrator relay wait has not started")


def handle_user_prompt(payload: dict) -> None:
    cleanup_materialized_agents(payload)
    remove_private_record(materialized_agents_record_path(payload.get("session_id")))
    remove_private_record(orchestrator_relay_record_path(payload.get("session_id")))
    protected_agents: list[str] = []
    relay_start_command = ""
    relay_wait_command = ""
    if is_exact_vsdd_entry_prompt(payload.get("prompt")):
        protected_agents = materialize_project_agents(payload)
        if os.environ.get(PROJECT_AGENTS_READY_ENV) != "1":
            relay_start_command, relay_wait_command = create_orchestrator_relay(payload)
    path = pr_consent_record_path(payload.get("session_id"))
    remove_private_record(path)
    operation = exact_pr_consent_operation(payload.get("prompt"))
    if operation is not None:
        cwd = normalized_cwd(payload)
        prompt_id = str(payload.get("prompt_id") or "")
        prompt = str(payload.get("prompt") or "")
        if path is None or cwd is None or not PROMPT_ID_RE.fullmatch(prompt_id):
            deny("explicit PR consent requires session_id, cwd, and prompt_id")
        try:
            write_private_json(
                path,
                {
                    "schema_version": 1,
                    "authorization": "vsdd-pr-consent",
                    "session_id": safe_session_id(payload.get("session_id")),
                    "cwd": cwd,
                    "prompt_id": prompt_id,
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    "operation": operation,
                    "created_at": int(time.time()),
                },
            )
        except OSError as error:
            deny(f"cannot persist prompt-bound PR consent: {error}")
    if protected_agents:
        if relay_start_command:
            context = (
                "ecc-vsdd materialized project-local protected workers after this "
                "session's agent registry was initialized. Before any phase work, invoke "
                f"exactly this Bash start command: {relay_start_command}. Then invoke "
                f"exactly this Bash wait command: {relay_wait_command}. Repeat only the "
                "same wait command while its status is RUNNING. Return the child session's "
                "terminal result and do nothing else. Do not inspect the repository or launch "
                "an Agent first."
            )
        else:
            context = (
                "ecc-vsdd protected project workers were present before this child "
                "session initialized. Launch worker agents only by these unscoped names: "
                + ", ".join(protected_agents)
                + ". Never launch ecc-vsdd:vsdd-* plugin-scoped workers."
            )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": context,
                    }
                }
            )
        )


def current_pr_consent(
    payload: dict, *, expected_operation: str | None = None
) -> tuple[Path, dict]:
    path = pr_consent_record_path(payload.get("session_id"))
    record = read_private_json(path) if path is not None else None
    prompt_id = str(payload.get("prompt_id") or "")
    if record is None or path is None or not PROMPT_ID_RE.fullmatch(prompt_id):
        deny("operation lacks prompt-bound PR consent")
    created_at = record.get("created_at")
    age = time.time() - created_at if isinstance(created_at, int) else -1
    if not (
        record.get("schema_version") == 1
        and record.get("authorization") == "vsdd-pr-consent"
        and record.get("session_id") == safe_session_id(payload.get("session_id"))
        and record.get("cwd") == normalized_cwd(payload)
        and record.get("prompt_id") == prompt_id
        and re.fullmatch(r"[0-9a-f]{64}", str(record.get("prompt_sha256") or ""))
        and record.get("operation") in {"start", "resume"}
        and 0 <= age <= PR_CONSENT_TTL_SECONDS
    ):
        deny("operation lacks valid prompt-bound PR consent")
    if expected_operation and record.get("operation") != expected_operation:
        deny(
            "prompt-bound PR consent operation does not match "
            f"{expected_operation!r}"
        )
    return path, record


def consume_pr_consent(payload: dict, worktree: Path, slug: str) -> None:
    path, record = current_pr_consent(payload)
    tool_use_id = str(payload.get("tool_use_id") or "")
    if not tool_use_id:
        deny("PR worker launch lacks a tool_use_id for prompt-bound PR consent")
    consumed_by = record.get("consumed_by_tool_use_id")
    if consumed_by:
        if not (
            consumed_by == tool_use_id
            and record.get("slug") == slug
            and record.get("integration_worktree") == str(worktree)
        ):
            deny("prompt-bound PR consent was already consumed")
        return
    record["consumed_by_tool_use_id"] = tool_use_id
    record["slug"] = slug
    record["integration_worktree"] = str(worktree)
    record["consumed_at"] = int(time.time())
    try:
        write_private_json(path, record)
    except OSError as error:
        deny(f"cannot consume prompt-bound PR consent: {error}")


def authorize_strict_session(payload: dict) -> None:
    path = authorization_record_path(payload.get("session_id"))
    cwd = normalized_cwd(payload)
    if path is None or cwd is None:
        deny("cannot persist strict session authorization")
    try:
        write_private_json(
            path,
            {
                "schema_version": 1,
                "agent_type": "ecc-vsdd:vsdd-orchestrator",
                "authorization": "vsdd-run-strict",
                "session_id": safe_session_id(payload.get("session_id")),
                "cwd": cwd,
                "created_at": int(time.time()),
            },
        )
    except OSError as error:
        deny(f"cannot persist strict session authorization: {error}")


def strict_session_authorized(payload: dict) -> bool:
    path = authorization_record_path(payload.get("session_id"))
    if path is None:
        return False
    record = read_private_json(path)
    if record is None:
        return False
    created_at = record.get("created_at")
    age = time.time() - created_at if isinstance(created_at, int) else -1
    return (
        record.get("schema_version") == 1
        and record.get("agent_type") == "ecc-vsdd:vsdd-orchestrator"
        and record.get("authorization") == "vsdd-run-strict"
        and record.get("session_id") == safe_session_id(payload.get("session_id"))
        and record.get("cwd") == normalized_cwd(payload)
        and 0 <= age <= AUTHORIZATION_TTL_SECONDS
    )


def clear_session_state(payload: dict) -> None:
    cleanup_materialized_agents(payload)
    for resolver in (
        authorization_record_path,
        pr_authorization_record_path,
        pr_consent_record_path,
        session_record_path,
        materialized_agents_record_path,
        orchestrator_relay_record_path,
    ):
        remove_private_record(resolver(payload.get("session_id")))


def sweep_expired_session_state() -> None:
    root = guard_runtime_root()
    ensure_private_directory(root)
    now_value = time.time()
    for directory_name in (
        "authorized-sessions",
        "pr-authorized-sessions",
        "pr-consent-sessions",
        "session-models",
        "materialized-agent-sessions",
        "orchestrator-relay-sessions",
    ):
        directory = root / directory_name
        if not directory.exists():
            continue
        ensure_private_directory(directory)
        for path in directory.glob("*.json"):
            record = read_private_json(path)
            if record is None:
                continue
            created_at = record.get("created_at")
            if isinstance(created_at, int):
                age = now_value - created_at
            else:
                try:
                    age = now_value - path.stat().st_mtime
                except OSError:
                    continue
            ttl = (
                PR_CONSENT_TTL_SECONDS
                if directory_name == "pr-consent-sessions"
                else (
                    ORCHESTRATOR_RELAY_TTL_SECONDS
                    if directory_name == "orchestrator-relay-sessions"
                    else AUTHORIZATION_TTL_SECONDS
                )
            )
            if age < 0 or age > ttl:
                if directory_name == "materialized-agent-sessions" and record:
                    has_current_owner = False
                    for other_path in directory.glob("*.json"):
                        if other_path == path:
                            continue
                        other = read_private_json(other_path)
                        other_created_at = other.get("created_at") if other else None
                        if (
                            other
                            and other.get("cwd") == record.get("cwd")
                            and isinstance(other_created_at, int)
                            and 0
                            <= now_value - other_created_at
                            <= AUTHORIZATION_TTL_SECONDS
                        ):
                            has_current_owner = True
                            break
                    if not has_current_owner:
                        remove_recorded_project_agent_files(record)
                remove_private_record(path)


def standalone_orchestrator_relay(
    arguments: list[str], *, require_prompt_id: bool = True
) -> tuple[Path, dict]:
    expected_length = 6 if require_prompt_id else 4
    if (
        len(arguments) != expected_length
        or arguments[0] != "--session-id"
        or (require_prompt_id and arguments[2] != "--prompt-id")
        or arguments[-2] != "--capability"
    ):
        deny("invalid orchestrator relay arguments")
    session_id = arguments[1]
    prompt_id = arguments[3] if require_prompt_id else None
    capability = arguments[-1]
    path = orchestrator_relay_record_path(session_id)
    record = read_private_json(path) if path is not None else None
    created_at = record.get("created_at") if record else None
    age = time.time() - created_at if isinstance(created_at, int) else -1
    prompt = str(record.get("prompt") or "") if record else ""
    if not (
        path is not None
        and record
        and record.get("schema_version") == 1
        and record.get("authorization") == "vsdd-orchestrator-relay"
        and record.get("session_id") == safe_session_id(session_id)
        and (prompt_id is None or record.get("prompt_id") == prompt_id)
        and secrets.compare_digest(str(record.get("capability") or ""), capability)
        and record.get("cwd") == str(Path.cwd().resolve())
        and record.get("prompt_sha256")
        == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        and is_exact_vsdd_entry_prompt(prompt)
        and 0 <= age <= ORCHESTRATOR_RELAY_TTL_SECONDS
    ):
        deny("orchestrator relay authorization is invalid or expired")
    return path, record


def start_orchestrator_relay(arguments: list[str]) -> None:
    path, record = standalone_orchestrator_relay(arguments)
    if record.get("status") != "READY" or record.get("consumed_at") is not None:
        deny("orchestrator relay authorization is consumed or not ready")
    record["consumed_at"] = int(time.time())
    record["status"] = "RUNNING"
    record["started_at"] = int(time.time())
    try:
        write_private_json(path, record)
        subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--relay-supervise",
                "--session-id",
                str(record["session_id"]),
                "--capability",
                str(record["capability"]),
            ],
            cwd=record["cwd"],
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as error:
        record["status"] = "BLOCKED"
        record["error"] = f"cannot start protected orchestrator supervisor: {error}"
        write_private_json(path, record)
        deny(record["error"])
    print(
        json.dumps(
            {
                "status": "STARTED",
                "evidence": str(path),
                "wait_command": record["wait_command"],
            }
        )
    )


def supervise_orchestrator_relay(arguments: list[str]) -> None:
    path, record = standalone_orchestrator_relay(arguments, require_prompt_id=False)
    if record.get("status") != "RUNNING":
        deny("orchestrator relay supervisor is not running")
    prompt = str(record.get("prompt") or "")
    claude = os.environ.get("VSDD_CLAUDE_BIN") or shutil.which("claude")
    if not claude:
        record["status"] = "BLOCKED"
        record["error"] = "claude executable not found for orchestrator relay"
        write_private_json(path, record)
        return
    env = os.environ.copy()
    env[PROJECT_AGENTS_READY_ENV] = "1"
    command = [
        claude,
        "-p",
        prompt,
        "--agent",
        "ecc-vsdd:vsdd-orchestrator",
        "--effort",
        "high",
        "--permission-mode",
        "dontAsk",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=record["cwd"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        record["status"] = "BLOCKED"
        record["error"] = f"cannot start protected orchestrator child session: {error}"
    else:
        record["returncode"] = completed.returncode
        record["stdout"] = completed.stdout
        record["stderr"] = completed.stderr
        record["status"] = "COMPLETE" if completed.returncode == 0 else "BLOCKED"
    record["finished_at"] = int(time.time())
    write_private_json(path, record)


def wait_orchestrator_relay(arguments: list[str]) -> None:
    if len(arguments) != 8 or arguments[-2:] != ["--wait-seconds", "45"]:
        deny("invalid orchestrator relay wait arguments")
    path, record = standalone_orchestrator_relay(arguments[:-2])
    if record.get("status") not in {"RUNNING", "COMPLETE", "BLOCKED"}:
        deny("orchestrator relay wait has not started")
    deadline = time.monotonic() + 45
    while record.get("status") == "RUNNING" and time.monotonic() < deadline:
        time.sleep(0.25)
        updated = read_private_json(path)
        if updated is None:
            deny("orchestrator relay evidence disappeared")
        record = updated
    status = str(record.get("status") or "BLOCKED")
    if status == "RUNNING":
        print(json.dumps({"status": "RUNNING", "evidence": str(path)}))
        return
    stdout = str(record.get("stdout") or "")
    stderr = str(record.get("stderr") or record.get("error") or "")
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
    print(json.dumps({"status": status, "evidence": str(path)}))
    raise SystemExit(0 if status == "COMPLETE" else 1)


def normalized_agent(agent_type: object) -> str:
    value = str(agent_type or "")
    if value in EXPECTED_EFFORT:
        return value
    scoped = f"ecc-vsdd:{value}"
    return scoped if scoped in EXPECTED_EFFORT else value


def check_effort(
    payload: dict, agent_type: str, *, allow_unobservable: bool = False
) -> None:
    expected = EXPECTED_EFFORT[agent_type]
    if "effort" not in payload and allow_unobservable:
        # Claude Code 2.1.211 omits effort from subagent hook payloads even
        # though it resolves the agent frontmatter model and effort. In that
        # case the immutable frontmatter check is the strongest observable
        # guarantee; reject a disagreement whenever an effective value is
        # actually exposed.
        return
    actual = payload.get("effort") or {}
    level = actual.get("level") if isinstance(actual, dict) else None
    if level != expected:
        deny(f"{agent_type} requires effort {expected!r}; active effort is {level!r}")


def session_record_path(session_id: object) -> Path | None:
    safe_id = re.sub(r"[^a-zA-Z0-9-]", "", str(session_id or ""))
    if not safe_id:
        return None
    return guard_runtime_root() / "session-models" / f"{safe_id}.json"


def record_session_model(payload: dict) -> None:
    agent_type = normalized_agent(payload.get("agent_type"))
    if agent_type not in EXPECTED_MODEL:
        return
    raw_model = payload.get("model")
    if raw_model is None or not str(raw_model).strip():
        # Claude Code documents model as optional and current SessionStart
        # payloads may omit it. Agent frontmatter and launch-time override
        # checks remain authoritative when no effective model is observable.
        return
    path = session_record_path(payload.get("session_id"))
    if path is None:
        return
    model = str(raw_model).lower()
    write_private_json(
        path,
        {
            "agent_type": agent_type,
            "model": model,
            "created_at": int(time.time()),
        },
    )
    expected = EXPECTED_MODEL[agent_type]
    if not model or expected not in model:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": (
                            f"VSDD RUN BLOCKED: {agent_type} requires model {expected}; "
                            f"active model is {model}. Do not use tools."
                        ),
                    }
                }
            )
        )


def check_recorded_model(payload: dict, agent_type: str) -> None:
    path = session_record_path(payload.get("session_id"))
    if path is None:
        return
    record = read_private_json(path)
    if record is None:
        if not path.exists() and not path.is_symlink():
            return
        deny("cannot verify the private session model record")
    model = str(record.get("model") or "").lower()
    if not model:
        return
    expected = EXPECTED_MODEL[agent_type]
    if not model or expected not in model:
        deny(f"{agent_type} requires model {expected!r}; active model is {model!r}")


def agent_definition_path(agent_type: str) -> Path:
    plugin_root = installed_plugin_root()
    name = agent_type.split(":", 1)[-1]
    return plugin_root / "agents" / f"{name}.md"


def agent_frontmatter(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        deny(f"cannot read pinned agent definition {path}: {error}")
    if not lines or lines[0].strip() != "---":
        deny(f"pinned agent definition lacks frontmatter: {path}")
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return values
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    deny(f"pinned agent definition frontmatter is not closed: {path}")


def check_pinned_agent_definition(agent_type: str) -> None:
    values = agent_frontmatter(agent_definition_path(agent_type))
    expected_model = EXPECTED_MODEL[agent_type]
    expected_effort = EXPECTED_EFFORT[agent_type]
    if values.get("model", "").lower() != expected_model:
        deny(
            f"{agent_type} frontmatter must pin model {expected_model!r}; "
            f"got {values.get('model')!r}"
        )
    if agent_type == "ecc-vsdd:vsdd-implementation-driver":
        if "effort" in values:
            deny(
                "vsdd-implementation-driver must omit frontmatter effort; "
                "the launcher pins --effort ultracode"
            )
        return
    if values.get("effort", "").lower() != expected_effort:
        deny(
            f"{agent_type} frontmatter must pin effort {expected_effort!r}; "
            f"got {values.get('effort')!r}"
        )


def check_subagent_model_overrides(tool_input: dict) -> None:
    requested_model = str(tool_input.get("model") or "").strip()
    if requested_model:
        deny(
            "per-invocation model override is prohibited; use the pinned agent frontmatter"
        )
    global_model = os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL", "").strip().lower()
    if global_model and global_model != "inherit":
        deny(
            "CLAUDE_CODE_SUBAGENT_MODEL must be unset or 'inherit' for mixed pinned routing"
        )


def run_context_fields(prompt: object) -> dict[str, str]:
    match = re.search(
        r"(?ms)(?:^|\n)VSDD_RUN_CONTEXT\s*\n(.*?)^END_VSDD_RUN_CONTEXT\s*$",
        str(prompt or ""),
    )
    if not match:
        deny("PR worker launch requires a VSDD_RUN_CONTEXT envelope")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def check_pr_launch(payload: dict, tool_input: dict) -> None:
    """Require persisted PR consent and current review gates before agent launch."""
    fields = run_context_fields(tool_input.get("prompt"))
    slug = fields.get("slug", "")
    raw_worktree = fields.get("integration_worktree", "")
    raw_state = fields.get("run_state", "")
    if (
        fields.get("schema_version") != "1"
        or fields.get("execution_mode") != "unattended"
        or fields.get("operation") != "phase"
        or fields.get("phase") != "pr"
        or not SLUG_RE.fullmatch(slug)
    ):
        deny("PR worker launch context is invalid")
    worktree = Path(raw_worktree)
    if not worktree.is_absolute() or not worktree.is_dir():
        deny("PR worker launch requires an existing absolute integration worktree")
    worktree = worktree.resolve()
    expected_state = worktree / ".claude" / "specs" / slug / "run-state.json"
    state_path = Path(raw_state)
    if not state_path.is_absolute() or state_path.resolve() != expected_state:
        deny("PR worker launch run_state does not match its slug and worktree")

    run_pr_preflight(worktree, slug)
    consume_pr_consent(payload, worktree, slug)
    authorize_pr_session(payload, worktree, slug)


def run_pr_preflight(worktree: Path, slug: str) -> None:
    runtime = (installed_plugin_root() / "scripts" / "vsdd-runtime-state.py").resolve()
    try:
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
                "pr",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        deny(f"cannot run PR launch preflight: {error}")
    try:
        evidence = json.loads(result.stdout)
    except json.JSONDecodeError:
        evidence = {}
    if result.returncode or evidence != {"status": "READY", "phase": "pr"}:
        detail = (result.stderr or result.stdout or "runtime rejected PR launch").strip()
        deny(f"PR worker preflight failed: {detail[:500]}")


def authorize_pr_session(payload: dict, worktree: Path, slug: str) -> None:
    path = pr_authorization_record_path(payload.get("session_id"))
    cwd = normalized_cwd(payload)
    if path is None or cwd is None:
        deny("cannot persist PR worker launch authorization")
    prompt_id = str(payload.get("prompt_id") or "")
    launch_tool_use_id = str(payload.get("tool_use_id") or "")
    if not PROMPT_ID_RE.fullmatch(prompt_id) or not launch_tool_use_id:
        deny("cannot bind PR authorization to its prompt and launch tool")
    existing = read_private_json(path)
    capability = secrets.token_urlsafe(32)
    agent_id = None
    if existing is not None:
        same_launch = (
            existing.get("session_id") == safe_session_id(payload.get("session_id"))
            and existing.get("cwd") == cwd
            and existing.get("prompt_id") == prompt_id
            and existing.get("launch_tool_use_id") == launch_tool_use_id
            and existing.get("slug") == slug
            and existing.get("integration_worktree") == str(worktree)
        )
        if not same_launch:
            deny("conflicting PR worker launch authorization already exists")
        capability = str(existing.get("capability") or capability)
        agent_id = existing.get("agent_id")
    try:
        write_private_json(
            path,
            {
                "schema_version": 2,
                "authorization": "vsdd-pr",
                "session_id": safe_session_id(payload.get("session_id")),
                "cwd": cwd,
                "prompt_id": prompt_id,
                "launch_tool_use_id": launch_tool_use_id,
                "slug": slug,
                "integration_worktree": str(worktree),
                "capability": capability,
                "agent_id": agent_id,
                "created_at": int(time.time()),
            },
        )
    except OSError as error:
        deny(f"cannot persist PR worker launch authorization: {error}")


def bind_subagent(payload: dict) -> None:
    raw_agent_type = payload.get("agent_type")
    agent_type = normalized_agent(raw_agent_type)
    if agent_type not in WORKERS:
        return
    check_materialized_project_agent(payload, raw_agent_type, agent_type)
    plugin_root = installed_plugin_root()
    context = [
        "Use these injected literal paths. Do not search the filesystem for the "
        "plugin or depend on CLAUDE_PLUGIN_ROOT being present in Bash.",
        f"VSDD_PLUGIN_ROOT: {plugin_root}",
        f"VSDD_RUNTIME_STATE: {plugin_root / 'scripts' / 'vsdd-runtime-state.py'}",
        f"VSDD_WORKER_LAUNCHER: {plugin_root / 'scripts' / 'vsdd-launch-worker.py'}",
        f"VSDD_PR_ACTION_BROKER: {plugin_root / 'scripts' / 'vsdd-pr-action.py'}",
    ]
    if agent_type != "ecc-vsdd:vsdd-pr-worker":
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SubagentStart",
                        "additionalContext": "\n".join(context),
                    }
                }
            )
        )
        return
    path = pr_authorization_record_path(payload.get("session_id"))
    record = read_private_json(path) if path is not None else None
    agent_id = str(payload.get("agent_id") or "")
    if record is None or not agent_id:
        deny("PR worker start lacks a launch authorization")
    if not (
        record.get("schema_version") == 2
        and record.get("authorization") == "vsdd-pr"
        and record.get("session_id") == safe_session_id(payload.get("session_id"))
        and record.get("cwd") == normalized_cwd(payload)
        and record.get("prompt_id") == str(payload.get("prompt_id") or "")
        and record.get("agent_id") in {None, agent_id}
    ):
        deny("PR worker start does not match its launch authorization")
    capability = str(record.get("capability") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", capability):
        deny("PR worker launch authorization lacks a valid capability")
    record["agent_id"] = agent_id
    record["agent_bound_at"] = int(time.time())
    try:
        write_private_json(path, record)
    except OSError as error:
        deny(f"cannot bind the actual PR worker: {error}")
    context.extend(
        [
            "Use only the bundled VSDD PR action broker for push and PR creation.",
            f"VSDD_PR_ACTION_CAPABILITY: {capability}",
            f"VSDD_PR_ACTION_SESSION_ID: {record['session_id']}",
            f"VSDD_PR_ACTION_AGENT_ID: {agent_id}",
        ]
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SubagentStart",
                    "additionalContext": "\n".join(context),
                }
            }
        )
    )


def check_pr_worker_tool(payload: dict) -> dict:
    path = pr_authorization_record_path(payload.get("session_id"))
    record = read_private_json(path) if path is not None else None
    if record is None:
        deny("PR worker tool use lacks a session-bound launch authorization")
    created_at = record.get("created_at")
    age = time.time() - created_at if isinstance(created_at, int) else -1
    slug = str(record.get("slug") or "")
    if not (
        record.get("schema_version") == 2
        and record.get("authorization") == "vsdd-pr"
        and record.get("session_id") == safe_session_id(payload.get("session_id"))
        and record.get("cwd") == normalized_cwd(payload)
        and record.get("prompt_id") == str(payload.get("prompt_id") or "")
        and bool(record.get("agent_id"))
        and SLUG_RE.fullmatch(slug)
        and 0 <= age <= AUTHORIZATION_TTL_SECONDS
    ):
        deny("PR worker launch authorization is invalid or expired")
    if not re.fullmatch(
        r"[A-Za-z0-9_-]{32,128}", str(record.get("capability") or "")
    ):
        deny("PR worker launch authorization lacks a valid capability")
    worktree = Path(str(record.get("integration_worktree") or ""))
    if not worktree.is_absolute() or not worktree.is_dir():
        deny("PR worker launch authorization has no valid integration worktree")
    run_pr_preflight(worktree.resolve(), slug)
    return record


def shell_segments(command: object) -> list[list[str]]:
    raw = str(command or "")
    try:
        lexer = shlex.shlex(raw, posix=True, punctuation_chars=";&|(){}<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return [[raw]] if raw else []
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token and all(character in ";&|(){}" for character in token):
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def executable_tokens(segment: list[str]) -> list[str]:
    tokens = list(segment)
    while tokens:
        before = list(tokens)
        tokens = strip_leading_shell_syntax(tokens)
        if tokens and Path(tokens[0]).name in {"command", "exec", "nohup", "sudo"}:
            tokens.pop(0)
            while tokens and tokens[0].startswith("-"):
                tokens.pop(0)
        if tokens and Path(tokens[0]).name == "env":
            tokens.pop(0)
            while tokens and (
                tokens[0].startswith("-")
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0])
            ):
                tokens.pop(0)
        if tokens == before:
            break
    return tokens


def strip_leading_shell_syntax(segment: list[str]) -> list[str]:
    """Remove assignments and redirections that may precede a simple command."""
    tokens = list(segment)
    while tokens:
        before = list(tokens)
        while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
            tokens.pop(0)
        while tokens:
            operator_index = 1 if (
                len(tokens) > 1
                and tokens[0].isdigit()
                and re.fullmatch(r"[<>|&]+", tokens[1])
                and any(character in "<>" for character in tokens[1])
            ) else 0
            operator = tokens[operator_index]
            if not (
                re.fullmatch(r"[<>|&]+", operator)
                and any(character in "<>" for character in operator)
            ):
                break
            del tokens[: operator_index + 1]
            if tokens:
                tokens.pop(0)
        if tokens == before:
            break
    return tokens


def starts_with_command_wrapper(segment: list[str]) -> bool:
    tokens = strip_leading_shell_syntax(segment)
    return bool(tokens and Path(tokens[0]).name in SHELL_COMMAND_WRAPPERS)


def git_subcommand(tokens: list[str]) -> str:
    index = 1
    options_with_values = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
    while index < len(tokens):
        token = tokens[index]
        if token in options_with_values:
            index += 2
            continue
        if token.startswith(("--git-dir=", "--work-tree=", "--namespace=")):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return ""


def interpreter_payload(tokens: list[str], executable: str) -> str | None:
    """Return inline shell/code supplied to a known interpreter, if any."""
    flags = {"-c"}
    if executable in {"node", "nodejs", "perl", "ruby"}:
        flags.add("-e")
        flags.add("--eval")
    for index, token in enumerate(tokens[1:], start=1):
        inline = token in flags
        if executable in SHELL_INTERPRETERS and re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", token):
            inline = True
        if inline:
            return tokens[index + 1] if index + 1 < len(tokens) else ""
    return None


def suspicious_inline_outbound_code(source: str) -> bool:
    lowered = source.lower()
    executable_marker = re.search(
        r"(?:\bgit\b|\bgh\b|\bhub\b|api\.github\.com|github\.com)", lowered
    )
    mutation_marker = re.search(
        r"(?:\bpush\b|send[-_ ]?pack|\bpr\b.{0,20}"
        r"(?:create|edit|merge|ready|close|reopen)|\bpulls?\b|"
        r"\b(?:post|put|patch|delete)\b)",
        lowered,
    )
    return executable_marker is not None and mutation_marker is not None


def github_http_mutation(tokens: list[str], executable: str) -> bool:
    lowered = [token.lower() for token in tokens[1:]]
    joined = " ".join(lowered)
    if not (
        "api.github.com" in joined
        or re.search(r"github\.com/[^/\s]+/[^/\s]+/(?:pulls?|issues?)", joined)
    ):
        return False
    mutation_flags = {
        "-d",
        "-f",
        "-t",
        "--data",
        "--data-ascii",
        "--data-binary",
        "--data-raw",
        "--form",
        "--form-string",
        "--json",
        "--post-data",
        "--post-file",
        "--body-data",
        "--body-file",
        "--upload-file",
    }
    for index, token in enumerate(lowered):
        if token in mutation_flags or any(
            token.startswith(prefix)
            for prefix in (
                "--data=",
                "--form=",
                "--json=",
                "--post-data=",
                "--post-file=",
                "--body-data=",
                "--body-file=",
                "--upload-file=",
            )
        ):
            return True
        method = None
        if token in {"-x", "--request", "--method"} and index + 1 < len(lowered):
            method = lowered[index + 1]
        elif token.startswith("-x") and len(token) > 2:
            method = token[2:]
        elif token.startswith(("--request=", "--method=")):
            method = token.split("=", 1)[1]
        if method and method.upper() not in {"GET", "HEAD"}:
            return True
    return False


def external_mutation_reason(command: object, *, depth: int = 0) -> str | None:
    raw = str(command or "")
    if depth > 4:
        return "nested command depth is not safely classifiable"
    if ("\n" in raw or "\r" in raw) and suspicious_inline_outbound_code(raw):
        return "multiline outbound-capable command is not safely classifiable"
    if re.search(r"\|\s*(?:ba|da|k|z)?sh(?:\s|$)", raw) and suspicious_inline_outbound_code(
        raw
    ):
        return "outbound-capable command piped to a shell"
    if ("$" in raw or "`" in raw) and re.search(
        r"(?:\bgit\b|\bgh\b|\bhub\b|\bcurl\b|\bwget\b|"
        r"api\.github\.com|\bpush\b|send-pack|\bpulls?\b)",
        raw,
        flags=re.IGNORECASE,
    ):
        return "unresolved shell expansion in an outbound-capable command"
    for segment in shell_segments(command):
        if starts_with_command_wrapper(segment) and suspicious_inline_outbound_code(
            " ".join(segment)
        ):
            return "outbound mutation hidden behind a shell command wrapper"
        tokens = executable_tokens(segment)
        if not tokens:
            continue
        executable = Path(tokens[0]).name
        if executable in {"git-push", "git-send-pack"}:
            return "Git outbound helper mutation"
        if executable in {"busybox", "find", "parallel", "xargs"} and (
            suspicious_inline_outbound_code(" ".join(tokens))
        ):
            return f"outbound mutation hidden behind {executable}"
        payload = interpreter_payload(tokens, executable)
        if executable in SHELL_INTERPRETERS and payload is not None:
            nested = external_mutation_reason(payload, depth=depth + 1)
            if nested:
                return f"nested shell command: {nested}"
        is_code_interpreter = executable in CODE_INTERPRETERS or bool(
            re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable)
        )
        if is_code_interpreter and payload is not None:
            if suspicious_inline_outbound_code(payload):
                return "inline interpreter can perform an outbound mutation"
        if executable == "git":
            subcommand = git_subcommand(tokens)
            if subcommand in {"push", "send-pack"}:
                return "git outbound mutation"
            if subcommand not in SAFE_GIT_SUBCOMMANDS:
                return f"unclassified Git subcommand {subcommand!r}"
        if executable == "gh" and len(tokens) >= 2:
            if tokens[1] == "api":
                return "GitHub API mutation-capable command"
            command_key = tuple(tokens[1:3])
            if command_key not in SAFE_GH_COMMANDS and (command_key[:1] not in SAFE_GH_COMMANDS):
                return f"unclassified GitHub CLI command {command_key!r}"
        if executable == "hub":
            return "legacy GitHub CLI command is mutation-capable"
        if executable in {"curl", "wget"} and github_http_mutation(tokens, executable):
            return "GitHub HTTP mutation"
    return None


def pr_broker_invocation(command: object) -> dict[str, str] | None:
    raw = str(command or "")
    if "vsdd-pr-action.py" not in raw:
        return None
    try:
        lexer = shlex.shlex(raw, posix=True, punctuation_chars=";&|(){}<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        argv = list(lexer)
    except ValueError as error:
        deny(f"cannot parse VSDD PR action broker invocation: {error}")
    if any(token and all(char in ";&|(){}" for char in token) for token in argv):
        deny("VSDD PR action broker invocation cannot use shell control operators")
    plugin_root = installed_plugin_root()
    broker = (plugin_root / "scripts" / "vsdd-pr-action.py").resolve()
    placeholder = "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-pr-action.py"
    if (
        len(argv) < 4
        or Path(argv[0]).name not in {"python", "python3"}
        or (argv[1] != placeholder and Path(argv[1]).resolve() != broker)
        or argv[2] != "publish"
    ):
        deny("only the bundled VSDD PR action broker publish command is allowed")
    if any(("$" in token and token != placeholder) or "`" in token for token in argv):
        deny("shell expansion is prohibited in the PR action broker invocation")
    value_flags = {
        "--worktree",
        "--slug",
        "--session-id",
        "--agent-id",
        "--capability",
        "--title",
        "--body-file",
        "--remote",
    }
    flag_values: dict[str, str] = {}
    index = 3
    while index < len(argv):
        flag = argv[index]
        if flag == "--draft":
            if flag in flag_values:
                deny("duplicate PR action broker --draft flag")
            flag_values[flag] = "true"
            index += 1
            continue
        if flag not in value_flags or flag in flag_values:
            deny(f"invalid or duplicate PR action broker argument {flag!r}")
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            deny(f"missing value for PR action broker argument {flag!r}")
        flag_values[flag] = argv[index + 1]
        index += 2
    required = value_flags - {"--remote"}
    if not required.issubset(flag_values):
        deny(
            "PR action broker invocation is missing: "
            + ", ".join(sorted(required - flag_values.keys()))
        )
    return flag_values


def check_pr_broker_context(payload: dict, fields: dict[str, str], record: dict) -> None:
    expected = {
        "--session-id": safe_session_id(payload.get("session_id")),
        "--agent-id": str(record.get("agent_id") or ""),
        "--capability": str(record.get("capability") or ""),
        "--slug": str(record.get("slug") or ""),
        "--worktree": str(record.get("integration_worktree") or ""),
    }
    for flag, expected_value in expected.items():
        actual = fields.get(flag, "")
        if flag == "--worktree":
            try:
                matches = Path(actual).resolve() == Path(expected_value).resolve()
            except OSError:
                matches = False
        else:
            matches = secrets.compare_digest(actual, expected_value)
        if not matches:
            deny(f"PR action broker invocation does not match authorization: {flag}")


def pr_boundary_operation(command: object, *, depth: int = 0) -> str | None:
    if depth > 4:
        return None
    plugin_root = installed_plugin_root()
    runtime = (plugin_root / "scripts" / "vsdd-runtime-state.py").resolve()
    placeholder = "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-runtime-state.py"
    for segment in shell_segments(command):
        tokens = executable_tokens(segment)
        if tokens:
            executable = Path(tokens[0]).name
            payload = interpreter_payload(tokens, executable)
            if executable in SHELL_INTERPRETERS and payload is not None:
                nested = pr_boundary_operation(payload, depth=depth + 1)
                if nested is not None:
                    return nested
            if payload is not None and "vsdd-runtime-state.py" in payload:
                if re.search(r"\bbootstrap\b", payload) and re.search(
                    r"--until(?:=|\s+)pr\b", payload
                ):
                    return "start"
                if re.search(r"\bextend\b", payload) and re.search(
                    r"--until(?:=|\s+)pr\b", payload
                ):
                    return "resume"
        if len(tokens) < 4 or not re.fullmatch(
            r"python(?:\d+(?:\.\d+)*)?", Path(tokens[0]).name
        ):
            continue
        if tokens[1] != placeholder and Path(tokens[1]).resolve() != runtime:
            continue
        runtime_command = tokens[2]
        if runtime_command not in {"bootstrap", "extend"}:
            continue
        until_values: list[str] = []
        index = 3
        while index < len(tokens):
            if tokens[index] == "--until" and index + 1 < len(tokens):
                until_values.append(tokens[index + 1])
                index += 2
                continue
            if tokens[index].startswith("--until="):
                until_values.append(tokens[index].split("=", 1)[1])
            index += 1
        if until_values == ["pr"]:
            return "start" if runtime_command == "bootstrap" else "resume"
    return None


def check_launcher(command: object) -> None:
    raw_command = str(command or "")
    if any(character in raw_command for character in "\r\n;|&<>{}*?[]~"):
        deny("shell control operators are prohibited in the VSDD launcher command")
    if "$(" in raw_command or "`" in raw_command:
        deny("shell command substitution is prohibited in the VSDD launcher command")

    try:
        argv = shlex.split(raw_command)
    except ValueError as error:
        deny(f"cannot parse Bash command: {error}")

    plugin_root = installed_plugin_root()
    launcher = (plugin_root / "scripts" / "vsdd-launch-worker.py").resolve()
    placeholder_launcher = "${CLAUDE_PLUGIN_ROOT}/scripts/vsdd-launch-worker.py"
    if len(argv) < 2 or Path(argv[0]).name not in {"python", "python3"}:
        deny("Fable may use Bash only to invoke the bundled VSDD worker launcher")
    if argv[1] != placeholder_launcher and Path(argv[1]).resolve() != launcher:
        deny("Fable may use Bash only to invoke the bundled VSDD worker launcher")
    if any(
        ("$" in token and token != placeholder_launcher) or "`" in token
        for token in argv
    ):
        deny("shell expansion is prohibited in VSDD launcher arguments")
    if len(argv) < 7 or argv[2] not in {
        "plan",
        "revise-plan",
        "implement",
        "remediate",
        "wait",
    }:
        deny("invalid VSDD launcher stage")

    stage = argv[2]
    allowed_flags = {
        "--slug",
        "--worktree",
        "--session-id",
        "--dry-run",
        "--detach",
        "--evidence",
        "--wait-seconds",
    }
    index = 3
    seen: set[str] = set()
    while index < len(argv):
        flag = argv[index]
        if flag not in allowed_flags or flag in seen:
            deny(f"invalid or duplicate VSDD launcher argument {flag!r}")
        seen.add(flag)
        if flag in {"--dry-run", "--detach"}:
            index += 1
            continue
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            deny(f"missing value for VSDD launcher argument {flag!r}")
        index += 2
    if not {"--slug", "--worktree"}.issubset(seen):
        deny("VSDD launcher requires --slug and --worktree")
    if stage == "wait":
        if "--evidence" not in seen:
            deny("VSDD launcher wait requires --evidence")
        prohibited = seen.intersection({"--session-id", "--dry-run", "--detach"})
        if prohibited:
            deny(f"invalid VSDD launcher wait arguments {sorted(prohibited)!r}")
    elif seen.intersection({"--evidence", "--wait-seconds"}):
        deny("--evidence and --wait-seconds are valid only for VSDD launcher wait")


def main() -> None:
    global ACTIVE_HOOK_EVENT, ACTIVE_PROJECT_AGENT
    arguments = sys.argv[1:]
    if arguments[:1] == ["--relay-start"]:
        start_orchestrator_relay(arguments[1:])
        return
    if arguments[:1] == ["--relay-wait"]:
        wait_orchestrator_relay(arguments[1:])
        return
    if arguments[:1] == ["--relay-supervise"]:
        supervise_orchestrator_relay(arguments[1:])
        return
    strict = arguments == ["--strict"]
    session_start = arguments == ["--session-start"]
    session_end = arguments == ["--session-end"]
    user_prompt_submit = arguments == ["--user-prompt-submit"]
    subagent_start = arguments == ["--subagent-start"]
    project_agent = arguments == ["--project-agent"]
    if arguments and not any(
        (
            strict,
            session_start,
            session_end,
            user_prompt_submit,
            subagent_start,
            project_agent,
        )
    ):
        deny("unsupported guard argument")

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as error:
        deny(f"invalid hook input: {error}")
    ACTIVE_HOOK_EVENT = str(payload.get("hook_event_name") or "")
    ACTIVE_PROJECT_AGENT = project_agent

    if session_start:
        sweep_expired_session_state()
        record_session_model(payload)
        return
    if session_end:
        clear_session_state(payload)
        return
    if user_prompt_submit:
        handle_user_prompt(payload)
        return
    if subagent_start:
        bind_subagent(payload)
        return

    raw_agent_type = payload.get("agent_type")
    agent_type = normalized_agent(raw_agent_type)
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}

    if agent_type in WORKERS:
        if project_agent:
            check_materialized_project_agent(payload, raw_agent_type, agent_type)
        check_pinned_agent_definition(agent_type)
        # Subagent hooks share the parent session_id and do not expose a model.
        # Applying the parent's SessionStart model would reject every correctly
        # pinned mixed-model worker. Separate main-agent sessions still have a
        # model-bearing SessionStart record and remain verifiable here.
        if agent_type == "ecc-vsdd:vsdd-implementation-driver":
            check_recorded_model(payload, agent_type)
        check_effort(
            payload,
            agent_type,
            allow_unobservable=agent_type
            != "ecc-vsdd:vsdd-implementation-driver",
        )
        if tool_name == "Bash":
            boundary_operation = pr_boundary_operation(tool_input.get("command"))
            if boundary_operation is not None:
                expected_agent = (
                    "ecc-vsdd:vsdd-init-worker"
                    if boundary_operation == "start"
                    else "ecc-vsdd:vsdd-status-worker"
                )
                if agent_type != expected_agent:
                    deny(
                        f"only {expected_agent} may change the PR execution boundary"
                    )
                current_pr_consent(
                    payload,
                    expected_operation=boundary_operation,
                )
            broker_fields = pr_broker_invocation(tool_input.get("command"))
            if broker_fields is not None and agent_type != "ecc-vsdd:vsdd-pr-worker":
                deny("only the actual PR worker may invoke the PR action broker")
            mutation = external_mutation_reason(tool_input.get("command"))
            if mutation:
                deny(
                    "direct external Git/GitHub mutation is prohibited "
                    f"({mutation}); use the bundled VSDD PR action broker"
                )
            if agent_type == "ecc-vsdd:vsdd-pr-worker":
                record = check_pr_worker_tool(payload)
                if broker_fields is not None:
                    check_pr_broker_context(payload, broker_fields, record)
        allow_validated_tool(strict or strict_session_authorized(payload))
        return

    if agent_type not in EXPECTED_EFFORT and not strict:
        if project_agent:
            deny("project agent guard may run only inside a pinned VSDD worker")
        return

    if agent_type != "ecc-vsdd:vsdd-orchestrator":
        deny(
            "start Claude Code with --agent ecc-vsdd:vsdd-orchestrator; "
            "inline execution and inherited models are prohibited"
        )

    check_pinned_agent_definition(agent_type)
    check_recorded_model(payload, agent_type)
    check_effort(payload, agent_type)

    pending_relay = current_orchestrator_relay(payload)
    if pending_relay is not None and os.environ.get(PROJECT_AGENTS_READY_ENV) != "1":
        if tool_name == "Skill":
            requested_skill = str(
                tool_input.get("skill")
                or tool_input.get("name")
                or tool_input.get("command")
                or ""
            )
            if requested_skill not in ORCHESTRATOR_SKILLS:
                deny(f"Fable cannot invoke non-orchestration skill {requested_skill!r}")
            allow_validated_tool(strict)
            return
        if tool_name != "Bash":
            deny("Fable must start the protected orchestrator relay before phase work")
        check_orchestrator_relay(payload, tool_input.get("command"))
        if strict:
            authorize_strict_session(payload)
        allow_validated_tool(True)
        return

    if tool_name == "Bash":
        if tool_input.get("run_in_background") not in (None, False):
            deny("the VSDD worker launcher must run in the foreground until completion")
        check_launcher(tool_input.get("command"))
        if strict:
            authorize_strict_session(payload)
        allow_validated_tool(strict)
        return

    if tool_name not in ORCHESTRATOR_TOOLS:
        deny(f"Fable control plane cannot use {tool_name!r}")

    if tool_name == "Skill":
        requested_skill = str(
            tool_input.get("skill")
            or tool_input.get("name")
            or tool_input.get("command")
            or ""
        )
        if requested_skill not in ORCHESTRATOR_SKILLS:
            deny(f"Fable cannot invoke non-orchestration skill {requested_skill!r}")

    if tool_name in {"Agent", "Task"}:
        check_subagent_model_overrides(tool_input)
        raw_requested = (
            tool_input.get("subagent_type")
            or tool_input.get("agent_type")
            or tool_input.get("name")
        )
        requested = normalized_agent(raw_requested)
        if requested not in ORCHESTRATOR_AGENTS:
            deny(f"Fable cannot launch unpinned agent {requested!r}")
        check_materialized_project_agent(payload, raw_requested, requested)
        check_pinned_agent_definition(requested)
        if requested == "ecc-vsdd:vsdd-pr-worker":
            check_pr_launch(payload, tool_input)

    if strict:
        authorize_strict_session(payload)
    allow_validated_tool(strict)


if __name__ == "__main__":
    main()
