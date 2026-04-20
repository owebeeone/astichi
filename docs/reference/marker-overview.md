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
astichi_ref(value)
astichi_ref(external=name)
@astichi_insert(target, order=…, ref=…)
```

Call-argument note:

- `astichi_funcargs(...)` is the authored call-argument payload surface
- decorator-form `@astichi_insert(...)` remains the public block-shell surface
- for non-call expression holes, author a plain expression source such as `42`
  or `(value := 2, value)`; build/merge normalizes it internally
- expression-form `astichi_insert(target, expr)` is internal normalization
  metadata, not an authored user surface

Reference-path note:

- `astichi_ref(value)` is the authored value-form reference surface; it lowers
  a compile-time path string (e.g. `"self.f0"` or `"pkg.mod.attr"`) into the
  corresponding `Name` / `Attribute` AST at materialize time
- `astichi_ref(external=name)` is sugar for
  `astichi_ref(astichi_bind_external(name))` and surfaces the inner bind site
  as a normal demand port
- `astichi_ref(...).astichi_v` (or the `._` shorthand) wraps the value form so
  it is grammatically legal as an `Assign` / `AugAssign` / `Delete` target

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
| Reference-path values (`astichi_ref`) | [marker-ref.md](marker-ref.md) |
| Preserved names | [marker-keep.md](marker-keep.md) |

Unsupported starred / double-starred contexts are **hard errors** in V1.
