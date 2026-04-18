# Using the API

This guide walks through the main pipeline: **compile** a snippet, **compose**
with the builder, **materialize** for a runnable target, then **emit** source.

## 1. Imports

```python
import astichi
from astichi import Composable, build
from astichi.emit import verify_round_trip
```

Astichi currently recognizes marker names from the **source text** you pass to
`astichi.compile(...)`. There is **no** runtime `astichi.markers` shim module in
the package today, so the examples below place marker-bearing code directly in
the compiled source string.

## 2. Compile a snippet

`compile` parses marker-bearing source and returns a **`Composable`**. Pass
**origin** metadata so diagnostics and `ast` line numbers match the real
container (for example a slice extracted from a `.yidl` file).

```python
root_src = """
def run():
    astichi_hole(body)
"""

root = astichi.compile(
    root_src,
    file_name="snippet.py",
    line_number=1,
    offset=0,
)
assert isinstance(root, Composable)
```

The returned value carries **source origin** (`file_name`, line, offset) for
errors and provenance.

## 3. Bind compile-time externals

`astichi_bind_external(name)` declares a compile-time input. The current
frontend returns a concrete composable that supports **`.bind(...)`**, which
replaces those sites with literal AST values and returns a new immutable
composable.

```python
bound = astichi.compile(
    """
astichi_bind_external(fields)
print(fields)
""",
    file_name="externals.py",
).bind(fields=("a", "b"))
```

Keyword bindings and mapping bindings are both supported; kwargs win on key
collision.

## 4. Compose with the builder

Create a builder with **`build()`**, register named **instances** of
`Composable`, and **insert** into holes with an explicit **`order`** when
several fragments attach to the same variadic site.

```python
child = astichi.compile(
    "value = 1\nprint(value)\n",
    file_name="child.py",
)

builder = build()
builder.add.Root(root)
builder.add.Child(child)
builder.Root.body.add.Child(order=10)

graph = builder.build()
```

If you use indexed targets such as `builder.Root.slot[0]`, `builder.build()`
defaults to `unroll="auto"` and unrolls `astichi_for(...)` sites as needed for
those indexed edges.

If a later stage reuses a built composable, descendant paths stay fluent:

```python
builder.Pipeline.Parse.body.add.Step(order=0)
builder.assign.Step.total.to().Pipeline.Right.total
```

The same fluent descendant syntax appears in emitted block-shell metadata as
`@astichi_insert(..., ref=Pipeline.Parse)`.

`build()` on the graph returns a **new** `Composable`. Boundary **holes** may
still be open if you chose not to wire every demand.

## 5. Materialize

When all **mandatory** demands for your target are satisfied and **hygiene**
checks pass, call **`materialize()`** to obtain a representation suitable for
execution or final emission (expression, `def`, class body, module—per your
target contract).

```python
closed = graph.materialize()
```

If a required hole is missing or a name rule is violated, **`materialize`**
raises with a diagnostic.

## 6. Emit

Produce Python **source** for inspection, tests, or downstream tools.

```python
text = closed.emit(provenance=True)   # default: append provenance tail
text_plain = closed.emit(provenance=False)
verify_round_trip(text)
```

With **`provenance=True`**, emitted text ends with one trailing comment of the
form `# astichi-provenance: ...`. The emitted Python body remains authoritative;
the provenance payload is only for AST/source-location restoration and
round-trip checks. See [Materialize and emit](../reference/materialize-and-emit.md).

## 7. Where to read next

- [Reference index](../reference/README.md)
- **[`AstichiSingleSourceSummary.md`](../../dev-docs/AstichiSingleSourceSummary.md)** — current snapshot and open gaps
