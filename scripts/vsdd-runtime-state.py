#!/usr/bin/env python3
"""Deterministic state and transition guards for unattended ecc-vsdd runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


PROJECT_AGENT_MARKER = "<!-- ecc-vsdd-generated-agent-proxy:v1 -->"
PROJECT_WORKER_NAMES = {
    "vsdd-code-reviewer.md",
    "vsdd-design-worker.md",
    "vsdd-implementation-workflow-reviewer.md",
    "vsdd-init-worker.md",
    "vsdd-plan-reviewer.md",
    "vsdd-pr-worker.md",
    "vsdd-remediation-worker.md",
    "vsdd-requirements-reviewer.md",
    "vsdd-requirements-worker.md",
    "vsdd-security-reviewer.md",
    "vsdd-status-worker.md",
    "vsdd-steering-worker.md",
    "vsdd-tasks-worker.md",
}


PHASE_ORDER = (
    "steering",
    "init",
    "requirements",
    "requirements-review",
    "design",
    "tasks",
    "plan-review",
    "implementation-plan",
    "implementation-plan-review",
    "implementation",
    "code-review",
    "security-review",
    "remediation",
    "pr",
)
PHASE_INDEX = {phase: index for index, phase in enumerate(PHASE_ORDER)}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TASK_RE = re.compile(r"TASK-\d{3}")
MISSING_HASH = "MISSING"
REVIEW_PHASES = {
    "requirements-review": ("requirement-review.md", "requirements", "N/A"),
    "plan-review": ("plan-review.md", "plan", "N/A"),
    "implementation-plan-review": (
        "implementation-workflow-review.md",
        "implementation-workflow",
        "N/A",
    ),
    "code-review": ("code-review.md", "code", "HEAD"),
    "security-review": ("security-review.md", "security", "HEAD"),
}
REVIEW_ATTEMPT_SCOPES = {
    "requirements-review": "requirements-review",
    "plan-review": "plan-review",
    "implementation-plan-review": "implementation-plan-review",
    "code-review": "post-implementation-review",
    "security-review": "post-implementation-review",
}
ATTEMPT_LIMIT = 3
ATTEMPT_SCOPES = tuple(
    sorted(set(REVIEW_ATTEMPT_SCOPES.values()) | {"implementation-task"})
)
PHASE_PREREQUISITES = {
    "steering": (),
    "init": ("steering",),
    "requirements": ("init",),
    "requirements-review": ("requirements",),
    "design": ("requirements-review",),
    "tasks": ("design",),
    "plan-review": ("tasks",),
    "implementation-plan": ("plan-review",),
    "implementation-plan-review": ("implementation-plan",),
    "implementation": ("implementation-plan-review",),
    "code-review": ("implementation",),
    "security-review": ("implementation",),
    "remediation": ("implementation",),
    "pr": (
        "requirements-review",
        "plan-review",
        "implementation-plan-review",
        "implementation",
        "code-review",
        "security-review",
    ),
}


class RuntimeBlocked(RuntimeError):
    """Raised when a deterministic VSDD gate cannot safely proceed."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeBlocked(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.rstrip("\r\n") if result.returncode == 0 else ""


def validate_repo(repo: Path) -> Path:
    root = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    if root != repo.resolve():
        raise RuntimeBlocked(f"path is not the Git top-level: {repo}")
    return root


def resolve_commit(repo: Path, ref: str) -> str:
    sha = git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeBlocked(f"base ref does not resolve to a commit: {ref}")
    return sha


def branch_from_ref(ref: str) -> str:
    for prefix in ("refs/remotes/origin/", "refs/heads/", "origin/"):
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    return ref


def detect_base(repo: Path, explicit: str | None) -> dict[str, str]:
    """Resolve the actual base or block rather than guessing main."""
    repo = validate_repo(repo.resolve())
    if explicit:
        base_ref = explicit
    else:
        origin_head = git(
            repo,
            "symbolic-ref",
            "--quiet",
            "--short",
            "refs/remotes/origin/HEAD",
            check=False,
        )
        if origin_head:
            base_ref = origin_head
        else:
            refs = git(
                repo,
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/remotes/origin",
                "refs/heads",
            ).splitlines()
            refs = [ref for ref in refs if ref and ref != "origin/HEAD"]
            conventional = {"main", "master", "develop", "trunk"}
            by_branch: dict[str, list[str]] = {}
            for ref in refs:
                branch = branch_from_ref(ref)
                if branch in conventional:
                    by_branch.setdefault(branch, []).append(ref)
            if len(by_branch) == 1:
                candidates = next(iter(by_branch.values()))
                base_ref = next(
                    (ref for ref in candidates if ref.startswith("origin/")),
                    candidates[0],
                )
            elif not by_branch:
                local_refs = [ref for ref in refs if not ref.startswith("origin/")]
                if len(local_refs) == 1:
                    base_ref = local_refs[0]
                else:
                    raise RuntimeBlocked(
                        "repository default branch is not discoverable; pass --base explicitly"
                    )
            else:
                names = ", ".join(sorted(by_branch))
                raise RuntimeBlocked(
                    f"repository base is ambiguous ({names}); pass --base explicitly"
                )

    return {
        "base_ref": base_ref,
        "base_branch": branch_from_ref(base_ref),
        "base_sha": resolve_commit(repo, base_ref),
    }


def is_generated_project_agent_status(repo: Path, status_line: str) -> bool:
    prefix = "?? .claude/agents/"
    if not status_line.startswith(prefix):
        return False
    filename = status_line[len(prefix) :]
    if filename not in PROJECT_WORKER_NAMES or "/" in filename:
        return False
    path = repo / ".claude" / "agents" / filename
    if path.is_symlink() or not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    expected_name = filename.removesuffix(".md")
    return all(
        token in content
        for token in (
            PROJECT_AGENT_MARKER,
            f"name: {expected_name}",
            "hooks:\n  PreToolUse:",
            "vsdd-model-guard.py",
            '            - "--project-agent"',
        )
    )


def bootstrap_dirty_status(repo: Path) -> list[str]:
    output = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    return [
        line
        for line in output.splitlines()
        if line and not is_generated_project_agent_status(repo, line)
    ]


def bootstrap_run(
    repo: Path,
    slug: str,
    integration_worktree: Path,
    request: str,
    until: str,
    mode: str,
    explicit_base: str | None,
) -> dict:
    """Create the one valid pre-Steering managed bootstrap shape."""
    repo = validate_repo(repo.expanduser().resolve())
    validate_slug(slug)
    integration_worktree = integration_worktree.expanduser().resolve()
    if not request.strip():
        raise RuntimeBlocked("bootstrap request must not be empty")
    if until not in {"review", "pr"}:
        raise RuntimeBlocked("bootstrap until must be 'review' or 'pr'")
    if mode not in {"auto", "standard"}:
        raise RuntimeBlocked("bootstrap mode must be 'auto' or 'standard'")
    if bootstrap_dirty_status(repo):
        raise RuntimeBlocked("managed bootstrap requires a clean source checkout")

    base = detect_base(repo, explicit_base)
    branch = f"vsdd/{slug}"
    if git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False):
        raise RuntimeBlocked(f"integration branch already exists: {branch}")
    if integration_worktree.exists():
        raise RuntimeBlocked(f"integration worktree path already exists: {integration_worktree}")

    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "worktree",
            "add",
            "-b",
            branch,
            str(integration_worktree),
            base["base_ref"],
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeBlocked(f"managed bootstrap worktree creation failed: {detail}")

    state = {
        "schema_version": 4,
        "slug": slug,
        "status": "RUNNING",
        "execution_mode": "unattended",
        "request": request.strip(),
        "source_paths": [],
        "until": until,
        **base,
        "integration_branch": branch,
        "integration_worktree": str(integration_worktree),
        "bootstrap_status": "READY",
        "current_phase": "steering",
        "implementation_session_id": None,
        "phases": {phase: {"status": "PENDING"} for phase in PHASE_ORDER},
        "artifact_hashes": {},
        "attempt_ledger": {},
        "invalidation_history": [],
        "blocker": None,
    }
    try:
        write_state_atomic(integration_worktree, slug, state)
    except OSError as error:
        raise RuntimeBlocked(
            "managed bootstrap created the worktree but could not persist run-state; "
            f"preserved worktree: {integration_worktree}: {error}"
        ) from error
    return {
        "status": "BOOTSTRAPPED",
        "slug": slug,
        "integration_branch": branch,
        "integration_worktree": str(integration_worktree),
        **base,
    }


def validate_slug(slug: str) -> None:
    if not SLUG_RE.fullmatch(slug):
        raise RuntimeBlocked("slug must be lowercase kebab-case")


def spec_root(worktree: Path, slug: str) -> Path:
    validate_slug(slug)
    return worktree / ".claude" / "specs" / slug


def state_path(worktree: Path, slug: str) -> Path:
    return spec_root(worktree, slug) / "run-state.json"


def read_state(worktree: Path, slug: str) -> dict:
    path = state_path(worktree, slug)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeBlocked(f"missing run state: {path}") from error
    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeBlocked(f"cannot read run state {path}: {error}") from error
    if not isinstance(value, dict) or value.get("slug") != slug:
        raise RuntimeBlocked(f"invalid run state identity: {path}")
    return value


def write_state_atomic(worktree: Path, slug: str, state: dict) -> None:
    path = state_path(worktree, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now()
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def artifact_paths(worktree: Path, slug: str, phase: str) -> list[Path]:
    spec = spec_root(worktree, slug)
    steering = worktree / ".claude" / "specs" / "_steering"
    outputs = {
        "steering": [
            steering / "tech.md",
            steering / "structure.md",
            steering / "context.md",
            steering / "open-questions.md",
        ],
        "source": [spec / "source-notion.md", spec / "source-request.md"],
        "init": [],
        "requirements": [spec / "requirements.md"],
        "requirements-review": [spec / "review-results" / "requirement-review.md"],
        "design": [spec / "design.md"],
        "tasks": [spec / "tasks.md"],
        "plan-review": [spec / "review-results" / "plan-review.md"],
        "implementation-plan": [spec / "implementation-workflow.md"],
        "implementation-plan-review": [
            spec / "review-results" / "implementation-workflow-review.md"
        ],
        "implementation": [spec / "implementation-ledger.md"],
        "code-review": [spec / "review-results" / "code-review.md"],
        "security-review": [spec / "review-results" / "security-review.md"],
        "remediation": [spec / "implementation-ledger.md"],
        "pr": [spec / "pr-result.json"],
    }
    if phase not in outputs:
        raise RuntimeBlocked(f"unknown snapshot phase: {phase}")
    return outputs[phase]


def owner_for_snapshot(phase: str) -> str:
    return "requirements" if phase == "source" else phase


def init_output_issues(worktree: Path, slug: str) -> list[str]:
    spec = spec_root(worktree, slug)
    required_files = (
        "progress.md",
        "change-log.md",
        "requirements.md",
        "design.md",
        "tasks.md",
    )
    missing = [name for name in required_files if not (spec / name).is_file()]
    if not (spec / "review-results").is_dir():
        missing.append("review-results/")
    return [f"Init outputs are missing: {', '.join(missing)}"] if missing else []


def relative_path(worktree: Path, path: Path) -> str:
    try:
        return path.relative_to(worktree).as_posix()
    except ValueError as error:
        raise RuntimeBlocked(f"artifact escapes integration worktree: {path}") from error


def digest_path(path: Path) -> str:
    if not path.exists():
        return MISSING_HASH
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(child.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def parse_frontmatter(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RuntimeBlocked(f"cannot read review artifact {path}: {error}") from error
    if not lines or lines[0].strip() != "---":
        raise RuntimeBlocked(f"review artifact lacks YAML frontmatter: {path}")
    values: dict[str, str] = {}
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in values:
            raise RuntimeBlocked(f"duplicate review frontmatter field {key!r}: {path}")
        values[key] = value.strip()
    if not closed:
        raise RuntimeBlocked(f"review frontmatter is not closed: {path}")
    return values


def validate_review_artifact(
    worktree: Path, slug: str, phase: str
) -> tuple[Path, dict[str, str]]:
    if phase not in REVIEW_PHASES:
        raise RuntimeBlocked(f"phase is not a review phase: {phase}")
    filename, expected_type, target_kind = REVIEW_PHASES[phase]
    path = spec_root(worktree, slug) / "review-results" / filename
    if not path.is_file():
        raise RuntimeBlocked(f"missing review artifact for {phase}: {path}")
    values = parse_frontmatter(path)
    required = {
        "review_type",
        "target_commit",
        "verdict",
        "critical",
        "high",
        "medium",
        "low",
        "remediation_mode",
        "reviewer_model",
        "reviewer_effort",
        "review_attempt",
    }
    missing = sorted(required - values.keys())
    if missing:
        raise RuntimeBlocked(
            f"review frontmatter for {phase} is missing: {', '.join(missing)}"
        )
    if values["review_type"] != expected_type:
        raise RuntimeBlocked(
            f"{phase} review_type must be {expected_type!r}; got {values['review_type']!r}"
        )
    if values["reviewer_model"].lower() != "opus":
        raise RuntimeBlocked(f"{phase} reviewer_model must be 'opus'")
    if values["reviewer_effort"].lower() != "xhigh":
        raise RuntimeBlocked(f"{phase} reviewer_effort must be 'xhigh'")
    verdict = values["verdict"].upper()
    if verdict not in {"PASS", "REVISE", "BLOCKED"}:
        raise RuntimeBlocked(f"invalid {phase} verdict: {values['verdict']!r}")
    values["verdict"] = verdict
    if values["remediation_mode"] not in {"none", "standard", "workflow"}:
        raise RuntimeBlocked(
            f"invalid {phase} remediation_mode: {values['remediation_mode']!r}"
        )

    severities: dict[str, int] = {}
    for name in ("critical", "high", "medium", "low"):
        try:
            count = int(values[name])
        except ValueError as error:
            raise RuntimeBlocked(f"{phase} {name} must be an integer") from error
        if count < 0:
            raise RuntimeBlocked(f"{phase} {name} cannot be negative")
        severities[name] = count
    blocking = severities["critical"] + severities["high"]
    if verdict == "PASS" and blocking:
        raise RuntimeBlocked(f"{phase} cannot PASS with CRITICAL/HIGH findings")
    if verdict == "REVISE" and not blocking:
        raise RuntimeBlocked(f"{phase} cannot REVISE without CRITICAL/HIGH findings")

    try:
        attempt = int(values["review_attempt"])
    except ValueError as error:
        raise RuntimeBlocked(f"{phase} review_attempt must be an integer") from error
    if attempt not in {1, 2, 3}:
        raise RuntimeBlocked(f"{phase} review_attempt must be between 1 and 3")

    expected_target = git(worktree, "rev-parse", "HEAD") if target_kind == "HEAD" else "N/A"
    if values["target_commit"] != expected_target:
        raise RuntimeBlocked(
            f"{phase} target_commit must be {expected_target!r}; "
            f"got {values['target_commit']!r}"
        )
    return path, values


def validate_pr_artifact(worktree: Path, slug: str, state: dict) -> tuple[Path, dict]:
    path = spec_root(worktree, slug) / "pr-result.json"
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeBlocked(f"PR completion requires {path}") from error
    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeBlocked(f"cannot read PR evidence {path}: {error}") from error
    if not isinstance(evidence, dict):
        raise RuntimeBlocked("PR evidence must be a JSON object")
    required = {
        "url",
        "number",
        "base_branch",
        "base_sha",
        "head_branch",
        "head_sha",
        "target_commit",
    }
    missing = sorted(required - evidence.keys())
    if missing:
        raise RuntimeBlocked(f"PR evidence is missing: {', '.join(missing)}")
    match = re.fullmatch(
        r"https://github\.com/[^/]+/[^/]+/pull/(\d+)", str(evidence["url"])
    )
    if not match or not isinstance(evidence["number"], int) or evidence["number"] < 1:
        raise RuntimeBlocked("PR evidence URL and positive integer number are required")
    if int(match.group(1)) != evidence["number"]:
        raise RuntimeBlocked("PR evidence URL and number do not match")
    expected_branch = f"vsdd/{slug}"
    if evidence["head_branch"] != expected_branch:
        raise RuntimeBlocked(f"PR head_branch must be {expected_branch!r}")
    if evidence["base_branch"] != state.get("base_branch"):
        raise RuntimeBlocked("PR base_branch does not match run-state")
    if evidence["base_sha"] != state.get("base_sha"):
        raise RuntimeBlocked("PR base_sha does not match run-state")
    head = git(worktree, "rev-parse", "HEAD")
    if evidence["head_sha"] != head or evidence["target_commit"] != head:
        raise RuntimeBlocked("PR evidence must target the current integration HEAD")
    return path, evidence


def attempt_key(scope: str, task_id: str | None = None) -> str:
    if scope == "implementation-task":
        if not task_id or not TASK_RE.fullmatch(task_id):
            raise RuntimeBlocked("implementation-task attempt requires --task-id TASK-NNN")
        return f"implementation-task:{task_id}"
    if task_id:
        raise RuntimeBlocked("--task-id is valid only for implementation-task attempts")
    if scope not in ATTEMPT_SCOPES:
        raise RuntimeBlocked(f"unknown attempt scope: {scope}")
    return scope


def begin_attempt(
    worktree: Path, slug: str, scope: str, task_id: str | None = None
) -> dict:
    worktree = validate_repo(worktree.resolve())
    state = read_state(worktree, slug)
    key = attempt_key(scope, task_id)
    if scope == "implementation-task":
        tasks_path = spec_root(worktree, slug) / "tasks.md"
        task_ids = (
            set(task_headings(tasks_path.read_text(encoding="utf-8")))
            if tasks_path.is_file()
            else set()
        )
        if task_id not in task_ids:
            raise RuntimeBlocked(f"attempt TASK is not present in tasks.md: {task_id}")
    ledger = state.setdefault("attempt_ledger", {})
    record = ledger.setdefault(key, {"attempts_started": 0, "limit": ATTEMPT_LIMIT})
    started = int(record.get("attempts_started", 0))
    limit = int(record.get("limit", ATTEMPT_LIMIT))
    if limit != ATTEMPT_LIMIT:
        raise RuntimeBlocked(f"attempt ledger limit is invalid for {key}: {limit}")
    if started >= limit:
        state["status"] = "BLOCKED"
        state["blocker"] = f"retry budget exhausted for {key}: {started}/{limit}"
        write_state_atomic(worktree, slug, state)
        raise RuntimeBlocked(state["blocker"])
    if started and int(record.get("last_finished_attempt", 0)) != started:
        raise RuntimeBlocked(f"attempt {started} for {key} has not been finished")
    started += 1
    record["attempts_started"] = started
    record["last_started_at"] = now()
    state["schema_version"] = max(int(state.get("schema_version", 1)), 4)
    write_state_atomic(worktree, slug, state)
    return {
        "status": "ATTEMPT_STARTED",
        "scope": scope,
        "task_id": task_id,
        "attempt": started,
        "limit": limit,
    }


def finish_attempt(
    worktree: Path,
    slug: str,
    scope: str,
    attempt: int,
    outcome: str,
    task_id: str | None = None,
) -> dict:
    worktree = validate_repo(worktree.resolve())
    state = read_state(worktree, slug)
    key = attempt_key(scope, task_id)
    if outcome not in {"PASS", "FAIL"}:
        raise RuntimeBlocked("attempt outcome must be PASS or FAIL")
    record = state.get("attempt_ledger", {}).get(key)
    if not isinstance(record, dict):
        raise RuntimeBlocked(f"attempt was not begun for {key}")
    started = int(record.get("attempts_started", 0))
    if attempt != started:
        raise RuntimeBlocked(
            f"finished attempt must equal current begun attempt {started}; got {attempt}"
        )
    finished = int(record.get("last_finished_attempt", 0))
    if finished == attempt:
        if record.get("last_outcome") != outcome:
            raise RuntimeBlocked(f"attempt {attempt} for {key} already has another outcome")
        return {
            "status": "ATTEMPT_FINISHED",
            "scope": scope,
            "task_id": task_id,
            "attempt": attempt,
            "outcome": outcome,
            "limit": ATTEMPT_LIMIT,
        }
    record["last_finished_attempt"] = attempt
    record["last_outcome"] = outcome
    record["last_finished_at"] = now()
    if outcome == "FAIL" and attempt >= ATTEMPT_LIMIT:
        state["status"] = "BLOCKED"
        state["blocker"] = f"retry budget exhausted for {key}: {attempt}/{ATTEMPT_LIMIT}"
    write_state_atomic(worktree, slug, state)
    return {
        "status": "ATTEMPT_FINISHED",
        "scope": scope,
        "task_id": task_id,
        "attempt": attempt,
        "outcome": outcome,
        "limit": ATTEMPT_LIMIT,
    }


def review_attempt_issues(
    worktree: Path,
    slug: str,
    phase: str,
    state: dict,
    metadata: dict[str, str],
) -> list[str]:
    scope = REVIEW_ATTEMPT_SCOPES[phase]
    record = state.get("attempt_ledger", {}).get(scope)
    if not isinstance(record, dict):
        return [f"{phase} requires begin-attempt for scope {scope!r}"]
    started = int(record.get("attempts_started", 0))
    attempt = int(metadata["review_attempt"])
    if started != attempt:
        return [
            f"{phase} review_attempt must equal the current begun attempt {started}; "
            f"got {attempt}"
        ]
    path = artifact_paths(worktree, slug, phase)[0]
    key = relative_path(worktree, path)
    entry = state.get("phases", {}).get(phase, {})
    previous = entry.get("output_hashes", {}).get(key)
    if entry.get("review_attempt") == attempt and previous:
        current = digest_path(path)
        if previous != current:
            return [
                f"{phase} attempt {attempt} was already snapshotted; "
                "begin the next attempt before replacing its report"
            ]
    return []


def snapshot_dependents(phase: str) -> tuple[str, ...]:
    if phase == "source":
        return PHASE_ORDER[PHASE_INDEX["requirements"] :]
    if phase == "code-review":
        return ("remediation", "pr")
    if phase == "security-review":
        return ("remediation", "pr")
    if phase == "remediation":
        return ("code-review", "security-review", "pr")
    if phase not in PHASE_INDEX or phase == "pr":
        return ()
    return PHASE_ORDER[PHASE_INDEX[phase] + 1 :]


def reset_attempts_for_phases(state: dict, phases: set[str]) -> None:
    ledger = state.setdefault("attempt_ledger", {})
    for review_phase, scope in REVIEW_ATTEMPT_SCOPES.items():
        if review_phase in phases:
            ledger.pop(scope, None)
    if "implementation" in phases:
        for key in list(ledger):
            if key.startswith("implementation-task:"):
                del ledger[key]


def invalidate_phase_entries(
    current: dict,
    phases: tuple[str, ...] | list[str],
    reason: str,
    *,
    reset_attempts: bool,
) -> list[str]:
    history = current.setdefault("invalidation_history", [])
    changed: list[str] = []
    for phase in phases:
        entry = current.setdefault("phases", {}).setdefault(phase, {})
        if entry.get("status") not in {None, "PENDING"}:
            history.append(
                {
                    "phase": phase,
                    "previous_status": entry.get("status"),
                    "reason": reason,
                    "invalidated_at": now(),
                }
            )
        entry["status"] = "PENDING"
        entry["invalidated_at"] = now()
        entry["invalidation_reason"] = reason
        for key in (
            "verdict",
            "target_commit",
            "review_attempt",
            "completed_at",
            "checkpointed_at",
            "input_hashes",
            "output_hashes",
            "evidence_paths",
            "url",
            "number",
        ):
            entry.pop(key, None)
        changed.append(phase)
    invalidated = set(changed)
    records = current.setdefault("artifact_hashes", {})
    for path, record in list(records.items()):
        if isinstance(record, dict) and record.get("owner_phase") in invalidated:
            del records[path]
    if reset_attempts:
        reset_attempts_for_phases(current, invalidated)
    return changed


def snapshot_phase(
    worktree: Path, slug: str, phase: str, phase_status: str = "COMPLETE"
) -> dict:
    worktree = validate_repo(worktree.resolve())
    state = read_state(worktree, slug)
    paths = artifact_paths(worktree, slug, phase)
    if phase == "source" and not any(path.is_file() for path in paths):
        raise RuntimeBlocked("source snapshot requires source-notion.md or source-request.md")
    if phase == "init":
        issues = init_output_issues(worktree, slug)
        if issues:
            raise RuntimeBlocked("; ".join(issues))
    missing = [path for path in paths if not path.is_file()]
    if phase != "source" and missing:
        rendered = ", ".join(str(path) for path in missing)
        raise RuntimeBlocked(f"phase outputs are missing: {rendered}")

    review_metadata: dict[str, str] | None = None
    pr_metadata: dict | None = None
    if phase in REVIEW_PHASES:
        _, review_metadata = validate_review_artifact(worktree, slug, phase)
        attempt_issues = review_attempt_issues(
            worktree, slug, phase, state, review_metadata
        )
        if attempt_issues:
            raise RuntimeBlocked("; ".join(attempt_issues))
        expected_status = {
            "PASS": "COMPLETE",
            "REVISE": "REVISE",
            "BLOCKED": "BLOCKED",
        }[review_metadata["verdict"]]
        if phase_status != expected_status:
            raise RuntimeBlocked(
                f"{phase} phase status must be {expected_status!r} for verdict "
                f"{review_metadata['verdict']!r}"
            )
    if phase == "pr":
        _, pr_metadata = validate_pr_artifact(worktree, slug, state)

    records = state.setdefault("artifact_hashes", {})
    owner = owner_for_snapshot(phase)
    captured: dict[str, str] = {}
    for path in paths:
        key = relative_path(worktree, path)
        digest = digest_path(path)
        existing = records.get(key)
        if isinstance(existing, dict) and existing.get("sha256") != digest:
            dependents = snapshot_dependents(phase)
            if dependents:
                invalidate_phase_entries(
                    state,
                    dependents,
                    f"{phase} output changed during a new snapshot: {key}",
                    reset_attempts=phase != "remediation",
                )
                records = state.setdefault("artifact_hashes", {})
        records[key] = {"sha256": digest, "owner_phase": owner, "recorded_at": now()}
        captured[key] = digest

    if phase in PHASE_INDEX:
        entry = state.setdefault("phases", {}).setdefault(phase, {})
        entry["status"] = phase_status
        entry["output_hashes"] = captured
        entry["checkpointed_at"] = now()
        if review_metadata is not None:
            entry["verdict"] = review_metadata["verdict"]
            entry["target_commit"] = review_metadata["target_commit"]
            review_attempt = int(review_metadata["review_attempt"])
            entry["review_attempt"] = review_attempt
            scope = REVIEW_ATTEMPT_SCOPES[phase]
            attempt_record = state["attempt_ledger"][scope]
            attempt_record["last_finished_attempt"] = review_attempt
            attempt_record["last_outcome"] = (
                "PASS" if review_metadata["verdict"] == "PASS" else "FAIL"
            )
            attempt_record["last_finished_at"] = now()
            if review_metadata["verdict"] == "BLOCKED" or (
                review_metadata["verdict"] == "REVISE"
                and review_attempt >= ATTEMPT_LIMIT
            ):
                state["status"] = "BLOCKED"
                state["blocker"] = (
                    f"retry budget exhausted or review blocked for {phase}: "
                    f"attempt {review_attempt}/{ATTEMPT_LIMIT}"
                )
        if pr_metadata is not None:
            entry["url"] = pr_metadata["url"]
            entry["number"] = pr_metadata["number"]
            entry["base_branch"] = pr_metadata["base_branch"]
            entry["base_sha"] = pr_metadata["base_sha"]
            entry["head_branch"] = pr_metadata["head_branch"]
            entry["head_sha"] = pr_metadata["head_sha"]
            entry["target_commit"] = pr_metadata["target_commit"]
    if phase == "init":
        state["bootstrap_status"] = "CONSUMED"
    state["schema_version"] = max(int(state.get("schema_version", 1)), 4)
    write_state_atomic(worktree, slug, state)
    return {"status": "SNAPSHOT", "phase": phase, "artifacts": captured}


def invalidate_state(
    worktree: Path, slug: str, from_phase: str, reason: str, state: dict | None = None
) -> dict:
    if from_phase not in PHASE_INDEX:
        raise RuntimeBlocked(f"unknown invalidation phase: {from_phase}")
    worktree = validate_repo(worktree.resolve())
    current = state if state is not None else read_state(worktree, slug)
    changed = invalidate_phase_entries(
        current,
        PHASE_ORDER[PHASE_INDEX[from_phase] :],
        reason,
        reset_attempts=False,
    )
    reset_attempts_for_phases(current, set(snapshot_dependents(from_phase)))
    current["status"] = "RUNNING"
    current["current_phase"] = from_phase
    current["blocker"] = None
    current.pop("reached", None)
    current.pop("completed_at", None)
    current.pop("review_completed_at", None)
    write_state_atomic(worktree, slug, current)
    return {"status": "INVALIDATED", "earliest_phase": from_phase, "phases": changed}


def audit_state(worktree: Path, slug: str) -> dict:
    worktree = validate_repo(worktree.resolve())
    state = read_state(worktree, slug)
    changes: list[dict[str, str]] = []
    for key, record in state.get("artifact_hashes", {}).items():
        if not isinstance(record, dict):
            continue
        owner = record.get("owner_phase")
        if owner not in PHASE_INDEX:
            raise RuntimeBlocked(f"invalid artifact owner for {key}: {owner!r}")
        actual = digest_path(worktree / key)
        expected = str(record.get("sha256") or "")
        if actual != expected:
            changes.append(
                {
                    "path": key,
                    "owner_phase": owner,
                    "expected": expected,
                    "actual": actual,
                }
            )
    if not changes:
        return {"status": "VALID", "changes": []}
    earliest = min(changes, key=lambda item: PHASE_INDEX[item["owner_phase"]])[
        "owner_phase"
    ]
    reason = "artifact hash changed: " + ", ".join(item["path"] for item in changes)
    result = invalidate_state(worktree, slug, earliest, reason, state=state)
    result["changes"] = changes
    return result


def open_question_blocks(text: str) -> list[str]:
    match = re.search(r"(?ms)^## Open\s*$\n(.*?)(?=^##\s|\Z)", text)
    if not match:
        return []
    section = match.group(1)
    blocks = re.split(r"(?m)(?=^###\s+Q-\d+\b)", section)
    issues: list[str] = []
    for block in blocks:
        identifier = re.search(r"(?m)^###\s+(Q-\d+)\b", block)
        if not identifier:
            continue
        status = re.search(r"(?im)^\s*-\s*Status:\s*([a-z-]+)\s*$", block)
        value = status.group(1).lower() if status else "open"
        if value not in {"resolved", "dismissed", "assumed"}:
            issues.append(f"{identifier.group(1)} remains {value} in open-questions.md")
    return issues


def steering_issues(worktree: Path, slug: str) -> list[str]:
    steering = worktree / ".claude" / "specs" / "_steering"
    required = ("tech.md", "structure.md", "context.md", "open-questions.md")
    issues: list[str] = []
    for name in required:
        path = steering / name
        if not path.is_file():
            issues.append(f"missing Steering artifact: {path}")
    open_path = steering / "open-questions.md"
    if open_path.is_file():
        issues.extend(open_question_blocks(open_path.read_text(encoding="utf-8")))
    for path in steering.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"<!--\s*DRAFT\b", text, flags=re.IGNORECASE):
            issues.append(f"DRAFT marker remains in {path.relative_to(worktree)}")
    requirements = spec_root(worktree, slug) / "requirements.md"
    if requirements.is_file() and re.search(
        r"Glossary pending", requirements.read_text(encoding="utf-8"), re.IGNORECASE
    ):
        issues.append(f"Glossary pending marker remains in {requirements.relative_to(worktree)}")
    return issues


def task_headings(text: str) -> list[str]:
    return re.findall(r"(?m)^#{2,4}\s+(TASK-\d{3})\b", text)


def progress_tasks(text: str) -> tuple[list[str], dict[str, str]]:
    identifiers: list[str] = []
    statuses: dict[str, str] = {}
    for line in text.splitlines():
        if not re.match(r"^\s*\|\s*TASK-\d{3}\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        identifier = cells[0]
        identifiers.append(identifier)
        statuses[identifier] = cells[2].lower() if len(cells) > 2 else ""
    return identifiers, statuses


def ledger_mapping(text: str) -> tuple[list[str], dict[str, str]]:
    section = re.search(
        r"(?ms)^## TASK-to-SHA Mapping\s*$\n(.*?)(?=^##\s|\Z)", text
    )
    if not section:
        return [], {}
    pairs = re.findall(
        r"(?im)^\s*\|\s*(TASK-\d{3})\s*\|\s*`?([0-9a-f]{7,40})`?\s*\|",
        section.group(1),
    )
    identifiers = [identifier for identifier, _ in pairs]
    return identifiers, dict(pairs)


def duplicate_issues(label: str, identifiers: list[str]) -> list[str]:
    duplicates = sorted(item for item, count in Counter(identifiers).items() if count > 1)
    return [f"duplicate {label} IDs: {', '.join(duplicates)}"] if duplicates else []


def set_difference_issue(label: str, expected: set[str], actual: set[str]) -> list[str]:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if not missing and not extra:
        return []
    parts = []
    if missing:
        parts.append(f"missing {', '.join(missing)}")
    if extra:
        parts.append(f"unexpected {', '.join(extra)}")
    return [f"{label} TASK set mismatch: {'; '.join(parts)}"]


def task_attempt_issues(state: dict, task_ids: set[str]) -> list[str]:
    ledger = state.get("attempt_ledger", {})
    issues: list[str] = []
    for task_id in sorted(task_ids):
        key = f"implementation-task:{task_id}"
        record = ledger.get(key)
        if not isinstance(record, dict) or int(record.get("attempts_started", 0)) < 1:
            issues.append(f"TASK attempt was never begun: {task_id}")
            continue
        started = int(record.get("attempts_started", 0))
        if started > ATTEMPT_LIMIT:
            issues.append(f"TASK attempt ledger exceeds limit for {task_id}: {started}")
        if (
            int(record.get("last_finished_attempt", 0)) != started
            or record.get("last_outcome") != "PASS"
        ):
            issues.append(f"TASK attempt has no successful finish: {task_id}")
    return issues


def task_set_issues(
    worktree: Path,
    slug: str,
    require_ledger: bool,
    state: dict | None = None,
) -> list[str]:
    spec = spec_root(worktree, slug)
    tasks_path = spec / "tasks.md"
    progress_path = spec / "progress.md"
    issues: list[str] = []
    if not tasks_path.is_file() or not progress_path.is_file():
        return ["tasks.md and progress.md are both required"]

    task_ids = task_headings(tasks_path.read_text(encoding="utf-8"))
    progress_ids, statuses = progress_tasks(progress_path.read_text(encoding="utf-8"))
    issues.extend(duplicate_issues("tasks.md", task_ids))
    issues.extend(duplicate_issues("progress.md", progress_ids))
    task_set = set(task_ids)
    progress_set = set(progress_ids)
    if not task_set:
        issues.append("tasks.md contains no TASK-NNN headings")
    issues.extend(set_difference_issue("progress.md", task_set, progress_set))

    if require_ledger:
        ledger_path = spec / "implementation-ledger.md"
        if not ledger_path.is_file():
            issues.append("implementation-ledger.md is required")
            return issues
        ledger_ids, mapping = ledger_mapping(ledger_path.read_text(encoding="utf-8"))
        issues.extend(duplicate_issues("implementation-ledger.md", ledger_ids))
        issues.extend(set_difference_issue("implementation ledger", task_set, set(ledger_ids)))
        not_done = sorted(
            identifier for identifier in task_set if statuses.get(identifier) != "done"
        )
        if not_done:
            issues.append(f"TASKs are not done in progress.md: {', '.join(not_done)}")
        for identifier, sha in mapping.items():
            exists = subprocess.run(
                ["git", "-C", str(worktree), "cat-file", "-e", f"{sha}^{{commit}}"],
                capture_output=True,
                check=False,
            ).returncode == 0
            if not exists:
                issues.append(f"{identifier} maps to a missing commit: {sha}")
                continue
            integrated = subprocess.run(
                ["git", "-C", str(worktree), "merge-base", "--is-ancestor", sha, "HEAD"],
                capture_output=True,
                check=False,
            ).returncode == 0
            if not integrated:
                issues.append(
                    f"{identifier} commit is not reachable from integration HEAD: {sha}"
                )
        if state is not None:
            issues.extend(task_attempt_issues(state, task_set))
    return issues


def bootstrap_issues(worktree: Path, slug: str, state: dict) -> list[str]:
    """Validate the managed Start skeleton consumed by the Phase 1 Init worker."""
    issues: list[str] = []
    if state.get("bootstrap_status") != "READY":
        issues.append("run-state bootstrap_status must be 'READY' before Init")
    init_status = state.get("phases", {}).get("init", {}).get("status")
    if init_status != "PENDING":
        issues.append(f"Init bootstrap cannot be consumed from status {init_status!r}")
    spec = spec_root(worktree, slug)
    if not spec.is_dir():
        issues.append(f"managed bootstrap spec directory is missing: {spec}")
        return issues
    allowed = {"run-state.json"}
    unexpected = sorted(path.name for path in spec.iterdir() if path.name not in allowed)
    if unexpected:
        issues.append(f"unexpected pre-init artifact(s): {', '.join(unexpected)}")
    return issues


def integration_issues(worktree: Path, slug: str, state: dict) -> list[str]:
    issues: list[str] = []
    branch = git(worktree, "branch", "--show-current", check=False)
    expected_branch = f"vsdd/{slug}"
    recorded_branch = state.get("integration_branch")
    if recorded_branch != expected_branch:
        issues.append(
            f"run-state integration_branch must record {expected_branch!r}; "
            f"got {recorded_branch!r}"
        )
    if branch != expected_branch:
        issues.append(
            f"integration branch must be {expected_branch!r}; active branch is {branch!r}"
        )
    recorded_worktree = state.get("integration_worktree")
    if recorded_worktree and Path(recorded_worktree).resolve() != worktree.resolve():
        issues.append("run-state integration_worktree does not match the active worktree")
    base_sha = str(state.get("base_sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        issues.append("run-state base_sha is missing or invalid")
    elif subprocess.run(
        ["git", "-C", str(worktree), "merge-base", "--is-ancestor", base_sha, "HEAD"],
        capture_output=True,
        check=False,
    ).returncode:
        issues.append("recorded base_sha is not an ancestor of integration HEAD")
    if not state.get("base_ref") or not state.get("base_branch"):
        issues.append("run-state must persist base_ref and base_branch")
    return issues


def review_state_issues(
    worktree: Path,
    slug: str,
    phase: str,
    state: dict,
    required_verdict: str | None = "PASS",
) -> list[str]:
    try:
        path, metadata = validate_review_artifact(worktree, slug, phase)
    except RuntimeBlocked as error:
        return [str(error)]
    issues: list[str] = []
    entry = state.get("phases", {}).get(phase, {})
    expected_status = {
        "PASS": "COMPLETE",
        "REVISE": "REVISE",
        "BLOCKED": "BLOCKED",
    }[metadata["verdict"]]
    if entry.get("status") != expected_status:
        issues.append(
            f"{phase} state status must be {expected_status!r}; got {entry.get('status')!r}"
        )
    if entry.get("verdict") != metadata["verdict"]:
        issues.append(f"{phase} state verdict does not match its review artifact")
    if entry.get("target_commit") != metadata["target_commit"]:
        issues.append(f"{phase} state target_commit does not match its review artifact")
    if required_verdict and metadata["verdict"] != required_verdict:
        issues.append(
            f"{phase} requires verdict {required_verdict!r}; got {metadata['verdict']!r}"
        )

    key = relative_path(worktree, path)
    digest = digest_path(path)
    record = state.get("artifact_hashes", {}).get(key)
    output_digest = entry.get("output_hashes", {}).get(key)
    if not isinstance(record, dict) or record.get("owner_phase") != phase:
        issues.append(f"{phase} lacks a deterministic artifact snapshot")
    elif record.get("sha256") != digest:
        issues.append(f"{phase} artifact snapshot does not match disk")
    if output_digest != digest:
        issues.append(f"{phase} output hash does not match disk")
    return issues


def post_review_pair_issues(state: dict) -> list[str]:
    """Require Code and Security evidence from the same current review round."""
    phases = state.get("phases", {})
    code_attempt = phases.get("code-review", {}).get("review_attempt")
    security_attempt = phases.get("security-review", {}).get("review_attempt")
    issues: list[str] = []
    if code_attempt != security_attempt:
        issues.append(
            "code-review and security-review must use the same review_attempt; "
            f"got {code_attempt!r} and {security_attempt!r}"
        )
        return issues
    ledger = state.get("attempt_ledger", {}).get("post-implementation-review")
    if not isinstance(ledger, dict):
        return ["post-implementation-review attempt ledger is missing"]
    started = int(ledger.get("attempts_started", 0))
    finished = int(ledger.get("last_finished_attempt", 0))
    if code_attempt != started or finished != started:
        issues.append(
            "Code/Security review evidence must match the current finished "
            f"post-implementation-review attempt {started}; got pair {code_attempt!r} "
            f"and finished {finished}"
        )
    return issues


def phase_prerequisite_issues(
    worktree: Path, slug: str, phase: str, state: dict
) -> list[str]:
    issues: list[str] = []
    for prerequisite in PHASE_PREREQUISITES[phase]:
        if prerequisite in REVIEW_PHASES:
            issues.extend(
                review_state_issues(
                    worktree, slug, prerequisite, state, required_verdict="PASS"
                )
            )
            continue
        status = state.get("phases", {}).get(prerequisite, {}).get("status")
        if status != "COMPLETE":
            issues.append(
                f"{phase} requires {prerequisite} status 'COMPLETE'; got {status!r}"
            )

    if phase == "remediation":
        verdicts: list[str] = []
        for review_phase in ("code-review", "security-review"):
            review_issues = review_state_issues(
                worktree, slug, review_phase, state, required_verdict=None
            )
            issues.extend(review_issues)
            verdict = state.get("phases", {}).get(review_phase, {}).get("verdict")
            if verdict:
                verdicts.append(verdict)
        if "BLOCKED" in verdicts:
            issues.append("remediation cannot proceed from a BLOCKED review")
        elif verdicts and "REVISE" not in verdicts:
            issues.append("remediation requires at least one REVISE review")
        issues.extend(post_review_pair_issues(state))
    elif phase == "pr":
        issues.extend(post_review_pair_issues(state))
    return issues


def preflight(
    worktree: Path,
    slug: str,
    phase: str,
    *,
    enforce_requested_boundary: bool = True,
) -> dict:
    if phase not in PHASE_INDEX:
        raise RuntimeBlocked(f"unknown preflight phase: {phase}")
    worktree = validate_repo(worktree.resolve())
    audit = audit_state(worktree, slug)
    if audit["status"] == "INVALIDATED":
        return audit
    state = read_state(worktree, slug)
    issues: list[str] = []
    if state.get("status") != "RUNNING":
        issues.append(f"run-state status must be 'RUNNING'; got {state.get('status')!r}")
    if (
        phase == "pr"
        and enforce_requested_boundary
        and state.get("until") != "pr"
    ):
        issues.append(
            f"PR phase requires explicit until 'pr'; got {state.get('until')!r}"
        )
    issues.extend(integration_issues(worktree, slug, state))
    if phase != "steering":
        issues.extend(steering_issues(worktree, slug))
    if phase == "init":
        issues.extend(bootstrap_issues(worktree, slug, state))
    issues.extend(phase_prerequisite_issues(worktree, slug, phase, state))
    if PHASE_INDEX[phase] >= PHASE_INDEX["plan-review"]:
        require_ledger = PHASE_INDEX[phase] >= PHASE_INDEX["code-review"]
        issues.extend(
            task_set_issues(
                worktree, slug, require_ledger=require_ledger, state=state
            )
        )
    if issues:
        raise RuntimeBlocked("; ".join(issues))
    return {"status": "READY", "phase": phase}


def task_gate(worktree: Path, slug: str) -> dict:
    """Verify implementation bookkeeping before accepting a worker COMPLETE result."""
    worktree = validate_repo(worktree.resolve())
    state = read_state(worktree, slug)
    issues: list[str] = []
    if state.get("status") != "RUNNING":
        issues.append(f"run-state status must be 'RUNNING'; got {state.get('status')!r}")
    issues.extend(integration_issues(worktree, slug, state))
    issues.extend(
        task_set_issues(worktree, slug, require_ledger=True, state=state)
    )
    if issues:
        raise RuntimeBlocked("; ".join(issues))
    return {"status": "READY", "gate": "task-integrity"}


def pr_snapshot_issues(worktree: Path, slug: str, state: dict) -> list[str]:
    try:
        path, metadata = validate_pr_artifact(worktree, slug, state)
    except RuntimeBlocked as error:
        return [str(error)]
    entry = state.get("phases", {}).get("pr", {})
    key = relative_path(worktree, path)
    digest = digest_path(path)
    record = state.get("artifact_hashes", {}).get(key)
    issues: list[str] = []
    if entry.get("status") != "COMPLETE":
        issues.append(f"pr state status must be 'COMPLETE'; got {entry.get('status')!r}")
    if entry.get("target_commit") != metadata["target_commit"]:
        issues.append("pr state target_commit does not match pr-result.json")
    if not isinstance(record, dict) or record.get("owner_phase") != "pr":
        issues.append("pr lacks a deterministic artifact snapshot")
    elif record.get("sha256") != digest:
        issues.append("pr artifact snapshot does not match disk")
    if entry.get("output_hashes", {}).get(key) != digest:
        issues.append("pr output hash does not match disk")
    return issues


def terminal_completion_issues(
    worktree: Path, slug: str, state: dict, reached: str
) -> tuple[str | None, list[str]]:
    """Revalidate a closed run against mutable repository and steering state."""
    grouped: list[tuple[str, list[str]]] = [
        ("init", integration_issues(worktree, slug, state)),
        ("steering", steering_issues(worktree, slug)),
        (
            "tasks",
            task_set_issues(worktree, slug, require_ledger=True, state=state),
        ),
    ]
    for prerequisite in PHASE_PREREQUISITES["pr"]:
        if prerequisite in REVIEW_PHASES:
            issues = review_state_issues(
                worktree,
                slug,
                prerequisite,
                state,
                required_verdict="PASS",
            )
        else:
            status = state.get("phases", {}).get(prerequisite, {}).get("status")
            issues = (
                []
                if status == "COMPLETE"
                else [
                    f"terminal completion requires {prerequisite} status "
                    f"'COMPLETE'; got {status!r}"
                ]
            )
        grouped.append((prerequisite, issues))
    grouped.append(("code-review", post_review_pair_issues(state)))
    if reached == "pr":
        grouped.append(("pr", pr_snapshot_issues(worktree, slug, state)))

    failures = [(phase, issues) for phase, issues in grouped if issues]
    if not failures:
        return None, []
    earliest = min(failures, key=lambda item: PHASE_INDEX[item[0]])[0]
    return earliest, [issue for _, issues in failures for issue in issues]


def complete_run(worktree: Path, slug: str, reached: str) -> dict:
    """Close a run only after deterministic evidence reaches its requested boundary."""
    worktree = validate_repo(worktree.resolve())
    if reached not in {"review", "pr"}:
        raise RuntimeBlocked("completion boundary must be 'review' or 'pr'")
    state = read_state(worktree, slug)
    if state.get("status") == "COMPLETE":
        if state.get("reached") == reached:
            audit = audit_state(worktree, slug)
            if audit["status"] != "VALID":
                raise RuntimeBlocked(
                    "run artifacts changed; resume from the invalidated phase"
                )
            state = read_state(worktree, slug)
            earliest, issues = terminal_completion_issues(
                worktree, slug, state, reached
            )
            if earliest is not None:
                invalidate_state(
                    worktree,
                    slug,
                    earliest,
                    "terminal completion evidence changed: " + "; ".join(issues),
                    state=state,
                )
                raise RuntimeBlocked(
                    f"terminal completion evidence invalidated {earliest}; "
                    "resume from the invalidated phase"
                )
            return {"status": "COMPLETE", "reached": reached, "idempotent": True}
        raise RuntimeBlocked(
            f"run already completed at {state.get('reached')!r}; extend it explicitly"
        )
    if state.get("status") != "RUNNING":
        raise RuntimeBlocked(
            f"run-state status must be 'RUNNING'; got {state.get('status')!r}"
        )
    if state.get("until") != reached:
        raise RuntimeBlocked(
            f"completion boundary {reached!r} does not match run until {state.get('until')!r}"
        )

    readiness = preflight(
        worktree,
        slug,
        "pr",
        enforce_requested_boundary=reached == "pr",
    )
    if readiness.get("status") != "READY":
        raise RuntimeBlocked(
            f"completion preflight invalidated {readiness.get('earliest_phase')}; "
            "resume from the invalidated phase"
        )
    state = read_state(worktree, slug)
    if reached == "pr":
        issues = pr_snapshot_issues(worktree, slug, state)
        if issues:
            raise RuntimeBlocked("; ".join(issues))

    state["status"] = "COMPLETE"
    state["current_phase"] = "security-review" if reached == "review" else "pr"
    state["reached"] = reached
    state["completed_at"] = now()
    state["blocker"] = None
    write_state_atomic(worktree, slug, state)
    return {"status": "COMPLETE", "reached": reached, "idempotent": False}


def extend_run(worktree: Path, slug: str, until: str) -> dict:
    """Reopen a review-complete run only for an explicitly authorized PR target."""
    worktree = validate_repo(worktree.resolve())
    if until != "pr":
        raise RuntimeBlocked("the only supported extension target is 'pr'")
    audit = audit_state(worktree, slug)
    if audit["status"] != "VALID":
        raise RuntimeBlocked("run artifacts changed; resume from the invalidated phase")
    state = read_state(worktree, slug)
    if state.get("status") == "RUNNING" and state.get("until") == "pr":
        return {"status": "RUNNING", "until": "pr", "idempotent": True}
    if not (
        state.get("status") == "COMPLETE"
        and state.get("reached") == "review"
        and state.get("until") == "review"
    ):
        raise RuntimeBlocked(
            "only a review-complete run can be extended to the PR boundary"
        )
    earliest, issues = terminal_completion_issues(worktree, slug, state, "review")
    if earliest is not None:
        invalidate_state(
            worktree,
            slug,
            earliest,
            "review extension evidence changed: " + "; ".join(issues),
            state=state,
        )
        raise RuntimeBlocked(
            f"review extension evidence invalidated {earliest}; "
            "resume from the invalidated phase"
        )

    state["review_completed_at"] = state.get("completed_at")
    state.pop("completed_at", None)
    state.pop("reached", None)
    state["status"] = "RUNNING"
    state["until"] = "pr"
    state["current_phase"] = "pr"
    state["blocker"] = None
    write_state_atomic(worktree, slug, state)
    return {"status": "RUNNING", "until": "pr", "idempotent": False}


def print_json(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect = subparsers.add_parser("detect-base")
    detect.add_argument("--repo", required=True, type=Path)
    detect.add_argument("--base")

    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--repo", required=True, type=Path)
    bootstrap.add_argument("--slug", required=True)
    bootstrap.add_argument("--worktree", required=True, type=Path)
    bootstrap.add_argument("--request", required=True)
    bootstrap.add_argument("--until", choices=("review", "pr"), default="review")
    bootstrap.add_argument("--mode", choices=("auto", "standard"), default="auto")
    bootstrap.add_argument("--base")

    attempt = subparsers.add_parser("begin-attempt")
    attempt.add_argument("--worktree", required=True, type=Path)
    attempt.add_argument("--slug", required=True)
    attempt.add_argument("--scope", required=True, choices=ATTEMPT_SCOPES)
    attempt.add_argument("--task-id")

    finish = subparsers.add_parser("finish-attempt")
    finish.add_argument("--worktree", required=True, type=Path)
    finish.add_argument("--slug", required=True)
    finish.add_argument("--scope", required=True, choices=ATTEMPT_SCOPES)
    finish.add_argument("--task-id")
    finish.add_argument("--attempt", required=True, type=int)
    finish.add_argument("--outcome", required=True, choices=("PASS", "FAIL"))

    for command in (
        "snapshot",
        "audit",
        "invalidate",
        "preflight",
        "task-gate",
        "complete",
        "extend",
    ):
        child = subparsers.add_parser(command)
        child.add_argument("--worktree", required=True, type=Path)
        child.add_argument("--slug", required=True)
        if command == "snapshot":
            child.add_argument("--phase", required=True)
            child.add_argument(
                "--phase-status",
                choices=("COMPLETE", "REVISE", "BLOCKED"),
                default="COMPLETE",
            )
        elif command == "invalidate":
            child.add_argument("--from-phase", required=True, choices=PHASE_ORDER)
            child.add_argument("--reason", required=True)
        elif command == "preflight":
            child.add_argument("--phase", required=True, choices=PHASE_ORDER)
        elif command == "complete":
            child.add_argument("--reached", required=True, choices=("review", "pr"))
        elif command == "extend":
            child.add_argument("--until", required=True, choices=("pr",))

    args = parser.parse_args()
    try:
        if args.command == "detect-base":
            result = detect_base(args.repo, args.base)
        elif args.command == "bootstrap":
            result = bootstrap_run(
                args.repo,
                args.slug,
                args.worktree,
                args.request,
                args.until,
                args.mode,
                args.base,
            )
        elif args.command == "begin-attempt":
            result = begin_attempt(
                args.worktree, args.slug, args.scope, task_id=args.task_id
            )
        elif args.command == "finish-attempt":
            result = finish_attempt(
                args.worktree,
                args.slug,
                args.scope,
                args.attempt,
                args.outcome,
                task_id=args.task_id,
            )
        elif args.command == "snapshot":
            result = snapshot_phase(
                args.worktree, args.slug, args.phase, phase_status=args.phase_status
            )
        elif args.command == "audit":
            result = audit_state(args.worktree, args.slug)
        elif args.command == "invalidate":
            result = invalidate_state(
                args.worktree, args.slug, args.from_phase, args.reason
            )
        elif args.command == "task-gate":
            result = task_gate(args.worktree, args.slug)
        elif args.command == "complete":
            result = complete_run(args.worktree, args.slug, args.reached)
        elif args.command == "extend":
            result = extend_run(args.worktree, args.slug, args.until)
        else:
            result = preflight(args.worktree, args.slug, args.phase)
    except (RuntimeBlocked, OSError) as error:
        print_json({"status": "BLOCKED", "error": str(error)})
        raise SystemExit(1)
    print_json(result)


if __name__ == "__main__":
    main()
