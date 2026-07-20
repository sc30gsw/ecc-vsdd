---
name: vsdd-steering
description: This skill should be used to bootstrap or refresh repository steering files, stack verification commands, conventions, structure, domain context, and open questions for VSDD.
---

# Skill: vsdd-steering

## Mandatory execution routing

Delegate all artifact work to a fresh `vsdd-steering-worker` (Opus, `xhigh`). When already running as that agent, execute the steps below inline and do not delegate again. Never generate Steering with the invoking main model.

When `VSDD_RUN_CONTEXT` says `execution_mode: unattended`, obey the bundled runtime contract: do not stop for routine confirmation and do not emit a phase-local confirmation gate. Persist reversible technical assumptions as `assumed`, never as `open` or `DRAFT`. Return `BLOCKED` instead of guessing when a decision affects product behavior, data loss, security, compatibility, destructive operations, or external authority.

## Invocation

```
/vsdd-steering [--force] [--dry-run]
```

**Arguments:**

- `--force` — overwrite the existing `_steering/` and re-bootstrap from scratch (manual sections are also reset).
- `--dry-run` — preview only. No files are written; planned changes go to stdout.

Behavior when no argument is given:

- `.claude/specs/_steering/` missing → **bootstrap** (creates four files).
- Already present → **refresh** (regenerates auto sections only, preserves manual sections).

---

## Purpose

Generate and update the four steering files under `.claude/specs/_steering/`. These are the baseline files that guarantee coherence between VSDD specs and the codebase **before** any spec is created.

**`tech.md` is the single source of truth for everything stack-specific.** All other VSDD skills (`vsdd-design`, `vsdd-tasks`, `vsdd-impl`, `vsdd-review*`) are stack-agnostic: they define process only and read stack knowledge from `tech.md` at runtime. This skill is the only place where the project's technology is inspected and recorded.

| File                | Role                                                               | Auto / Manual                   |
| ------------------- | ------------------------------------------------------------------ | ------------------------------- |
| `tech.md`           | Stack table, Design Viewpoints, Conventions, Verification Commands | Auto-draft + interview confirm  |
| `structure.md`      | Source layout and exported symbols                                 | Auto + manual notes             |
| `context.md`        | Domain glossary (semantic notes)                                   | Manual (LLM draft allowed)      |
| `open-questions.md` | Unresolved items + auto-detected flags                             | Auto-append + manual resolution |

ADRs are kept separately under `docs/adr/`. This skill does NOT create ADRs.

---

## Execution Steps

### Step 1: Parse arguments

- `--force` detected: move existing `_steering/` to `_steering/.bak/` and regenerate.
- `--dry-run` detected: redirect all writes to stdout as a unified diff preview.

### Step 2: Ensure `_steering/` directory exists

```bash
mkdir -p .claude/specs/_steering/
```

### Step 3: Generate `tech.md` (detect → draft → interview → confirm)

`tech.md` has exactly four sections. Scaffold from the template bundled with this skill (`templates/tech.md`).

#### 3a. Detect

Inspect the project for stack signals:

| Signal               | Examples                                                                                                                                           |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dependency manifests | `package.json`, `Gemfile`, `go.mod`, `pyproject.toml` / `requirements.txt`, `Cargo.toml`, `pom.xml` / `build.gradle*`, `composer.json`, `*.csproj` |
| Lint / format config | `.oxlintrc*`, `eslint.config.*`, `.rubocop.yml`, `ruff.toml`, `.golangci.yml`, ...                                                                  |
| Test config          | `vitest.config.*`, `jest.config.*`, `spec/`, `*_test.go`, `pytest.ini`, ...                                                                         |
| CI workflows         | `.github/workflows/*` — reveals the real verification commands                                                                                      |

**Greenfield fallback**: if no manifests are found, use the interview in standalone mode. In unattended mode, infer only from persisted source and repository evidence; return `BLOCKED` when the intended stack or verification commands cannot be established safely. Set frontmatter `mode: interview` or `mode: unattended-inference`.

#### 3b. Draft the four sections

1. **Stack** — `Layer | Technology | Role` rows derived from the manifests (runtime, framework, data access, UI, state, validation, testing, lint). One row per major dependency with a one-line purpose note.
2. **Design Viewpoints** — propose from the catalog at `references/design-viewpoints.md` (in this skill's directory), based on the detected project type(s): web-frontend, web-api, fullstack (= combine both), cli, batch, mobile, library. Each viewpoint row names the `design.md` section it produces.
3. **Conventions** — error-handling policy, validation policy, import/naming rules, and other implementation rules detected from config or stated by the user. If the project keeps rules under `.claude/rules/`, link those files here instead of copying their content.
4. **Verification Commands** — the exact lint / format / type-check / test commands (from package scripts, Makefile, Rake tasks, or CI).

#### 3c. Confirm or record assumptions

For standalone invocation, present the draft to the user before writing:

- **Stack table**: confirm or correct rows (detection can mislabel roles).
- **Design Viewpoints**: this is a judgment call — the user must approve which viewpoints every future `design.md` will be required to cover.
- **Conventions / Verification Commands**: confirm; ask for anything detection could not see.

For an orchestrated `vsdd-run`, validate the draft against manifests, CI, repository conventions, and supplied source material without pausing. Record every reversible technical assumption in the artifact. If the evidence leaves a product, data-loss, security, compatibility, destructive-operation, or external-authority decision unresolved, return `BLOCKED` with the exact question instead of writing a guessed answer.

Frontmatter:

```yaml
---
generated: <ISO8601>
source: <manifest file(s) | interview>
mode: auto | interview
---
```

Preserve any `<!-- MANUAL:START -->` ... `<!-- MANUAL:END -->` section verbatim on refresh.

### Step 4: Regenerate `structure.md` (auto + manual)

Detect the source layout (common roots: `src/`, `app/`, `lib/`, `cmd/`, `internal/`, or the layout recorded in `tech.md` Conventions). For each module/feature directory, collect:

- subdirectory layout
- exported types / public symbols, using the idiom of the detected language (e.g. `export` statements, public classes/modules, package-level functions)

Frontmatter:

```yaml
---
generated: <ISO8601>
source: <source root(s)>
mode: auto
---
```

Render each module as a row in a table. Preserve any `<!-- MANUAL:START -->` ... `<!-- MANUAL:END -->` section.

### Step 5: Append glossary entries to `context.md` (LLM)

Preserve any existing content in `context.md`. For each module, if a relevant domain term is not yet defined, append a section. Standalone uncertain entries use `<!-- DRAFT YYYY-MM-DD -->`. Unattended entries supported by repository evidence use `<!-- ASSUMED YYYY-MM-DD source:<path> -->`:

```markdown
### Supplier

Wholesale electricity company. Connected to Consumer via a contract.

<!-- ASSUMED 2026-05-28 source:src/domain/supplier.ts -->
```

Frontmatter:

```yaml
---
last-grilled: <YYYY-MM-DD> # date when grill-with-docs last confirmed entries
mode: manual
---
```

Never leave a `DRAFT` marker at the unattended completion gate. Keep evidence-backed reversible entries as `ASSUMED`; leave high-impact uncertainty as DRAFT and return `BLOCKED`. When the user confirms an entry during a grill session, remove its marker manually.

### Step 6: Run detection rules → append to `open-questions.md`

Run these four rules and append matches to the `## Open` section using `Q-XXX` IDs (skip if the same ID already exists):

1. **Term collision**: the same stem appears across multiple modules (e.g. `Group` appears in `linked-groups` / `mail-groups` / `users`).
2. **Unused symbols**: run the project's dead-code tool **only if one is recorded in `tech.md` §4 Verification Commands**; skip otherwise.
3. **Version drift**: **only if the project has a `.claude/rules/` directory** — flag a major version mismatch between a dependency manifest and the rule documents. Skip silently when the directory is absent.
4. **Opaque module**: a directory exposing no types/contracts — the agent subjectively flags it as "responsibility unclear".

Entry format:

```markdown
### Q-001: <title>

- Detected from: <path>
- Detected on: YYYY-MM-DD
- Rule: <1-4>
- Detail: <short>
- Impact: technical|product|data-loss|security|compatibility|destructive|external-authority
- Status: open
```

In unattended mode, set reversible technical findings to `Status: assumed` and add `Assumption` plus `Evidence`. Leave every other finding `open` and return `BLOCKED`.

### Step 7: Emit diff report

`--dry-run`: emit unified diff of planned changes for all four files to stdout.
Normal run: list changed files and report the number of new `Q-XXX` entries to stdout.

If **one or more** new `Q-XXX` entries were added, append to stdout:

```
⚠ NEW OPEN QUESTIONS: <count>
When this skill runs standalone, this is a warning only.
When invoked from an unattended run, every remaining `Status: open` entry halts the workflow.
```

---

## Caller integration

Designed to be invoked internally by `/vsdd-init` (Phase 2 wiring):

1. `/vsdd-init <slug>` starts.
2. `/vsdd-steering` runs internally.
3. The runtime preflight verifies that no `open` or `DRAFT` item remains.
4. Evidence-backed reversible assumptions may continue as `assumed`; every remaining open item halts.

(Phase 2: `/vsdd-requirements`, `/vsdd-design`, and the `/vsdd-review-*` skills also consume the steering files as read-only baselines.)

---

## Notes

- This skill does NOT create ADRs. When a new ADR is needed, hand-write `docs/adr/NNNN-<slug>.md`.
- Everything under `_steering/` is tracked in git so that manual sections survive as history.
- `_steering/.bak/` is `.gitignore`-d (used as a backup target by `--force`).
- Immediately after bootstrap, manual sections are empty. Fill them in iteratively via grill-with-docs.
- **Migration from the old tech.md format** (stack list only, no §2–§4): downstream skills detect the missing sections and recommend re-running `/vsdd-steering`. Refresh regenerates the four-section format while preserving manual notes.

---

== PHASE COMPLETE: vsdd-steering ==
Artifact: .claude/specs/\_steering/
Summary:

- Regenerated or bootstrapped tech.md / structure.md / context.md / open-questions.md
- tech.md confirmed by user: Stack, Design Viewpoints, Conventions, Verification Commands
- Ran detection rules 1-4 and appended findings to open-questions.md
- Reported the number of new open questions

⏸ Caller decision

- Direct user invocation: warn only and exit
- `/vsdd-init` internal invocation (Phase 2): continue if new question count is 0, halt if ≥ 1
