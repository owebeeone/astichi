# Addressing

When you wire child composables into a parent, you **address** a specific
**hole** (or loop-expanded site) on a named **instance**.

## Root-instance-first

Paths start at the **instance** registered on the builder (e.g. **`A`**), then
a **named hole** or slot on that instance:

```text
A.init
A.first[0]
A.second[0, 1]
A.third
```

These are **real handle objects**, not transient parser state (**[§2.4](../../dev-docs/AstichiApiDesignV1.md)**).

## Loop-expanded indices

When the parent snippet uses **`astichi_for`** over a compile-time domain, the
builder exposes **one target per iteration** for inner holes. Indices attach to
the handle:

```python
# Conceptual: inner hole `second` for outer (0,) and inner (1,)
a.second[0, 1].add.B(order=10)
```

Nested loop expansion produces a **Cartesian-style** index tuple per the design
examples in **[§9.2](../../dev-docs/AstichiApiDesignV1.md)** and **§16.1**.

## Deep traversal

Arbitrary **deep** paths beyond the phase-1 **root-instance-first** model are
**not** part of the locked surface; prefer flattening composition or extending
the design before relying on deeper syntax.

## See also

- [Builder API](builder-api.md)
- **[§9 — Addressing](../../dev-docs/AstichiApiDesignV1.md)**
