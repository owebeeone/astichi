# Marker: `astichi_hole`

## Form

```python
astichi_hole(slot)       # scalar expression hole (in expr position)
*astichi_hole(args)      # positional variadic
**astichi_hole(kwargs)   # keyword variadic
```

`slot`, `args`, `kwargs` are **identifiers**, not string literals.

## Semantics

- The argument **names the hole** for wiring and `@astichi_insert`.
- It does **not** select hole “kind”; **position in the tree** selects shape:
  - ordinary **expression** position → scalar expression demand
  - `*` / `**` positions → variadic demands per V1 §5.1
  - **standalone** statement expression in a block → **block** insertion site
    (V1 wording)

## Requirements

- Source must **parse** as valid Python for your target Python version(s).
- Unsupported `*` / `**` placements → error (fail early).

## See also

- [marker-overview.md](marker-overview.md)
- **[§5.1](../../dev-docs/AstichiApiDesignV1.md)**
