# Proposal: boundary `scope_policy` (AST identifiers → API enums)

Status: **proposal** — not implemented.

## 1. Problem

Astichi treats each insert boundary (hole / contribution shell / root wrap) as a
**separate Astichi scope** by default. That is intentional: lexical isolation is a
feature; cross-scope name identity is explicit (`astichi_import`,
`astichi_pass`, `astichi_export`, `arg_names=`, `keep_names=`,
`builder.assign...`).

Some call sites want an **optional escape hatch**: when a contribution crosses a
particular insert boundary, **do not** seal a new Astichi scope for that edge —
**join** the contribution into the enclosing composable’s Astichi scope for
hygiene (same rename bucket as the parent body around the hole).

This proposal names that knob **`scope_policy`**, keeps the **surface dumb in
AST land**, and lifts it to a **typed enum in API land**, mirroring the
marker-recognition pattern (raw call-site shape → canonical meaning after
lowering).

**Vocabulary:** only two policies are in scope for v1 — **`seal`** and
**join**. There is no third “copy” or implicit duplication story unless we add
a separate mechanism later; the knob is purely “does this boundary introduce a
new Astichi scope or not?”

## 2. Two-layer model

### 2.1 AST land (dumb)

- **Syntax**: a **simple identifier** (string) carried on the AST node that
  represents the boundary. No enum types in the parse tree; no runtime imports
  inside user source beyond what already exists for markers.
- **Examples** (illustrative — exact call shape is TBD when implemented):

  ```python
  astichi_hole(body, scope_policy="seal")
  @astichi_insert(body, order=0, scope_policy="join")
  def _(): ...
  ```

- **Rules**:
  - Omitted `scope_policy` means the **default** identifier (see §3.1).
  - Unknown identifiers are a **compile-time** error after recognition (same
    class of failure as an unknown marker variant), not a silent fallback.
  - Identifiers are **stable spellings** in docs and tests: lowercase, no
    clever parsing.

### 2.2 API land (meaning)

- After lowering / marker recognition, the dumb string is translated to a
  **single canonical enum** with **capitalized** members (same naming
  convention as other Astichi public enums).

  ```text
  ast land          →  api land
  "seal"            →  ScopePolicy.SEAL
  "join"            →  ScopePolicy.JOIN
  ```

- **Enum name**: `ScopePolicy` (or `BoundaryScopePolicy` if we need to avoid
  collision with unrelated “scope” concepts; prefer the shorter name unless a
  clash appears).

- **Semantics live on the enum**, not on raw strings: docs, `match` in the
  merge/hygiene pipeline, and builder validation all use `ScopePolicy`, not
  free-form `str`.

### 2.3 Parity with markers

Same pipeline shape as existing markers:

1. Parse / walk AST → record raw identifier on the boundary node.
2. Recognize → `RecognizedBoundary` / attach `scope_policy_raw: str`.
3. Validate → map to `ScopePolicy`; reject unknown spellings.
4. Materialize / merge / hygiene consume **`ScopePolicy`** only.

## 3. Initial policy set (intentionally small)

Keep the first version **dumb**: only two identifiers plus default.

| AST identifier | API member         | Meaning (hygiene) |
|----------------|--------------------|-------------------|
| *(default)*    | `ScopePolicy.SEAL` | **Seal** the boundary: crossing it introduces a **new** Astichi scope; rename and trust rules apply per scope as today. |
| `"seal"`       | `ScopePolicy.SEAL` | Explicit spelling of the default (optional for authors who want clarity). |
| `"join"`       | `ScopePolicy.JOIN` | **Join** across the boundary: the attached contribution does **not** get its own Astichi scope; lexical hygiene treats the child’s names as part of the **parent** scope around the hole (subject to §4 precedence). |

**Non-goals for v1**: `builder`-only policy strings, per-name exceptions, or
interaction with `trust_names` beyond “same scope bucket means same collision
domain.” **Copy / duplicate semantics** are out of scope here — if we need
those, they are a different feature (not a third `scope_policy` value).

## 4. Where the knob lives: hole vs builder

Both surfaces may carry policy **in the long run**; v1 can ship **hole-only**
if we want a minimal slice.

| Surface | Role |
|---------|------|
| **Hole / insert site** | Declares the **default policy** for “what crossing *this* boundary means” in the source that owns the demand port. |
| **Builder edge** (`add`, etc.) | Optional **per-edge override** when composing instances — only if we need composition-time flexibility without recompiling the parent. |

**Precedence (recommended):**

1. **Sealing wins by default**: if **either** hole or builder says `SEAL`, the
   edge is sealed. `JOIN` applies only when **both** allow join (hole allows +
   builder does not force seal). This preserves “structural scoping is the safe
   default.”

2. **Alternative (simpler to explain):** **hole wins** for conflicting requests:
   builder cannot relax a hole that is `SEAL`; builder may only pass through or
   tighten. Pick one rule for v1 and document it; do not leave ambiguity.

Implementation detail: store resolved `ScopePolicy` on the **merged edge
record** after precedence, so merge/hygiene see a single value.

## 5. Interaction with explicit wiring

`scope_policy=JOIN` is **orthogonal** to `astichi_import` / `pass` /
`export` / `assign`:

- **Join** = “this contribution shares the parent’s Astichi scope” for lexical
  collision grouping.
- **Import/pass/export** = “this name’s identity crosses **distinct** scopes”
  when scopes remain distinct.

A future composition might use `JOIN` for ergonomics inside one merged tree
and still use explicit wiring for cross-root or multi-stage graphs.

## 6. Open design choices (before implementation)

1. **Exact AST shape**: keyword-only on `astichi_hole` / `@astichi_insert`, vs
   a dedicated micro-marker — must match existing marker ergonomics and
   provenance.
2. **Root wrap**: whether the synthetic per-root `astichi_hole` /
   `@astichi_insert` pair also accepts `scope_policy` (probably defaults to
   `SEAL` forever for sibling-root independence).
3. **Diagnostics**: when a user writes `JOIN` but still has colliding names,
   error messages should cite **boundary policy** and **explicit wiring** as two
   different levers.
4. **Precedence rule**: confirm “seal wins” vs “hole wins” with one
   paragraph in user-facing docs.

## 7. Documentation and tests (when implemented)

- Add a short subsection to `AstichiSingleSourceSummary.md` under hygiene /
  boundaries pointing at this file.
- Tests: golden parse → `ScopePolicy`; merge behaviour `SEAL` vs `JOIN` on
  a minimal hole+step; precedence tests if builder override exists.

## 8. Implementation scope (work breakdown)

This feature is **not** a single hygiene tweak: it threads through **hole
sites**, **insert synthesis**, **builder graph records**, **`build_merge`**, and
**hygiene**. Below is the scoped sequence of work; order matters because later
layers consume resolved `ScopePolicy` values produced earlier.

### 8.1 AST + recognition (dumb identifiers → enum)

- Extend **`astichi_hole(...)`** call parsing to accept an optional keyword
  `scope_policy="seal"|"join"` (exact spelling TBD with marker ergonomics).
  Omitted → `seal`.
- Extend **`@astichi_insert(...)`** / bare **`astichi_insert(..., expr)`**
  recognition the same way when we need author-written shells (rare for
  builder-driven block inserts; see §8.3).
- In **`astichi.lowering.markers`** (or adjacent): map raw string →
  **`ScopePolicy`**; reject unknown identifiers at compile/recognition time.
- Golden tests: parse + unparse round-trip preserves keywords; bad spellings
  fail loudly.

### 8.2 Demand ports: “values from holes”

The merge pipeline must **read policy from the hole**, not invent it only on the
builder edge.

- **`extract_demand_ports`** / port model (`astichi.model.ports`): carry a
  **`scope_policy: ScopePolicy`** (default `SEAL`) on **block** and **expr**
  demand ports, populated from the corresponding **`astichi_hole(...)`** call’s
  keywords when the hole is recognized.
- Any code path that lists holes for validation (`_locally_satisfied_hole_names`,
  indexed-target checks) must remain consistent: the hole is still the anchor;
  policy is extra metadata on the same node.

This is the literal “**get values from holes**” step: the authoritative default
for an edge into `body` comes from **`astichi_hole(body, scope_policy=...)`** on
the **target** composable’s tree.

### 8.3 Augment `astichi_insert` site processing (merge-time synthesis)

Today **`build_merge`** builds contributions in
`materialize/api.py`: **`_BlockContribution`** + **`_make_block_insert_shell`**
always emits a decorated **`FunctionDef`** shell with
`@astichi_insert(target_name, order=...)`.

Augment this path:

- Thread a resolved **`ScopePolicy`** into **`_make_block_insert_shell`** (and
  the expression-insert path **`_make_expression_insert_call`** if expr holes
  participate in v1).
- Emit the keyword on the synthetic AST:
  `astichi_insert(..., scope_policy="join")` **or** omit when `SEAL` (dumb
  string in AST; enum only in Python API types inside the compiler).
- **`_BlockContribution`** (dataclass in `materialize/api.py`) gains a field
  **`resolved_scope_policy: ScopePolicy`** filled **after** merging hole
  default + builder override (§8.4).

For **`JOIN`**, the **behavioural** choice (implemented in hygiene / flatten,
not only AST sugar) is: the synthesized insert site must **not** introduce a
fresh Astichi scope. Two implementation strategies (pick one in §6):

1. **Marker-driven hygiene**: keep a shell in the tree but teach
   **`assign_scope_identity`** / `_ScopeIdentityVisitor` to treat
   `@astichi_insert(..., scope_policy=join)` like “same scope as parent”, **or**
2. **Structural**: for `JOIN`, splice the contribution body **without** a shell
   (only where soundness allows — likely block holes only).

Expression-form holes may stay **`SEAL`-only** in v1 if `JOIN` is ambiguous for
expr positions.

### 8.4 Build graph: new fields on edges (“build nodes”)

Extend **`AdditiveEdge`** in **`astichi/builder/graph.py`** with an optional
**`scope_policy: ScopePolicy | None`** (or `Literal[...] | None` until the enum
lands).

- **`None`** → “no builder override; use hole default from target.”
- **`ScopePolicy.SEAL` / `JOIN`** → explicit edge-level policy for this `.add()`.

Plumb through the **fluent builder** (`builder/handles.py` or equivalent): e.g.
`Root.body.add.Step(..., scope_policy=ScopePolicy.JOIN)` — exact API TBD.

**Precedence** (see §4): resolve to a single **`ScopePolicy`** in **`build_merge`**
when constructing each **`_BlockContribution`**, before calling
**`_make_block_insert_shell`**.

### 8.5 `build_merge` resolution order

For each additive edge into `(inst_name, effective_target_name)`:

1. Load **hole default** from the **target** instance’s demand port for that
   hole name (§8.2).
2. Apply **builder edge override** if non-`None` (§8.4).
3. Apply **precedence rule** (seal wins, or hole wins — document one).
4. Store on **`_BlockContribution`** and pass into shell synthesis (§8.3).

Root-scope wrap (**`_wrap_in_root_scope`**) should **stay `SEAL`** unless we
explicitly decide sibling roots can join (unlikely; would defeat independence).

### 8.6 Hygiene + flatten

- **`assign_scope_identity`** / **`_ScopeIdentityVisitor`**: boundaries that
  were “fresh Astichi scope” solely because of an insert shell must **respect
  `JOIN`** (§8.3 strategy).
- **`_flatten_block_inserts`** (post-hygiene): unchanged contract for **where**
  flatten runs; verify **`JOIN`** shells flatten to the same shape as today or
  are skipped if bodies were inlined.

### 8.7 Files likely touched (checklist)

| Area | Files / symbols |
|------|-----------------|
| Enum + mapping | New `astichi/.../scope_policy.py` or next to `markers.py`; **`ScopePolicy`**, **`parse_scope_policy_keyword(...)`** |
| Hole / port extraction | **`model/ports.py`**, **`lowering/markers.py`**, demand port dataclasses |
| Merge | **`materialize/api.py`**: **`_make_block_insert_shell`**, **`_BlockContribution`**, **`build_merge`** loop, **`_make_expression_insert_call`** |
| Graph | **`builder/graph.py`**: **`AdditiveEdge`**, **`add_additive_edge`** |
| Fluent API | **`builder/handles.py`** (or wherever `.add` is built) |
| Hygiene | **`hygiene/api.py`**: scope visitor + any insert-shell detection |
| Tests | **`tests/test_materialize.py`**, **`tests/test_boundaries.py`**, new focused tests for seal/join |

### 8.8 Non-goals for this slice

- Copy/duplicate semantics for names (separate feature).
- Changing **`astichi_import` / `assign`** semantics (orthogonal; still needed
  when scopes remain distinct).

## 9. Summary

| Layer | Representation |
|-------|----------------|
| AST | Dumb string identifiers (`"seal"`, `"join"`); default = seal. |
| API | `ScopePolicy` enum (`SEAL`, `JOIN`); same names, typed meaning. |
| Pipeline | Recognize → validate → enum; merge/hygiene consume enum only. |
| Placement | Primary on hole/insert; optional builder override with explicit precedence. |

This keeps the user-facing syntax minimal, keeps semantics centralized in one
enum, and stays aligned with how markers already bridge raw Python AST and
Astichi’s typed model. **Seal vs join** is the full vocabulary for v1 unless we
add a separate *copy* mechanism later.
