# astichi

AST-level composition and stitching for Python code generation.

Astichi takes small, marker-bearing Python snippets, composes them into one
coherent program, and emits runnable Python. It is built for generators that
need low-overhead output without falling back to brittle string templates or
runtime abstraction in hot paths.

Astichi is a fit when you want to:

- describe codegen intent in Python-shaped snippets
- stitch block and expression fragments at named composition sites
- bind compile-time values into source before final lowering
- unroll compile-time loops into straight-line Python
- synthesize managed imports that participate in hygiene
- inspect composables with descriptors before wiring them
- emit inspectable source with provenance instead of opaque runtime machinery

It is **not** a general macro system and **not** a generic codemod framework.
It is a focused library for generators that need a reliable AST stitcher.

## Why Astichi

Code generators often hit the same wall: the desired output is simple,
specialized Python, but the implementation ends up split between string
concatenation, ad hoc templates, and fragile scope management.

Astichi handles the parts that usually go wrong:

- valid Python ASTs instead of fragile template fragments
- deterministic insertion order for stitched code
- compile-time binding and loop unrolling before emission
- specialized straight-line Python instead of runtime dispatch layers
- emitted source you can diff, test, and round-trip

## Marker mental model

Astichi is marker-bearing Python source plus a small build pipeline.

- Markers are recognized from authored Python source.
- Marker meaning comes from AST position, not string matching alone.
- `compile(...)` parses marker-bearing source into a `Composable`.
- `build()` wires composables together.
- `describe()` exposes holes, binds, ports, and builder target addresses for
  data-driven composition.
- `materialize()` resolves inserts, bindings, and hygiene, then produces real
  Python.

The core markers are:

- `astichi_hole(name)` -> insertion site
- `astichi_keep(name)` -> hygiene-preserved name in expression / statement source
- `name__astichi_keep__` -> hygiene-preserved name in identifier position
- `name__astichi_arg__` -> identifier demand
- `name__astichi_param_hole__` -> function-parameter insertion target
- `astichi_funcargs(...)` -> call-argument payload
- `astichi_bind_external(name)` -> external/literal value slot
- `astichi_ref(path)` -> compile-time reducible identifier / attribute path
- `astichi_pyimport(module=..., names=(...))` -> managed Python import
- `astichi_comment("...")` -> final-output source comment
- `astichi_pass(name, outer_bind=True)` -> explicit same-name boundary read
- `astichi_import(name)` -> explicit whole-scope boundary import
- `astichi_export(name)` -> explicit outward supply
- `astichi_insert(...)` -> internal emitted metadata, not general authored API

Comment marker note:

- `astichi_comment("...")` is statement-only. Ordinary `materialize()` strips
  it for executable output; `emit_commented()` renders it as real `#` comments.
- Multi-line payloads keep the marker statement's indentation, and only exact
  `{__file__}` / `{__line__}` substrings are expanded.

Value-form target note:

- `astichi_ref(...)` and `astichi_pass(...)` are ordinary value-form surfaces in
  expressions.
- If the marker result itself must occupy an `Assign` / `AugAssign` / `Delete`
  target position, append `._` or `.astichi_v`:
  `astichi_ref("self.f0")._ = 1`,
  `astichi_pass(counter).astichi_v = 1`.
- If you immediately continue to a real attribute, plain Python target syntax
  already works:
  `astichi_pass(obj).field = 1`.

The one rule that matters most is scope:

- `astichi_insert` is the basic Astichi boundary.
- Each inserted composable lives in its own Astichi scope.
- There is no implicit capture across that boundary.
- If a name crosses the boundary, make it explicit with `keep`, `pass`,
  `import`, or `export`.
- Function parameters are the pinned exception: parameter names and uses in the
  function scope stay attached to that parameter binding.

Small example:

```python
import astichi

builder = astichi.build()
builder.add.Root(
    astichi.compile(
        """
items = []
astichi_hole(body)
result = tuple(items)
"""
    )
)
builder.add.Step(
    astichi.compile(
        """
astichi_pass(items, outer_bind=True).append("x")
"""
    )
)
builder.Root.body.add.Step(order=0)

materialized = builder.build().materialize()
print(materialized.emit(provenance=False))
```

Emitted Python:

```python
items = []
items.append("x")
result = tuple(items)
```

Without `astichi_pass(items, outer_bind=True)`, the inner snippet does not get
to reuse `items` just because the spelling matches. That is deliberate. Astichi
defaults to isolated scopes and only crosses them when the source says so.

The fluent builder is also available as a data-driven named API. Descriptor
target data can feed that API directly:

```python
hole = root.describe().single_hole_named("body")

builder = astichi.build()
builder.add("Root", root)
builder.add("Step", astichi.compile("value = 1\n"))
builder.target(hole.with_root_instance("Root")).add("Step")
```

That `builder.target(...)` call uses the same target address as
`builder.Root.body.add.Step()`, but the address came from `describe()` instead
of a Python attribute chain.

## Example: schema-specialized row projector

Suppose an ingestion pipeline knows its event schema at build time, and each
field needs its own normalization step. A runtime loop or dispatch table adds
overhead to every row. String templating works until ordering, scope, and
correctness start fighting each other.

Astichi lets you define the skeleton once, stitch in field-specific steps, and
emit the straight-line Python you actually want to run.

```python
import astichi

root = astichi.compile(
    """
astichi_bind_external(FIELDS)

def project_row(row):
    out = {}
    for field in astichi_for(FIELDS):
        astichi_hole(step)
    return out
"""
).bind(FIELDS=("user_id", "total_cents", "created_at"))

builder = astichi.build()
builder.add.Root(root)

builder.add.UserId(
    astichi.compile("out['user_id'] = int(row['user_id'])\n")
)
builder.add.TotalCents(
    astichi.compile("out['total_cents'] = int(row['total_cents'])\n")
)
builder.add.CreatedAt(
    astichi.compile("out['created_at'] = row['created_at'][:10]\n")
)

builder.Root.step[0].add.UserId()
builder.Root.step[1].add.TotalCents()
builder.Root.step[2].add.CreatedAt()

projector = builder.build().materialize()
print(projector.emit(provenance=False))
```

Emitted Python:

```python
def project_row(row):
    out = {}
    out["user_id"] = int(row["user_id"])
    out["total_cents"] = int(row["total_cents"])
    out["created_at"] = row["created_at"][:10]
    return out
```

That is the point: no runtime field loop, no dispatch registry, no handwritten
template surgery. The generated function is plain Python, specialized to the
known schema, and suitable for hot-path use.

This is exactly the class of problem where a reliable AST stitcher matters:

- block fragments must land in the right lexical scope
- per-field steps must keep deterministic order
- compile-time schema data must become literal Python
- the final output must still be valid, inspectable source

## Current surface

Astichi currently provides:

- `astichi.compile(source, file_name=None, line_number=1, offset=0)`
- `astichi.build()` for builder-based composition
- concrete composables with `.bind(...)`, `.describe()`, `.materialize()`, and
  `.emit(...)` / `.emit_commented()`
- data-driven builder calls such as `builder.add("Root", root)` and
  `builder.target(hole.with_root_instance("Root")).add("Step")`
- provenance helpers in `astichi.emit`

Supported pieces today include block holes, expression inserts, external
binding, managed Python imports, materialization, emission, and builder-driven
loop unrolling.

## Layout

| Path | Role |
|------|------|
| `src/astichi/` | Library code |
| `docs/` | User-facing docs |
| `tests/` | Pytest suite |
| `dev-docs/` | Design notes, active summary, and requirements |
| `scratch/` | Throwaway experiments (not shipped) |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest
```

## Status

Early development (`0.1.0`), but already useful for controlled codegen
pipelines.

Start with:

- `docs/` for the user-facing surface
- `dev-docs/AstichiSingleSourceSummary.md` for the current implementation
  snapshot and known gaps
