# vsdd-design

**Slash command**: `/vsdd-design <slug>`
**Purpose**: Create `design.md` by delegating to the `/ecc:plan` command for architecture and step planning, then merging output into the design template. Stack-agnostic: all technology knowledge comes from `.claude/specs/_steering/tech.md`.

---

## Prerequisites

- `.claude/specs/<slug>/requirements.md` must exist (run `/vsdd-requirements` first)
- `.claude/specs/<slug>/source-notion.md` may optionally be present for additional context

---

## Steps

### 0. Load steering baseline

Read the project steering files as read-only context:

- `.claude/specs/_steering/tech.md` — **the stack contract**: §1 Stack, §2 Design Viewpoints, §3 Conventions, §4 Verification Commands. The design uses only listed technologies unless an ADR justifies a new one, and MUST produce one section per §2 viewpoint.
- `.claude/specs/_steering/structure.md` — current module boundaries and exported symbols (the design MUST respect these boundaries; new features should be additive, not overlapping)
- `.claude/specs/_steering/context.md` — domain glossary (use registered terms only)
- `docs/adr/*.md` — accepted architectural decisions (cite relevant ADRs as `Satisfies: ADR-NNNN` in design sections)

If `.claude/specs/_steering/` is missing, abort with: "Run `/vsdd-steering` first to bootstrap the steering files."

If `tech.md` lacks the §2 Design Viewpoints / §3 Conventions / §4 Verification Commands sections (old format), pause and recommend: "tech.md uses the old format — re-run `/vsdd-steering` to regenerate it." Continue only if the user explicitly accepts designing without viewpoints.

When the design introduces a new architectural decision (new state-management or persistence pattern, new third-party library, new cross-cutting concern):

- Flag it in the design with `> **ADR candidate**: <short rationale>`
- After design sign-off, hand-write `docs/adr/NNNN-<slug>.md` and reference it from the design section.

### 1. Read spec inputs

```
.claude/specs/<slug>/requirements.md      (required)
.claude/specs/<slug>/source-notion.md     (optional)
```

Extract:

- All REQ-XXX IDs and their acceptance criteria
- Non-functional requirements (performance, security, accessibility)
- Scope boundaries (in-scope / out-of-scope)

### 2. Invoke `/ecc:plan`

Call the `/ecc:plan` command with the feature context derived from requirements.md and tech.md.

Build the prompt framing **from tech.md** — do not hardcode any technology:

```
Feature: <feature name from requirements.md>
Context:
<render tech.md §1 Stack as "Layer: Technology — Role" lines>

Conventions:
<render tech.md §3 Conventions as bullet lines>

Requirements summary:
<paste REQ list>

Produce: architecture decisions, file structure, a design plan for each of
the following viewpoints: <list tech.md §2 viewpoint names>, error handling
strategy, and test strategy.
```

**`--mode standard`**: Present the `/ecc:plan` output to the user. Allow the user to review, comment, and guide design interactively before proceeding. Incorporate feedback before scaffolding.

**`--mode auto`**: Run `/ecc:plan` autonomously. Produce `design.md` directly, then append a plain-language "Auto-Design Summary" section at the top of the file for non-engineer reviewers to confirm before implementation starts.

### 3. Scaffold `design.md` from template

Copy the template bundled with this skill (`templates/design.md`) to:

```
.claude/specs/<slug>/design.md
```

Then instantiate the viewpoint placeholder: insert one `## <N>. <Viewpoint section name>` section per row of tech.md §2, between the File Structure Plan and Error Handling Strategy sections, renumbering subsequent sections.

### 4. Merge `/ecc:plan` output into design sections

Fill every section using the `/ecc:plan` output and your own analysis:

| Template section          | Source                                                                |
| ------------------------- | --------------------------------------------------------------------- |
| Overview                  | requirements.md § Scope + /ecc:plan summary                           |
| Architecture diagram      | /ecc:plan architecture decisions → Mermaid                            |
| File Structure Plan       | /ecc:plan file list → mapped to the layout in structure.md            |
| One section per viewpoint | /ecc:plan viewpoint plans → cross-checked with tech.md §2 definitions |
| Error handling strategy   | /ecc:plan error handling → applied per tech.md §3 Conventions         |
| Test strategy             | /ecc:plan test plan → using tech.md §4 Verification Commands          |

### 5. Add traceability links

Every section must end with:

```
Satisfies: REQ-XXX, REQ-YYY
```

If a section satisfies no requirements directly, write:

```
Satisfies: <!-- cross-cutting concern, no direct REQ -->
```

---

## Output

```
.claude/specs/<slug>/design.md
```

---

## Phase Gate

**Next skill after design is always `vsdd-tasks`, never `vsdd-review-plan`.**  
`vsdd-review-plan` requires `tasks.md` and runs only after `/vsdd-tasks`.

Use the same gate for the initial write and for any later revision to `design.md`.

### Initial completion

Update `.claude/specs/<slug>/progress.md`: change `vsdd-design` from `⬜ not started` to `✅ complete`.

Append to `.claude/specs/<slug>/change-log.md`:

```
| <YYYY-MM-DD> | vsdd-design | design.md 作成 |
```

```
== PHASE COMPLETE: vsdd-design ==
Artifact: .claude/specs/<slug>/design.md
Summary:
- Architecture decisions recorded with Mermaid diagrams
- File structure mapped to the project layout from structure.md
- One design section per tech.md §2 Design Viewpoint, all covered
- Error handling and test strategy follow tech.md Conventions / Verification Commands
- All sections include Satisfies: REQ-XXX traceability links

⏸ WAITING FOR CONFIRMATION
Next: CONFIRM vsdd-tasks   (run /vsdd-tasks <slug> — task breakdown)
Or: describe further design changes
```

### After user-requested revisions

Append to `.claude/specs/<slug>/change-log.md`:

```
| <YYYY-MM-DD> | vsdd-design | design.md 更新 (<list changed sections>) |
```

When the user asks to change sections of an existing `design.md` (do not treat this as plan review):

```
== DESIGN REVISED ==
Artifact: .claude/specs/<slug>/design.md（更新箇所: <list sections>）
Summary:
- <bullet: what changed and why>

⏸ WAITING FOR CONFIRMATION
Next (recommended): CONFIRM vsdd-tasks   → /vsdd-tasks <slug>
  - Required if tasks.md is still empty or predates this revision
  - Re-run tasks when file structure / viewpoint sections changed materially
Optional: CONFIRM vsdd-review-plan   → only after tasks.md exists AND user wants plan review without regenerating tasks
Or: describe further design changes

Do NOT recommend CONFIRM vsdd-review-plan as the default next step after design-only work.
```

### If `tasks.md` already exists

If design changed materially and `tasks.md` was generated from the old design:

1. Tell the user tasks may be stale.
2. Recommend `CONFIRM vsdd-tasks` to regenerate (or `/vsdd-tasks <slug>` after confirm).
3. Only after an up-to-date `tasks.md` exists, `CONFIRM vsdd-review-plan` is valid.
