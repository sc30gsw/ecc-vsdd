#!/usr/bin/env python3
"""Deny control-plane work and enforce pinned VSDD agent effort levels."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
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
ORCHESTRATOR_SKILLS = {"ecc-vsdd:vsdd-run", "vsdd-run"}


def deny(message: str) -> None:
    print(f"VSDD control-plane guard: {message}", file=sys.stderr)
    raise SystemExit(2)


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
    data_root = os.environ.get("CLAUDE_PLUGIN_DATA")
    safe_id = re.sub(r"[^a-zA-Z0-9-]", "", str(session_id or ""))
    if not data_root or not safe_id:
        return None
    return Path(data_root) / "session-models" / f"{safe_id}.json"


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"agent_type": agent_type, "model": model}) + "\n",
        encoding="utf-8",
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
    if path is None or not path.is_file():
        return
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        deny(f"cannot verify session model: {error}")
    model = str(record.get("model") or "").lower()
    if not model:
        return
    expected = EXPECTED_MODEL[agent_type]
    if not model or expected not in model:
        deny(f"{agent_type} requires model {expected!r}; active model is {model!r}")


def agent_definition_path(agent_type: str) -> Path:
    plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", "")).resolve()
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


def check_launcher(command: object) -> None:
    raw_command = str(command or "")
    if any(character in raw_command for character in "\r\n;|&<>"):
        deny("shell control operators are prohibited in the VSDD launcher command")
    if "$(" in raw_command or "`" in raw_command:
        deny("shell command substitution is prohibited in the VSDD launcher command")

    try:
        argv = shlex.split(raw_command)
    except ValueError as error:
        deny(f"cannot parse Bash command: {error}")

    plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", "")).resolve()
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
    strict = sys.argv[1:] == ["--strict"]
    session_start = sys.argv[1:] == ["--session-start"]
    if sys.argv[1:] and not strict and not session_start:
        deny("unsupported guard argument")

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as error:
        deny(f"invalid hook input: {error}")

    if session_start:
        record_session_model(payload)
        return

    agent_type = normalized_agent(payload.get("agent_type"))
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}

    if agent_type in WORKERS:
        check_pinned_agent_definition(agent_type)
        # Subagent hooks share the parent session_id and do not expose a model.
        # Applying the parent's SessionStart model would reject every correctly
        # pinned mixed-model worker. Separate main-agent sessions still have a
        # model-bearing SessionStart record and remain verifiable here.
        if not payload.get("agent_id"):
            check_recorded_model(payload, agent_type)
        check_effort(
            payload,
            agent_type,
            allow_unobservable=agent_type
            != "ecc-vsdd:vsdd-implementation-driver",
        )
        return

    if agent_type not in EXPECTED_EFFORT and not strict:
        return

    if agent_type != "ecc-vsdd:vsdd-orchestrator":
        deny(
            "start Claude Code with --agent ecc-vsdd:vsdd-orchestrator; "
            "inline execution and inherited models are prohibited"
        )

    check_pinned_agent_definition(agent_type)
    check_recorded_model(payload, agent_type)
    check_effort(payload, agent_type)

    if tool_name == "Bash":
        if tool_input.get("run_in_background") not in (None, False):
            deny("the VSDD worker launcher must run in the foreground until completion")
        check_launcher(tool_input.get("command"))
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
        requested = normalized_agent(
            tool_input.get("subagent_type")
            or tool_input.get("agent_type")
            or tool_input.get("name")
        )
        if requested not in ORCHESTRATOR_AGENTS:
            deny(f"Fable cannot launch unpinned agent {requested!r}")
        check_pinned_agent_definition(requested)


if __name__ == "__main__":
    main()
