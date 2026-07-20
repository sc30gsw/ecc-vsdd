# Model and effort routing

| Responsibility | Agent | Model | Effort |
| --- | --- | --- | --- |
| Control plane | `vsdd-orchestrator` | Fable | `high` |
| Steering | `vsdd-steering-worker` | Opus | `xhigh` |
| Init/lifecycle | `vsdd-init-worker` | Haiku | `low` |
| Requirements | `vsdd-requirements-worker` | Opus | `xhigh` |
| Requirements review | `vsdd-requirements-reviewer` | Opus | `xhigh` |
| Design | `vsdd-design-worker` | Opus | `xhigh` |
| Tasks | `vsdd-tasks-worker` | Sonnet | `high` |
| Plan review | `vsdd-plan-reviewer` | Opus | `xhigh` |
| Implementation plan review | `vsdd-implementation-workflow-reviewer` | Opus | `xhigh` |
| Implementation | `vsdd-implementation-driver` | Sonnet | `ultracode` |
| Code review | `vsdd-code-reviewer` | Opus | `xhigh` |
| Security review | `vsdd-security-reviewer` | Opus | `xhigh` |
| Ordinary remediation | `vsdd-remediation-worker` | Sonnet | `high` |
| Complex remediation | `vsdd-implementation-driver` | Sonnet | `ultracode` |
| PR | `vsdd-pr-worker` | Sonnet | `medium` |
| Status/bookkeeping | `vsdd-status-worker` | Haiku | `low` |

Never use `inherit`, `max`, fallback models, or Fable for worker work. Treat an unavailable model, effort, workflow capability, or pinned agent as `VSDD RUN BLOCKED`.

Fable must omit the per-invocation `model` parameter and launch every delegated worker only by its unscoped project-local name. Claude Code ignores `hooks`, `mcpServers`, and `permissionMode` in plugin subagents, so `UserPromptSubmit` atomically materializes protected project agents from the immutable plugin templates with the literal installed guard path. Because Claude Code fixes the agent registry before prompt submission, the first parent Fable may invoke only the exact prompt-bound relay start command and repeat its exact 45-second wait command; the relay detaches one child Fable session after the proxies exist and repeats the same exact prompt without binding the full workflow to one Bash call. The runtime rejects replay or modification of that relay, plugin-scoped worker launches, and materialized-file tampering before launch and every tool use. It also rejects any model override because Claude Code resolves it before agent frontmatter and rejects a non-`inherit` global `CLAUDE_CODE_SUBAGENT_MODEL` in the mixed-model orchestration session. Claude subagent hook payloads share the parent `session_id`, do not expose the subagent model, and may omit effective effort. The guard therefore never misuses parent Fable values as worker values: it validates pinned source frontmatter, the protected proxy identity, and effort whenever exposed. Separate main-agent sessions validate their own model-bearing `SessionStart` when present and always require effective effort. The Sonnet Dynamic Workflow launcher may set `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` only inside its isolated all-Sonnet implementation session.

`vsdd-implementation-driver` intentionally omits agent-frontmatter `effort`. Claude Code custom-agent frontmatter does not accept `ultracode`; the bundled launcher is the sole entry point and pins the session with `--effort ultracode`. The hook validates its effective `xhigh` reasoning level while the launcher prompt activates Dynamic Workflow orchestration.

Run every review in a new agent with disk-only context. Requirements, plan, implementation-workflow, code, and security reviews must never reuse their author session. Run code and security review as separate agents against the same commit.
