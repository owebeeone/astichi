# Markers: binds and exports

## `astichi_bind_once(name, expr)`

Current status: **recognized only**.

- Astichi currently recognizes the marker during `compile(...)`.
- The current materialize pipeline does **not** lower or strip it yet.
- Do **not** rely on this marker as finished user-facing semantics.

## `astichi_bind_shared(name, expr)`

Current status: **recognized only**.

- Astichi currently recognizes the marker during `compile(...)`.
- The current materialize pipeline does **not** lower or strip it yet.
- Do **not** rely on this marker as finished user-facing semantics.

## `astichi_bind_external(name)`

- Declares a **compile-time** input keyed by `name` (identifier).
- Values are applied through the current concrete composable API:
  **`.bind(mapping=None, /, **values)`**.
- Values come from **composition context**, not from normal runtime name lookup
  of the generated module.
- Current supported value shapes are `None`, `bool`, `int`, `float`, `str`, and
  recursively nested `tuple` / `list` / `dict` values using those element
  types.

## `astichi_export(name)`

- Exposes a binding from the snippet as a **supply port** on the resulting
  `Composable`.
- The **public** export name is the declared name; internal hygiene must not
  change that public name.

## Identifier keys

`name` arguments use the same **bare identifier** rule as `astichi_hole`.

## See also

- [public-api.md](public-api.md)
- **[§5.2–5.6](../../dev-docs/AstichiApiDesignV1.md)**
