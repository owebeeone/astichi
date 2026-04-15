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

---

## 4. Emission modes: full source vs markers; round-trip

**Downstream of `materialize()`** (§2.7, §3), **emit** turns a resolved tree into **text** or into **`compile`**. Two emission modes matter for tooling and for “see the boundary”:

1. **Full source** — holes are gone; output is ordinary Python text (subject to formatter policy).
2. **Marker-preserving (skeleton) source** — the emitter places **stable markers** at every site that was (or could be) a **demand port** or an **intended supply/export** in the composition model: e.g. sentinel comments, placeholder identifiers with a defined prefix, or a small **surface syntax** agreed for parse-back. The goal is **honest partial programs**: humans and tools see **where** composition happened without pretending unspecified holes are valid Python.

**Does marker emission “completely” recreate a `Composable`?** Not from string alone. **Round-trip** is a **second pipeline**: **marker grammar + parser** (or AST lowering with sentinel nodes) that reconstructs **ports and edges** into a new `Composable`. Whether that reconstruction is **lossless** depends on what the markers carry (at minimum: port ids or keys, variadic **order**, definitional-name vs expr kind). Treat **emit-with-markers → parse → `Composable`** as an **optional, documented** adapter, not an automatic property of pretty-printing.

**Open `build()` / boundary Composables:** marker emission is especially useful when **mandatory** holes remain: markers label **unsatisfied** demands so downstream tools can diff or complete wiring before `materialize()`.

---

_(Further sections: operator taxonomy, scope graph API vs Composable surface, marker grammar spec, emission vs compile adapters—TBD.)_
