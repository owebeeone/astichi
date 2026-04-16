# Public API

## Package: `astichi`

| Name | Role |
|------|------|
| `__version__` | Package version. |
| `Composable` | Abstract type for composed program fragments. |
| `compile` | Parse marker-bearing **source** into a `Composable`. |
| `build` | Create a **mutable builder** for wiring `Composable` instances. |

```python
from astichi import Composable, compile, build
```

## Submodule: `astichi.markers`

Runtime callables and decorators used **in snippet source** so it remains valid
Python:

| Symbols (illustrative) | Role |
|------------------------|------|
| `astichi_hole` | Mark a named demand site. |
| `astichi_bind_once`, `astichi_bind_shared`, `astichi_bind_external` | Declare bindings and compile-time externals. |
| `astichi_keep` | Preserve a lexical identifier spelling. |
| `astichi_export` | Export a binding as a **supply** port. |
| `astichi_for` | Compile-time loop domain. |
| `astichi_insert` | Decorator factory for `@astichi_insert(target, order=…)`. |

Exact export list matches
**[`AstichiApiDesignV1.md` §5](../../dev-docs/AstichiApiDesignV1.md)**.

```python
from astichi.markers import astichi_hole, astichi_bind_external
```

## Submodule: `astichi.frontend`

Lower-level access to the compiler surface:

| Name | Role |
|------|------|
| `compile` | Same as package `compile`. |
| `CompileOrigin` | `file_name`, `line_number`, `offset` for a compiled snippet. |

Concrete composable types may be exposed here for typing or introspection; all
satisfy **`Composable`**.

## Submodule: `astichi.builder`

Builder construction and graph types used by **`build()`** and advanced callers.
