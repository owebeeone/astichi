# Marker: `astichi_ref`

`astichi_ref(...)` is the authored value-form **reference** surface. It takes a
compile-time path string and lowers it at materialize time into the
corresponding `Name` / `Attribute` chain. It is the right tool whenever a
template needs to point at an externally chosen attribute path
(e.g. `self.f0`, `pkg.mod.attr`) without authoring that path as raw source
text.

**Normative spec:**
[`AstichiV3ExternalRefBind.m4`](../../dev-docs/AstichiV3ExternalRefBind.m4).

## Surface

```python
astichi_ref(value)
astichi_ref(external=name)
```

- `astichi_ref(value)` interprets `value` as a Python reference path; `value`
  must reduce at compile time to a string of dot-separated identifiers.
- `astichi_ref(external=name)` is sugar for
  `astichi_ref(astichi_bind_external(name))`. The inner `astichi_bind_external`
  surfaces a normal demand port, so `compose.bind(name=...)` and the
  `materialize` gate validate it like any other external bind.

The marker is **expression-only** in its bare form. Bare statement-form
`astichi_ref(...)` is rejected at `compile()` time. To use it as the target of
an `Assign`, `AugAssign`, or `Delete`, wrap it in the §3a sentinel attribute
described below. That same sentinel is also valid in ordinary expression
positions and is stripped exactly once at materialize time.

## Accepted values

The reduced value must be a non-empty string whose `.`-separated segments are
all valid Python identifiers. Examples:

```text
foo
self.f0
pkg.mod.attr
```

The argument expression may be:

- a string literal — `astichi_ref("pkg.mod.attr")`
- an f-string whose formatted parts reduce to compile-time scalars
- a compile-time subscript over a literal container (tuple/list/string)

Allowed compile-time scalar sources for f-string parts and subscripts:

- bare `astichi_for` loop variables (substituted to literals at unroll time)
- bare externally bound values (substituted to literals at `bind()` time)
- compile-time subscript lookups over those values

```python
# After unroll: i becomes 0, 1, 2 ...
for i in astichi_for((0, 1, 2)):
    value = astichi_ref(f"self.f{i}")

# After bind(prefix="self"): prefix becomes the literal "self".
astichi_bind_external(prefix)
value = astichi_ref(f"{prefix}.field")

# Compile-time subscript over a bound tuple:
astichi_bind_external(names)
value = astichi_ref(f"{names[0]}.{names[1]}")
```

The lowering pass **never** executes arbitrary Python to compute the path
string. Calls, attribute reads, arithmetic, slice notation, and unbound names
inside an `astichi_ref` argument are all rejected.

## Lowering

After `bind()` substitutions and `astichi_for` unrolling have run, materialize
applies `apply_external_ref_lowering`:

- `astichi_ref("foo")` → `foo` (`ast.Name`)
- `astichi_ref("a.b.c")` → `a.b.c` (`ast.Attribute(ast.Attribute(ast.Name))`)
- `call(astichi_ref("a.b"))` → `call(a.b)`

The chain head is then a normal `ast.Name` / `ast.Attribute` and participates
in the usual hygiene pass.

## §3a: LHS, AugAssign, and Delete sites

Python's grammar rejects a bare `Call` as the target of `Assign`, `AugAssign`,
or `Delete`. To use `astichi_ref(...)` in those positions, wrap the call in a
sentinel attribute access:

```python
astichi_ref(path).astichi_v = value      # Store:    lowers to <path> = value
astichi_ref(path).astichi_v += 1         # AugStore: lowers to <path> += 1
del astichi_ref(path).astichi_v          # Delete:   lowers to del <path>
```

`._` is accepted as a shorthand synonym of `.astichi_v`, mirroring the `_=`
carrier in `astichi_funcargs(...)`.

The first immediate sentinel segment after `astichi_ref(...)` is stripped at
lowering time and its `ctx` (`Load`, `Store`, `Del`) is propagated onto the
rightmost node of the lowered chain. The sentinel attribute name is **never**
observed at runtime.

Examples after lowering with `bind(path="self.f0")`:

```python
astichi_ref(path).astichi_v = 42         #  ->  self.f0 = 42
total += astichi_ref(path).astichi_v     #  ->  total += self.f0
astichi_ref(path).astichi_v ^= 1         #  ->  self.f0 ^= 1
del astichi_ref(path).astichi_v          #  ->  del self.f0
```

The strip is **one-shot**. Any further postfix syntax is preserved literally
and applies to the lowered reference:

```python
astichi_ref("pkg.mod").other             #  ->  pkg.mod.other
astichi_ref("pkg.mod")._.other           #  ->  pkg.mod.other
astichi_ref("factory").astichi_v()       #  ->  factory()
astichi_ref("obj")._._                   #  ->  obj._
```

## Loop / unroll example

```python
# Build with unroll=True (or rely on auto-unroll from indexed edges).
for spec in astichi_for(((1, "self.f0", 42), (2, "self.f1", 43))):
    if not (m & spec[0]):
        astichi_ref(spec[1]).astichi_v = spec[2]
        m |= spec[0]
```

After unroll, `spec` is the iteration tuple literal; the compile-time
subscript `spec[1]` reduces to `"self.f0"` (and `"self.f1"` for the next
iteration), and the sentinel wrapper materialises each LHS as the
corresponding attribute store.

## Rejection cases

The following shapes are rejected. Surface-level shape errors fire at
`compile()`; path-string content errors fire at `materialize()`.

Value-form rejections:

- `astichi_ref()` — missing argument
- `astichi_ref(external=path, other=x)` — extra keyword
- `astichi_ref(positional, external=name)` — positional and `external=` mixed
- `astichi_ref(external="pkg.mod")` — `external=` must be a bare identifier
- `astichi_ref("a..b")` — empty path segment
- `astichi_ref("")` — empty path
- `astichi_ref("a.1b")` — non-identifier segment
- `astichi_ref(f"{obj.attr}")` — attribute read in formatted part
- `astichi_ref(f"{make_name()}")` — call in formatted part

There are no extra chained-sentinel rejection rules. The first immediate
`.astichi_v` / `._` segment is simply removed, once, and any later postfix
syntax is treated as ordinary Python on the lowered reference.

## Pipeline ordering

`astichi_ref` is lowered at materialize time, after:

1. `compose.bind(...)` has substituted `astichi_bind_external` sites and
   bound-name `Load` references with literals.
2. `build(unroll=True)` (or auto-unroll) has substituted `astichi_for` loop
   variables with their per-iteration literal values.

By that point every legal `astichi_ref(...)` argument is reducible by the
restricted compile-time evaluator. The lowering runs **before** hygiene so the
lowered chain heads participate in scope analysis as ordinary identifier
expressions.

## See also

- [`marker-overview.md`](marker-overview.md) — full marker vocabulary
- [`marker-for-and-insert.md`](marker-for-and-insert.md) — `astichi_for` and
  `astichi_funcargs`
- [`AstichiV3ExternalRefBind.m4`](../../dev-docs/AstichiV3ExternalRefBind.m4) —
  normative spec
