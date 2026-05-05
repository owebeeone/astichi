# Marker overview

Markers are **valid Python** syntax: calls, decorators, and identifier suffixes
your snippet uses so astichi can find holes, binds, and composition sites.

The current package does **not** ship an `astichi.markers` runtime shim, so
marker-bearing examples are typically embedded directly in the source string
passed to `astichi.compile(...)`.

**Hole shape** (scalar vs variadic vs block) is inferred from **AST context**,
not from encoding a “kind” in the hole name.

**Design background:**
**[AstichiApiDesignV1.md §5](../../dev-docs/historical/AstichiApiDesignV1.md)**.

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
def astichi_params(...): pass
async def astichi_params(...): pass
astichi_ref(value)
astichi_ref(external=name)
astichi_pyimport(module=module_path, names=(name,))
astichi_pyimport(module=module_path, as_=alias)
astichi_comment("comment text")
name__astichi_keep__
name__astichi_arg__
name__astichi_param_hole__
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

Parameter note:

- `name__astichi_param_hole__` declares a function-parameter insertion target
  in an ordinary parameter slot.
- `def astichi_params(...): pass` and
  `async def astichi_params(...): pass` are the authored parameter payload
  carriers; only the signature is inserted.
- Astichi may emit internal `@astichi_insert(name, kind="params", ...)`
  wrappers in pre-materialized source. They are not authored user surface.

Reference-path note:

- `astichi_ref(value)` is the authored value-form reference surface; it lowers
  a compile-time path string (e.g. `"self.f0"` or `"pkg.mod.attr"`) into the
  corresponding `Name` / `Attribute` AST at materialize time
- prefer `astichi_ref(...)` over `getattr(...)` when the attribute path is
  compile-time reducible; keep `getattr(...)` for genuinely runtime-dynamic
  lookup
- `astichi_ref(external=name)` is sugar for
  `astichi_ref(astichi_bind_external(name))` and surfaces the inner bind site
  as a normal demand port
- `astichi_ref(...).astichi_v` (or the `._` shorthand) wraps the value form so
  it is grammatically legal as an `Assign` / `AugAssign` / `Delete` target.
  Prefer bare `astichi_ref(...)` in ordinary expression chains.

Managed import note:

- `astichi_pyimport(...)` declares imports that are synthesized during
  `materialize()` and emitted as ordinary Python imports at module head.
- Imported local names participate in hygiene like other local bindings, so a
  collision can turn `from foo import a` into
  `from foo import a as a__astichi_scoped_1`.
- Use `module=astichi_ref(external=name)` when the module path comes from an
  externally bound compile-time string.
- Pyimport is a top-of-Astichi-scope statement-prefix marker; it is not valid
  inside `astichi_for(...)` bodies or nested real user-authored function/class
  bodies.

Comment note:

- `astichi_comment("...")` is a statement-only final-output comment marker.
- Ordinary `emit()` preserves it as a marker for round-trip. Ordinary
  `materialize()` strips it, inserting `pass` only when a non-module suite
  would otherwise become empty.
- `emit_commented()` is the narrow final-output surface that materializes with
  comments preserved long enough to render them as real `#` comment lines.
- The literal payload may contain `{__file__}` and `{__line__}` placeholders;
  only those exact substrings are replaced. Other braces pass through
  unchanged.

Cross-scope note:

- `astichi_import(name)` is the declaration-form identifier-threading surface
  for a whole Astichi scope
- `astichi_pass(name)` is the value-form surface and belongs in a real
  expression (`x = astichi_pass(y)`, `call(astichi_pass(y))`,
  `astichi_pass(obj).field = 1`)
- when the `astichi_pass(...)` result itself must occupy the target position,
  append `._` or `.astichi_v`:
  `astichi_pass(counter)._ = 1`
- `outer_bind=True` is the explicit convenience form for “bind this marker to
  the same-named identifier in the immediately enclosing Astichi scope”
- explicit builder / `arg_names=` / `.bind_identifier(...)` wiring now
  round-trips in source as `bound=True` on the rewritten marker call
- bare statement-form `astichi_pass(name)` is rejected; if you need
  declaration-style scope threading, use `astichi_import(name)`

Identifier-suffix note:

- `name__astichi_keep__` is the identifier-position form of keep. It pins the
  base spelling `name` through hygiene and strips the suffix during
  materialize.
- `name__astichi_arg__` creates an identifier demand named `name`. Resolve it
  through `arg_names=`, `.bind_identifier(...)`, builder `arg_names=`, or
  `builder.assign...` before materialize.
- `name__astichi_param_hole__` creates a parameter-list insertion target named
  `name`. It is stripped by parameter materialization, not by the ordinary
  identifier arg/keep strip pass.
- Use suffix forms when the marker must live inside an identifier slot, such
  as a class name, function name, parameter name, assignment target, or
  reference.

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
| Parameter holes | [marker-params.md](marker-params.md) |
| Reference-path values (`astichi_ref`) | [marker-ref.md](marker-ref.md) |
| Managed Python imports (`astichi_pyimport`) | [marker-pyimport.md](marker-pyimport.md) |
| Preserved names | [marker-keep.md](marker-keep.md) |
| Identifier suffixes | [classification-modes.md](classification-modes.md) |
| Scoping and hygiene | [scoping-hygiene.md](scoping-hygiene.md) |

Unsupported starred / double-starred contexts are **hard errors**.
