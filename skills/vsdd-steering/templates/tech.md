---
generated: <!-- ISO8601 -->
source: <!-- package.json | Gemfile | go.mod | pyproject.toml | interview | ... -->
mode: <!-- auto | interview -->
---

# Tech Steering

> Single source of truth for everything stack-specific in this project.
> All VSDD skills (`vsdd-design`, `vsdd-impl`, `vsdd-review*`, `vsdd-tasks`) read this file
> at runtime instead of hardcoding any technology. Re-run `/vsdd-steering` when the stack changes.

## 1. Stack

<!-- One row per major technology. Drafted from dependency manifests; confirmed by the user. -->

| Layer                     | Technology                      | Role                           |
| ------------------------- | ------------------------------- | ------------------------------ |
| <!-- e.g. Runtime -->     | <!-- e.g. Node.js 22 (pnpm) --> | <!-- one-line purpose note --> |
| <!-- e.g. Framework -->   | <!-- e.g. Next.js / Rails -->   | <!-- -->                       |
| <!-- e.g. Data access --> | <!-- e.g. ActiveRecord -->      | <!-- -->                       |
| <!-- e.g. Validation -->  | <!-- e.g. Valibot / dry-rb -->  | <!-- -->                       |
| <!-- e.g. Testing -->     | <!-- e.g. Vitest / RSpec -->    | <!-- -->                       |

## 2. Design Viewpoints

<!-- Every spec's design.md in this project MUST contain one section per viewpoint listed here.
     Pick from the catalog (vsdd-steering skill: references/design-viewpoints.md) or add
     project-specific viewpoints. This list is a judgment call — always user-confirmed. -->

| Viewpoint                      | design.md section it produces   | Why it applies here             |
| ------------------------------ | ------------------------------- | ------------------------------- |
| <!-- e.g. State Management --> | <!-- State Management -->       | <!-- SPA with server cache -->  |
| <!-- e.g. Data Model -->       | <!-- Data Model & Migration --> | <!-- owns persistent tables --> |

## 3. Conventions

<!-- Implementation rules every task must follow. vsdd-impl enforces them at every commit;
     vsdd-review checks the diff against each rule. If the project keeps rules under
     .claude/rules/, link those files here instead of copying their content. -->

- Error handling: <!-- e.g. Result type, no bare try/catch | exceptions + central handler -->
- Validation: <!-- e.g. schema validation at all system boundaries -->
- Imports / exports: <!-- e.g. path alias only; no default exports outside pages/ -->
- Naming / structure: <!-- e.g. feature-first layout under src/features/ -->
- <!-- additional rules, or links: see .claude/rules/<file>.md -->

## 4. Verification Commands

<!-- Exact commands. vsdd-impl runs these in every TDD cycle; vsdd-review re-runs them. -->

| Purpose             | Command                                             |
| ------------------- | --------------------------------------------------- |
| Lint                | <!-- e.g. pnpm lint / bundle exec rubocop -->       |
| Format check        | <!-- e.g. pnpm fmt:check (omit if N/A) -->          |
| Type check          | <!-- e.g. pnpm typecheck / mypy . (omit if N/A) --> |
| Test                | <!-- e.g. pnpm test:run / bundle exec rspec -->     |
| All-in-one (if any) | <!-- e.g. pnpm check -->                            |

<!-- MANUAL:START -->
<!-- Free-form notes preserved verbatim across refreshes -->
<!-- MANUAL:END -->
