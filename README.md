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
- concrete composables with `.bind(...)`, `.materialize()`, and `.emit(...)`
- provenance helpers in `astichi.emit`

Supported pieces today include block holes, expression inserts, external
binding, materialization, emission, and builder-driven loop unrolling.

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
