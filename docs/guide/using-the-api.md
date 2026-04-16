# Using the API

This guide walks through the main pipeline: **compile** a snippet, **compose**
with the builder, **materialize** for a runnable target, then **emit** source.

## 1. Imports

```python
import astichi
from astichi import compile, build, Composable
from astichi.markers import (
    astichi_hole,
    astichi_bind_external,
    astichi_for,
    astichi_export,
)
```

Marker callables live in **`astichi.markers`** so snippet modules can import
them and still parse as ordinary Python.

## 2. Compile a snippet

`compile` parses marker-bearing source and returns a **`Composable`**. Pass
**origin** metadata so diagnostics and `ast` line numbers match the real
container (for example a slice extracted from a `.yidl` file).

```python
snippet = """
astichi_bind_external(items)

def run():
    for x in astichi_for(items):
        astichi_hole(body)
    astichi_export(result)
"""

comp = astichi.compile(
    snippet,
    file_name="snippet.py",
    line_number=1,
    offset=0,
)
assert isinstance(comp, Composable)
```

The returned value carries **source origin** (`file_name`, line, offset) for
errors and provenance.

## 3. Compose with the builder

Create a builder with **`build()`**, register named **instances** of
`Composable`, and **insert** into holes with an explicit **`order`** when
several fragments attach to the same variadic site.

```python
child = astichi.compile("y = 1\n", file_name="child.py")

graph = (
    build()
    .add.A(comp)
    .add.B(child)
    .A.body.add.B(order=10)
    .build()
)
```

The same workflow works with **broken-out handles** instead of fluent chaining;
see [Builder API](../reference/builder-api.md) and [Addressing](../reference/addressing.md).

`build()` on the graph returns a **new** `Composable`. Boundary **holes** may
still be open if you chose not to wire every demand.

## 4. Materialize

When all **mandatory** demands for your target are satisfied and **hygiene**
checks pass, call **`materialize()`** to obtain a representation suitable for
execution or final emission (expression, `def`, class body, module—per your
target contract).

```python
closed = graph.materialize()
```

If a required hole is missing or a name rule is violated, **`materialize`**
raises with a diagnostic.

## 5. Emit

Produce Python **source** for inspection, tests, or downstream tools.

```python
text = closed.emit(provenance=True)   # default: append provenance tail
text_plain = closed.emit(provenance=False)
```

With **`provenance=True`**, emitted text ends with
`astichi_provenance_payload("…")` for AST and source-location restoration; the
**body** of the file remains authoritative for marker semantics (reparsable
Python). See [Materialize and emit](../reference/materialize-and-emit.md).

## 6. Where to read next

- [Reference index](../reference/README.md)
- **[`AstichiApiDesignV1.md`](../../dev-docs/AstichiApiDesignV1.md)** — full V1 design
