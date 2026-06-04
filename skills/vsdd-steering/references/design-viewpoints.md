# Design Viewpoint Catalog

Reference data for `/vsdd-steering` (tech.md §2 Design Viewpoints drafting). Read on demand —
NOT loaded into every prompt. Each viewpoint = a design concern that, once selected into a
project's `tech.md`, becomes a **required section** in every spec's `design.md`.

A project combines groups freely:

- fullstack web app → `web-frontend` + `web-api` (+ Common)
- API-only service → `web-api` (+ Common)
- internal tool CLI → `cli` (+ Common)

Viewpoint names below are suggestions — rename or add project-specific viewpoints as needed.
What matters is that tech.md §2 lists each one with the design.md section it produces.

---

## Common (consider for every project type)

| Viewpoint           | The design.md section must answer                                   |
| ------------------- | -------------------------------------------------------------------- |
| Data Contracts      | What types/schemas cross module boundaries? Where are they defined?  |
| AuthZ / Permissions | Who may invoke this feature? Where is access enforced?               |
| Observability       | What is logged/measured? How are failures diagnosed in production?   |

## web-frontend

| Viewpoint            | The design.md section must answer                                                            |
| -------------------- | -------------------------------------------------------------------------------------------- |
| State Management     | Which state is server / client / URL / form state? Which tool owns each? Where does it live? |
| Component Hierarchy  | Container/presentation split, prop flow, responsibility per component                        |
| API Integration      | Which endpoints are consumed, through which client layer, with what error mapping?           |
| Routing & Navigation | New routes/URL params, navigation guards, deep-link behavior                                 |
| Accessibility        | Keyboard flows, roles/labels, focus management for new UI                                    |

## web-api (backend)

| Viewpoint                 | The design.md section must answer                                               |
| ------------------------- | -------------------------------------------------------------------------------- |
| Data Model & Persistence  | New/changed tables or documents, indexes, constraints, ownership                 |
| Migration Plan            | Schema migration steps, backward compatibility, rollout/rollback                 |
| API Contract              | Exposed endpoints/messages: method, path, request/response schema, status codes  |
| Domain Logic Placement    | Which layer owns the business rules (service / model / usecase)?                 |
| Transaction & Consistency | Transaction boundaries, idempotency, concurrency control                         |
| Background Jobs           | Queues/schedulers introduced, retry policy, failure handling                     |

## cli

| Viewpoint       | The design.md section must answer                            |
| --------------- | ------------------------------------------------------------- |
| Command Surface | Subcommands, args/flags, exit codes, help text                |
| Configuration   | Config files, env vars, precedence rules                      |
| I/O Formats     | stdin/stdout/stderr contracts, machine-readable output modes  |

## batch / pipeline

| Viewpoint                  | The design.md section must answer                           |
| -------------------------- | ------------------------------------------------------------ |
| Scheduling & Triggers      | What starts the job? Cron, event, manual? Overlap handling?  |
| Idempotency & Retry        | Re-run safety, checkpointing, partial-failure recovery       |
| Data Volume & Partitioning | Expected volume, batching/partition strategy, backpressure   |

## mobile

| Viewpoint             | The design.md section must answer                       |
| --------------------- | --------------------------------------------------------- |
| Screen Flow           | New screens, navigation graph, state restoration          |
| Offline & Sync        | Offline behavior, conflict resolution, sync triggers      |
| Platform Capabilities | Permissions, platform APIs used, OS-version constraints   |

## library

| Viewpoint                  | The design.md section must answer                      |
| -------------------------- | -------------------------------------------------------- |
| Public API Surface         | Exported symbols, naming, stability guarantees           |
| Versioning & Compatibility | Semver impact, deprecation path, breaking-change policy  |
| Examples & Docs            | What usage examples/docs ship with the change?           |
