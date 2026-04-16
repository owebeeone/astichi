# Glossary

Short definitions. Authoritative rules:
**[`../../dev-docs/AstichiApiDesignV1.md`](../../dev-docs/AstichiApiDesignV1.md)**.

| Term | Meaning |
|------|---------|
| **`Composable`** | Immutable carrier of a Python-shaped fragment plus metadata for composition, `materialize`, and `emit`. |
| **Demand port** | A site that may accept composition input (hole, implied demand, …). |
| **Supply port** | A site that offers a binding or value (`astichi_export`, …). |
| **Hole** | Named splice site: **`astichi_hole(name)`**. Shape comes from **AST position**, not from encoding a “kind” in the name. |
| **Marker** | Call or decorator in **source** that astichi lowers (`astichi_hole`, `@astichi_insert`, …). |
| **`compile`** | Parse and lower marker-bearing **source** into a `Composable`. |
| **`build()`** (builder factory) | Create a **mutable** builder graph over `Composable` instances. |
| **`.build()`** (on graph) | Fold the graph into one **new** `Composable`. |
| **`materialize()`** | Close a composable for a runnable target; enforce holes and hygiene. |
| **`emit()`** | Render source text; optional **provenance** tail. |
| **Origin** | `file_name`, `line_number`, `offset` passed to **`compile`** so diagnostics match embedded or multi-file contexts. |
| **Strict / permissive** | How **unresolved free identifiers** are classified. |
| **Additive composition** | Phase 1: only **insert** into holes; **no replacement** of filled sites. |
