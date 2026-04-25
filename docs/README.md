# Astichi user documentation

**astichi** is a library for **composing** Python-shaped fragments: compile
marker-bearing source into a **`Composable`**, wire
fragments with a **builder**, then **`materialize`** and **`emit`** when you
need runnable or inspectable Python.

These pages describe the **current user-facing behavior** in `src/` and the
test suite.

For the active project snapshot and known gaps, start with
**[`../dev-docs/AstichiSingleSourceSummary.md`](../dev-docs/AstichiSingleSourceSummary.md)**.
Older V1 design docs remain useful background, but some planned details there
no longer match the live implementation exactly.

## Where to start

| You want… | Read |
|-----------|------|
| End-to-end flow (compile → build → materialize → emit) | [Guide: Using the API](guide/using-the-api.md) |
| Phase-1 error categories | [Reference: Errors](reference/errors.md) |
| Public imports and submodules | [Reference: Public API](reference/public-api.md) |
| `compile(...)` and source origins | [Reference: Compile API](reference/compile-api.md) |
| `Composable.emit` / `materialize` | [Reference: Composable API](reference/composable-api.md) |
| Builder (fluent, handle-oriented, and data-driven named API) | [Reference: Builder API](reference/builder-api.md) |
| Target addressing (`A.first[0]`, …) | [Reference: Addressing](reference/addressing.md) |
| Marker vocabulary | [Reference: Markers](reference/marker-overview.md) |

## Layout

- **`guide/`** — short, task-oriented walkthroughs.
- **`reference/`** — compact, linkable API and behavior.

Contributor design notes, milestones, and internals live under
**[`../dev-docs/`](../dev-docs/)**.
