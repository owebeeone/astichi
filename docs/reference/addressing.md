# Addressing

When you wire child composables into a parent, you **address** a specific
**hole** (or loop-expanded site) on a named **instance**. The same fluent path
shape is also used by builder-level identifier wiring and by emitted
`@astichi_insert(..., ref=...)` shell metadata.

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

## Descendant paths

Addressing can continue through **named descendants** that were preserved across
earlier `build()` stages. The fluent shape is:

```text
<Instance>.<descendant>...[indices].<leaf>
```

Examples:

```text
Pipeline.Parse.body
Pipeline.Parse.rows[1, 2].Normalize.body
Pipeline.Right.total
```

This applies to:

- additive targets such as `builder.Pipeline.Parse.body.add.Step(order=0)`
- identifier wiring such as
  `builder.assign.Step.total.to().Pipeline.Right.total`
- emitted shell refs such as
  `@astichi_insert(body, ref=Pipeline.Parse[1, 2].Normalize)`

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

## See also

- [Builder API](builder-api.md)
- **[§9 — Addressing](../../dev-docs/AstichiApiDesignV1.md)**
