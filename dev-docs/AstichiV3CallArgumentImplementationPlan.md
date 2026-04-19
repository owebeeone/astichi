# Astichi V3 call-argument implementation plan

Status: implementation plan for the `astichi_funcargs(...)` surface described in
`AstichiV3CallArgumentAddendum.md`.

This plan is about implementation order, not final API rationale. The rationale
lives in the addendum and related design notes.

## Resolved upfront

These policy questions are already resolved and should not remain as active plan
steps.

- `astichi_funcargs(...)` is call-site-only
- user-authored `astichi_insert(target, expr)` is not an accepted surface for
  call-argument composition
- generated internal `astichi_insert(...)` remains valid placement metadata and
  the normalization target for `astichi_funcargs(...)`
- all three call-target forms are allowed:
  - `func(astichi_hole(a))`
  - `func(*astichi_hole(a))`
  - `func(**astichi_hole(a))`
- `func(astichi_hole(a))` is a mixed call-bundle region
- `func(*astichi_hole(a))` accepts only positional and starred items
- `func(**astichi_hole(a))` accepts only named keyword and `**mapping` items
- for plain call-position holes, generated keyword / `**` items append after
  the authored explicit keyword / `**` region of the enclosing call
- generated `astichi_insert(...)` wrappers are inserted alongside the target
  hole; holes are insertion points, not one-off replacement sites
- within one hole, explicit `order=` overrides insertion order
- insertion order is the tie-breaker when `order=` is equal
- item order inside one `astichi_funcargs(...)` payload is preserved, subject
  only to the minimum reordering needed to emit legal Python
- `_=` is special only when its direct value is `astichi_import(name)` or
  `astichi_export(name)`
- repeated special `_=` entries are allowed at the Astichi source level because
  markers only need to survive parse-to-AST
- `_=` with any other value is an ordinary emitted keyword argument
- wrapped container forms in `_=` are compile-time errors
- `astichi_pass(name)` is not valid in `_=` because it is the value-level form
- `astichi_bind_external(name)` is a normal emitted value form, not a directive
  carrier
- payload-local `astichi_import(name)` / `astichi_export(name)` on the same name
  as `astichi_bind_external(name)` are rejected
- duplicate statically-known emitted keyword names reject during build
- duplicate names knowable only through dynamic `**mapping` expansion are left
  to normal Python runtime behavior

## Step 1. Current support inventory

Goal: pin down the exact current implementation before the new surface lands.

### Step 1a. Source and generated surfaces

- record the exact current authored/source surfaces that already work today for
  expression/call-argument composition
- record the exact current generated/internal surfaces used by build/merge

### Step 1b. Current call-hole and boundary behavior

- record the exact current hole semantics in call context:
  - plain call-position `astichi_hole(...)`
  - `*astichi_hole(...)`
  - `**astichi_hole(...)`
- record the exact current boundary-marker behavior that affects payload work:
  - where `astichi_import(...)` is accepted today
  - where `astichi_pass(...)` is accepted today
  - where `astichi_export(...)` is accepted today
  - where `astichi_bind_external(...)` is accepted today

### Step 1c. Current binding and wiring surfaces

- record the exact current binding/wiring surfaces that interact with the new
  payload work:
  - `arg_names=`
  - `builder.assign`

Exit rules:

- the inventory is descriptive and concrete, not a restatement of intent
- the inventory names the current code paths and tests that prove current
  behavior

## Step 2. Recognition

Goal: teach compile/lowering to recognize the new authored payload surface.

### Step 2a. Recognize `astichi_funcargs(...)`

- add marker/surface recognition for `astichi_funcargs(...)`
- reject unsupported placements early if the surface is call-site-only

### Step 2b. Recognize `_=` directive carriers

- detect `_=` entries inside `astichi_funcargs(...)`
- preserve authored order of repeated `_=` entries
- validate the allowed marker forms in `_=` values

### Step 2c. Reject malformed payloads

- reject `astichi_pass(name)` inside `_=`
- reject unsupported marker calls inside `_=`
- reject obviously invalid `astichi_funcargs(...)` payload shapes with direct
  diagnostics

Exit rules:

- focused compile-time tests prove `astichi_funcargs(...)` and `_=` are
  recognized
- malformed payloads fail during compile/lowering, not later during materialize

## Step 3. Internal payload model

Goal: extract authored `astichi_funcargs(...)` into a structured internal form.

### Step 3a. Define the payload structure

- positional items
- starred items
- named keyword items
- double-star items
- non-emitting directive items

### Step 3b. Extract payloads

- convert `astichi_funcargs(...)` into the internal payload model
- preserve authored order within one payload
- preserve repeated `_=` directive order

Exit rules:

- extraction tests prove the authored AST becomes the expected internal model
- ordering is explicit and tested
- no lowering to final call syntax is required yet

## Step 4. Boundary and binding resolution

Goal: make payload-local boundary markers work with the existing binding
surfaces.

### Step 4a. Payload-scope import classification

- ensure `astichi_import(name)` carried in `_=` belongs to the fresh expression
  payload scope
- ensure payload-local imported names classify with the correct outer scope
  identity

### Step 4b. Payload-scope pass/export behavior

- ensure `astichi_pass(name)` in emitted argument expressions behaves as the
  value-level boundary form
- ensure `astichi_export(name)` carried in `_=` publishes from the payload
  scope, not the surrounding module scope

### Step 4c. `arg_names=` and `builder.assign` support

- extend import rewrite/resolution so payload-local `astichi_import(...)` is
  rewritten by `arg_names=` and `builder.assign`
- do not limit import rewrite to top-of-shell decorator-form bodies

### Step 4d. Implement resolved interaction and collision rules

- preserve the current import/pass/export interaction rules where they still
  apply
- lock and test that `astichi_bind_external(...)` is a value-form participant in
  payloads, not a directive
- reject payload-local `astichi_import(name)` + `astichi_bind_external(name)` on
  the same name
- reject payload-local `astichi_export(name)` + `astichi_bind_external(name)` on
  the same name
- test those mixed-mode rejections directly

Exit rules:

- focused tests cover `arg_names=`, `builder.assign`, walrus payloads, and
  payload-local import/export/pass
- supplied bindings reach payload-local imports correctly
- unresolved payload-local imports fail with direct diagnostics

## Step 5. Materialize lowering

Goal: lower payloads into final call syntax and strip directive carriers.

### Step 5a. Implement resolved call-hole lowering

- implement lowering for:
  - `func(astichi_hole(a))`
  - `func(*astichi_hole(a))`
  - `func(**astichi_hole(a))`
- preserve the resolved hole/contribution/item ordering contract
- normalize payloads through generated internal `astichi_insert(...)` wrappers
  until realization

### Step 5b. Implement region-specific validation

- reject named keyword / `**mapping` items targeting `*astichi_hole(...)`
- reject positional / starred items targeting `**astichi_hole(...)`
- preserve the resolved plain-hole split between positional-region items and
  keyword-region items

### Step 5c. Duplicate keyword rejection

- reject statically-known duplicate explicit keyword names
- reject them during build
- leave collisions knowable only through dynamic `**mapping` expansion to
  normal Python runtime behavior

### Step 5d. Strip carriers and generated metadata

- strip `_=` directive carriers
- strip any generated expression placement metadata
- keep generated internal `astichi_insert(...)` wrappers as the normalization
  target for `astichi_funcargs(...)` until realization
- emit runnable Python with no `astichi_funcargs(...)` or `_=` surface left

Exit rules:

- materialize emits runnable Python
- duplicate-key tests pass
- no `_=` carrier or `astichi_funcargs(...)` survives emitted source

## Step 6. Documentation alignment

Goal: make the active docs and test plans describe the new surface accurately
while the old authored surface still exists during migration.

### Step 6a. Public reference cleanup

- update active marker docs
- update the single-source summary
- update any user docs that still fail to describe `astichi_funcargs(...)` as
  the intended call-argument surface

### Step 6b. Test-plan alignment

- update the V3 staged test plan so staged coverage is written against the
  chosen authored surface

Exit rules:

- active docs do not disagree on the intended authored source surface
- staged plans and active docs point at the same surface

## Step 7. Staged build coverage

Goal: prove the new payload surface survives build boundaries.

### Step 7a. Stage-built payload reuse

- built payload contributors can be reused in later stages without losing
  payload shape or directives

### Step 7b. Descendant-ref addressing with payloads

- deep descendant addressing works when the addressed target is a call-argument
  site fed by payload-based contributions

### Step 7c. Cross-stage import/export/pass

- payload-local imports can be wired in later stages
- payload-local exports survive stage boundaries as intended

### Step 7d. Reuse isolation

- reused built composables keep per-instance payload scope separation
- reused staged payloads do not alias each other's exports, imports, or walrus
  locals

Exit rules:

- staged tests prove the surface survives `build()` boundaries
- failures in this stage indicate real implementation bugs, not unspecified
  semantics

## Step 8. Legacy authored-surface removal

Goal: remove the old user-authored `astichi_insert(target, expr)` path for
call-argument composition only after the new surface is implemented and covered.

### Step 8a. Migrate remaining old-surface tests

- convert old authored-expression tests to the new payload surface
- keep only the coverage that still belongs to generated/internal
  `astichi_insert(...)` behavior

### Step 8b. Reject the legacy authored surface

- reject legacy user-authored `astichi_insert(target, expr)` for this surface
- keep the rejection scoped to call-argument composition

### Step 8c. Final removal/regression coverage

- keep only the minimum regression coverage needed to prove the authored form
  is no longer accepted here
- verify generated internal `astichi_insert(...)` normalization still works

Exit rules:

- no active call-argument tests rely on user-authored
  `astichi_insert(target, expr)`
- authored `astichi_insert(target, expr)` is rejected for this surface
- generated internal `astichi_insert(...)` behavior remains covered

## Recommended rollout note

The highest-risk part of the plan is Step 5b: plain call-position lowering for
mixed call bundles. Everything else can be staged around that core lowering
contract. The authored old-surface removal in Step 8 should land only after the
new surface is implemented, migrated, and stage-covered.
