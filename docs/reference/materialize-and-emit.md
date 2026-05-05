# Materialize and emit

## `materialize()`

**`materialize()`** validates a `Composable` and produces a **closed** value for
a chosen **runnable / emittable** target (expression, `def`, class body, module
fragment, …—per product API).

It **requires**:

- every **mandatory** demand port satisfied for that target  
- **valid lexical hygiene** (`IdentifierHygieneRequirements.md`)  
- **legal** shape for the target  

On violation it **raises**; it never returns a value that violates the contract
(**[§10.2](../../dev-docs/historical/AstichiApiDesignV1.md)**).

During materialization Astichi also consumes executable-only markers. Managed
`astichi_pyimport(...)` statements become ordinary Python imports at module
head, after a module docstring and after ordinary `from __future__ import ...`
statements. No `astichi_pyimport(...)` call survives final materialized output.
`astichi_comment(...)` statements are also stripped from executable
materialized output; marker-only non-module suites receive `pass`.

## `emit(*, provenance: bool = True) -> str`

Renders **source text** for debugging, tests, inspection, or downstream codegen.

| `provenance` | Behavior |
|--------------|----------|
| `True` (default) | Emit body, then append one trailing comment of the form **`# astichi-provenance: ...`**. The payload is used only for AST/provenance restoration. |
| `False` | Emit without the provenance tail. |

**Semantics of the tail:** holes, binds, inserts, exports, and related meaning
are always recovered by **reparsing** the emitted Python before the tail. The
payload is **not** a second source of truth for markers (**[§11.2](../../dev-docs/historical/AstichiApiDesignV1.md)**).

### Edited files

If a user edits emitted source so the AST **no longer matches** the payload,
provenance restoration **fails**. Removing the trailing
**`# astichi-provenance: ...`** comment drops back to the edited source as the
authoritative version.

## Provenance helpers

`astichi.emit` exposes the current round-trip helpers used by the test suite:

- `extract_provenance(source)`
- `verify_round_trip(source)`
- `encode_provenance(tree)` / `decode_provenance(payload)`
- `RoundTripError`

## Marker-bearing emission

Astichi **may** emit source that still contains **markers** at boundary sites so
that **`compile`** can reconstruct a `Composable`. Whether a given emission is
full Python or skeleton is a **documented policy** of the emit mode.

Pre-materialized emission preserves source-visible markers, including
`astichi_pyimport(...)`, for round-trip. Final materialized emission strips or
realizes those markers into executable Python.

## `emit_commented() -> str`

Renders final Python source with `astichi_comment("...")` statements converted
to real `#` comments. This is a peer operation to `materialize()`, not a mode
of ordinary `emit()`: it runs materialization with comment preservation enabled,
renders the preserved comment markers, and returns plain source with no
provenance trailer.

Only exact `{__file__}` and `{__line__}` substrings in comment payloads are
expanded. Other brace text is emitted literally.

## See also

- [Composable API](composable-api.md)
- [Compile API](compile-api.md)
- [Marker: astichi_comment](marker-comment.md)
- [Marker: astichi_pyimport](marker-pyimport.md)
- **[§10–13](../../dev-docs/historical/AstichiApiDesignV1.md)**
