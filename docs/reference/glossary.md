# Glossary

Short definitions. Design background:
**[`../../dev-docs/AstichiApiDesignV1.md`](../../dev-docs/AstichiApiDesignV1.md)**.

| Term | Meaning |
|------|---------|
| **`Composable`** | Immutable carrier of a Python-shaped fragment plus metadata for composition, `materialize`, and `emit`. |
| **Demand port** | A site that may accept composition input (hole, implied demand, …). |
| **Supply port** | A site that offers a binding or value (`astichi_export`, …). |
| **Hole** | Named splice site: **`astichi_hole(name)`**. Shape comes from **AST position**, not from encoding a “kind” in the name. |
| **Marker** | Call, decorator, or identifier suffix in **source** that astichi lowers (`astichi_hole`, `astichi_bind_external`, `name__astichi_arg__`, …). |
| **Astichi scope** | Composition-time scope used to keep independent snippet locals from accidentally colliding when materialized into one Python target. |
| **Hygiene** | Identifier safety pass that preserves explicitly wired names and renames ordinary locals when composition would otherwise collide. |
| **`compile`** | Parse and lower marker-bearing **source** into a `Composable`. |
| **`build()`** (builder factory) | Create a **mutable** builder graph over `Composable` instances. |
| **`.build()`** (on graph) | Fold the graph into one **new** `Composable`. |
| **`materialize()`** | Close a composable for a runnable target; enforce holes and hygiene. |
| **`emit()`** | Render source text; optional **provenance** tail. |
| **Origin** | `file_name`, `line_number`, `offset` passed to **`compile`** so diagnostics match embedded or multi-file contexts. |
| **Strict / permissive** | How **unresolved free identifiers** are classified. |
| **Additive composition** | Composition **inserts** contributions into holes; it does not replace already-filled sites. |
