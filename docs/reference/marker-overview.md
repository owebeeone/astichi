# Marker overview

Markers are **valid Python** syntax: calls and decorators your snippet uses so
astichi can find holes, binds, and composition sites.

The current package does **not** ship an `astichi.markers` runtime shim, so
marker-bearing examples are typically embedded directly in the source string
passed to `astichi.compile(...)`.

**Hole shape** (scalar vs variadic vs block) is inferred from **AST context**,
not from encoding a “kind” in the hole name.

**Design background:**
**[AstichiApiDesignV1.md §5](../../dev-docs/AstichiApiDesignV1.md)**.

## Marker Vocabulary

```text
astichi_hole(name)
astichi_bind_external(name)
astichi_keep(name)
astichi_import(name)
astichi_pass(name)
astichi_export(name)
astichi_for(domain)
astichi_funcargs(...)
astichi_ref(value)
astichi_ref(external=name)
```

Reserved names:

- `astichi_bind_once(name, expr)` and `astichi_bind_shared(name, expr)` are
  reserved and obsolete marker names; `compile(...)` rejects them with a
  diagnostic.

Internal emitted metadata:

- `astichi_insert(...)` is reserved for Astichi-emitted source. Ordinary
  `astichi.compile(...)` rejects it in the default `source_kind="authored"`
  mode; only re-ingest Astichi output with
  `source_kind="astichi-emitted"`.

Call-argument note:

- `astichi_funcargs(...)` is the authored call-argument payload surface
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
  and is otherwise a transparent one-shot segment that strips during
  materialize

Cross-scope note:

- `astichi_import(name)` is the declaration-form identifier-threading surface
  for a whole Astichi scope
- `astichi_pass(name)` is the value-form surface and belongs in a real
  expression (`x = astichi_pass(y)`, `call(astichi_pass(y))`,
  `astichi_pass(obj)._.field = 1`)
- `outer_bind=True` is the explicit convenience form for “bind this marker to
  the same-named identifier in the immediately enclosing Astichi scope”
- explicit builder / `arg_names=` / `.bind_identifier(...)` wiring now
  round-trips in source as `bound=True` on the rewritten marker call
- bare statement-form `astichi_pass(name)` is rejected; if you need
  declaration-style scope threading, use `astichi_import(name)`

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

Unsupported starred / double-starred contexts are **hard errors**.
