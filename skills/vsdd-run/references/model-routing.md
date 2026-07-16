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

Fable must omit the per-invocation `model` parameter when launching every pinned plugin agent. The runtime guard rejects any such override because Claude Code resolves it before agent frontmatter. It also rejects a non-`inherit` global `CLAUDE_CODE_SUBAGENT_MODEL` in the mixed-model orchestration session and verifies the immutable plugin agent frontmatter before launch and again in worker hooks. Claude subagent hook payloads share the parent `session_id`, do not expose the subagent model, and may omit effective effort. The guard therefore never misuses parent Fable values as worker values: it always validates pinned frontmatter, validates effort when the worker payload exposes it, and rejects every observed disagreement. Separate main-agent sessions validate their own model-bearing `SessionStart` when present and always require effective effort. The Sonnet Dynamic Workflow launcher may set `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` only inside its isolated all-Sonnet implementation session.

`vsdd-implementation-driver` intentionally omits agent-frontmatter `effort`. Claude Code custom-agent frontmatter does not accept `ultracode`; the bundled launcher is the sole entry point and pins the session with `--effort ultracode`. The hook validates its effective `xhigh` reasoning level while the launcher prompt activates Dynamic Workflow orchestration.

Run every review in a new agent with disk-only context. Requirements, plan, implementation-workflow, code, and security reviews must never reuse their author session. Run code and security review as separate agents against the same commit.
