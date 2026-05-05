# Public API

## Package: `astichi`

| Name | Role |
|------|------|
| `__version__` | Package version. |
| `Composable` | Abstract type for composed program fragments. |
| `ComposableDescription` | Immutable descriptor returned by `Composable.describe()`. |
| `ComposableHole` | Additive-hole descriptor with builder target address data. |
| `TargetAddress` | Data-driven target address accepted by `builder.target(...)`. |
| `compile` | Parse marker-bearing **source** into a `Composable`. |
| `build` | Create a **mutable builder** for wiring `Composable` instances. |

```python
from astichi import Composable, ComposableDescription, ComposableHole, TargetAddress
from astichi import compile, build
```

## Marker names in compiled source

Astichi recognizes marker names such as `astichi_hole`, `astichi_bind_external`,
`astichi_for`, `astichi_pyimport`, and `astichi_comment` from the **source
text** passed to `astichi.compile(...)`.

`astichi_insert(...)` is reserved internal metadata. The default
`astichi.compile(..., source_kind="authored")` rejects it; only re-ingest
Astichi-emitted source with `source_kind="astichi-emitted"`.

The current package does **not** ship a runtime `astichi.markers` helper module,
so marker-bearing examples are typically embedded directly in the source string
that Astichi parses.

## Submodule: `astichi.frontend`

Lower-level access to the compiler surface:

| Name | Role |
|------|------|
| `compile` | Same as package `compile`. |
| `CompileOrigin` | `file_name`, `line_number`, `offset` for a compiled snippet. |

Concrete composable types may be exposed here for typing or introspection; all
satisfy **`Composable`**.

## Concrete composables today

Current frontend and builder results are concrete `BasicComposable` values
(with `FrontendComposable` as a frontend alias).

```python
compiled = astichi.compile("astichi_bind_external(fields)\nprint(fields)\n")
bound = compiled.bind(fields=("a", "b"))
```

`.bind(mapping=None, /, **values)` applies `astichi_bind_external(...)`
substitutions and returns a new immutable composable.

`.describe()` returns immutable descriptor metadata for data-driven
composition. See [descriptor-api.md](descriptor-api.md).

`.emit_commented()` runs final materialization and renders `astichi_comment(...)`
markers as real Python comments. It returns plain source with no provenance
tail.

Additional descriptor value objects for advanced inspection are exported from
`astichi.model`, including `PortDescriptor`, `HoleDescriptor`,
`ProductionDescriptor`, `ExternalBindDescriptor`,
`IdentifierDemandDescriptor`, `IdentifierSupplyDescriptor`, `SINGLE_ADD`, and
`MULTI_ADD`.

## Submodule: `astichi.builder`

Builder construction and graph types used by **`build()`** and advanced callers.
The public builder handle supports both fluent chains and data-driven named
calls such as `builder.add("Root", piece)`,
`builder.instance("Root").target("body").add("Step")`, `builder.target(...)`,
and `builder.assign(source_instance=..., inner_name=..., target_instance=...,
outer_name=...)`. Descriptor identifier demand/supply pairs can be bound with
`builder.bind_identifier(...)`.

## Submodule: `astichi.emit`

Source emission and provenance helpers:

| Name | Role |
|------|------|
| `emit_source` | Render a module AST to source with optional provenance. |
| `encode_provenance` / `decode_provenance` | Encode and decode the embedded provenance payload. |
| `extract_provenance` | Read provenance from emitted source text. |
| `verify_round_trip` | Verify that emitted source reparses to the embedded AST. |
| `RoundTripError` | Raised when provenance is missing or mismatched. |
