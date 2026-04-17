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
- `astichi/dev-docs/V1DeferredFeatures.md` §4.1 (supersedes the deferral)

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

## 6. Binding API surface

### 6.1 `Composable.bind(**values)`

```python
bound = snippet.bind(fields=("a", "b", "c"), mode="strict")
```

Semantics:

- Returns a new immutable `Composable`.
- `**values` is the natural keyword-argument form. Each key must be a
  valid Python identifier.
- Applies substitution and marker-statement removal (§7) to a deep copy
  of the internal AST.
- Re-extracts markers and ports on the mutated AST (same discipline as
  `build_merge` in 5a).
- Raises at bind time if any binding value has an unsupported shape
  (§3) or if substitution fails under the rules of §7.

### 6.2 Interaction with `materialize()`

After `bind()`, any `astichi_bind_external(...)` site that was **not**
satisfied by the binding remains in the tree as a demand. `materialize()`
rejects these the same way it rejects unresolved holes today:

- Demand ports with `sources={"bind_external"}` that are still present
  at materialize time are mandatory.
- Error: "external binding for `<name>` was not supplied; call
  `composable.bind(<name>=...)` before materializing."

This keeps the materialize hard-gate behavior consistent with 5c.

### 6.3 Partial bindings

`bind()` accepts a subset of the snippet's external demands. Remaining
demands carry forward on the returned composable and can be filled by a
later `bind()` call:

```python
stage1 = snippet.bind(fields=("a", "b"))
stage2 = stage1.bind(mode="strict")
```

Both stages produce valid composables; only the final materialize
requires all externals to be supplied.

### 6.4 Re-binding a name is an error

If a name has already been satisfied by a prior `bind()` (the marker
statement is gone and references are substituted), calling `bind()`
again for the same name is an error: the substitutable site no longer
exists. Error message names the offending key and suggests that the
bind was already applied.

### 6.5 Binding a name not present in the tree is an error

`snippet.bind(unknown=1)` when `unknown` has no corresponding
`astichi_bind_external(unknown)` in the tree raises at bind time.
Silent acceptance would mask typos; V1 prefers strictness.

### 6.6 Scope on the Composable type

`bind()` belongs on `BasicComposable` (the concrete V1 carrier). Future
carrier types (`Source`, `Compiled`, etc. — deferred per
`V1DeferredFeatures.md` §3.3) inherit the discipline independently.

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

### 7.2 Load-context substitution

For each `Name(id=n, ctx=Load())` in the tree where `n in bindings`:

- Replace the node with `value_to_ast(bindings[n])` at the same
  structural position.
- Preserve surrounding node fields (location info is fresh from
  `ast.fix_missing_locations`).

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

### 7.4 Same-scope rebinding is rejected

If the same scope that declared `astichi_bind_external(name)` re-binds
`name` at the top level (e.g. `name = 5`), the binding is rejected at
bind time with a clear message. The substitution model assumes the
declared name is stable within its scope; shadowing via assignment
produces ambiguous semantics.

Exception: intentional loop-target overlap inside nested for-loops is
permitted because the `For` target creates a recognized scope boundary
(§7.3); the inner reference is never substituted.

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

### 9.2 Provenance

The pickled provenance payload (per 6b) reflects the post-bind tree.
Round-trip reads back the bound form unchanged. This is consistent
with the "source-is-authoritative" discipline: the emitted source
already shows the bound values, and the payload matches.

A caller that wants to preserve the pre-bind form for later
re-binding with different values must retain a reference to the
pre-bind composable — bind produces a new immutable snapshot.

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
- **`KeyError`** (or `ValueError`): binding key has no corresponding
  `astichi_bind_external(...)` site in the tree (§6.5).
- **`ValueError`**: same-scope rebinding of a bound name (§7.4).
- **`ValueError`**: a name-bearing marker's identifier argument matches
  a bound name (§7.5).

Errors raised at `materialize()` time:

- **`ValueError`**: an `astichi_bind_external(...)` demand remains
  unsatisfied (§6.2).

Errors at edge resolution / build time remain unchanged from existing
V1 behavior — bind does not add new edge-resolution failure modes.

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

## 12. Open questions (to resolve before implementation)

Numbered for discussion; my recommended answers included.

### 12.1 `.bind()` kwargs vs mapping

Should `.bind()` accept only `**values`, or also a `mapping` positional
argument (`snippet.bind({"fields": (...)})`)?

**Recommendation**: both, via a small overload. The mapping form is
needed when keys come from runtime data. Implementation cost is trivial.

### 12.2 Binding ordering within a single call

When `bind(a=1, b=2)` is called, substitutions happen in parallel
(both markers removed, both sets of references replaced) rather than
sequentially. Required because sequential semantics could make result
depend on dict iteration order.

**Recommendation**: parallel (locked in §7). No user-visible ordering
dependency.

### 12.3 Nested binding values referencing each other

Is `snippet.bind(fields=(x, y))` meaningful when `x` and `y` are Python
variables in the caller's scope holding other bound names? The answer
is no — by the time the tuple is passed in, `x` and `y` are already
ordinary Python values, not references.

**Recommendation**: documented as "values are resolved in the caller's
Python scope before being passed to `bind()`; bind never resolves
names itself."

### 12.4 Bind-only snippets without any markers to satisfy

`snippet.bind()` with no kwargs on a snippet that has no
`astichi_bind_external` sites — no-op or error?

**Recommendation**: no-op. Returns a new composable identical to the
original (the snapshot discipline makes this trivially cheap).

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
   `.bind(**values: object) -> BasicComposable`:
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
7. **Update `V1DeferredFeatures.md §4.1`** to move this item from
   deferred to in-scope, crossing out the deferral and pointing to
   this document.
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

## 14. Milestone placement

Suggested placement in the V1 execution plan:

- **Milestone 7**: Loop unroll (V1-lite, per
  `AstichiApiDesignV1-UnrollRevision.md`).
- **Milestone 8**: External bind (this document).

Ordering rationale: unroll can ship against literal domains alone,
covering a meaningful class of generators. Bind extends the surface by
producing literal domains from caller values, and depends on the
unroll pass's scope-aware substitution visitor as a reusable helper.
Building unroll first gives us the shared infrastructure; building
bind second turns parameterized generators from "almost possible" into
"practical."

Alternative: bind before unroll. This is defensible if parameterized
generators are more urgent than loop unrolling. The shared
infrastructure flows the other way — bind's substitution visitor gets
reused by unroll — and the net implementation cost is similar.
