# astichi API design proposal

Living document for the public API and algebraic shape of the library.

---

## 1. Carrier and vocabulary (locked)

**Composable** is the name of the **element** of the algebra: the unit you hold, transform, compose, and (after **materialize**, §3) emit or compile into runnable Python.

The **main API surface** is the set of **Composable** values and the **operations** that map Composables to Composables (closure). **Composable values themselves are immutable**; incremental wiring uses a separate **mutable builder** (see §3). Internal machinery—scopes, binding metadata, parent links, diagnostics—may exist, but callers reason in terms of **Composable** and operators that always yield another **Composable** when their preconditions are met.

_Status: this naming and surface decision is **done** for the purposes of this proposal._

---

## 2. Composable (proposed): what the concept is

A **Composable** is a closed carrier for a fragment of Python-shaped program structure, together with enough metadata that **transforms** and **composition** stay well-defined. Publicly, operations on a Composable yield another Composable when preconditions hold (algebraic closure); scopes, binding tables, and diagnostics may live inside but are not the primary mental model.

### 2.1 Shape and role

- **Syntactic root kind** — whether the fragment is **expression-shaped**, **statement-list-shaped**, **suite-shaped** (e.g. under a `def` body), or another distinguished root. This fixes **where** the fragment may legally appear when splicing.
- **LHS vs RHS (and related)** — for expressions, **position matters**: e.g. **store** vs **load** vs **del** contexts impose different **lvalue** rules. This is a **placement** predicate on ports or on the whole fragment, not the same thing as value “constness.”
- **Coarse effects / ordering** — optional but useful tags: read-only vs may mutate, may raise, may branch, etc. Used to **reject** illegal wirings or to fix **evaluation order** obligations when composing.

### 2.2 Ports: holes vs offers (inputs/outputs refined)

It is clearer to speak in terms of **ports** than a single vague “inputs/outputs”:

- **Holes (demand ports)** — “I need something here”: a **site** in the fragment with a contract (expr vs stmt vs region, scope constraints, constness / mutability expectations, etc.). These are the **inputs** from the **Composable’s own** point of view: **dependencies the fragment declares** to whoever composes it.
- **Offers (supply ports)** — “I provide something here”: a **binding**, value, or definitional **output** another fragment can rely on (again under a contract: name identity via scope objects, type or kind summary, stability under rewrite).

Typed **IO** attaches naturally to **ports** (demand and supply carry type or kind summaries). Whole-fragment “this Composable expects these free names” is the **limiting case** of demand ports (implicit holes at the boundary).

**Syntactic demand kinds (non-exhaustive):** not every hole is “expression-shaped.” The same port machinery should distinguish **contracts** so composition and emit stay honest:

| Kind | Example site | Contract (sketch) |
|------|----------------|-------------------|
| **Expr-shaped** | RHS, subexpr | May splice another expr-shaped Composable; obeys LHS/RHS placement when relevant. |
| **Stmt- or suite-shaped** | Function body, module top level | May splice stmt-list or suite-shaped fragments; scope and dominance rules apply. |
| **Region / block-shaped** | Class body, `try` suite | Same family as suite-shaped but may carry extra structure (e.g. “class member decls only”). |
| **Definitional name (identifier-only)** | `class <name>:`, `def <name>(...)`, single-name binding targets where grammar requires **`identifier`** | **Not** a general expression hole: the demand is “one **binding / lexical name** site” constrained to **identifier** spelling and hygiene for **that** role (see `IdentifierHygieneRequirements.md` for lexical occurrences). Callers wire a **name-shaped** or **identifier-port** offer, not an arbitrary expr. |

Missing this split (e.g. treating a class head name like a generic expr hole) loses **intent** and weakens validation: you cannot accidentally splice a call expression where only a simple name is legal.

### 2.3 Variadic demand ports and ordering

Some holes accept **many** child fragments in **one** syntactic list: class member declarations, statements in a function body, decorators on a definition, etc. Model these as **variadic demand ports** (zero or more **edges** into the same port key), not as a single binary compose repeated without structure.

**Ordering** must be explicit when multiple edges attach to the same variadic port: **textual order** in the emitted program should not be guessed from insertion order alone unless the API **documents** that insertion order *is* the order. Prefer an explicit **priority** (or sequence index) on each **tie** in the builder so composition is **deterministic** and reorderable without reshaping the graph:

- **`tie(..., order=n)`** or **`tie(..., priority=n)`** — lower number first (or fixed convention: monotonic `sequence`); ties with the same order are a **product error** unless a secondary stable key is defined.
- **`build()`** materializes variadic children **sorted by** that order field into the underlying `ast` list fields.

Binary `compose` remains the algebraic building block; **variadic ports** are how **n-ary children of one list-shaped site** stay first-class in the builder and in port maps.

### 2.4 Constness and compatibility

**Constness / mutability** is a **compatibility dimension on edges** in the wiring graph: an offer may or may not satisfy a hole’s “read-only” or “stable for the duration of this region” requirement.

**LHS vs RHS** is primarily **structural** (may this expr appear in a binding position?); **constness** is primarily **semantic** (may this use mutate?). Both participate in **“may this port accept that offer?”** checks.

### 2.5 Composition as pairing (wiring)

**Compose**, at the semantic core, is a **pairing / wiring** relation: connect **compatible** supply ports on one Composable to **demand** ports on another (with renaming and scope merge rules from the identifier-hygiene design).

- A **kernel** form is **`compose(a, b, pairing)`** (or equivalent) where `pairing` is an explicit edge set—most precise.
- **Ergonomics** wrap the same law: e.g. **`plug`** (one edge at a time), **`sequence`** when convention fixes pairing (e.g. two stmt-list bodies).
- **Order** still matters where **effects** exist: wiring implies not only **dataflow** but **dominance** / “runs before” obligations even when types match. The pairing contract must say whether an edge implies execution order, dependency only, or both.

**Binary vs n-ary:** algebraically, repeated **binary** merge is enough. **Batched** composition (many edges in one call) remains valuable for **one** scope/rename pass, **global** port satisfiability, **atomic** validate-or-reject, and fewer intermediate **`build()` results**—it is **sugar** over the same pairing semantics, not a different species of `Composable`.

### 2.6 Immutability of `Composable`

Treat **`Composable` instances as immutable snapshots**. Transforms return **new** values; the builder (§3) holds **references** to immutable pieces while the **wiring graph** evolves.

### 2.7 What stays outside the Composable law (for now)

**Emit** (pretty-print) and **compile** (to code object) are **downstream of `materialize()`** for “expect to work” artifacts: policies, `__future__`, line tables, and formatting are not part of the closure of “Composable → Composable” unless explicitly modeled as a final morphism into a different carrier (e.g. `Source` or `Compiled`).

**Provenance** (spans, pass ids) is a **sidecar** for errors and tooling, not required for the algebraic identity of composition.

---

## 3. Composition builder: `build()` vs `materialize()`

Incremental composition uses a **mutable builder** over **immutable** `Composable` operands. The builder records **instances** (wrapped references under stable handles), **ties** (edges between demand and supply ports), and optionally **constraints** or **schedules** for effect order.

**`build()` and `materialize()` are not the same operation:**

| Step | Input | Output | Resolution |
|------|--------|--------|--------------|
| **`build()`** | Builder graph (instances + ties) | A **new `Composable`** | **May** leave **boundary** demand/offer ports open. Still a valid value in the algebra; not yet promised runnable as a whole program. |
| **`materialize()`** (name TBD) | A `Composable` (often post-`build()`) that is intended to become runnable | A **fully resolved** artifact for a chosen target (e.g. **function**, **class**, **expression** suitable for `exec`/`eval`) | **All required ports / bindings** for that target are satisfied so you can **generate source**, **`compile`**, or **`exec`** and **expect it to work** (subject only to normal Python/runtime rules). |

Lazy editing: the graph can grow until `build()`; further transforms or wiring may follow. **`materialize()` is the hard gate** before treating the tree as “done” for emission or execution.

### 3.1 Conceptual API (illustrative, not literal syntax)

```text
builder.instance(composable1, id=A).instance(composable2, id=B).instance(composable3, id=C)
       .tie(A.demand(I1), B.offer(O1))
       .tie(A.demand(body), C.offer(out1), order=0)
       .tie(A.demand(body), B.offer(out2), order=1)
       .build() → Composable
```

- **`instance(composable, id=…)`** — registers an immutable `Composable` under a builder-local **instance handle** (return value or explicit id).
- **`tie(left_port, right_port, order=…)`** — adds a **directed** wiring edge; **`order`** (or **`priority`**) is **required** when the demand port is **variadic** (§2.3) so multiple children serialize in a defined order; omit or default when the port accepts at most one edge.
- **`build()`** — folds the wiring graph into **one new `Composable`** whose body and **port map** reflect merged structure; **open boundary ports are allowed** unless a stricter builder mode rejects dangling **required** edges (product choice).

### 3.2 `materialize()`: closed under the emission contract

**`materialize()`** means: produce a representation that is **fully resolved** for the chosen **emission shape** (expression vs `def` vs `class` body vs module fragment, etc.): no **mandatory** holes remain, names and scopes line up with the hygiene rules, and the result is suitable for **source generation**, **`compile`**, or **`exec`/`eval`** as documented.

- If resolution cannot complete (unsatisfied required port, hygiene violation, illegal shape), **`materialize()` fails**—unlike `build()`, which may still return a composable “work in progress.”
- Optional **offers** that remain unwired may still be allowed if the emission contract treats them as dead exports or the target shape does not require them—again a **documented** policy.

### 3.3 Naming: three layers (avoid conflating them)

| Layer | Role | Naming guidance |
|-------|------|-------------------|
| **Builder instance handle** | Stable reference to *which* operand in the graph (`A`, `B`, …). | **Opaque or structured instance id** returned by `instance(...)`—not a Python `ast.Name` string. |
| **Builder port endpoint** | Which hole/offer on that instance (`I1`, `O1`, …). | **`PortId`**: e.g. `(instance_handle, role, key)` where `role` is demand vs offer and `key` is user-chosen or auto-allocated. Do **not** overload raw user strings as the only port key if they collide with hygiene or Python `id` spellings. |
| **Lexical / emitted names** | Actual `ast.Name` `id` strings after lowering, tied to **scope objects** per `IdentifierHygieneRequirements.md`. | Produced during **emit / finalize** steps from `(PortId, scope, …)`—separate from builder graph keys. |

**Vocabulary:** **Wired edge** = satisfied connection inside the builder graph. **Open demand** / **open offer** (or **boundary hole** / **boundary supply**) = port still exposed on the **result** after `build()`. After **`materialize()`**, by definition, **no required open ports** remain for the chosen target.

### 3.4 Design questions to close early

- **`build()` and dangling ports** — always returns a `Composable` with explicit boundary ports vs rejects when any **required** edge is missing.
- **`materialize()` input** — only `Composable`, or also “builder + auto-build”; exact signature and result type name (`Materialized`, `Executable`, …).
- **Edge direction semantics** — dataflow only vs dominance / “runs before” vs both (must align with §2.5).
- **Error model** — builder invalidation vs errors at `build()` vs errors only at `materialize()`.

### 3.5 Builder ergonomics: fluent and handle-oriented

The builder API should support both fluent chaining and broken-out handles with
the same semantics.

Fluent style should work for compact cases:

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

Broken-out handles should work for larger cases:

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

The intended handle layers are:

- builder handle
- instance handle, e.g. `builder.A`
- target handle, e.g. `builder.A.first[0]`

These should be real handle objects, not merely transient chain nodes. That is
what allows chaining and decomposition to coexist without diverging semantics.

This fluent surface is intentionally the high-level language. Underneath it
there should be a plain explicit raw API with the same semantics and much
higher boilerplate.

That raw API is the assembler-like layer:

- suitable for implementation internals
- suitable for testing/debugging/tooling
- expected to be more verbose and less pleasant

The fluent API should be understood as a constrained DSL over that lower-level
builder graph API, not as the semantic core itself.

### 3.6 Proposal-level guardrails

The following points should be recorded now so they are not omitted later,
even though the final normative semantics belong in the design document rather
than this proposal.

- A composed result is itself a `Composable`.
- If a loop introduced by `astichi_for(...)` is not unrolled during a build, it
  should remain as a loop in the resulting `Composable`.
- `build()` should not force eager unrolling merely because a loop exists.
- Unresolved holes, loops, and related marker-lowered structure should survive
  into the resulting `Composable` when they are not discharged by the current
  build.
- Marker-bearing Python should lower into the internal port / instance /
  binding model through an explicit pipeline:
  parse Python AST -> recognize markers -> classify names -> lower into the
  builder/composable model.
- Source fidelity matters. Provenance should be preserved as part of the
  internal composable/build model, not treated as an afterthought.
- Source emission should be able to include or omit provenance metadata with a
  simple boolean policy, e.g. `emit(provenance=True)` vs
  `emit(provenance=False)`.
- The current default direction is `provenance=True`.
- If provenance is emitted, the source should end with a simple reserved
  one-parameter call such as `astichi_provenance_payload("...")`.
- That payload is for AST/provenance restoration only. Holes, binds, inserts,
  and related semantics must be rediscovered from reparsing the source itself.
- If provenance is emitted, the payload should be compressed. The exact
  serialization/compression details are implementation concerns, not public API
  surface.
- The source file is authoritative. If the emitted source has been edited and
  its AST shape no longer matches the payload, provenance restoration should
  fail with an error instructing the user to remove the
  `astichi_provenance_payload(...)` call.
- In that edited-source case, the file's current source locations are
  authoritative; prior provenance is not recovered.
- `astichi.compile(...)` should also accept source-origin location parameters
  alongside the source string so compilation can preserve the true originating
  file and line context. The important directional inputs are:
  - source string
  - file name
  - starting line number
  - starting column/offset
- This is needed for cases where the snippet came from another source container
  such as a `.yidl` file and diagnostics should point back to that file rather
  than to an artificial intermediate string location.
- First-level targeting and loop-instance indexing are the current solid
  addressing story. Deeper descendant traversal is still exploratory and should
  not be treated as locked by this proposal.
- Phase-1 loop-domain support should stay narrow: literals, constant
  `range(...)`, and compile-time externals are the current intended baseline.

---

## 4. Emission modes: full source vs markers; round-trip

**Downstream of `materialize()`** (§2.7, §3), **emit** turns a resolved tree into **text** or into **`compile`**. Two emission modes matter for tooling and for “see the boundary”:

1. **Full source** — holes are gone; output is ordinary Python text (subject to formatter policy).
2. **Marker-preserving (skeleton) source** — the emitter places **stable markers** at every site that was (or could be) a **demand port** or an **intended supply/export** in the composition model: e.g. sentinel comments, placeholder identifiers with a defined prefix, or a small **surface syntax** agreed for parse-back. The goal is **honest partial programs**: humans and tools see **where** composition happened without pretending unspecified holes are valid Python.

**Does marker emission “completely” recreate a `Composable`?** Not from string alone. **Round-trip** is a **second pipeline**: **marker grammar + parser** (or AST lowering with sentinel nodes) that reconstructs **ports and edges** into a new `Composable`. Whether that reconstruction is **lossless** depends on what the markers carry (at minimum: port ids or keys, variadic **order**, definitional-name vs expr kind). Treat **emit-with-markers → parse → `Composable`** as an **optional, documented** adapter, not an automatic property of pretty-printing.

**Open `build()` / boundary Composables:** marker emission is especially useful when **mandatory** holes remain: markers label **unsatisfied** demands so downstream tools can diff or complete wiring before `materialize()`.

---

## 5. Marker surface (proposed)

The current proposed source-facing marker set is:

```python
astichi_hole(name)
astichi_bind_once(name, expr)
astichi_bind_shared(name, expr)
astichi_bind_external(name)
astichi_keep(name)
astichi_export(name)
astichi_for(domain)
@astichi_insert(hole_name, order=10)
```

These forms are intentionally Python-shaped. They are the marker vocabulary
that snippet authors write; the internal `Composable` / port model remains the
lowered representation.

The argument to `astichi_hole(name)` names the hole. It is not a hole-kind
enum. In source syntax it is an identifier-like reference, not a string
literal. Earlier placeholder examples such as `block` and `expr` should be
read only as provisional names, not as normative shape tags.

Holes are constrained by default.

- plain `astichi_hole(name)` in expression position means a scalar
  expression hole
- `*astichi_hole(name)` means variadic positional expansion
- `**astichi_hole(name)` means variadic named expansion

Astichi should infer the required hole shape from the containing Python AST
context rather than from a larger surface marker taxonomy.

That means:

- one hole marker is enough
- `*` and `**` are the explicit widening syntax
- unsupported starred/double-starred contexts must be rejected early
- any desired marker form must still parse as valid Python for the target
  Python versions

`astichi_bind_external("name")` is the marker for compile-time external
inputs. Those externals may include:

- constants
- plain lists or tuples
- field/domain lists prepared by the caller
- other compile-time values that drive insertion, selection, or unrolling

`astichi_keep(name)` is the marker for a preserved lexical name. It means:

- keep this identifier spelling unchanged
- do not hygienically rename it
- do not let another composable capture or collide with it

This is a name-preservation rule, not a Python scope rule. It does not imply
module-global lookup by itself.

### 5.1 Canonical example

```python
@astichi_insert(class_body, order=10)
def build_total_property():
    astichi_bind_external(field_values)
    astichi_bind_shared(sum, 0)

    for x in astichi_for(field_values):
        sum += x

    astichi_export(sum)


class Subject:
    astichi_hole(body)

    @property
    def total(self):
        value = astichi_hole(value_slot)
        return value
```

```python
for s in astichi_keep(sys).argv:
    astichi_hole(output_function)(s)
```

```python
value = astichi_hole(value_slot)
result = func(*astichi_hole(arg_list), **astichi_hole(kwarg_list))
items = (*astichi_hole(item_list),)
```

This example fixes the intended surface shape:

- `astichi_hole(body)` is a named hole used here in block position
- `@astichi_insert(..., order=...)` targets that site deterministically
- `astichi_bind_external(field_values)` declares a compile-time external
  input, such as a constant-domain list supplied by the caller
- `astichi_bind_shared(sum, 0)` declares an accumulator that survives loop
  expansion
- `for x in astichi_for(field_values):` is the canonical Python-shaped
  iteration marker
- `astichi_keep(sys)` marks a preserved lexical root name that must not be
  captured or renamed by composition
- `astichi_export(sum)` makes the final value available to the enclosing
  composition step
- `astichi_hole(value_slot)` is a named hole used here in scalar expression
  position
- plain `astichi_hole(...)` is scalar by default
- `*astichi_hole(...)` widens that hole to positional variadic expansion
- `**astichi_hole(...)` widens that hole to named variadic expansion

### 5.2 Hole shape and real Python AST

Astichi should only rely on source forms that parse as real Python AST.

The intended phase-1 mapping is:

- `x = astichi_hole(value)`
  means one expression node/value in ordinary expression position
- `func(*astichi_hole(args))`
  means a positional variadic hole in a starred argument position
- `func(**astichi_hole(kwargs))`
  means a named variadic hole in a double-star keyword position
- `items = (*astichi_hole(item_list),)`
  means a starred-sequence hole in a tuple-display position

Astichi should parse ordinary Python AST first, then recognize marker patterns
in context. The surrounding AST node type determines what kind of insertion
contract the hole has.

This also means unsupported contexts are not “almost supported.” If the syntax
does not parse as valid Python, or if the surrounding AST shape is not one of
the explicitly supported insertion contexts, Astichi should reject it.

Empirical note from a real `ast.parse(...)` probe:

- `*astichi_hole(bases)` in a class header lands in `ClassDef.bases` as a
  `Starred(...)` expression
- `metaclass=astichi_hole(meta)` lands in `ClassDef.keywords` as
  `keyword(arg="metaclass", value=...)`
- `**astichi_hole(class_kwargs)` lands in `ClassDef.keywords` as
  `keyword(arg=None, value=...)`
- `func(*astichi_hole(args), **astichi_hole(kwargs))` uses the same call
  shapes: `Starred(...)` in `Call.args` and `keyword(arg=None, value=...)` in
  `Call.keywords`
- `astichi_keep(sys).argv` parses as an `Attribute(...)` rooted at a
  `Call(astichi_keep, [Name("sys")])`, so keep-marker recognition should run
  before ordinary free-name classification inside that subtree

### 5.3 Name classification

Astichi needs an explicit name-classification pass.

The intended classes are:

- local/generated bindings
- explicitly preserved names via `astichi_keep(name)`
- compile-time externals declared via `astichi_bind_external("name")`
- unresolved free names

Composition/materialization context may also provide a set of preserved names.
Those are ambient names that should be treated as auto-kept roots for that
composition run.

Conceptually:

```python
ComposeContext(
    preserved_names={"print", "len", "range", "sys"},
)
```

The rule is lexical:

- if a free identifier is explicitly kept, preserve it
- if a free identifier is in the context-provided preserved-name set, preserve
  it
- otherwise treat it according to strict/permissive mode

If a local binding collides with a preserved name:

- strict mode: error
- permissive mode: hygiene-rename the local binding and its local references

This is what prevents a composed fragment from accidentally stealing the
spelling of a preserved root such as `sys`.

### 5.4 Strict and permissive mode

Strict mode:

- unresolved free identifiers are an error unless explicitly kept, explicitly
  declared external, or preserved by the composition context

Permissive mode:

- unresolved free identifiers may be promoted to implied named demands

Conceptually:

```python
for x in bar:
    print(x)
```

may lower as if `bar` were an implied demand, while `print` remains preserved
through the context-preserved-name set.

### 5.5 Immediate open question

One unresolved question is exactly how `astichi_bind_external("name")` binds
to supplied compile-time values.

In particular, the design still needs to pin down how plain compile-time
values such as lists are supplied so they can drive:

- const-unroll
- const insertion
- strategy evaluation during code-generation research

_(Further sections: operator taxonomy, scope graph API vs Composable surface, marker grammar spec, emission vs compile adapters—TBD.)_
