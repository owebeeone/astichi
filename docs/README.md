# Astichi user documentation

**astichi** is a library for **ahead-of-time** composition of Python-shaped
fragments: compile marker-bearing source into a **`Composable`**, wire
fragments with a **builder**, then **`materialize`** and **`emit`** when you
need runnable or inspectable Python.

These pages describe the **intended user-facing behavior** once Astichi V1 is
complete. Normative detail lives in
**[`../dev-docs/AstichiApiDesignV1.md`](../dev-docs/AstichiApiDesignV1.md)**.

## Where to start

| You want… | Read |
|-----------|------|
| End-to-end flow (compile → build → materialize → emit) | [Guide: Using the API](guide/using-the-api.md) |
| Phase-1 error categories | [Reference: Errors](reference/errors.md) |
| Public imports and submodules | [Reference: Public API](reference/public-api.md) |
| `compile(...)` and source origins | [Reference: Compile API](reference/compile-api.md) |
| `Composable.emit` / `materialize` | [Reference: Composable API](reference/composable-api.md) |
| Builder (fluent and handle-oriented) | [Reference: Builder API](reference/builder-api.md) |
| Target addressing (`A.first[0]`, …) | [Reference: Addressing](reference/addressing.md) |
| Marker vocabulary | [Reference: Markers](reference/marker-overview.md) |

## Layout

- **`guide/`** — short, task-oriented walkthroughs.
- **`reference/`** — compact, linkable API and behavior.

Contributor design notes, milestones, and internals live under
**[`../dev-docs/`](../dev-docs/)**.
