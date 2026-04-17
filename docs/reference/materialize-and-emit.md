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
(**[§10.2](../../dev-docs/AstichiApiDesignV1.md)**).

## `emit(*, provenance: bool = True) -> str`

Renders **source text** for debugging, tests, inspection, or downstream codegen.

| `provenance` | Behavior |
|--------------|----------|
| `True` (default) | Emit body, then append one trailing comment of the form **`# astichi-provenance: ...`**. The payload is used only for AST/provenance restoration. |
| `False` | Emit without the provenance tail. |

**Semantics of the tail:** holes, binds, inserts, exports, and related meaning
are always recovered by **reparsing** the emitted Python before the tail. The
payload is **not** a second source of truth for markers (**[§11.2](../../dev-docs/AstichiApiDesignV1.md)**).

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

## See also

- [Composable API](composable-api.md)
- [Compile API](compile-api.md)
- **[§10–13](../../dev-docs/AstichiApiDesignV1.md)**
