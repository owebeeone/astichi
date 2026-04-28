# Addressing

When you wire child composables into a parent, you **address** a specific
**hole** (or loop-expanded site) on a named **instance**. The same fluent path
shape is also used by builder-level identifier wiring and by internal
emitted-shell metadata.

## Root-instance-first

Paths start at the **instance** registered on the builder (e.g. **`A`**), then
a **named hole** or slot on that instance:

```text
A.init
A.first[0]
A.second[0, 1]
A.third
```

These are **real handle objects**, not transient parser state (**[§2.4](../../dev-docs/historical/AstichiApiDesignV1.md)**).

## Descendant paths

Addressing can continue through **named descendants** that were preserved across
earlier `build()` stages. The fluent shape is:

```text
<Instance>.<descendant>...[indices].<leaf>
```

Examples:

```text
Pipeline.Root.Parse.body
Pipeline.Root.Parse.rows[1, 2].Normalize.body
Pipeline.Root.Right.total
```

This applies to:

- additive targets such as `builder.Pipeline.Root.Parse.body.add.Step(order=0)`
- identifier wiring such as
  `builder.assign.Step.total.to().Pipeline.Root.Right.total`
- data-driven additive targets such as
  `builder.target(root_instance="Pipeline", ref_path=("Root", "Parse"), target_name="body").add("Step")`
- descriptor targets whose `TargetAddress` carries the same `root_instance`,
  `ref_path`, `target_name`, and `leaf_path` fields
- internal emitted shell refs such as
  `@astichi_insert(body, ref=Pipeline.Root.Parse[1, 2].Normalize)`

Rules:

- A descendant path must resolve to **exactly one** preserved shell on the
  addressed instance.
- Stage-built composables expose their preserved build root name as the first
  descendant segment. Use the full path (`Pipeline.Root...`), not a
  root-elided shortcut (`Pipeline...`).
- **Unknown** descendant refs reject.
- **Ambiguous repeated-use** descendant refs reject; reused built composables
  must carry unique full `ref=` paths.
- On already-registered instances, descendant hops are validated eagerly by the
  fluent builder surface.

## Loop-expanded indices

When the parent snippet uses **`astichi_for`** over a compile-time domain, the
builder exposes **one target per iteration** for inner holes. Indices attach to
the handle:

```python
# Conceptual: inner hole `second` for outer (0,) and inner (1,)
a.second[0, 1].add.B(order=10)
```

Nested loop expansion produces a **Cartesian-style** index tuple per the design
examples in **[§9.2](../../dev-docs/historical/AstichiApiDesignV1.md)** and **§16.1**.

## See also

- [Builder API](builder-api.md)
- [Descriptor API](descriptor-api.md)
- **[§9 — Addressing](../../dev-docs/historical/AstichiApiDesignV1.md)**
