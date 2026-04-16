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
| `True` (default) | Emit body, then append **`astichi_provenance_payload("…")`** — single argument, reserved name, **compressed** payload used only for AST/provenance restoration. |
| `False` | Emit without the provenance tail. |

**Semantics of the tail:** holes, binds, inserts, exports, and related meaning
are always recovered by **reparsing** the emitted Python before the tail. The
payload is **not** a second source of truth for markers (**[§11.2](../../dev-docs/AstichiApiDesignV1.md)**).

### Edited files

If a user edits emitted source so the AST **no longer matches** the payload,
provenance restoration **fails** with an error instructing removal of
**`astichi_provenance_payload(...)`**. Current buffer locations are then
authoritative (**[§12](../../dev-docs/AstichiApiDesignV1.md)**).

## Marker-bearing emission

Astichi **may** emit source that still contains **markers** at boundary sites so
that **`compile`** can reconstruct a `Composable`. Whether a given emission is
full Python or skeleton is a **documented policy** of the emit mode.

## See also

- [Composable API](composable-api.md)
- [Compile API](compile-api.md)
- **[§10–13](../../dev-docs/AstichiApiDesignV1.md)**
