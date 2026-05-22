# Marker: `astichi_hole`

## Form

```python
astichi_hole(slot)       # scalar expression hole (in expr position)
*astichi_hole(args)      # positional variadic
**astichi_hole(kwargs)   # keyword variadic
```

`slot`, `args`, `kwargs` are **identifiers**, not string literals.

Clause targets are separate from ordinary holes. Use
`astichi_elif(name)` when the target is an additive `elif` branch slot inside
an existing `if` / `elif` chain.

## Semantics

- The argument **names the hole** for builder wiring and internal emitted
  insert metadata.
- It does **not** select hole “kind”; **position in the tree** selects shape:
  - ordinary **expression** position → scalar expression demand
  - `*` / `**` positions → variadic demands
  - **standalone** statement expression in a block → **block** insertion site

## Requirements

- Source must **parse** as valid Python for your target Python version(s).
- Unsupported `*` / `**` placements → error (fail early).

## See also

- [marker-overview.md](marker-overview.md)
- [marker-clause-targets.md](marker-clause-targets.md)
- **[§5.1](../../dev-docs/historical/AstichiApiDesignV1.md)**
