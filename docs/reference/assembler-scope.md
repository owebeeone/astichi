# Assembler Scope

`astichi.assembler` is a helper layer for tools that already have
their own data model and want to apply the minimum needed information to an
Astichi builder. It sits on top of the current lower-backed scope facade. Build
and materialize remain authoritative.

Use it when a client can express a resource and a partial selector:

- this composable, inserted as this builder name
- this external Python value
- this identifier spelling
- this optional demand name
- this optional build-path or code-owner match

The helpers then find compatible inventory records, return candidate
applications, and let the caller require one unambiguous result.

## Resource Wrappers

```python
from astichi.assembler import as_composable, as_external_value, as_identifier

as_composable(piece, build_name="GetterBody", build_index=1, order=10)
as_external_value(42)
as_identifier("GeneratedGetter")
```

`as_composable(...)` needs a builder name because the builder graph names a
registered instance independently of the composable object. `build_index=1`
creates the concrete instance name `GetterBody[1]`; tuple indexes create names
such as `GetterBody[1,2]`. `order=` is passed to the additive target edge.

External values and identifiers do not need builder names. The selected demand
record determines which registered instance is rebound.

## Candidate Lookup

```python
from astichi.assembler import require_one

candidate = require_one(
    scope.find_candidates(
        as_external_value(9),
        name="delta",
        build_match=("Root", "GetterBody[1]"),
    )
)
scope.apply(candidate)
```

`AssemblyScope.wire(...)` collapses that
`apply(require_one(find_candidates(...)))` triad into one call, returning the
resolved candidate. Selector semantics, the structural compatibility match, and
the multi-line `require_one` diagnostic on a missing/ambiguous match are
identical:

```python
scope.wire(
    as_external_value(9),
    name="delta",
    build_match=("Root", "GetterBody[1]"),
)
```

Selector fields are intentionally optional:

| Field | Meaning |
| --- | --- |
| `name` | Literal demand name. `None` means all compatible names. |
| `build_match` | Tuple selector against `InventoryRecord.build_path.parts`. |
| `owner_match` | Tuple selector against logical code-owner names. |

`build_match` and `owner_match` use `astichi.pathmatch.matches_path(...)`.
Literal parts match exact names. Special parts are:

| Part | Meaning |
| --- | --- |
| `.` | exactly one non-empty component |
| `?` | zero or one component |
| `*` | zero or more components |
| `+` | one or more components |

Examples:

```python
build_match=("Root",)
build_match=("Root", "GetterBody[1]")
build_match=("Root", "+")
owner_match=("GeneratedGetter", ".")
```

## Applying Candidates

`AssemblyScope` wraps an existing builder and keeps lower-backed assembly state
current after each applied candidate.

```python
import astichi
from astichi.assembler import AssemblyScope

scope = AssemblyScope(astichi.build())
scope.add("Root", root)
scope.apply(candidate)
result = scope.build()
```

Batch-capable callers can pass an ordered request stream and let the scope
resolve and apply each request through the lower layer:

```python
from astichi.assembler import BindingRequest

scope.apply_batch(
    (
        BindingRequest(as_identifier("GeneratedGetter"), name="class_name"),
        BindingRequest(as_external_value(9), name="delta"),
    )
)
```

`BindingRequest(..., allow_equivalent_demand_sites=True)` accepts repeated
same-name demand sites only when every candidate has the same build path, code
owner, name, and inventory kind. This is intended for generated planners that
coalesce equivalent binding markers.

Native-selected `apply_batch(...)` keeps native assembly state authoritative
by default. Python lower-state mirror replay is quarantined behind
`ASTICHI_NATIVE_SCOPE_MIRROR_REPLAY=1` for compatibility and oracle work.

`scope.apply(...)` currently supports:

- composable candidates: register the resource with its build name/index and
  add it to the selected hole
- external value candidates: bind the external value on the selected owning
  registered instance
- identifier candidates: bind the identifier name on the selected owning
  registered instance

When `require_one(...)` does not receive exactly one candidate, it raises a
multi-line diagnostic that includes the demand build path, logical owner path,
source location when available, locator, and resource-side information.

## Reference Snippets

- [assembler_scope/resource_candidates](snippets/assembler_scope/resource_candidates/recipe.py)
  — explicit `find_candidates` / `require_one` / `apply` form.
- [resource_candidates_generated.py](snippets/assembler_scope/resource_candidates/resource_candidates_generated.py)
- [assembler_scope/wire_shorthand](snippets/assembler_scope/wire_shorthand/recipe.py)
  — the one-call `wire(...)` form; one polymorphic template specialized into many.
- [wire_shorthand_generated.py](snippets/assembler_scope/wire_shorthand/wire_shorthand_generated.py)
