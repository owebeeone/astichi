# Marker overview

Markers are **valid Python** syntax: calls and decorators your snippet uses so
astichi can find holes, binds, and composition sites.

The current package does **not** ship an `astichi.markers` runtime shim, so
marker-bearing examples are typically embedded directly in the source string
passed to `astichi.compile(...)`.

**Hole shape** (scalar vs variadic vs block) is inferred from **AST context**,
not from encoding a “kind” in the hole name.

**Normative list:**
**[AstichiApiDesignV1.md §5](../../dev-docs/AstichiApiDesignV1.md)**.

## Phase-1 marker vocabulary

```text
astichi_hole(name)
astichi_bind_once(name, expr)
astichi_bind_shared(name, expr)
astichi_bind_external(name)
astichi_keep(name)
astichi_export(name)
astichi_for(domain)
astichi_funcargs(...)
@astichi_insert(target, order=…, ref=…)
```

Call-argument note:

- `astichi_funcargs(...)` is the authored call-argument payload surface
- decorator-form `@astichi_insert(...)` remains the public block-shell surface
- user-authored `astichi_insert(target, expr)` may still exist as legacy
  behavior, but it is not the intended authored call-argument API

## Identifier arguments

For `name` / `target` / bind keys: use a **bare identifier** in source (a
`Name` in the AST), **not** a string literal. The identifier **names** the hole
or bind; it is **not** a hole-kind enum like `"expr"` vs `"block"`.

## Per-topic reference

| Topic | Page |
|-------|------|
| Holes, `*`, `**`, block position | [marker-holes.md](marker-holes.md) |
| Binds and exports | [marker-binds-and-exports.md](marker-binds-and-exports.md) |
| Loops and inserts | [marker-for-and-insert.md](marker-for-and-insert.md) |
| Preserved names | [marker-keep.md](marker-keep.md) |

Unsupported starred / double-starred contexts are **hard errors** in V1.
