# Markers: `astichi_for`, `astichi_funcargs`, and internal inserts

## `astichi_for(domain)`

- Declares a **compile-time** iteration domain.
- The loop remains part of the `Composable` until / unless unrolled.
- **`build(unroll="auto")`** unrolls only when indexed target paths require it;
  `build(unroll=True)` always unrolls and `build(unroll=False)` never does.

**Supported domains:**

- Literal tuples/lists (constant shapes)
- `range(...)` with **compile-time constant** arguments
- Domains tied to **`astichi_bind_external`** values

**Unsupported domains:** arbitrary runtime iterables, arbitrary calls,
comprehensions as the domain expression.

Unpacking in the `for` target follows Python rules at compile time; failure →
error.

## Internal insert metadata

`astichi_insert(...)` is **not** public authored source.

Authored snippets should declare holes with `astichi_hole(...)` and wire
children through `astichi.build()`. Build/merge may emit internal insert
metadata so the built composable can be inspected, emitted, and re-ingested.

Ordinary `astichi.compile(...)` defaults to `source_kind="authored"` and rejects
`astichi_insert(...)` calls. Only recompile Astichi-emitted source with the
explicit opt-in:

```python
astichi.compile(source, source_kind="astichi-emitted")
```

The emitted metadata forms are:

- `@astichi_insert(target, order=..., ref=...)` for block-shell placement.
- `astichi_insert(target, expr)` for expression placement.

The metadata has these semantics:

- **`target`** names the hole receiving the child contribution.
- **Additive only**: composition inserts contributions into holes; it does not
  replace already-filled sites.
- **`order`**: lower values run first among inserts into the same variadic hole;
  equal `order` ties keep first-added edge first order.
- **`ref`** is optional descendant/build-path metadata for decorator-form
  shells. It uses the same fluent syntax as builder addressing:

```python
@astichi_insert(body, ref=Pipeline.Root.Parse)
def parse_shell():
    ...

@astichi_insert(body, ref=Pipeline.Root.Parse[1, 2].Normalize)
def normalize_shell():
    ...
```

- `ref=` is metadata for block shells. Expression-form metadata
  `astichi_insert(target, expr)` does **not** take `ref=`.
- Builder-generated shells emit `ref=` automatically so later build stages can
  address descendants with the same fluent path language.

## `astichi_funcargs(...)`

- Authored call-argument payload surface for:
  - plain call-position holes: `func(astichi_hole(args))`
  - starred call holes: `func(*astichi_hole(args))`
  - double-starred call holes: `func(**astichi_hole(kwargs))`
- Build/merge normalizes payload contributions through generated internal
  placement wrappers until realization.
- Author one `astichi_funcargs(...)` payload per contributing snippet; the
  target hole and edge order determine where that payload lands.
- If exact ordering boundaries matter, expose multiple holes in the target
  call surface and rely on authored hole order first, then contribution order
  within each hole.
- `_=` is special only when its direct value is:
  - `astichi_import(name)`
  - `astichi_export(name)`
- Any other `_=` entry is just an ordinary emitted keyword argument named `_`.
- `astichi_pass(name)` is the value-form participant and belongs in an emitted
  argument expression, not in `_=`:

```python
astichi_funcargs(
    (out := astichi_pass(seed)),
    _=astichi_export(out),
)
```

- `astichi_pass(name).astichi_v` (or `._`) follows the same transparent
  one-shot strip rule as `astichi_ref(...)`. Use it where Python needs an
  assignable/deleteable target rather than a bare call:

```python
astichi_pass(trace).append("leaf")       # -> trace.append("leaf")
astichi_pass(counter).astichi_v = 1      # -> counter = 1
del astichi_pass(cache)._                # -> del cache
```

- For a same-name bind to the immediately enclosing Astichi scope, spell it
  explicitly with `outer_bind=True`:

```python
astichi_pass(trace, outer_bind=True).append("leaf")
astichi_import(total, outer_bind=True)
```

- Explicit `arg_names=` / `.bind_identifier(...)` / `builder.assign...`
  resolution is serialized back into source as `bound=True` on the rewritten
  marker call so `emit()` -> `compile()` preserves the wiring contract.

- Bare statement-form `astichi_pass(name)` (including
  `astichi_pass(name).astichi_v`) rejects at `compile()` time. If you need a
  declaration-form threaded name for a whole scope, use `astichi_import(name)`.

- Duplicate explicit emitted keyword names reject at build time.
- For non-call expression holes, the authored surface is a plain expression:

```python
42
```

- Do not author `astichi_insert(...)` in source. Astichi may emit equivalent
  internal placement metadata in built state, but that form is not part of the
  public authored API.

## See also

- [marker-holes.md](marker-holes.md)
- **[§5.7–5.8](../../dev-docs/AstichiApiDesignV1.md)**
