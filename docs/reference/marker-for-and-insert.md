# Markers: `astichi_for`, `astichi_funcargs`, and `@astichi_insert`

## `astichi_for(domain)`

- Declares a **compile-time** iteration domain.
- The loop remains part of the `Composable` until / unless unrolled.
- **`build(unroll="auto")`** unrolls only when indexed target paths require it;
  `build(unroll=True)` always unrolls and `build(unroll=False)` never does.

**Supported domains (phase 1):**

- Literal tuples/lists (constant shapes)
- `range(...)` with **compile-time constant** arguments
- Domains tied to **`astichi_bind_external`** values

**Unsupported (phase 1):** arbitrary runtime iterables, arbitrary calls,
comprehensions as the domain expression.

Unpacking in the `for` target follows Python rules at compile time; failure →
error.

## `@astichi_insert(target, order=…, ref=…)`

- Inserts a child `Composable` into the hole named **`target`** (identifier).
- **Additive only** in phase 1 — no replacement of an already-filled site.
- **`order`**: lower values run first among inserts into the **same** variadic
  hole; **equal `order`** ties keep **first-added edge first** order.
- **`ref`** is an optional **descendant/build path** for decorator-form shells.
  The public/source form uses the same fluent syntax as builder addressing:

```python
@astichi_insert(body, ref=Pipeline.Parse)
def parse_shell():
    ...

@astichi_insert(body, ref=Pipeline.Parse[1, 2].Normalize)
def normalize_shell():
    ...
```

- `ref=` is metadata for block shells. Expression-form
  `astichi_insert(target, expr)` does **not** take `ref=`.
- Builder-generated shells emit `ref=` automatically so later build stages can
  address descendants with the same fluent path language.

## `astichi_funcargs(...)`

- Authored call-argument payload surface for:
  - plain call-position holes: `func(astichi_hole(args))`
  - starred call holes: `func(*astichi_hole(args))`
  - double-starred call holes: `func(**astichi_hole(kwargs))`
- Build/merge normalizes payload contributions through generated internal
  `astichi_insert(...)` wrappers until realization.
- `_=` is special only when its direct value is:
  - `astichi_import(name)`
  - `astichi_export(name)`
- `astichi_pass(name)` is the value-form participant and belongs in an emitted
  argument expression, not in `_=`:

```python
astichi_funcargs(
    (out := astichi_pass(seed)),
    _=astichi_export(out),
)
```

- User-authored `astichi_insert(target, expr)` is rejected for call-argument
  targets. It remains legacy behavior only for non-call expression targets.

## See also

- [marker-holes.md](marker-holes.md)
- **[§5.7–5.8](../../dev-docs/AstichiApiDesignV1.md)**
