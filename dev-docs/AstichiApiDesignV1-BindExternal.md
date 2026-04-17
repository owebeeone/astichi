# Astichi API design V1: external binding

This document defines the V1 surface for `astichi_bind_external` — the marker
that lets callers supply compile-time values into a composable.

Without this surface, every parameterized generator must author its parameters
directly into the source text, which defeats the structured-AST purpose of
the library. With it, a single generic composable can be specialized per
caller while retaining full AST-level composition benefits.

This document completes the "immediate open question" recorded in the
historical proposal §5.5.

Related documents:

- `astichi/dev-docs/AstichiApiDesignV1.md` (especially §5.4 on
  `astichi_bind_external`)
- `astichi/dev-docs/AstichiApiDesignV1-UnrollRevision.md` (bind enables
  non-literal-source loop domains)
- `astichi/dev-docs/IdentifierHygieneRequirements.md`
- `astichi/dev-docs/V2DeferredFeatures.md` §1.1 (active V2 tracker;
  originally deferred per `historical/V1DeferredFeatures.md §4.1`)

## 1. Problem statement

Today, `astichi_bind_external(name)` is recognized as a marker but has no
supporting infrastructure:

- The port-extraction pipeline (`src/astichi/model/ports.py`) does not
  create a demand port from it. Callers have no slot to fill.
- There is no `bind()` API — no way for a caller to say "for this snippet,
  `name` equals this compile-time value."
- There is no substitution engine — no pass that rewrites `Name(name,
  Load)` references to the supplied value.

The practical consequence: the canonical use case for a code generator —
"emit N accessors for a caller-supplied list of fields" — cannot be
expressed. Loop domains must be authored directly as literals in the
source, and every parameterization requires separate source text.

## 2. Canonical example

```python
source = """
astichi_bind_external(fields)

@astichi_insert(class_body)
def total(self):
    total = 0
    for name in astichi_for(fields):
        total = total + getattr(self, name)
    return total
"""

snippet = astichi.compile(source)
bound = snippet.bind(fields=("a", "b", "c"))
```

After `bind(...)`, the internal AST transitions from:

```python
astichi_bind_external(fields)

@astichi_insert(class_body)
def total(self):
    total = 0
    for name in astichi_for(fields):
        total = total + getattr(self, name)
    return total
```

to:

```python
@astichi_insert(class_body)
def total(self):
    total = 0
    for name in astichi_for(("a", "b", "c")):
        total = total + getattr(self, name)
    return total
```

Two things happen:

1. The `astichi_bind_external(fields)` statement is **removed** from the
   enclosing body.
2. Every `Name(id="fields", ctx=Load)` is **replaced** with the AST
   representation of `("a", "b", "c")`.

End-to-end composition then proceeds normally:

```python
result = (
    astichi.build()
    .add.Shell(astichi.compile(
        "class Subject:\n    astichi_hole(class_body)\n"
    ))
    .add.Totaller(bound)
    .Shell.class_body.add.Totaller()
    .build(unroll=True)
    .materialize()
)
```

Emitted source:

```python
class Subject:
    def total(self):
        total = 0
        total = total + getattr(self, "a")
        total = total + getattr(self, "b")
        total = total + getattr(self, "c")
        return total
```

## 3. Value-shape policy

V1 accepts a narrow, literal-only value set. These are the values that
round-trip faithfully through `ast.Constant` and standard AST node types:

- `int`, `float`, `str`, `bool`, `None`
- `tuple` and `list` recursively containing any of the above (nested
  collections are allowed)

Values explicitly **rejected** in V1:

- `dict` — no direct AST representation that preserves semantic intent
  across use-sites (are the keys identifiers? constants?). Deferred.
- `set` / `frozenset` — unordered, hurts determinism. Deferred.
- Arbitrary objects, callables, class instances — substituting these
  would require persisting references, which crosses from "compile-time
  data" into "runtime data." Out of scope for V1.
- `bytes` — deferrable; `ast.Constant(bytes)` works, but use cases are
  niche. Not a V1 priority; can be added in a minor extension.
- `complex` — deferrable; same reason.

Rejected values produce a clear `ValueError` at `bind()` time, before
any AST mutation.

Examples:

```python
# Accepted — scalar literals.
snippet.bind(count=3)
snippet.bind(label="row")
snippet.bind(pi=3.14)
snippet.bind(enabled=True)
snippet.bind(sentinel=None)

# Accepted — recursive tuple/list of scalars.
snippet.bind(fields=("a", "b", "c"))
snippet.bind(rows=[("a", 1), ("b", 2)])
snippet.bind(matrix=[[1, 2], [3, 4]])
snippet.bind(mixed=("header", 0, True, None, ("nested", "tuple")))

# Rejected — not part of the V1 value-shape policy.
snippet.bind(config={"k": "v"})            # ValueError: dict not supported
snippet.bind(tags={"a", "b"})              # ValueError: set not supported
snippet.bind(client=HttpClient())          # ValueError: object not supported
snippet.bind(hook=lambda x: x)             # ValueError: callable not supported
snippet.bind(data=b"bytes")                # ValueError: bytes deferred
snippet.bind(nested=(1, {"k": 1}))         # ValueError: dict inside tuple
```

## 4. Python value → AST converter

A pure helper:

```python
def value_to_ast(value: object) -> ast.expr: ...
```

Rules:

| Input | Output |
|-------|--------|
| `int`, `float`, `str`, `bool`, `None` | `ast.Constant(value=...)` |
| `tuple` | `ast.Tuple(elts=[value_to_ast(v) for v in value], ctx=Load())` |
| `list` | `ast.List(elts=[value_to_ast(v) for v in value], ctx=Load())` |
| any other type | raise `ValueError` with type name |

Placement: `src/astichi/model/external_values.py` (new module). Pure
function, no cross-layer dependencies.

Recursion guard: V1 caps nesting depth at 32 to catch accidental
self-references and keep errors friendly. Deeper legitimate structures
should be decomposed or handled by a later pass.

Concrete conversions (Python value → AST node → unparsed form):

```python
value_to_ast(3)
# → Constant(value=3)
# unparsed: "3"

value_to_ast("row")
# → Constant(value="row")
# unparsed: "'row'"

value_to_ast(True)
# → Constant(value=True)
# unparsed: "True"

value_to_ast(None)
# → Constant(value=None)
# unparsed: "None"

value_to_ast(("a", "b", "c"))
# → Tuple(elts=[Constant("a"), Constant("b"), Constant("c")], ctx=Load())
# unparsed: "('a', 'b', 'c')"

value_to_ast([1, 2, 3])
# → List(elts=[Constant(1), Constant(2), Constant(3)], ctx=Load())
# unparsed: "[1, 2, 3]"

value_to_ast((1, ("nested", "tuple")))
# → Tuple(elts=[
#       Constant(1),
#       Tuple(elts=[Constant("nested"), Constant("tuple")], ctx=Load()),
#   ], ctx=Load())
# unparsed: "(1, ('nested', 'tuple'))"

value_to_ast({"k": 1})
# → raises ValueError("unsupported binding value type: dict")
```

## 5. Port model integration

`astichi_bind_external(name)` becomes a first-class demand port alongside
`astichi_hole`. Extraction logic in
`src/astichi/model/ports.py::extract_demand_ports`:

```python
DemandPort(
    name=marker.name_id,
    shape=SCALAR_EXPR,
    placement="expr",
    mutability="const",
    sources=frozenset({"bind_external"}),
)
```

Rationale for this shape:

- **`SCALAR_EXPR`**: the bound value appears in expression positions
  (loop domains, function arguments, constant initializers).
- **`placement="expr"`**: compatible with the relaxed expr-placement
  rule introduced by 4i (any expr shape satisfies any expr demand).
- **`mutability="const"`**: bindings are compile-time constants; they
  cannot be mutated post-bind.
- **`sources={"bind_external"}`** distinguishes this demand from
  `sources={"hole"}` so `materialize()`'s mandatory-demand closure can
  decide per-source whether satisfaction is required.

Example trace. Given:

```python
snippet = astichi.compile("""
astichi_bind_external(fields)
astichi_bind_external(row_count)
for name in astichi_for(fields):
    ...
""")
```

`snippet.demand_ports` then includes (in addition to any hole
demands):

```python
DemandPort(
    name="fields",
    shape=SCALAR_EXPR,
    placement="expr",
    mutability="const",
    sources=frozenset({"bind_external"}),
)
DemandPort(
    name="row_count",
    shape=SCALAR_EXPR,
    placement="expr",
    mutability="const",
    sources=frozenset({"bind_external"}),
)
```

After `snippet.bind(fields=("a", "b"), row_count=2)`, both demand
ports are gone and the corresponding marker statements have been
removed from the tree.

## 6. Binding API surface

### 6.1 `Composable.bind(*mapping, **values)`

```python
# Keyword form (primary).
bound = snippet.bind(fields=("a", "b", "c"))

# Mapping positional form (for runtime-sourced keys).
bound = snippet.bind({"fields": ("a", "b", "c")})

# Both forms may be combined; keyword entries win on key collision
# (standard dict(**mapping, **kwargs) discipline).
bound = snippet.bind({"fields": base_fields}, mode=caller_mode)
```

Signature (locked for V2):

```python
def bind(
    self,
    mapping: Mapping[str, object] | None = None,
    /,
    **values: object,
) -> BasicComposable: ...
```

Semantics:

- Returns a new immutable `Composable`.
- Accepts either the positional mapping, the keyword form, or both.
  The two forms are merged via `dict(**mapping, **values)`; keyword
  entries override mapping entries on collision. Each effective key
  must be a valid Python identifier.
- Applies substitution and marker-statement removal (§7) to a deep copy
  of the internal AST.
- Re-extracts markers and ports on the mutated AST (same discipline as
  `build_merge` in 5a).
- Raises at bind time if any binding value has an unsupported shape
  (§3) or if substitution fails under the rules of §7.

Rationale for accepting both forms:

- The keyword form is the clean user-facing surface and covers the
  common case.
- The mapping form is needed whenever keys come from runtime data
  (e.g. driven by a user-supplied config or generated from another
  composable's port set). Without it, callers would have to construct
  a dict and unpack it, which fails on non-identifier keys silently.
- Implementation cost is negligible (one extra line in the signature).

### 6.2 Interaction with `materialize()`

After `bind()`, any `astichi_bind_external(...)` site that was **not**
satisfied by the binding remains in the tree as a demand. `materialize()`
rejects these the same way it rejects unresolved holes today:

- Demand ports with `sources={"bind_external"}` that are still present
  at materialize time are mandatory.
- Error: "external binding for `<name>` was not supplied; call
  `composable.bind(<name>=...)` before materializing."

This keeps the materialize hard-gate behavior consistent with 5c.

Example:

```python
snippet = astichi.compile("""
astichi_bind_external(fields)
astichi_bind_external(row_count)
""")

# Only one of the two externals bound.
partial = snippet.bind(fields=("a", "b"))

partial.materialize()
# ValueError: external binding for `row_count` was not supplied;
# call composable.bind(row_count=...) before materializing.
```

### 6.3 Partial bindings

`bind()` accepts a subset of the snippet's external demands. Remaining
demands carry forward on the returned composable and can be filled by a
later `bind()` call:

```python
snippet = astichi.compile("""
astichi_bind_external(fields)
astichi_bind_external(row_count)
""")

stage1 = snippet.bind(fields=("a", "b"))
# stage1.demand_ports still contains row_count.

stage2 = stage1.bind(row_count=2)
# stage2 has no bind_external demand ports left.

final = stage2.materialize()
```

Both stages produce valid composables; only the final materialize
requires all externals to be supplied.

### 6.4 Re-binding a name is an error

If a name has already been satisfied by a prior `bind()` (the marker
statement is gone and references are substituted), calling `bind()`
again for the same name is an error: the substitutable site no longer
exists. Error message names the offending key and suggests that the
bind was already applied.

```python
snippet = astichi.compile("astichi_bind_external(fields)\n")

bound = snippet.bind(fields=("a", "b"))
bound.bind(fields=("x", "y"))
# ValueError: cannot re-bind `fields`: the external binding has already
# been applied to this composable; bind produces a new immutable
# snapshot — start from the pre-bind composable to rebind with a
# different value.
```

### 6.5 Binding a name not present in the tree is an error

`snippet.bind(unknown=1)` when `unknown` has no corresponding
`astichi_bind_external(unknown)` in the tree raises at bind time.
Silent acceptance would mask typos; V1 prefers strictness.

```python
snippet = astichi.compile("astichi_bind_external(fields)\n")

snippet.bind(feilds=("a", "b"))   # typo
# ValueError: no astichi_bind_external(feilds) site found; known
# bind-external demands on this composable: ('fields',).
```

### 6.6 Scope on the Composable type

`bind()` belongs on `BasicComposable` (the concrete V1 carrier). Future
carrier types (`Source`, `Compiled`, etc. — deferred per
`historical/V1DeferredFeatures.md` §3.3) inherit the discipline independently.

## 7. Substitution engine

New module: `src/astichi/lowering/external_bind.py`.

Primary function:

```python
def apply_external_bindings(
    tree: ast.Module,
    bindings: dict[str, object],
) -> None: ...
```

Mutates `tree` in place (after deep-copy at the API boundary).

### 7.1 Marker statement removal

For each `ast.Expr` statement whose value is
`Call(func=Name("astichi_bind_external"), args=[Name(target_name)])`:

- If `target_name in bindings`: remove the statement from the enclosing
  body.
- If `target_name not in bindings`: leave the statement in place (a
  later `bind()` call may satisfy it, or `materialize()` will reject it).

Recurses through every body-bearing compound statement
(`FunctionDef`, `AsyncFunctionDef`, `ClassDef`, `If`, `For`, `While`,
`With`, `Try`, etc.) — same traversal shape as the block-hole splice
in 5a.

Example. Source:

```python
astichi_bind_external(fields)
astichi_bind_external(row_count)
print(fields)
print(row_count)
```

After `bind(fields=("a", "b"))` (partial):

```python
astichi_bind_external(row_count)
print(('a', 'b'))
print(row_count)
```

The `fields` marker statement was removed; the `row_count` marker
statement and its `Load` reference were left alone.

### 7.2 Load-context substitution

For each `Name(id=n, ctx=Load())` in the tree where `n in bindings`:

- Replace the node with `value_to_ast(bindings[n])` at the same
  structural position.
- Preserve surrounding node fields (location info is fresh from
  `ast.fix_missing_locations`).

Other name contexts (`Store`, `Del`, `Param`) are not touched.
Conceptually: bind replaces *reads* of an external name; writes are
a separate phenomenon (and are governed by §7.4).

Example. Source (partial snippet, assume the marker is elsewhere):

```python
count = len(fields)               # Load → substituted
fields = fields + ("x",)          # Store (left) untouched; Load (right) substituted
del fields                        # Del untouched
```

After `bind(fields=("a", "b"))` of a snippet that *does not* declare
`fields` in the same scope (§7.4):

```python
count = len(('a', 'b'))
fields = ('a', 'b') + ("x",)
del fields
```

In practice, a snippet that writes to `fields` at the same scope as
`astichi_bind_external(fields)` is rejected by §7.4 — the above
illustration is purely to show which AST contexts are in and out of
scope for the substitution pass.

### 7.3 Scope-aware substitution

Substitution halts at any inner scope boundary that re-parameterizes
the bound name. This mirrors the scope-aware rule already specified in
`AstichiApiDesignV1-UnrollRevision.md §5.3.1`:

Scope boundaries that block substitution:

- `FunctionDef` / `AsyncFunctionDef` parameters and body (when a
  parameter shadows the bound name)
- `Lambda` arguments
- `ClassDef` body (class scope)
- Comprehension expressions (`ListComp`, `SetComp`, `DictComp`,
  `GeneratorExp`) — their target variables create a nested scope
- `For` and `AsyncFor` targets when the loop variable shadows the
  bound name

Inside a shadowing scope, references to the same name refer to the
inner binding, not the external, and are left untouched.

Examples for each recognized scope boundary. All use the same snippet
prefix:

```python
astichi_bind_external(fields)
```

bound with `bind(fields=("a", "b"))`. Only the relevant body is shown
for each case.

**Function parameter shadow.** The parameter re-binds the name; the
inner `fields` reference is *not* substituted:

```python
# before
def f(fields):
    return fields

# after bind — unchanged (inner name is local)
def f(fields):
    return fields
```

**Lambda argument shadow.** Same principle:

```python
# before
g = lambda fields: fields

# after bind — unchanged
g = lambda fields: fields
```

**Comprehension target shadow.** The comprehension target creates its
own scope; inner references are local:

```python
# before
doubled = [fields for fields in range(3)]

# after bind — unchanged
doubled = [fields for fields in range(3)]
```

**`for`-target shadow.** The outer-scope `fields` read in the loop
header is substituted, but the loop body sees the loop-local
re-binding and is not substituted:

```python
# before
for fields in ("x", "y"):
    print(fields)

# after bind — header iter is NOT the external, because there is no
# outer Load here (the iter literal is authored), and the body sees
# the loop-local `fields`. If the iter *had* read an external,
# substitution would apply there.
for fields in ("x", "y"):
    print(fields)
```

A more illustrative variant where the iter *does* reference the
external (a different external name to avoid the §7.4 same-scope
rebind trip):

```python
# before
astichi_bind_external(fields)
for x in fields:
    fields = transform(x)    # same-scope rebind — rejected by §7.4
    print(fields)
```

That case is rejected at bind time (§7.4). The hygienic shape is
either to keep the external read-only in its scope, or to shadow
inside a child scope such as a nested function.

**Outer reads that are substituted.** Reads outside any shadowing
scope are replaced:

```python
# before
astichi_bind_external(fields)
count = len(fields)
def f(other):
    return fields + other   # fields here IS the external

# after bind(fields=("a", "b"))
count = len(('a', 'b'))
def f(other):
    return ('a', 'b') + other
```

`ClassDef` bodies create a class-local scope similarly; a class-level
`fields = ...` assignment introduces a new binding visible only to
the class scope, and inner references to `fields` refer to the class
attribute, not the external.

### 7.4 Same-scope rebinding is rejected

If the same scope that declared `astichi_bind_external(name)` re-binds
`name` at the top level (e.g. `name = 5`), the binding is rejected at
bind time with a clear message. The substitution model assumes the
declared name is stable within its scope; shadowing via assignment
produces ambiguous semantics.

Exception: intentional loop-target overlap inside nested for-loops is
permitted because the `For` target creates a recognized scope boundary
(§7.3); the inner reference is never substituted.

```python
# REJECTED — same scope assigns to `fields` after the external marker.
astichi_bind_external(fields)
fields = ("x", "y")
print(fields)
# ValueError: same-scope rebind of externally bound name `fields`
# at line 2; declare the external at an inner scope or remove the
# rebind.

# REJECTED — augmented assignment counts as a write.
astichi_bind_external(fields)
fields += ("x",)
# ValueError: same-scope rebind of externally bound name `fields`
# at line 2.

# ACCEPTED — rebinding happens in an inner scope (function body); the
# outer `fields` is still read-only at its own scope.
astichi_bind_external(fields)
def mutate():
    fields = ("x", "y")
    return fields
print(fields)   # outer read — substituted

# ACCEPTED — the `for`-target creates a scope boundary.
astichi_bind_external(fields)
for fields in ("x", "y"):
    print(fields)   # loop body: inner `fields`, untouched
print(fields)       # after the loop: outer `fields`, substituted
```

### 7.5 Markers whose argument is a bound name

A name-bearing marker (`astichi_keep(name)`, `astichi_hole(name)`,
`astichi_export(name)`, `astichi_definitional_name(name)`, etc.) whose
identifier argument matches an externally bound name is rejected at
bind time. Rationale: substitution would turn the marker's identifier
argument into a constant literal, violating the "marker argument must
be a bare identifier" contract.

This check is syntactic and happens before substitution so the error
clearly attributes the conflict to the bind rather than to a downstream
lowering-validator failure.

This mirrors `AstichiApiDesignV1-UnrollRevision.md §5.5`.

```python
# REJECTED — `astichi_hole(fields)` takes `fields` as a *marker
# identifier argument*, not a read. Substituting here would turn the
# identifier into a literal and break the hole's addressing contract.
astichi_bind_external(fields)
astichi_hole(fields)
snippet.bind(fields=("a", "b"))
# ValueError: external binding `fields` collides with a name-bearing
# marker identifier at line 2 (astichi_hole). Rename one or the other.

# ACCEPTED — different names, no conflict.
astichi_bind_external(fields)
astichi_hole(slot)
snippet.bind(fields=("a", "b"))   # OK
```

## 8. Interaction with V1-lite loop unroll

Bind is specifically the mechanism that unlocks non-literal-source loop
domains for V1-lite unroll. Workflow:

```python
snippet = astichi.compile("""
astichi_bind_external(fields)
for name in astichi_for(fields):
    astichi_hole(slot)
""")

bound = snippet.bind(fields=("a", "b", "c"))
# After bind: astichi_for(("a", "b", "c"))  -- now literal.

builder = astichi.build()
builder.add.Main(bound)
builder.Main.slot[0].add.X()  # indexed edge triggers unroll (auto-detect)
result = builder.build()
```

The unroll pass (per `AstichiApiDesignV1-UnrollRevision.md`) sees a
literal tuple domain and proceeds normally. No coordination is needed
between the two passes; they are purely sequential — bind first, then
unroll.

The UnrollRevision doc's §7 ("Domain support") is amended to include:
"Domains that become literal after `bind()` substitution" — the
unroller sees the post-bind form unconditionally.

## 9. Interaction with hygiene, provenance, emit

### 9.1 Hygiene

Bound values are literal AST nodes with no `Name` content (they are
recursive combinations of `Constant`, `Tuple`, `List`). Hygiene's scope
identity and collision rename passes do not interact with them. No
changes to the hygiene engine.

Illustrative sequence — bind does not introduce new name collisions:

```python
snippet = astichi.compile("""
astichi_bind_external(fields)
value = 1
def inner():
    value = 2            # local
    return value
""")

bound = snippet.bind(fields=("a", "b"))
# Post-bind AST has no new Names; the literal ('a', 'b') contains only
# Constant nodes. Hygiene's scope identity pass sees the same Name
# graph as pre-bind (minus the marker statement). No rename.
```

### 9.2 Provenance

The pickled provenance payload (per 6b) reflects the post-bind tree.
Round-trip reads back the bound form unchanged. This is consistent
with the "source-is-authoritative" discipline: the emitted source
already shows the bound values, and the payload matches.

A caller that wants to preserve the pre-bind form for later
re-binding with different values must retain a reference to the
pre-bind composable — bind produces a new immutable snapshot.

```python
snippet = astichi.compile("""
astichi_bind_external(fields)
for name in astichi_for(fields):
    ...
""")

bound_a = snippet.bind(fields=("a", "b"))
bound_b = snippet.bind(fields=("x", "y"))
# snippet, bound_a, bound_b are three distinct immutable composables;
# each has its own provenance payload reflecting its own tree.

emitted = bound_a.emit()
# emitted contains:
#   # astichi-provenance: <base64 payload of bound_a tree>
#   for name in astichi_for(('a', 'b')):
#       ...

verify_round_trip(emitted)   # passes; extracted AST matches bound_a.tree
```

### 9.3 Emit

No changes. `ast.unparse` handles `Constant`, `Tuple`, `List` normally.
Emitted source reads naturally as Python:

```python
for name in astichi_for(("a", "b", "c")):
    ...
```

or, after unroll:

```python
# loop eliminated, three copies of the body with name substituted
```

## 10. Error model

Errors raised at `bind()` time (before any mutation is visible):

- **`ValueError`**: unsupported value shape per §3, nesting depth
  exceeded, list/tuple contains disallowed element.
- **`ValueError`**: binding key is not a valid Python identifier.
- **`ValueError`**: binding key has no corresponding
  `astichi_bind_external(...)` site in the tree (§6.5).
- **`ValueError`**: name already bound by a prior `bind()` call (§6.4).
- **`ValueError`**: same-scope rebinding of a bound name (§7.4).
- **`ValueError`**: a name-bearing marker's identifier argument matches
  a bound name (§7.5).

Errors raised at `materialize()` time:

- **`ValueError`**: an `astichi_bind_external(...)` demand remains
  unsatisfied (§6.2).

Errors at edge resolution / build time remain unchanged from existing
V1 behavior — bind does not add new edge-resolution failure modes.

Compact examples for each failure mode:

```python
# Unsupported value shape (§3).
snippet.bind(fields={"a": 1})
# ValueError: unsupported binding value type for `fields`: dict.

# Non-identifier key (mapping form).
snippet.bind({"1fields": ("a",)})
# ValueError: binding key `1fields` is not a valid Python identifier.

# Unknown key (§6.5).
snippet.bind(feilds=("a", "b"))
# ValueError: no astichi_bind_external(feilds) site found; known
# bind-external demands on this composable: ('fields',).

# Already-bound re-bind (§6.4).
snippet.bind(fields=("a",)).bind(fields=("x",))
# ValueError: cannot re-bind `fields`: the external binding has
# already been applied to this composable.

# Same-scope rebind (§7.4).
astichi.compile("astichi_bind_external(fields)\nfields = ()\n").bind(fields=())
# ValueError: same-scope rebind of externally bound name `fields`.

# Marker-argument conflict (§7.5).
astichi.compile("astichi_bind_external(slot)\nastichi_hole(slot)\n").bind(slot=1)
# ValueError: external binding `slot` collides with a name-bearing
# marker identifier at line 2 (astichi_hole).

# Unsatisfied demand at materialize (§6.2).
astichi.compile("astichi_bind_external(fields)\n").materialize()
# ValueError: external binding for `fields` was not supplied;
# call composable.bind(fields=...) before materializing.
```

## 11. Forward compatibility

The V1 bind surface deliberately stays narrow to leave room for future
work:

- **Richer value types** (dict, custom objects, callables) — can be
  added by extending `value_to_ast` and the value-shape policy without
  changing the API surface.
- **`ComposeContext`** (proposal §5.3): a future `astichi.build(bind={...})`
  or `astichi.build(context=ComposeContext(...))` can layer on top of
  the same substitution engine.
- **Runtime-visible externals** (values evaluated at runtime rather
  than baked in at compile time) are a separate feature entirely and
  do not affect this surface.
- **Typed externals**: a future port-level type summary can attach
  expected-type metadata to the `bind_external` demand port without
  breaking V1 callers.

## 12. Resolved questions

Resolutions recorded for traceability. All locked; no open questions
remain for V2 bind implementation.

### 12.1 `.bind()` kwargs vs mapping — **LOCKED**

`.bind()` accepts **both** a positional mapping and `**values`, merged
via `dict(**mapping, **values)` with keyword entries winning on
collision. See §6.1 for the locked signature. Rationale: the mapping
form is needed when keys come from runtime data.

### 12.2 Binding ordering within a single call — **LOCKED**

When `bind(a=1, b=2)` is called, substitutions happen in parallel
(both markers removed, both sets of references replaced) rather than
sequentially. Required because sequential semantics could make result
depend on dict iteration order.

Substitutions happen in parallel (locked in §7). No user-visible
ordering dependency.

```python
snippet = astichi.compile("""
astichi_bind_external(a)
astichi_bind_external(b)
print(a, b)
print(b, a)
""")

# Parallel semantics: `a`'s value never has `b` substituted into it
# (or vice versa) because bind values are literal Python objects,
# not AST fragments. Order of kwargs is irrelevant.
assert (
    snippet.bind(a=1, b=2).emit()
    == snippet.bind(b=2, a=1).emit()
)
```

### 12.3 Nested binding values referencing each other — **LOCKED**

Is `snippet.bind(fields=(x, y))` meaningful when `x` and `y` are Python
variables in the caller's scope holding other bound names? The answer
is no — by the time the tuple is passed in, `x` and `y` are already
ordinary Python values, not references.

Values are resolved in the caller's Python scope before being passed
to `bind()`; bind never resolves names itself.

```python
# Caller-side Python — `fields` is just a Python variable here.
fields = ("a", "b", "c")

# bind receives the tuple value; it never inspects the caller's
# Python scope to see where `fields` came from.
bound = snippet.bind(fields=fields)

# Re-binding the caller-side variable has no effect on `bound`.
fields = ("x", "y")
# bound still holds ("a", "b", "c") — bind is snapshot-based.
```

### 12.4 Bind-only snippets without any markers to satisfy — **LOCKED**

`snippet.bind()` with no kwargs on a snippet that has no
`astichi_bind_external` sites is a no-op: returns a new composable
identical to the original (the snapshot discipline makes this
trivially cheap).

```python
snippet = astichi.compile("x = 1\nprint(x)\n")
# No astichi_bind_external(...) markers in this snippet.

same = snippet.bind()           # empty bind, no kwargs
assert same is not snippet      # new immutable snapshot
assert same.emit() == snippet.emit()

# Equivalent with an empty mapping.
snippet.bind({})                # same no-op behavior
```

## 13. Implementation outline

1. **New helpers in `src/astichi/model/external_values.py`**:
   - `value_to_ast(value) -> ast.expr`
   - `validate_external_value(value) -> None`
2. **New pass in `src/astichi/lowering/external_bind.py`**:
   - `apply_external_bindings(tree, bindings) -> None`
   - Internal scope-aware substitution visitor (mirrors the unroll
     visitor; refactor shared scope-boundary logic into a helper in
     `src/astichi/asttools/` once both passes land).
3. **Extend `src/astichi/model/ports.py::extract_demand_ports`** to
   emit demand ports for `astichi_bind_external` markers (§5).
4. **Extend `src/astichi/model/basic.py::BasicComposable`** with
   `.bind(mapping=None, /, **values) -> BasicComposable` per §6.1:
   - Merge `mapping` and `values` via `dict(**mapping, **values)`
     with `values` winning on collision; reject non-identifier keys.
   - Deep-copy the tree.
   - Validate each binding value (§3).
   - Validate scope and marker constraints (§7.4, §7.5, §6.4, §6.5).
   - Apply substitution.
   - Re-run `recognize_markers` and port extraction.
   - Return a new `BasicComposable`.
5. **Extend `src/astichi/materialize/api.py::materialize_composable`**:
   - Treat demand ports with `sources={"bind_external"}` as mandatory
     alongside `sources={"hole"}`.
6. **Update `AstichiApiDesignV1-UnrollRevision.md §7`** to add
   "post-bind literals" as a supported domain source.
7. **Record reinstatement in `V2DeferredFeatures.md §1.1`** (the active
   V2-era tracker). The frozen V1 list at
   `historical/V1DeferredFeatures.md §4.1` is not edited.
8. **Tests** (new file `tests/test_bind_external.py`):
   - Value-shape policy: int, float, str, bool, None, tuple, list,
     nested; dict/set/object rejected.
   - Simple substitution: single name, multiple sites.
   - Multiple names in one `bind()` call.
   - Partial bind: two `bind()` calls filling different names.
   - Rebind error: bind-then-bind-same-name.
   - Unknown-binding error: bind with key not present in tree.
   - Scope-aware shadowing: function parameter, lambda parameter,
     comprehension target, nested `for` loop with same variable.
   - Same-scope rebind rejection.
   - Marker-argument conflict rejection.
   - Materialize error when bind_external demand remains.
   - End-to-end with unroll: bind unlocks literal domain, unroll
     produces flat body.
   - Nested/complex values: `fields=("a", ("b", ("c",)))`.
   - Collection types: tuple of tuples, list of lists, mixed.
   - Provenance round-trip over a bound composable.
   - Emit produces valid Python after bind.

## 14. Plan placement

V2 scope sequencing is tracked in `V2Plan.md`. Bind ships as Phase 1
before unroll (Phase 2) because:

- Bind is self-contained and adds the scope-aware substitution visitor
  that unroll reuses.
- Bind broadens the class of programs that benefit from unroll (see §8:
  post-bind literal domains feed the unroll pass).

The reverse ordering is also defensible (unroll can ship against pure
literal domains alone), but V2 adopts bind-first for the shared-visitor
reason above.
