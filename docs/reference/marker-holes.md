# Marker: `astichi_hole`

## Form

```python
astichi_hole(slot)       # scalar expression hole (in expr position)
*astichi_hole(args)      # positional variadic
**astichi_hole(kwargs)   # keyword variadic

with astichi_hole(body) as astichi_fallback:
    return None          # default block body
```

`slot`, `args`, `kwargs`, and `body` are **identifiers**, not string
literals.

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
- `with astichi_hole(body) as astichi_fallback:` declares a **defaulted block
  hole**. The whole `with` statement is the hole. If builder inserts target
  `body`, those inserts replace the fallback suite; if no insert targets that
  site, the fallback suite is lowered in place during `materialize()`.
- `astichi_fallback` is a required sentinel name, not an application variable.
  Use exactly `as astichi_fallback` so Astichi can distinguish the marker form
  from ordinary context-manager code.
- Fallback contents are branch-inactive until selected. Markers inside a
  discarded fallback do not create demands; markers inside a selected fallback
  are recognized and validated during materialization.
- Defaulted block holes are additive like ordinary statement block holes.
  `describe()` exposes them as holes with `has_default=True`.

## Requirements

- Source must **parse** as valid Python for your target Python version(s).
- Unsupported `*` / `**` placements → error (fail early).
- Defaulted block holes must use one context manager, exactly
  `astichi_hole(name)`, exactly `as astichi_fallback`, and a non-empty fallback
  suite.
- `astichi_pyimport(...)` is not valid inside a defaulted fallback suite.

## Examples

- Unfilled defaulted block hole:
  [defaulted_block_hole_empty/root.py](https://github.com/owebeeone/astichi/blob/main/docs/reference/snippets/statement/defaulted_block_hole_empty/root.py)
  →
  [defaulted_block_hole_empty_generated.py](https://github.com/owebeeone/astichi/blob/main/docs/reference/snippets/statement/defaulted_block_hole_empty/defaulted_block_hole_empty_generated.py)
- Filled defaulted block hole:
  [defaulted_block_hole_filled/root.py](https://github.com/owebeeone/astichi/blob/main/docs/reference/snippets/statement/defaulted_block_hole_filled/root.py)
  →
  [defaulted_block_hole_filled_generated.py](https://github.com/owebeeone/astichi/blob/main/docs/reference/snippets/statement/defaulted_block_hole_filled/defaulted_block_hole_filled_generated.py)

## See also

- [marker-overview.md](marker-overview.md)
- [marker-clause-targets.md](marker-clause-targets.md)
