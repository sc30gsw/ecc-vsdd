# vsdd-tasks

**Slash command**: `/vsdd-tasks <slug>`
**Purpose**: Generate `tasks.md` (TASK-001..N) and `progress.md` from `requirements.md` and `design.md`.

---

## Prerequisites

- `.claude/specs/<slug>/requirements.md` must exist
- `.claude/specs/<slug>/design.md` must exist (run `/vsdd-design` first)

---

## Steps

### 1. Read spec inputs

```
.claude/specs/<slug>/requirements.md
.claude/specs/<slug>/design.md
```

Extract:

- Every REQ-XXX ID with its acceptance criteria
- Every design section (§X.X) with its title
- File structure plan (§3) for deriving "Files to modify"
- Viewpoint sections (one per tech.md §2 Design Viewpoint) for scoping tasks

### 2. Decompose requirements into tasks

Rules for decomposition:

- Each TASK must implement one or more REQ-XXX entries
- Each TASK maps to one or more design sections via `Design ref`
- One TASK per logical unit of work (one file, one hook, one component, or one test suite)
- If a task feels L complexity, split it
- Ordering: derive from design.md section dependencies — data contracts/schemas first, then core logic / data access, then interface layers (API endpoints / UI components), then tests and integration/E2E. Follow the layering implied by tech.md §1 Stack.

Complexity guidelines:

| Size | Meaning                                    |
| ---- | ------------------------------------------ |
| S    | ~30 min — single file, clear scope         |
| M    | ~2 h — multiple related files, clear scope |
| L    | ~4+ h — warn user; recommend splitting     |

### 3. Write `tasks.md`

Use the format below for every task. Copy the template bundled with this skill (`templates/tasks.md`) and fill it in.

```markdown
### TASK-001 — <title>

Implements: REQ-001, REQ-002
Design ref: §4 <viewpoint section title>
Type: feat | test | refactor | docs | chore
Estimated complexity: S | M | L
Files to modify:

- <path/to/new/file> (create)
- <path/to/existing/file> (modify)
  Acceptance: matches REQ-001 acceptance criteria
```

Field rules:

- `Implements`: comma-separated REQ-XXX IDs; every REQ must appear in at least one task
- `Design ref`: `§X.X <section title>` format; every design section must appear in at least one task
- `Type`: one of `feat`, `test`, `refactor`, `docs`, `chore`
- `Files to modify`: list with `(create)` or `(modify)` suffix
- `Acceptance`: copy or paraphrase directly from the REQ acceptance criteria

### 4. Update `progress.md`

Do NOT overwrite `progress.md`. It was created by `vsdd-init` and contains the Phase Status table and initialization metadata. Append the following section to the existing file:

```markdown
## Tasks

| Task     | Title                 | Status  | Started | Completed |
| -------- | --------------------- | ------- | ------- | --------- |
| TASK-001 | <title from tasks.md> | pending | —       | —         |
| TASK-002 | <title from tasks.md> | pending | —       | —         |
```

One row per TASK, all set to `pending`. Status values: `pending` | `in-progress` | `done` | `blocked`.

Also update the Phase Status table already in `progress.md`: change `vsdd-tasks` from `⬜ not started` to `✅ complete`.

Append to `.claude/specs/<slug>/change-log.md`:

```
| <YYYY-MM-DD> | vsdd-tasks | tasks.md 作成 (<N> TASKs) |
```

### 5. Mode-specific behaviour

**`--mode standard`**: Present the task breakdown to the user. Discuss granularity and ordering. Allow the user to add, remove, or reorder tasks before writing the files.

**`--mode auto`**: Decompose autonomously. If any task has L complexity, add a warning comment directly in `tasks.md` above that task:

```markdown
<!-- ⚠️ L-complexity task — consider splitting before implementation -->
```

---

## Output

```
.claude/specs/<slug>/tasks.md
.claude/specs/<slug>/progress.md
```

---

## Validation before writing

Before writing the files, verify:

1. Every REQ-XXX from requirements.md appears in at least one `Implements:` field
2. Every design section §X.X from design.md appears in at least one `Design ref:` field
3. No duplicate TASK-XXX IDs
4. No TASK is missing an `Implements:` field

If any check fails, report the gap and ask the user whether to auto-fill or stop.

---

## Phase Gate

```
== PHASE COMPLETE: vsdd-tasks ==
Artifact: .claude/specs/<slug>/tasks.md
Artifact: .claude/specs/<slug>/progress.md
Summary:
- TASK-001 through TASK-NNN generated covering all REQ-XXX entries
- All design sections §X.X covered by at least one Design ref
- Complexity estimates provided; L tasks flagged for splitting
- progress.md initialised with all tasks in pending state
- Mode recorded as standard|auto in progress.md header

⏸ WAITING FOR CONFIRMATION
Type `CONFIRM vsdd-review-plan` to proceed, or describe changes needed.
```
