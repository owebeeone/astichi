# Markers: `astichi_for` and `@astichi_insert`

## `astichi_for(domain)`

- Declares a **compile-time** iteration domain.
- The loop remains part of the `Composable` until / unless unrolled; **`build()`
  does not** force eager unrolling (V1 §5.7).

**Supported domains (phase 1):**

- Literal tuples/lists (constant shapes)
- `range(...)` with **compile-time constant** arguments
- Domains tied to **`astichi_bind_external`** values

**Unsupported (phase 1):** arbitrary runtime iterables, arbitrary calls,
comprehensions as the domain expression.

Unpacking in the `for` target follows Python rules at compile time; failure →
error.

## `@astichi_insert(target, order=…)` 

- Inserts a child `Composable` into the hole named **`target`** (identifier).
- **Additive only** in phase 1 — no replacement of an already-filled site.
- **`order`**: lower values run first among inserts into the **same** variadic
  hole; **equal `order` on the same target → error**.

## See also

- [marker-holes.md](marker-holes.md)
- **[§5.7–5.8](../../dev-docs/AstichiApiDesignV1.md)**
