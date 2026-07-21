---
name: vsdd-requirements
description: This skill should be used to create or revise traceable EARS requirements and acceptance criteria for an initialized VSDD specification.
---

# Skill: vsdd-requirements

## Mandatory execution routing

Delegate all requirements authoring and revision to a fresh `vsdd-requirements-worker` (Opus, `xhigh`). When already running as that agent, execute the steps below inline and do not delegate again. Record reversible technical assumptions, but return `BLOCKED` for unresolved product, data-loss, security, compatibility, destructive, or external-authority decisions.

When `VSDD_RUN_CONTEXT` says `execution_mode: unattended`, read every persisted source path and the original request from `run-state.json`, do not ask any elicitation or overwrite question, and do not wait on `CONFIRM`. The persisted artifact gate and fresh Opus review replace manual confirmation.

## Invocation

```
/vsdd-requirements <slug>
```

**Arguments:**

- `<slug>` — kebab-case feature identifier matching an existing `.vsdd/specs/<slug>/` directory

---

## Purpose

Create or refine `requirements.md` for the feature using the EARS (Event-Action-Response-Stimulus) format. The mode is read from `.vsdd/specs/<slug>/progress.md` and determines how the AI interacts with the user.

---

## Execution Steps

### Step 0: Load steering baseline

Read the project steering files as read-only context:

- `.vsdd/specs/_steering/context.md` — domain glossary (use ONLY registered terms in requirements.md)
- `.vsdd/specs/_steering/structure.md` — feature inventory (cross-reference with REQ scope)
- `.vsdd/specs/_steering/open-questions.md` — known unresolved items (avoid creating new requirements that depend on open questions)
- `docs/adr/*.md` — accepted architectural decisions (cite when relevant in NFRs)

If `.vsdd/specs/_steering/` is missing, abort with: "Run `/vsdd-steering` first to bootstrap the steering files."

When a REQ requires a domain term not in `context.md`:

1. Append a new `### Q-NNN: Undefined term '<term>' used in REQ-XXX` entry to `.vsdd/specs/_steering/open-questions.md` with `Impact: product` and `Status: open`.
2. Use the term in REQ with a `> **Glossary pending**: <term>` note.
3. In unattended mode return `BLOCKED` immediately; otherwise resolve in a separate grill-with-docs session before `/vsdd-design`.

### Step 1: Read mode from progress.md

Read `.vsdd/specs/<slug>/progress.md` and extract the `**Mode**:` value.

- If `standard` → follow the Standard Mode flow below.
- If `auto` → follow the Auto Mode flow below.
- If `progress.md` does not exist, abort and instruct the user to run `/vsdd-init <slug>` first.

### Step 2: Load source material (if available)

Read every path in `run-state.json.source_paths`, including `source-notion.md` or `source-request.md`, as background context. Do not output raw source content.

### Step 3: Mode-specific execution

#### Standard Mode

Engineer-led. The AI presents a scaffold and assists completions.

1. Copy the template from `.claude/skills/vsdd-requirements/templates/requirements.md` to `.vsdd/specs/<slug>/requirements.md` (do not overwrite if requirements.md already has real content — ask first).
2. Display the scaffold to the user.
3. Offer to help fill in individual REQ blocks:
   - "Tell me about the first user story and I'll draft the EARS format for you."
   - Suggest missing actors, triggers, or acceptance criteria.
4. After user provides input, write the refined content to `requirements.md`.
5. Validate EARS compliance and flag issues inline (see Checks section).

#### Auto Mode

AI-led. The AI asks Socratic questions, then constructs requirements autonomously.

When `execution_mode: unattended`, do not ask the questions below. Derive and record answers for all seven topics from persisted source material under a `## Elicitation Basis` section containing source paths, evidence, and stated reversible assumptions. If the evidence cannot answer a product, permission, security, compatibility, data-loss, destructive, or external-authority topic, return `BLOCKED` with the one missing decision. Otherwise synthesize and write the complete EARS requirements immediately.

Only for standalone Auto Mode, ask the following questions one at a time:

1. "What problem does this feature solve? Who experiences it?"
2. "Who are the main users of this feature? List their roles."
3. "What are the 3-5 most important things a user needs to be able to do?"
4. "What should the system do when each of those things happens?"
5. "What would make this feature obviously broken or incomplete?"
6. "Are there any constraints — time limits, data limits, permission rules?"
7. "What should NOT happen? Are there edge cases to guard against?"

After collecting answers:

- Synthesize them into EARS-format requirements.
- Write the full `requirements.md` without further prompting.
- State each decision made and its rationale.
- Do not ask for approval before writing — write, then present the result.

---

## EARS Format Reference

Each requirement block follows this structure:

```markdown
## REQ-001: <Short Title>

**User Story**: As a <role>, I want <goal> so that <benefit>.

**When** <triggering event or condition>, **the system shall** <observable system response>.

**Acceptance Criteria**:

- [ ] <Verifiable criterion 1>
- [ ] <Verifiable criterion 2>
- [ ] <Verifiable criterion 3>
```

**EARS keyword guide:**

- `When <event>, the system shall <response>` — event-driven behavior
- `While <condition>, the system shall <response>` — state-driven behavior
- `The system shall <response>` — unconditional behavior
- `If <condition>, then the system shall <response>` — optional/conditional feature
- `Where <feature included>, the system shall <response>` — feature-dependent behavior

---

## Validation Checks (applied after writing)

Run these checks on the completed `requirements.md` and flag issues as inline comments or a summary list:

1. **EARS compliance**: Each REQ has a When/shall clause and at least 2 acceptance criteria.
2. **Ambiguous terms**: Flag words like "fast", "easy", "some", "appropriate", "etc.", "various".
3. **Missing elements**: Each REQ must have an actor (role), trigger, and system response.
4. **Testability**: Each acceptance criterion must be binary (pass/fail), not subjective.
5. **Numbering**: REQ IDs must be sequential with no gaps (REQ-001, REQ-002, ...).

---

## Output

Write the completed requirements to `.vsdd/specs/<slug>/requirements.md`.

Update `.vsdd/specs/<slug>/progress.md`:

- Change `vsdd-requirements` status from `⬜ not started` to `✅ complete`.

Append to `.vsdd/specs/<slug>/change-log.md`:

```
| <YYYY-MM-DD> | vsdd-requirements | requirements.md 作成 (<N> REQs) |
```

---

## Notes

- Requirements must reflect user-observable behavior, not implementation details.
- Avoid implementation language ("the database will store...", "the API will call..."). Write in terms of what the system does from the user's perspective.
- In standalone `--mode auto`, if answers are technically ambiguous, make a stated reversible assumption rather than looping back. In unattended mode apply the stricter decision boundary above. Document every assumption in the REQ block as `> **Assumption**: <text>`.
- Rerunning this skill on an existing `requirements.md` opens an edit session, not a blank slate.

---

== PHASE COMPLETE: vsdd-requirements ==
Artifact: .vsdd/specs/<slug>/requirements.md
Summary:

- Mode read from progress.md
- All persisted source paths loaded as context (if available)
- Requirements elicited and written in EARS format
- EARS compliance checks run; issues flagged
- progress.md updated: vsdd-requirements → complete

[Standalone invocation only]
⏸ WAITING FOR CONFIRMATION
Type `CONFIRM vsdd-review-requirements` to proceed. Or describe changes needed.

Omit the standalone confirmation lines entirely when `execution_mode: unattended`; return the completion artifact to the orchestrator immediately.
