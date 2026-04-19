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

## Completed in roll-build: Step 1. Current support inventory

This inventory pins the exact implementation state before the new surface
lands.

### Step 1a. Source and generated surfaces

Current authored/source surfaces that already work today for
expression/call-argument composition:

- legacy user-authored `astichi_insert(target, expr)` is still accepted and
  recognized as a call-context insert marker in
  `src/astichi/lowering/markers.py`
- build/merge also accepts the current implicit expression source shape:
  zero or more top-level `astichi_import(...)` / `astichi_pass(...)` /
  `astichi_export(...)` expression statements followed by one trailing emitted
  expression; see `_implicit_expression_supply_after_boundary_prefix(...)` in
  `src/astichi/materialize/api.py`
- `astichi_funcargs(...)` has no current recognition path in `src/`

Current generated/internal surfaces used by build/merge:

- block contributions normalize to decorator shells via
  `_make_block_insert_shell(...)` in `src/astichi/materialize/api.py`
- expression contributions normalize to generated
  `astichi_insert(target, expr)` call wrappers via
  `_make_expression_insert_call(...)` and `_HoleReplacementTransformer` in
  `src/astichi/materialize/api.py`
- those generated expression wrappers are then stripped/realized by
  `_ExpressionInsertRealizer` / `_realize_expression_insert_wrappers(...)` in
  `src/astichi/materialize/api.py`

Current proving tests:

- `tests/test_expression_insert_pipeline.py`
- `tests/test_materialize.py`
- `tests/test_lowering_shapes.py`

### Step 1b. Current call-hole and boundary behavior

Current hole semantics in call context:

- `_infer_shape(...)` in `src/astichi/lowering/markers.py` currently classifies
  plain call-position `astichi_hole(...)` as `SCALAR_EXPR`
- `*astichi_hole(...)` currently classifies as `POSITIONAL_VARIADIC`
- `**astichi_hole(...)` and `{**astichi_hole(...)}` currently classify as
  `NAMED_VARIADIC`
- current realization only understands those three cases:
  - scalar replacement in `_HoleReplacementTransformer.visit_Call(...)`
  - starred expansion in `_HoleReplacementTransformer.visit_Starred(...)`
  - named-variadic keyword / dict expansion in
    `_HoleReplacementTransformer.visit_keyword(...)`,
    `_HoleReplacementTransformer.visit_Dict(...)`, and the corresponding paths
    in `_ExpressionInsertRealizer`

Current boundary-marker behavior that affects payload work:

- `astichi_import(...)`, `astichi_pass(...)`, `astichi_export(...)`, and
  `astichi_bind_external(...)` are all recognized from `ast.Call` sites by the
  marker registry in `src/astichi/lowering/markers.py`
- `src/astichi/lowering/boundaries.py` gives statement-prefix declaration
  meaning to `astichi_import(...)` / `astichi_pass(...)` at module scope and
  decorator-shell scope; expression-form `astichi_insert(...)` has no nested
  body scope there
- `astichi_export(...)` currently contributes a supply port and is stripped
  during materialize
- `astichi_bind_external(...)` currently contributes a scalar-expression demand
  port and is consumed by `BasicComposable.bind(...)` plus
  `src/astichi/lowering/external_bind.py`

Current proving tests:

- `tests/test_lowering_shapes.py`
- `tests/test_boundaries.py`
- `tests/test_materialize.py`
- `tests/test_bind_external.py`

### Step 1c. Current binding and wiring surfaces

Current binding/wiring surfaces that interact with payload work:

- compile-time and add-time `arg_names=` flow through
  `src/astichi/frontend/api.py`, `src/astichi/builder/handles.py`, and
  `BasicComposable.bind_identifier(...)` in `src/astichi/model/basic.py`
- those surfaces already resolve both identifier-suffix demands and
  `astichi_import(...)` identifier demands
- `builder.assign` demand discovery uses
  `collect_identifier_demands_in_body(...)` in `src/astichi/path_resolution.py`
  and already sees `astichi_import(...)` / `astichi_pass(...)` in expression
  positions
- actual assign rewriting is performed by `_apply_assign_bindings(...)` in
  `src/astichi/materialize/api.py`
- import renaming for explicit identifier bindings currently happens in
  `_apply_arg_name_bindings(...)` in `src/astichi/materialize/api.py`, but it
  is centered on top-of-shell import declarations rather than payload-local
  directive carriers

Current proving tests:

- `tests/test_builder_handles.py`
- `tests/test_boundaries.py`

## Completed in roll-build: Step 2. Recognition

Recognition now lives in:

- `src/astichi/lowering/call_argument_payloads.py`
- `src/astichi/frontend/api.py`
- `src/astichi/lowering/markers.py`

Completed behavior:

- `astichi_funcargs(...)` is now a recognized authored payload surface
- compile rejects non-payload placement early: the current authored form must be
  the only top-level expression statement in the snippet
- direct `_=astichi_import(name)` / `_=astichi_export(name)` carriers are
  recognized in authored order
- `_=` with any other value remains an ordinary emitted keyword argument
- `_=astichi_pass(name)` rejects directly
- `astichi_import(...)` / `astichi_export(...)` outside direct `_=` carriers
  reject directly
- wrapped directive-carrier forms reject directly

Current proving tests:

- `tests/test_call_argument_payload_recognition.py`
- `tests/test_lowering_shapes.py`
- `tests/test_expression_insert_pipeline.py`

## Completed in roll-build: Step 3. Internal payload model

The internal payload model now lives in
`src/astichi/lowering/call_argument_payloads.py`.

Completed behavior:

- authored `astichi_funcargs(...)` extracts to `FuncArgPayload`
- the payload currently preserves five item classes:
  - `PositionalFuncArgItem`
  - `StarredFuncArgItem`
  - `KeywordFuncArgItem`
  - `DoubleStarFuncArgItem`
  - `DirectiveFuncArgItem`
- extraction preserves authored item order within one payload
- repeated direct `_=` directive carriers preserve authored order
- ordinary `_=` values extract as ordinary keyword items, not directives

Current proving tests:

- `tests/test_call_argument_payload_model.py`
- `tests/test_call_argument_payload_recognition.py`
- `tests/test_lowering_shapes.py`

## Completed in roll-build: Step 4. Boundary, binding, and lowering

The combined boundary/binding/lowering work now lives across:

- `src/astichi/materialize/api.py`
- `src/astichi/lowering/external_bind.py`
- `src/astichi/lowering/call_argument_payloads.py`

Completed behavior:

- payload-local `astichi_import(...)` in direct `_=` carriers is now rewritten
  by both `arg_names=` and `builder.assign`
- payload-local `astichi_export(...)` in direct `_=` carriers now survives
  materialize as a supply port even though the carrier itself is stripped from
  emitted Python
- payload-local `astichi_pass(...)` remains the value-level boundary form in
  emitted argument positions
- payload-local `astichi_import/export(...)` on the same name as
  `astichi_bind_external(...)` reject directly
- `astichi_bind_external(...)` now works as a normal emitted value form inside
  `astichi_funcargs(...)`, including `.bind(...)` before materialize
- plain call-hole lowering is implemented for:
  - `func(astichi_hole(a))`
  - `func(*astichi_hole(a))`
  - `func(**astichi_hole(a))`
- plain call-position holes now keep positional/starred items in the hole
  region and append keyword / `**` items after the authored keyword region of
  the enclosing call
- `*astichi_hole(...)` rejects keyword / `**mapping` payload items
- `**astichi_hole(...)` rejects positional / starred payload items
- statically-known duplicate explicit keyword names reject during build
- dynamic collisions knowable only through `**mapping` expansion are still left
  to normal Python runtime behavior
- `_=` carriers and generated internal expression placement metadata are now
  stripped during realization
- emitted Python no longer contains `astichi_funcargs(...)` or `_=` carriers
- unsatisfied payload-local `astichi_import(...)` sites remain ordinary demand
  ports on the materialized composable rather than disappearing

Current proving tests:

- `tests/test_call_argument_payload_materialize.py`
- `tests/test_call_argument_payload_recognition.py`
- `tests/test_call_argument_payload_model.py`
- `tests/test_expression_insert_pipeline.py`
- `tests/test_bind_external.py`
- `tests/test_boundaries.py`
- `tests/test_materialize.py`

## Step 5. Staged build coverage

Goal: prove the new payload surface survives build boundaries.

### Step 5a. Stage-built payload reuse

- built payload contributors can be reused in later stages without losing
  payload shape or directives

### Step 5b. Descendant-ref addressing with payloads

- deep descendant addressing works when the addressed target is a call-argument
  site fed by payload-based contributions

### Step 5c. Cross-stage import/export/pass

- payload-local imports can be wired in later stages
- payload-local exports survive stage boundaries as intended

### Step 5d. Reuse isolation

- reused built composables keep per-instance payload scope separation
- reused staged payloads do not alias each other's exports, imports, or walrus
  locals

Exit rules:

- staged tests prove the surface survives `build()` boundaries
- failures in this stage indicate real implementation bugs, not unspecified
  semantics

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

## Step 7. Legacy authored-surface removal

Goal: remove the old user-authored `astichi_insert(target, expr)` path for
call-argument composition only after the new surface is implemented and covered.

### Step 7a. Migrate remaining old-surface tests

- convert old authored-expression tests to the new payload surface
- keep only the coverage that still belongs to generated/internal
  `astichi_insert(...)` behavior

### Step 7b. Reject the legacy authored surface

- reject legacy user-authored `astichi_insert(target, expr)` for this surface
- keep the rejection scoped to call-argument composition

### Step 7c. Final removal/regression coverage

- keep only the minimum regression coverage needed to prove the authored form
  is no longer accepted here
- verify generated internal `astichi_insert(...)` normalization still works

Exit rules:

- no active call-argument tests rely on user-authored
  `astichi_insert(target, expr)`
- authored `astichi_insert(target, expr)` is rejected for this surface
- generated internal `astichi_insert(...)` behavior remains covered

## Recommended rollout note

The highest-risk part of the plan is Step 4f: plain call-position lowering for
mixed call bundles. Everything else can be staged around that core lowering
contract. The authored old-surface removal in Step 7 should land only after the
new surface is implemented, migrated, and stage-covered.
