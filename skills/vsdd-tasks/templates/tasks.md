# Tasks: <!-- Feature Name -->

> **Spec slug**: <!-- slug -->
> **Generated**: <!-- YYYY-MM-DD -->
> **Total tasks**: <!-- N -->

---

### TASK-001 — Data contracts (schemas / types)

Implements: REQ-001, REQ-002
Design ref: §4 <!-- data-contract viewpoint section, per tech.md §2 -->
Type: feat
Estimated complexity: S
Files to modify:

- <!-- path/to/schema-or-type-file --> (create)
  Acceptance: Contract rejects invalid inputs; derived types match the design's data shapes

---

### TASK-002 — Core logic / data access

Implements: REQ-003
Design ref: §5 <!-- core-logic viewpoint section -->
Type: feat
Estimated complexity: S
Files to modify:

- <!-- path/to/core-module --> (create)
  Acceptance: Behavior matches REQ-003 acceptance criteria; errors handled per tech.md §3 Conventions

---

### TASK-003 — Tests for core logic

Implements: REQ-003
Design ref: §6 Test Strategy
Type: test
Estimated complexity: M
Files to modify:

- <!-- path/to/test-file --> (create)
- <!-- path/to/test-setup --> (modify)
  Acceptance: Success path and error path both tested; runs green via the test command in tech.md §4

---

_Template: vsdd-tasks skill `templates/tasks.md`_
