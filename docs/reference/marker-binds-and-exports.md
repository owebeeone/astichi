# Markers: binds and exports

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

## Reserved marker names

`astichi_bind_once(name, expr)` and `astichi_bind_shared(name, expr)` are
reserved and obsolete marker names. Astichi rejects them during `compile(...)`
so the names cannot accidentally mean something else.

- For single-evaluation reuse, use ordinary Python assignment.
- For shared state across composition boundaries, use enclosing Python state
  plus `astichi_import`, `astichi_pass`, `astichi_export`, or `builder.assign`.

## See also

- [scoping-hygiene.md](scoping-hygiene.md)
- [public-api.md](public-api.md)
- **[§5.2–5.6](../../dev-docs/historical/AstichiApiDesignV1.md)**
