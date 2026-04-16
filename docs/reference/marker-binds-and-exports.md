# Markers: binds and exports

## `astichi_bind_once(name, expr)`

- Evaluates **`expr`** once per rules of the enclosing region; binding is **local**
  to that lowered region.
- If the value is used multiple times, reuse is **required** (single evaluation).

## `astichi_bind_shared(name, expr)`

- Like `bind_once`, but the binding **survives** loop / structural expansion
  inside the region (shared state, accumulators).

## `astichi_bind_external(name)`

- Declares a **compile-time** input keyed by `name` (identifier).
- Values come from **composition / materialization context**, not from normal
  runtime name lookup of the generated module.
- Phase-1 allowed value shapes include constants, tuples/lists, and other
  caller-supplied compile-time values (V1 §5.4).

## `astichi_export(name)`

- Exposes a binding from the snippet as a **supply port** on the resulting
  `Composable`.
- The **public** export name is the declared name; internal hygiene must not
  change that public name.

## Identifier keys

`name` arguments use the same **bare identifier** rule as `astichi_hole`.

## See also

- **[§5.2–5.6](../../dev-docs/AstichiApiDesignV1.md)**
