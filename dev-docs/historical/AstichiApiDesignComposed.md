# astichi API design — composed (normative)

This document is the **normative** API and behavior contract for astichi. It
states what implementations **MUST**, **SHOULD**, and **MAY** do. Rationale,
sketches, examples, and non-binding discussion live in
`AstichiApiDesignProposal.md` (cited below as **the proposal**). Where this
document is silent, the proposal is informative only unless another normative
note is named.

**Normative companion:** `IdentifierHygieneRequirements.md` — lexical name
occurrences, scope objects, and requirements **H1–H11** for hygiene and
resolution. astichi **MUST** satisfy **H1–H11** for all in-scope lexical
`ast.Name` occurrences in its pipeline unless a section here explicitly defers
behavior.

The keywords **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, **MAY**, and
**RECOMMENDED** are to be interpreted as described in RFC 2119.

---

## 1. Authority and precedence

| Artifact | Role |
|----------|------|
| **This document** | Normative contract for astichi’s public model and required pipelines. |
| **The proposal** (`AstichiApiDesignProposal.md`) | Motivation, vocabulary introduction, examples, open questions, and product direction. |
| **`IdentifierHygieneRequirements.md`** | Normative hygiene rules for lexical names (see §0, requirement table). |

If the proposal and this document conflict on a **normative** point, **this
document wins** after explicit update; until then, treat conflict as an editorial
error to fix.

---

## 2. Carrier: `Composable`

### 2.1 Definition

A **`Composable`** is an immutable value representing a Python-shaped program
fragment plus metadata sufficient for defined transforms and composition.

- A **`Composable` MUST NOT** be mutated in place; operations that change meaning
  **MUST** yield a new `Composable` (or fail).
- The primary public reasoning unit **MUST** be `Composable` and operations on
  it; internal representations **MAY** include scopes, binding tables, parent
  links, and diagnostics as implementation details unless surfaced by API types
  named here.

**Informative:** naming and closure story — proposal §1, §2.6.

### 2.2 Shape and placement

Every `Composable` **MUST** carry enough information to decide **legal splice
contexts** (where the fragment may appear in a larger tree). At minimum:

1. **Syntactic root kind** — one of a documented set (e.g. expression-shaped,
   statement-list-shaped, suite-shaped, or other distinguished roots the product
   defines).
2. **Placement** — where relevant for expressions, predicates equivalent to the
   proposal’s **LHS vs RHS** (and related load/store/del) distinction so
   lvalue-shaped holes are not filled with illegal fragments.

**Informative:** effects tags, optional metadata — proposal §2.1.

### 2.3 Ports

#### 2.3.1 Roles

- A **demand port** (**hole**) is a typed site requiring a compatible fragment
  or binding per its contract.
- An **supply port** (**offer**) is a typed site exposing a binding, value, or
  definitional output under a contract.

Ports **MAY** carry type or **kind** summaries for compatibility checking.

**Informative:** ports vs whole-fragment free names — proposal §2.2.

#### 2.3.2 Demand kinds

Implementations **MUST** classify each demand port using a documented **demand
kind** at least covering the following intent (names are implementation-defined
but semantics **MUST** align):

| Demand kind (semantic) | Normative constraint |
|------------------------|----------------------|
| **Expr-shaped** | Wired fragment **MUST** be expression-shaped and **MUST** satisfy placement (§2.2) for the site. |
| **Stmt- or suite-shaped** | Wired fragment **MUST** match statement-list or suite contracts for that site. |
| **Region / block-shaped** | Wired fragment **MUST** match the declared region contract (e.g. class body members only). |
| **Definitional name (identifier-only)** | Wired offer **MUST NOT** be an arbitrary expression hole; it **MUST** be a **single identifier / name-shaped** binding site per grammar and hygiene for **lexical** names (`IdentifierHygieneRequirements.md`). |

**Informative:** table and examples — proposal §2.2.

#### 2.3.3 Variadic demand ports

When a single demand port key accepts **zero or more** child fragments in one
syntactic list:

1. Each wiring edge into that port **MUST** carry an explicit **order** (or
   **priority**) field unless the product documents a single default ordering
   rule for that port class.
2. For a given `(port, order)` pair, the implementation **MUST** either reject
   duplicates as an error **OR** define a secondary stable tie-breaker in the
   normative product spec.
3. **`build()`** (or equivalent merge) **MUST** materialize children into the
   target `ast` list fields in **ascending** documented order (e.g. lower
   `order` first).

**Informative:** motivation — proposal §2.3.

#### 2.3.4 Edge compatibility

Wiring an offer to a demand **MUST** succeed only if documented compatibility
rules pass, including:

- demand kind vs offer shape;
- **constness / mutability** expectations on the edge (proposal §2.4);
- structural **LHS** requirements vs offer.

**Informative:** constness vs LHS discussion — proposal §2.4.

### 2.4 Composition

Composition is **pairing**: directed edges from supply ports to demand ports
subject to compatibility (§2.3.4), hygiene (`IdentifierHygieneRequirements.md`),
and documented scope-merge rules.

- A **kernel** operation **MUST** accept an explicit pairing (edge set) or an
  equivalent derived structure.
- **Batched** composition APIs **MUST** be semantics-preserving with respect to
  applying the same set of edges via the kernel (atomicity and scope passes
  **MAY** differ as documented).

**Informative:** ergonomics (`plug`, `sequence`), binary vs batched sugar —
proposal §2.5.

**Open (tracked in proposal §3.4):** whether an edge implies **execution
order**, **dependency only**, or both — implementations **MUST** document their
choice until a single normative rule replaces this note.

### 2.5 Out of core law

The following **MUST NOT** be required for two `Composable` values to compare
equal or for composition preconditions to be evaluated, unless explicitly modeled
as a separate carrier type:

- pretty-print **emit** policies;
- `compile` / `exec` line-table policies beyond what Python assigns from caller
  inputs;
- formatting and `__future__` layout choices.

**Provenance** (file/line/column, optional pass ids, optional payloads) is a
**sidecar**: implementations **SHOULD** retain it through `build()` where a
definable mapping exists, but provenance **MUST NOT** alter the compositional
identity of a `Composable`.

**Informative:** morphism framing — proposal §2.7.

---

## 3. Builder: `build()` vs `materialize()`

### 3.1 Builder model

Incremental wiring uses a **mutable builder** over **immutable** `Composable`
operands. The builder **MUST** record:

- **instances** — operands under stable **instance handles**;
- **ties** — directed edges from a supply endpoint to a demand endpoint;
- optional documented constraints (e.g. effect ordering).

**Informative:** fluent vs raw ergonomics — proposal §3.5. A conforming product
**SHOULD** expose a **raw**, explicit graph API; any fluent API **MUST** be
semantics-equivalent to that raw layer.

### 3.2 `build()`

**Input:** builder state (instances + ties + options).  
**Output:** a new **`Composable`**.

**Normative:**

1. The result **MUST** itself be a `Composable`.
2. **Boundary** demand or offer ports **MAY** remain open unless a documented
   strict mode forbids missing **required** edges (proposal §3.4 — product
   choice **MUST** be documented).
3. If a loop exists in the operand because `astichi_for(...)` (or equivalent)
   was **not** discharged by this build, the result **MUST** retain that loop
   structure (no silent mandatory full unroll merely because a loop appears).
4. Unresolved holes, binds, inserts, and other marker-lowered structure **MUST**
   survive in the result when not discharged by this build.

**Informative:** lazy editing story — proposal §3.

### 3.3 `materialize()`

**Input:** a `Composable` plus a **target emission contract** (e.g. expression,
`def`, class body, module fragment).  
**Output:** a representation documented as suitable for emit/compile/exec for
that contract.

**Normative:**

1. For the chosen contract, **every mandatory demand port** **MUST** be
   satisfied; **MUST NOT** leave required holes open unless the contract explicitly
   allows deferred forms (documented exception list).
2. Lexical name treatment **MUST** satisfy `IdentifierHygieneRequirements.md`
   for in-scope occurrences.
3. On violation (missing port, hygiene failure, illegal shape), the operation
   **MUST** fail with a diagnostic; it **MUST NOT** return a “success” value that
   violates the contract.

Optional unwired offers **MAY** be allowed only under a documented policy
(proposal §3.2).

**Informative:** naming alternatives (`Materialized`, …) — proposal §3.4.

### 3.4 Naming layers

Implementations **MUST** keep distinct:

1. **Instance handle** — identifies which graph operand; **MUST NOT** be only a
   raw Python `ast.Name` string if that risks collision with hygiene or `id`
   spellings (proposal §3.3).
2. **`PortId`** — `(instance, role, key)` or equivalent; **role** distinguishes
   demand vs offer.
3. **Lexical emitted names** — produced during emit/finalize from `(PortId,
   scope, …)` per hygiene; **MUST NOT** be confused with port keys.

Marker lowering **MUST** map **surface hole and bind identifiers** (§4.2) to
`PortId` keys and bind keys by documented, stable rules; those identifiers are
**not** the same layer as instance handles or lexical emitted names.

**Informative:** table — proposal §3.3.

---

## 4. Lowering pipeline (marker-bearing Python → model)

For inputs authored with the marker surface (proposal §5), a conforming
implementation **MUST** implement a pipeline equivalent to the following ordered
stages:

1. **Parse** — source **MUST** parse as valid Python for the supported language
   version set (unsupported syntax **MUST** be rejected).
2. **Recognize markers** — detect documented marker patterns (`astichi_hole`,
   `astichi_insert`, `astichi_keep`, binds, exports, `astichi_for`, etc.) in
   **AST context** per proposal §5.2; unsupported contexts **MUST** be rejected
   (not partial support). Hole and bind **name parameters** **MUST** satisfy
   §4.2 (identifier form, not string kind tags).
3. **Classify names** — run an explicit pass assigning each relevant identifier to
   a documented class (local/generated, `astichi_keep`, `astichi_bind_external`,
   unresolved free, …) per proposal §5.3; apply **strict** or **permissive**
   mode rules exactly as documented for the product.
4. **Lower** — produce the internal port/instance/binding graph and `Composable`
   pieces.

**Informative:** examples and `ast.parse` shape notes — proposal §5.1–5.2.

### 4.1 Hole shape from AST context

Hole **arity** (scalar vs `*` vs `**`) **MUST** be inferred from the containing
Python AST shape (proposal §5.2), not from parallel hole taxonomies, unless a
later normative extension adds them.

### 4.2 Hole names and bind keys (surface identifiers)

The proposal requires that **hole and bind parameters** be written as
**identifier-like references** in source (typically `ast.Name` operands to the
marker calls), **not** as string literals carrying hole-**kind** tags.

**Normative:**

1. **`astichi_hole`** — the sole hole-name argument **MUST** be an **identifier**
   in source (parsed as a `Name`, not as a `Constant` string). That token **names
   the hole** for wiring and insertion; it **MUST NOT** be interpreted as a
   hole-shape or hole-kind **enum** (e.g. `"expr"` vs `"block"`). Shape is fixed
   only by §4.1 and demand kinds (§2.3.2) from placement and lowering rules.
2. **`astichi_bind_once`**, **`astichi_bind_shared`**, **`astichi_bind_external`** —
   the bind **key** argument(s) that identify the binding site in the proposal’s
   surface **MUST** use the same **identifier** form as (1), not string literals,
   unless a future normative extension explicitly allows alternates.
3. **`astichi_export`** — the export key **MUST** use the same identifier form as
   (1).
4. **`@astichi_insert`** — the hole **target** argument naming the demand port
   **MUST** use the same identifier form as (1).
5. Implementations **MUST** reject string-literal forms for any parameter covered
   by (1)–(4) when the proposal’s surface disallows them (proposal §5, marker
   list and “identifier-like reference” rule).

**Lowering:** the stable logical key for a hole or bind site **MUST** be derived
from the identifier’s **spelling** (Python identifier normalization) unless the
product documents an explicit prefix or mangling rule for collision avoidance.

**Informative:** proposal §5 (marker list, hole-name paragraph, canonical
examples).

### 4.3 Strict vs permissive unresolved frees

Products **MUST** document which mode is default. Normative intent:

- **Strict:** unresolved free identifiers **MUST** be errors unless explicitly
  kept, declared external, or in the context **preserved-names** set (proposal
  §5.4).
- **Permissive:** promotion to implied named demands **MAY** occur only as
  documented, with stable lowering rules.

**Note:** §4.2 applies only to **marker API parameters** (hole keys, bind keys,
export keys, `@astichi_insert` target names). §4.3 governs **classification of
other identifiers** in the snippet (strict vs permissive unresolved frees).

---

## 5. Emission and compilation

### 5.1 Gate

Operations that **advertise** “runnable” or “round-trippable Python output for
execution” **MUST** operate on **`materialize()` output** (or a type documented
as equivalent), not on arbitrary boundary `Composable` values, unless the
operation’s contract explicitly defines partial emission.

**Informative:** proposal §2.7, §4 intro.

### 5.2 Emission modes

Implementations **MUST** support these **named modes** (exact API spelling is
product-defined):

1. **Full source** — output without demand markers at satisfied sites; ordinary
   Python text subject to formatter policy.
2. **Marker-preserving source** — output that retains documented markers at
   boundary demand/supply sites for tooling (proposal §4).

**Informative:** round-trip limitations — proposal §4.

### 5.3 Source provenance

**MUST:**

1. Support `emit(..., provenance=True|False)` (or equivalent); default **SHOULD**
   be `True` for developer-oriented round trips unless a product-wide config
   overrides (proposal §3.6).
2. When provenance is enabled, append a single reserved tail call of the form
   `astichi_provenance_payload("…")` (exact identifier and arity as product
   schema define) whose string carries a **versioned**, **compressed** payload
   suitable for AST/provenance restoration **only** (proposal §3.6).
3. Treat the **source text before the tail** as authoritative for **marker and
   Python semantics**; holes/binds/inserts **MUST** be recoverable by reparsing
   that text. The payload **MUST NOT** be executed as code.
4. If the user edits the source so that the AST no longer matches what the
   payload can safely apply to, provenance restoration **MUST** fail with an
   error that instructs removal or replacement of the tail call; locations in
   the current buffer **MUST** then be treated as authoritative (proposal §3.6).

**SHOULD:** validate payload version and bounds before decode.

**Compile entrypoint:** `compile` (or `astichi.compile`, if wrapped) **MUST**
accept optional **origin parameters** alongside source: at minimum logical
**filename**, **starting line**, and **starting column or byte offset**, so
diagnostics can refer to containers such as embedded `.yidl` (proposal §3.6).

### 5.4 Round-trip adapters

**Emit → parse → `Composable`** via markers and **payload-assisted restore** **MAY**
be separate adapters. Losslessness **MUST** be stated per adapter; neither
adapter is implied by the other (proposal §4).

---

## 6. Phase-1 scope limits (normative baseline)

Until superseded by a later version of this document:

1. **Loop domains** for `astichi_for` / unrolling **MUST** be limited to the
   documented baseline: literals, constant `range(...)`, and compile-time
   externals (proposal §3.6).
2. **Addressing** for builder targets **MUST** support **first-level** sites and
   **loop-instance** indexing; arbitrary deep descendant paths **MAY** be
   unsupported or experimental and **MUST** be documented as such (proposal §3.6).

---

## 7. Explicit non-normative or deferred items

The following **MUST** be specified in a future revision or separate normative
addendum; until then implementations **MAY** choose locally but **MUST** document
behavior:

| Topic | Pointer |
|-------|---------|
| `build()` vs missing **required** edges | Proposal §3.4 |
| `materialize()` concrete result type and whether it accepts a builder | Proposal §3.4 |
| Edge semantics: dataflow vs dominance | Proposal §2.5, §3.4 |
| Error placement: builder vs `build()` vs `materialize()` | Proposal §3.4 |
| **`astichi_bind_external`** value injection API | Proposal §5.5 |
| Scope merge algorithm beyond hygiene H1–H11 | Proposal §2.5; hygiene note |
| Fluent handle path → `PortId` mapping | Proposal §3.5 |
| Operator taxonomy beyond compose/build/materialize | Proposal footer |

---

## Document history

- **Initial composed spec** — derived from `AstichiApiDesignProposal.md` as of
  the revision current when this file was added. Subsequent edits **SHOULD**
  note normative deltas here or in repository changelog practice.
- **Hole/bind identifier surface** — §4.2 and related cross-refs aligned with
  the proposal update: hole and bind keys as **identifiers**, not string
  hole-kind tags; shape from AST context only (proposal §5).
