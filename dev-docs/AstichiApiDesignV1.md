# Astichi API design V1

This document is the normative API/design statement for Astichi phase 1.

For rationale, alternatives, and explanatory narrative, see:

- `astichi/dev-docs/historical/AstichiApiDesignProposal.md`
- `astichi/dev-docs/IdentifierHygieneRequirements.md`

## 1. Scope

Astichi provides:

- a Python-shaped snippet compiler into `Composable`
- an immutable `Composable` model
- a mutable builder for composing `Composable` instances
- lowering/materialization into runnable Python forms
- optional emitted-source provenance support

Astichi phase 1 prioritizes:

- valid Python-shaped marker syntax
- explicit composition structure
- deterministic additive composition
- correct lexical hygiene
- low-complexity implementation choices

Astichi phase 1 does not lock:

- deep descendant traversal syntax beyond first-level addressing
- replacement semantics
- broad compile-time evaluation beyond the narrow supported domain set

## 2. Core objects

### 2.1 `Composable`

A `Composable` is an immutable carrier of Python-shaped program structure plus
composition metadata required for later transforms and materialization.

A `Composable` may contain unresolved:

- holes
- compile-time loops
- exports
- implied demands
- other marker-lowered structure

A `Composable` returned by `build()` is still a `Composable`.

### 2.2 Builder

The builder is a mutable composition graph over immutable `Composable`
instances.

The builder owns:

- named instances
- additive insertions/wirings
- ordering within variadic targets

The builder does not own the semantic source of markers; those come from the
compiled snippet source.

### 2.3 Demands and supplies

Astichi composition is defined in terms of:

- demand ports
- supply ports

Demand ports are places in a `Composable` that can accept composition input.
Examples:

- holes
- implied demands
- unresolved imports into the composition boundary

Supply ports are values/bindings a `Composable` can offer to other
`Composable`s. Examples:

- explicit exports
- definitional outputs lowered from snippet structure
- other implementation-defined supply points created during lowering

`astichi_export(...)` is the explicit source-surface mechanism for creating a
named supply port. It is not the only possible internal supply shape.

### 2.4 Handles

The builder API has three handle layers:

- builder handle
- instance handle
- target handle

Examples:

```python
builder = astichi_build()
builder.add.A(comp)

a = builder.A
t = a.second[0, 1]
```

These are real handles, not transient chain artifacts.

### 2.5 Port compatibility

Every composition edge must satisfy port compatibility checks before build or
materialization succeeds.

Phase-1 compatibility dimensions are:

- syntactic placement
- constness/mutability
- variadic vs scalar shape

Syntactic placement includes at least:

- expression position vs block position
- load/RHS-safe position vs store/LHS-required position
- positional variadic expansion vs named variadic expansion

Constness/mutability checks exist to prevent structurally valid but semantically
unsafe splices, including:

- inserting a read-only expression where a mutation target is required
- inserting a named expansion where a positional expansion is required
- inserting scalar content where a variadic site is required

Unsupported or incompatible pairings are hard errors.

## 3. High-level and raw APIs

Astichi exposes two equivalent API layers:

- a fluent/high-level API
- a raw/explicit assembler-style API

The fluent API is the preferred user-facing API.

The raw API:

- is supported
- has the same semantics
- is intentionally higher boilerplate
- is suitable for implementation internals, testing, and tooling

Every fluent operation must have an equivalent raw API operation.

## 3.1 Edge semantics

Phase-1 builder edges are additive composition edges.

An additive edge means:

- the source `Composable` is inserted at the addressed demand site
- execution order is determined by the enclosing target order rules
- lower `order` runs/appears before higher `order` in the same variadic target

Phase 1 does not attempt a richer generalized effect/dominance algebra.
Instead:

- block/variadic insertion order is explicit
- incompatible placements are rejected by port compatibility checks
- materialization must emit a deterministic runs-before order for accepted
  additive edges

## 4. Compile API

`astichi.compile(...)` compiles Python-shaped marker-bearing source into a
`Composable`.

Directional signature:

```python
astichi.compile(source, file_name=None, line_number=1, offset=0)
```

Required semantic inputs:

- source string
- originating file name
- starting line number
- starting column/offset

These origin parameters exist so diagnostics and restored source locations can
point back to the true originating file, including container formats such as
`.yidl` files.

## 5. Marker surface

Phase-1 marker surface:

```python
astichi_hole(name)
astichi_bind_once(name, expr)
astichi_bind_shared(name, expr)
astichi_bind_external(name)
astichi_keep(name)
astichi_export(name)
astichi_for(domain)
@astichi_insert(target, order=10)
```

### 5.1 `astichi_hole(name)`

`astichi_hole(name)` marks a hole.

The argument names the hole. It is not a hole-kind enum.
In source syntax it must be a bare identifier-like reference, not a string
literal and not an arbitrary runtime expression.

Hole shape is determined by the surrounding valid Python AST context:

- plain expression position: scalar expression hole
- `*astichi_hole(...)`: positional variadic expansion
- `**astichi_hole(...)`: named variadic expansion
- statement-expression position used as a standalone statement in a block:
  block insertion site

Astichi must only rely on marker forms that parse as valid Python for the
target Python versions.

Unsupported contexts must fail early.

### 5.2 `astichi_bind_once(name, expr)`

Declares a named binding that must be evaluated once and reused.

Phase-1 rule:

- the binding is local to the enclosing lowered region
- reuse is required if the bound value is referenced multiple times

### 5.3 `astichi_bind_shared(name, expr)`

Declares a named binding shared across a structural expansion region.

Phase-1 rule:

- the binding is local to the enclosing lowered region
- the binding survives loop/body expansion inside that region
- typical use is accumulation/shared state across generated siblings

### 5.4 `astichi_bind_external(name)`

Declares a compile-time external input by name.

External values are supplied by composition/materialization context, not by
runtime lexical lookup.

Phase-1 supported external value categories:

- constants
- tuples/lists
- other compile-time values supplied explicitly by the caller

### 5.5 `astichi_keep(name)`

Preserves a lexical identifier spelling.

Rules:

- the argument must be a bare identifier
- the identifier spelling must remain unchanged
- the identifier must not be hygienically renamed
- generated/local names must not collide with it

`astichi_keep(...)` is a lexical-preservation rule, not a Python scope rule.

### 5.6 `astichi_export(name)`

Exports a named binding/value from a snippet as an offer on the resulting
`Composable`.

Rules:

- the exported name must refer to a binding in the snippet
- the public export name is the declared export name
- internal hygienic renaming must not change the exported public name

### 5.7 `astichi_for(domain)`

Declares a compile-time loop domain.

The loop is part of the `Composable` unless/until it is unrolled.

`build()` must not force eager unrolling.

If a loop is not unrolled during a build, it remains a loop in the resulting
`Composable`.

Phase-1 supported domain categories:

- literal tuples/lists and equivalent constant shapes
- `range(...)` with compile-time constant arguments
- compile-time externals supplied via `astichi_bind_external(...)`

Phase-1 unsupported domain categories:

- arbitrary runtime iterables
- arbitrary function calls
- comprehensions

Loop target unpacking follows normal Python unpacking rules at compile time.
If unpacking fails, compilation/build fails.

### 5.8 `@astichi_insert(target, order=...)`

Adds a `Composable` into a target hole.

Phase-1 semantics are additive only.

Replacement semantics are not part of phase 1.

Ordering rules:

- lower `order` comes first
- equal-order conflicts on the same variadic target are errors

## 6. Name classification and hygiene

Astichi must implement lexical hygiene according to
`astichi/dev-docs/IdentifierHygieneRequirements.md`.

Phase-1 name classes:

- local/generated bindings
- explicitly kept names
- explicit compile-time externals
- unresolved free identifiers

Composition/materialization context may provide preserved names.

Conceptually:

```python
ComposeContext(
    preserved_names={"print", "len", "range", "sys"},
    external_values={"items": (1, 2, 3)},
)
```

### 6.1 Strict and permissive mode

Strict mode:

- unresolved free identifiers are errors unless preserved or declared external

Permissive mode:

- unresolved free identifiers may be promoted to implied named demands

### 6.2 Classification order

Phase-1 classification order:

1. collect local bindings
2. collect explicit `astichi_keep(...)` names
3. merge context-provided preserved names
4. collect explicit externals
5. classify remaining free identifiers:
   - preserved if kept/preserved
   - external if explicitly external
   - implied demand in permissive mode
   - error in strict mode

If a local binding collides with a preserved name:

- strict mode: error
- permissive mode: hygiene-rename the local binding and its local references

Keep-marker recognition must run before ordinary free-name classification inside
that subtree.

## 7. Marker lowering pipeline

The phase-1 lowering pipeline is:

1. parse Python AST
2. recognize Astichi markers
3. classify names
4. lower markers into the internal composable/builder model

Marker semantics are rediscovered from source on parse; they are not preserved
through hidden semantic payloads in emitted source.

## 8. Builder API

### 8.1 Fluent API

Fluent chaining is supported.

Example:

```python
result = (
    astichi_build()
    .add.A(loop_example)
    .add.B(print_example)
    .A.init.add.B(order=10)
    .A.first[0].add.B(order=10)
    .A.third.add.B(order=10)
    .build()
)
```

### 8.2 Handle-oriented API

Broken-out handles are equally supported.

Example:

```python
builder = astichi_build()
builder.add.A(loop_example)
builder.add.B(print_example)

a = builder.A

a.init.add.B(order=10)
a.first[0].add.B(order=10)
a.third.add.B(order=10)

result = builder.build()
```

Both forms must have identical semantics.

## 9. Addressing

### 9.1 Root-instance-first rule

Addressing uses root instance first.

Examples:

```python
A.init
A.first[0]
A.second[0, 1]
A.third
```

This is the phase-1 solid addressing model.

### 9.2 Loop-expanded addressing

Loop expansion indices are attached to the addressed target.

Example:

```python
for x, y in astichi_for(((1, 2), (2, 1))):
    astichi_hole(first)
    for a in astichi_for(range(y)):
        astichi_hole(second)
```

The loop-expanded targets are:

- `A.first[0]`
- `A.first[1]`
- `A.second[0, 0]`
- `A.second[0, 1]`
- `A.second[1, 0]`

### 9.3 Iteration environment

Each loop-expanded instance conceptually carries:

- a structural path tuple
- an iteration environment

The environment is implementation-facing metadata. Surface syntax does not
expose it in phase 1.

### 9.4 Descendant traversal

Deep descendant traversal beyond first-level root-instance-first addressing is
not locked in phase 1.

It is intentionally left unresolved to avoid premature complexity.

## 10. Build and materialize

### 10.1 `build()`

`build()` returns a new `Composable`.

The result may still contain unresolved:

- holes
- compile-time loops
- implied demands
- exports/offers

### 10.2 `materialize()`

`materialize()` closes a `Composable` for a chosen runnable/emittable target.

`materialize()` requires:

- required holes/demands satisfied for the chosen target
- valid hygiene
- legal target shape

`materialize()` fails if those conditions are not met.

Hygiene is enforced most critically at `materialize()` because symbolic
composition identities must become a concrete, valid Python naming layout.

## 11. Emit

`emit(...)` produces source output from a `Composable`.

Directional API:

```python
composable.emit(provenance=True)
composable.emit(provenance=False)
```

Default direction:

- `provenance=True`

Phase-1 source output is primarily for:

- debugging
- testing
- inspection

### 11.1 Marker-bearing source

Astichi may emit marker-bearing source that round-trips back into a
`Composable`.

The source remains authoritative.

### 11.2 Provenance payload

If `provenance=True`, emitted source ends with:

```python
astichi_provenance_payload("...")
```

Rules:

- single parameter only
- reserved call name
- payload is compressed
- payload is for AST/provenance restoration only
- holes, binds, inserts, exports, and related semantics are rediscovered by
  reparsing the source

If the source file is edited and its AST shape no longer matches the payload:

- provenance restoration must fail with an error
- the error must instruct removing the `astichi_provenance_payload(...)` call
- the edited file's current source locations become authoritative

If `provenance=False`, no provenance payload is emitted.

## 12. Source authority and round-trip

The source text is authoritative.

The provenance payload is only a restoration aid.

If emitted source is edited, Astichi must prefer the edited source semantics
over stale payload metadata.

## 13. Provenance and source locations

Astichi must preserve source provenance as part of the internal model so that:

- diagnostics can point to original snippet/container locations
- materialized/emitted code can recover useful source positions

If source is compiled from another container, such as a `.yidl` file, the
origin file and line information supplied to `astichi.compile(...)` must be
used as the authoritative origin.

## 14. Phase-1 constraints

Phase 1 intentionally keeps the design narrow:

- additive composition only
- no replacement semantics
- first-level root-instance-first addressing only
- narrow compile-time loop domains only
- boolean provenance emission policy only

This is deliberate. Additional features may be added later, but phase 1 must
prefer simpler semantics over speculative generality.

## 15. Errors

Phase-1 hard errors include:

- invalid marker placement
- unsupported starred/double-starred marker contexts
- invalid `astichi_keep(...)` argument form
- unresolved free identifiers in strict mode
- equal-order conflicts on the same variadic target
- compile-time loop unpacking failure
- provenance restoration against edited/non-matching source

## 16. Examples

### 16.1 Nested loop addressing

```python
loop_example: Composable = astichi.compile("""
astichi_hole(init)

for x, y in astichi_for(((1, 2), (2, 1))):
    astichi_hole(first)
    for a in astichi_for(range(y)):
        astichi_hole(second)
        print(a)

astichi_hole(third)
""")

builder = astichi_build()
builder.add.A(loop_example)
builder.add.B(print_example)
builder.add.C(return_example)

a = builder.A
a.init.add.B(order=10)
a.first[0].add.B(order=10)
a.second[0, 0].add.B(order=10)
a.second[0, 1].add.B(order=10)
a.second[1, 0].add.B(order=10)
a.third.add.C(order=10)

result = builder.build()
```

### 16.2 Valid Python marker shapes

```python
def probe(func):
    class Subject(
        *astichi_hole(parent_list),
        metaclass=astichi_hole(class_meta),
        **astichi_hole(class_kwarg_list),
    ):
        astichi_hole(body)

        def method(self):
            value = astichi_hole(value_slot)
            args_result = func(
                *astichi_hole(arg_list),
                **astichi_hole(kwarg_list),
            )
            tuple_result = (*astichi_hole(tuple_items),)
            for s in astichi_keep(sys).argv:
                astichi_hole(output_callable)(s)
            return value, args_result, tuple_result

    return Subject
```
