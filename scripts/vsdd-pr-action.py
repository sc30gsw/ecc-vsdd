#!/usr/bin/env python3
"""Perform the only supported VSDD push/PR mutation after deterministic gates."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = PLUGIN_ROOT / "scripts" / "vsdd-runtime-state.py"
GUARD = PLUGIN_ROOT / "scripts" / "vsdd-model-guard.py"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PR_URL_RE = re.compile(r"https://github\.com/[^/]+/[^/]+/pull/(\d+)")
AUTHORIZATION_TTL_SECONDS = 7 * 24 * 60 * 60


class ActionBlocked(RuntimeError):
    """Raised when the broker cannot prove an external action is authorized."""


def load_guard_module():
    spec = importlib.util.spec_from_file_location("vsdd_model_guard_for_pr", GUARD)
    if spec is None or spec.loader is None:
        raise ActionBlocked("cannot load the bundled authorization guard")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(
    argv: list[str], *, cwd: Path | None = None, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ActionBlocked(f"cannot execute {argv[0]!r}: {error}") from error


def require_success(
    argv: list[str], *, cwd: Path | None = None, timeout: int = 60
) -> str:
    result = command(argv, cwd=cwd, timeout=timeout)
    if result.returncode:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise ActionBlocked(f"{argv[0]} failed: {detail[:500]}")
    return result.stdout.strip()


def read_json_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        raise ActionBlocked(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise ActionBlocked(f"{label} must be a JSON object: {path}")
    return value


def validate_authorization(args: argparse.Namespace, worktree: Path) -> dict:
    guard = load_guard_module()
    safe_session = guard.safe_session_id(args.session_id)
    if safe_session != args.session_id:
        raise ActionBlocked("session ID is invalid")
    path = guard.pr_authorization_record_path(args.session_id)
    record = guard.read_private_json(path) if path is not None else None
    if record is None:
        raise ActionBlocked("PR action authorization is missing or unsafe")
    created_at = record.get("created_at")
    age = time.time() - created_at if isinstance(created_at, int) else -1
    if not (
        record.get("schema_version") == 2
        and record.get("authorization") == "vsdd-pr"
        and record.get("session_id") == args.session_id
        and record.get("cwd") == str(Path.cwd().resolve())
        and record.get("slug") == args.slug
        and record.get("integration_worktree") == str(worktree)
        and record.get("agent_id") == args.agent_id
        and 0 <= age <= AUTHORIZATION_TTL_SECONDS
    ):
        raise ActionBlocked("PR action authorization does not match this worker")
    recorded_capability = str(record.get("capability") or "")
    if not secrets.compare_digest(recorded_capability, args.capability):
        raise ActionBlocked("PR action capability does not match")
    return record


def runtime_preflight(worktree: Path, slug: str) -> None:
    result = command(
        [
            sys.executable,
            str(RUNTIME),
            "preflight",
            "--worktree",
            str(worktree),
            "--slug",
            slug,
            "--phase",
            "pr",
        ],
        timeout=30,
    )
    try:
        evidence = json.loads(result.stdout)
    except json.JSONDecodeError:
        evidence = None
    if result.returncode or evidence != {"status": "READY", "phase": "pr"}:
        detail = (result.stderr or result.stdout or "runtime rejected PR action").strip()
        raise ActionBlocked(f"PR runtime preflight failed: {detail[:500]}")


def validate_state(worktree: Path, slug: str) -> tuple[Path, dict, str, str, str]:
    spec = worktree / ".claude" / "specs" / slug
    state = read_json_object(spec / "run-state.json", "run-state")
    base_branch = str(state.get("base_branch") or "")
    base_sha = str(state.get("base_sha") or "")
    head_branch = str(state.get("integration_branch") or "")
    if not BRANCH_RE.fullmatch(base_branch) or not SHA_RE.fullmatch(base_sha):
        raise ActionBlocked("run-state base branch or SHA is invalid")
    if head_branch != f"vsdd/{slug}" or not BRANCH_RE.fullmatch(head_branch):
        raise ActionBlocked("run-state integration branch is invalid")
    if Path(str(state.get("integration_worktree") or "")).resolve() != worktree:
        raise ActionBlocked("run-state integration worktree does not match")
    current_branch = require_success(
        ["git", "-C", str(worktree), "branch", "--show-current"]
    )
    head_sha = require_success(["git", "-C", str(worktree), "rev-parse", "HEAD"])
    if current_branch != head_branch or not SHA_RE.fullmatch(head_sha):
        raise ActionBlocked("current integration branch or HEAD does not match run-state")
    return spec, state, base_branch, base_sha, head_sha


def validate_body_file(path: Path, spec: Path) -> Path:
    if not path.is_absolute():
        raise ActionBlocked("PR body file must be absolute")
    resolved = path.resolve()
    try:
        resolved.relative_to(spec.resolve())
    except ValueError as error:
        raise ActionBlocked("PR body file must be inside the current spec") from error
    if path.is_symlink() or not resolved.is_file():
        raise ActionBlocked("PR body file must be a regular non-symlink file")
    return resolved


def remote_ref_sha(worktree: Path, remote: str, branch: str) -> str:
    output = require_success(
        [
            "git",
            "-C",
            str(worktree),
            "ls-remote",
            "--exit-code",
            remote,
            f"refs/heads/{branch}",
        ]
    )
    fields = output.split()
    if len(fields) < 2 or fields[1] != f"refs/heads/{branch}":
        raise ActionBlocked(f"remote branch {branch!r} did not resolve uniquely")
    return fields[0]


def gh_pr_view(worktree: Path, head_branch: str) -> dict | None:
    result = command(
        [
            "gh",
            "pr",
            "view",
            head_branch,
            "--json",
            "number,url,baseRefName,baseRefOid,headRefName,headRefOid,isDraft",
        ],
        cwd=worktree,
    )
    if result.returncode:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ActionBlocked("gh pr view returned invalid JSON") from error
    if not isinstance(value, dict):
        raise ActionBlocked("gh pr view did not return a JSON object")
    return value


def validate_pr(
    value: dict,
    *,
    base_branch: str,
    base_sha: str,
    head_branch: str,
    head_sha: str,
    draft: bool,
) -> dict:
    url = str(value.get("url") or "")
    number = value.get("number")
    match = PR_URL_RE.fullmatch(url)
    if (
        not match
        or not isinstance(number, int)
        or number < 1
        or int(match.group(1)) != number
    ):
        raise ActionBlocked("GitHub PR URL and number are invalid")
    expected = {
        "baseRefName": base_branch,
        "baseRefOid": base_sha,
        "headRefName": head_branch,
        "headRefOid": head_sha,
        "isDraft": draft,
    }
    mismatches = [key for key, expected_value in expected.items() if value.get(key) != expected_value]
    if mismatches:
        raise ActionBlocked(
            "GitHub PR identity does not match current evidence: "
            + ", ".join(mismatches)
        )
    return {"url": url, "number": number}


def write_evidence(path: Path, evidence: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            json.dump(evidence, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def publish(args: argparse.Namespace) -> dict:
    if not SLUG_RE.fullmatch(args.slug):
        raise ActionBlocked("slug must be lowercase kebab-case")
    if not args.title.strip() or "\n" in args.title or len(args.title) > 256:
        raise ActionBlocked("PR title must be one non-empty line of at most 256 chars")
    if not BRANCH_RE.fullmatch(args.remote):
        raise ActionBlocked("remote name is invalid")
    worktree = Path(args.worktree)
    if not worktree.is_absolute() or not worktree.is_dir():
        raise ActionBlocked("integration worktree must be an existing absolute directory")
    worktree = worktree.resolve()
    validate_authorization(args, worktree)
    runtime_preflight(worktree, args.slug)
    spec, state, base_branch, base_sha, head_sha = validate_state(worktree, args.slug)
    body_file = validate_body_file(Path(args.body_file), spec)
    remote_base = remote_ref_sha(worktree, args.remote, base_branch)
    if remote_base != base_sha:
        raise ActionBlocked(
            f"remote base {base_branch!r} changed: expected {base_sha}, got {remote_base}"
        )
    head_branch = str(state["integration_branch"])
    require_success(
        [
            "git",
            "-C",
            str(worktree),
            "push",
            "--set-upstream",
            args.remote,
            f"refs/heads/{head_branch}:refs/heads/{head_branch}",
        ],
        timeout=120,
    )
    if remote_ref_sha(worktree, args.remote, head_branch) != head_sha:
        raise ActionBlocked("pushed integration branch does not target the current HEAD")

    runtime_preflight(worktree, args.slug)
    pr = gh_pr_view(worktree, head_branch)
    status = "EXISTING"
    if pr is None:
        create = [
            "gh",
            "pr",
            "create",
            "--base",
            base_branch,
            "--head",
            head_branch,
            "--title",
            args.title,
            "--body-file",
            str(body_file),
        ]
        if args.draft:
            create.append("--draft")
        require_success(create, cwd=worktree, timeout=120)
        pr = gh_pr_view(worktree, head_branch)
        status = "CREATED"
    if pr is None:
        raise ActionBlocked("GitHub PR could not be read after creation")
    identity = validate_pr(
        pr,
        base_branch=base_branch,
        base_sha=base_sha,
        head_branch=head_branch,
        head_sha=head_sha,
        draft=args.draft,
    )
    evidence = {
        "url": identity["url"],
        "number": identity["number"],
        "draft": args.draft,
        "base_branch": base_branch,
        "base_sha": base_sha,
        "head_branch": head_branch,
        "head_sha": head_sha,
        "target_commit": head_sha,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_evidence(spec / "pr-result.json", evidence)
    return {"status": status, **evidence}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    child = subparsers.add_parser("publish")
    child.add_argument("--worktree", required=True)
    child.add_argument("--slug", required=True)
    child.add_argument("--session-id", required=True)
    child.add_argument("--agent-id", required=True)
    child.add_argument("--capability", required=True)
    child.add_argument("--title", required=True)
    child.add_argument("--body-file", required=True)
    child.add_argument("--remote", default="origin")
    child.add_argument("--draft", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = publish(args)
    except ActionBlocked as error:
        print(f"VSDD PR action broker: {error}", file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
