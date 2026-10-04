# Astichi Support Plan For YIDL Better Merge

## Purpose

YIDL better-merge work needs one Astichi improvement before the YIDL grammar
work should proceed: defaulted block holes. The YIDL lifecycle generator
currently uses explicit pass contributions to keep generated Python blocks
syntactically valid when no feature contributes statements. That creates noise
in both authored YIDL and generated Python, and it makes feature-oriented
production phases harder to keep clean.

This plan defines the Astichi-side behavior that lets YIDL say "this generated
block has an extension point, and if no one fills it, emit this fallback suite".

The implementation should not add YIDL-specific logic to Astichi. Astichi should
gain a general source-level feature for defaulted block holes.

## Required Source Shape

Use `astichi_hole(...)` as a context-manager marker in statement position, with
an explicit `astichi_fallback` sentinel:

```python
def _prepare_commit_tx_0_fields(self):
    with astichi_hole(prepare_commit_fields_body) as astichi_fallback:
        pass
```

This means:

- `prepare_commit_fields_body` is still a normal named block hole.
- Children can still be inserted into that hole through the existing builder
  machinery.
- The exact `as astichi_fallback` target marks the `with` body as the fallback
  suite for this hole occurrence.
- If the hole receives at least one insertion, the fallback suite is discarded.
- If the hole receives no insertions, the fallback suite is emitted in place of
  the marker.
- No `with astichi_hole(...)` marker survives final `materialize()` or
  `emit_commented()`.

This keeps `astichi_hole(...)` as the only hole marker. `astichi_fallback` is a
reserved marker-owned sentinel in this one syntactic position, not a callable
marker, not a runtime local binding, and not a demand or supply port. Do not add
a second marker such as `astichi_optional_hole` or a stringly default flag.

## Expected Output Examples

### Empty hole

Input:

```python
def validate(self):
    with astichi_hole(validate_body) as astichi_fallback:
        return True
```

No additions:

```python
def validate(self):
    return True
```

### Filled hole

Input:

```python
def validate(self):
    with astichi_hole(validate_body) as astichi_fallback:
        return True
```

Builder wiring:

```python
builder.add.Root(astichi.compile(root_source))
builder.add.Validation(astichi.compile("return self._check_count()\n"))
builder.Root.validate_body.add.Validation(order=10)
```

Output:

```python
def validate(self):
    return self._check_count()
```

### Fallback can be more than `pass`

Input:

```python
def commit_order_key(self):
    with astichi_hole(commit_order_key_body) as astichi_fallback:
        return ()
```

If no feature contributes a commit order key, the generated function returns an
empty tuple. If a feature contributes a statement such as `return self._key()`,
the fallback return is removed.

## Semantics

### Hole identity

`with astichi_hole(name) as astichi_fallback: fallback` declares the same hole
identity as statement-form `astichi_hole(name)`.

The hole is still an additive multi-block target. Existing duplicate
statement-form block holes remain valid, and this feature must not change that
behavior:

```python
def f():
    astichi_hole(body)
    astichi_hole(body)
```

If the same local hole name appears more than once, each occurrence is processed
independently at that occurrence site:

```python
def f():
    with astichi_hole(body) as astichi_fallback:
        pass
    with astichi_hole(body) as astichi_fallback:
        return None
```

If `body` is filled, each matching occurrence emits the ordered inserted
payloads and discards its own fallback. If `body` is unfilled, each defaulted
occurrence emits its own fallback. A same-name mandatory `astichi_hole(body)`
occurrence with no matching insert remains mandatory and still rejects at
materialize time.

### Fallback suite

The fallback suite is ordinary Python source. It participates in Python parsing
and location tracking immediately, but it is branch-inactive until selected.
Initial compile-time marker recognition, inventory construction, port
extraction, and hygiene must not treat markers inside a fallback suite as active
source.

If the fallback branch is selected, Astichi lowers a clone of the fallback body
as ordinary source at that point. If the fallback branch is discarded, nested
markers and comments inside it are ignored.

The fallback suite may contain:

- ordinary statements
- `astichi_comment(...)`

The fallback suite must not contain:

- `astichi_pyimport(...)`
- unresolved mandatory holes unless those holes are also satisfied when the
  fallback is selected

Managed pyimports are rejected inside fallback suites in this slice by a
fallback-specific validation scan. Pyimport markers are valid only in the
contiguous top-of-Astichi-scope marker prefix, and a fallback suite may later be
discarded. Allowing pyimports there risks vestigial module imports when the
fallback is not selected. If a filled branch needs imports, the additive
contribution payload should declare them.

### Filled vs empty

The selected branch is based on whether the defaulted hole occurrence is filled
in the current build/materialize result.

- no matching local insert shell: use fallback suite
- one or more matching local insert shells: use ordered inserted payloads

Builder edges still determine which insert shells are generated during
`build_merge(...)`. Final materialization must not require access to the builder
graph: it determines filled status from the AST shape it already receives, using
the same local sibling relationship that block-hole flattening uses today.

Astichi must not inspect whether an inserted payload is "empty" source in this
phase. YIDL may already suppress empty-resource contributions before Astichi
wiring; Astichi's rule is insert-presence based.

### Descriptor surface

`describe()` should expose enough information for YIDL to know that a block hole
has a fallback:

```python
description.holes
# includes ComposableHole(
#     name="validate_body",
#     placement=block,
#     has_default=True,
# )
```

The exact attribute names can follow existing descriptor conventions, but the
information must distinguish:

- mandatory block hole
- defaulted block hole
- satisfied hole after build, if current descriptors expose that state

The default marker can be represented as a stable boolean such as
`has_default=True`. Do not add an enum or passive string tag for this simple
descriptor surface.

Implementation must use an explicit internal carrier for this state. Current
descriptors are derived from inventory records, so the defaulted-hole bit should
live in a hole inventory payload or equivalent model metadata that survives
compile, refresh, build merge, unroll, and descriptor reconstruction. Do not
infer `has_default` from rendered source text.

### Internal representation

Treat the whole `ast.With` statement as the block-hole occurrence. This keeps the
feature close to the existing block-hole and insert-shell machinery:

- marker recognition records a block-shaped `astichi_hole(...)` marker whose
  node is the `ast.With` statement
- `RecognizedMarker.name_id` extracts the hole name from the `with` context
  expression
- the fallback suite is carried by `ast.With.body`
- `withitem.optional_vars` must be exactly `ast.Name("astichi_fallback",
  Store())`
- marker-owned metadata names include the context call's marker names and the
  `astichi_fallback` sentinel so name analysis does not treat them as runtime
  loads or locals

Inventory should carry defaulted-hole state on the hole record, for example:

```python
@dataclass(frozen=True)
class HoleInventoryPayload(InventoryPayload):
    port: DemandPort
    has_default: bool = False
```

`describe()` then derives `ComposableHole.has_default` from this payload.

No separate fallback registry is required in this slice: the selected fallback
body remains available on the `ast.With` node until build/materialize lowers the
occurrence. If a future pass needs to detach fallback bodies from source nodes,
that can be added later without changing the public syntax.

### Materialize gate

The unresolved-hole gate must run against the selected effective tree:

- filled defaulted block holes contribute the inserted payload branch
- unfilled defaulted block holes contribute the fallback branch

A defaulted block hole whose fallback contains unresolved mandatory state still
rejects. The diagnostic should name the original hole and the unresolved state
inside the selected fallback.

### Pre-materialize emit

Pre-materialize `emit()` should preserve the source marker shape:

```python
with astichi_hole(validate_body) as astichi_fallback:
    return True
```

This keeps round-trip and edited-source semantics honest. Final materialization
removes the marker.

### `emit_commented()`

`emit_commented()` should behave like final materialization with comment
preservation. It should not render the `with astichi_hole(...)` marker itself.

If the fallback branch is selected and includes `astichi_comment(...)`, those
comments are rendered normally.

If the fallback branch is discarded because the hole is filled, fallback comments
must be discarded too and must not appear in `emit_commented()` output.

### Loop unrolling

Defaulted block holes inside `astichi_for(...)` loops must unroll as independent
defaulted block holes:

```python
for item in astichi_for(items):
    with astichi_hole(item_body) as astichi_fallback:
        pass
```

After unrolling, each synthetic target inherits both the block-hole identity and
its own copied fallback suite. If `item_body[0]` receives no additive edge but
`item_body[1]` does, the first synthetic hole emits its fallback and the second
discards its fallback.

The unroll implementation must copy and suffix the defaulted hole metadata and
fallback suite together. It must not share one mutable fallback AST between
unrolled targets.

Because the defaulted hole is represented by the `ast.With` occurrence itself,
the existing unroll rename pass can suffix the `astichi_hole(...)` call inside
the context expression. Each unrolled copy already has its own copied
`ast.With.body`, so the implementation should only need tests guarding that the
copied fallback bodies are independent.

## Non-Goals

- Do not add expression-hole defaults in this slice.
- Do not add call-argument or parameter-hole defaults in this slice.
- Do not add replacement semantics.
- Do not add deep descendant traversal.
- Do not implement YIDL production phases in Astichi.
- Do not use post-render source cleanup as the semantic model.

## Implementation Slices

### A1: Parse And Lower Context-Manager Block Holes

Teach the lowering/classification layer to recognize:

```python
with astichi_hole(name):
    ...
```

as invalid unless the exact fallback sentinel is present:

```python
with astichi_hole(name) as astichi_fallback:
    ...
```

The valid shape is a defaulted block hole marker.

Validation:

- the `with` item must be exactly one `astichi_hole(name)` call
- `as astichi_fallback` is required
- no other `as target` binding is allowed
- no additional context managers are allowed in the same `with` statement
- the marker must be in a statement-suite position
- the fallback suite must be non-empty Python source
- the fallback suite must reject `astichi_pyimport(...)`

Implementation note:

- Handle this through an explicit `visit_With` path in the marker visitor.
  Generic `visit_Call` shape inference will otherwise see the call parent as an
  `ast.withitem` and can misclassify the marker as a scalar expression. The
  `visit_With` path should recognize the context-manager marker, construct a
  block-shaped recognized marker plus defaulted-hole metadata, skip generic
  traversal of the context expression, and skip normal marker traversal of the
  fallback body. Run only fallback-specific validation over the fallback body at
  initial compile time.

Focused tests:

- compile a function with a defaulted block hole
- descriptor reports the hole and default state
- duplicate statement-form holes remain valid
- duplicate defaulted block holes use their own fallback bodies
- invalid bare `with astichi_hole(name):` rejects
- invalid `with astichi_hole(name) as x` rejects
- invalid `with astichi_hole(name), other_context:` rejects
- fallback suite containing `astichi_pyimport(...)` rejects

### A2: Build And Materialize Empty Defaulted Holes

Update build/materialize so an unfilled defaulted block hole emits its fallback
suite.

Implementation note:

- Generalize block-hole extraction from "statement-form `ast.Expr` call only"
  to "block-hole occurrence statement", where the occurrence may be either
  `astichi_hole(name)` or the defaulted `ast.With` form.
- When `_ApplyTargetReplacements` sees a defaulted `ast.With` target with
  matching block replacements, it should append the same generated
  `@astichi_insert(...)` shells after the `ast.With` occurrence that it appends
  after a statement-form block hole today.
- At materialize time, run a pre-gate normalization on a cloned tree:
  - if a defaulted `ast.With` occurrence has matching local insert shells,
    replace the `ast.With` occurrence with a statement-form
    `astichi_hole(name)` anchor and leave the shells in place
  - if a defaulted `ast.With` occurrence has no matching local insert shells,
    replace the `ast.With` occurrence with cloned fallback-body statements
- After this normalization, the existing materialize gate and block flattener
  can mostly operate on the current statement-form hole plus sibling insert
  shell model.
- The fallback body is lowered and revalidated only after this selection, so
  discarded fallback markers never become demand ports or materialize errors.

Focused tests:

```python
source = '''
def f():
    with astichi_hole(body) as astichi_fallback:
        return 1
'''
assert astichi.compile(source).materialize().emit(provenance=False) == '''
def f():
    return 1
'''
```

Also verify class-body fallback:

```python
class C:
    with astichi_hole(body) as astichi_fallback:
        pass
```

finalizes to:

```python
class C:
    pass
```

Also verify nested suite fallback:

```python
def f(flag):
    if flag:
        with astichi_hole(body) as astichi_fallback:
            pass
```

finalizes with the `with` wrapper removed and the fallback suite placed directly
inside the nested `if`.

### A3: Build And Materialize Filled Defaulted Holes

Update replacement logic so any additive edge targeting the hole discards the
fallback suite.

Focused test:

```python
root = astichi.compile('''
def f():
    with astichi_hole(body) as astichi_fallback:
        return 1
''')
payload = astichi.compile('''
return 2
''')
builder = astichi.build()
builder.add.Root(root)
builder.add.Payload(payload)
builder.Root.body.add.Payload(order=10)
assert builder.build().materialize().emit(provenance=False) == '''
def f():
    return 2
'''
```

Add a multi-edge ordering test:

```python
with astichi_hole(body) as astichi_fallback:
    pass
```

filled with two statement payloads emits both payloads in edge order.

Add an unrolled-loop test:

- unroll a loop containing a defaulted block hole
- fill only one synthetic hole
- verify the filled synthetic hole discards its fallback
- verify the unfilled synthetic hole emits its fallback

### A4: Comments, Managed Imports, And Diagnostics

Verify defaulted block holes interact correctly with current Astichi features:

- fallback `astichi_comment(...)` renders through `emit_commented()`
- filled branch discards fallback comments
- managed imports inside fallback suites reject
- markers inside discarded fallback suites do not create demand ports or
  materialize errors
- unresolved state inside selected fallback names the defaulted hole in the
  diagnostic

### A5: Documentation And Snippets

Update active docs and snippets:

- `dev-docs/AstichiSingleSourceSummary.md`
- `docs/reference/marker-holes.md`
- `docs/reference/marker-overview.md`
- `docs/reference/README.md`
- `docs/reference/ReferenceGuide.md`
- `docs/guide/using-the-api.md`
- focused reference snippets under `docs/reference/snippets/statement/`

The hole reference documentation should add:

- the defaulted block-hole form
  `with astichi_hole(name) as astichi_fallback: ...`
- a clear statement that `astichi_fallback` is a reserved sentinel, not a
  callable marker and not a runtime local
- the filled/unfilled branch rule
- the restriction to block holes only
- the branch-inactive fallback rule for nested markers
- the managed-pyimport rejection rule for fallback bodies

The snippets should include the YIDL-relevant pattern:

```python
def _rollback_tx_0_fields(self):
    with astichi_hole(rollback_fields_body) as astichi_fallback:
        pass
```

Add at least:

- `docs/reference/snippets/statement/defaulted_block_hole_empty/`
  showing an unfilled defaulted block hole materializing to its fallback return
- `docs/reference/snippets/statement/defaulted_block_hole_filled/`
  showing a builder contribution replacing the fallback return

Regenerate snippet outputs with:

```bash
uv run python scripts/generate_reference_snippet_outputs.py
```

Update `docs/reference/ReferenceGuide.md` so the `statement` row links to the
new snippet(s).

## Roll-Build Implementation Plan

If this work is run with the repository roll-build method, use these checkpoints.
Start from a clean `astichi/` git tree. If no user-provided start tag is given,
use `defaulted-block-hole-start`.

Commit and tag each phase only when the phase goal is met and its focused
verification passes. Suggested phase tag names are included to make the rollout
recoverable.

### R0: Baseline

Goal:

- verify the current checkout is clean enough to checkpoint
- create the roll-build start tag

Actions:

- confirm no unrelated dirty files in `astichi/`
- create tag `defaulted-block-hole-start`

Verification:

```bash
uv run --with pytest pytest tests/test_lowering_markers.py tests/test_model.py -q
```

Tag after success: `defaulted-block-hole-r0-baseline`.

### R1: Parse, Metadata, Inventory, And Descriptors

Goal:

- recognize `with astichi_hole(name) as astichi_fallback: ...`
- keep fallback bodies branch-inactive during initial compile
- expose `ComposableHole.has_default`

Owned areas:

- `src/astichi/lowering/markers.py`
- `src/astichi/model/inventory.py`
- `src/astichi/model/inventory_describe.py`
- `src/astichi/model/descriptors.py`
- focused lowering/model/descriptor tests

Tests:

- valid defaulted block-hole recognition
- invalid bare `with astichi_hole(name):`
- invalid non-`astichi_fallback` optional var
- invalid multiple context managers
- fallback body with discarded nested markers does not create active ports
- descriptor reports `has_default=True`
- duplicate normal block holes remain valid

Verification:

```bash
uv run --with pytest pytest tests/test_lowering_markers.py tests/test_model.py tests/test_descriptors.py -q -k "defaulted or duplicate"
```

Tag after success: `defaulted-block-hole-r1-lowering`.

### R2: Build And Materialize Selection

Goal:

- generated insert shells attach to defaulted `ast.With` block-hole occurrences
- unfilled defaulted holes materialize to fallback bodies
- filled defaulted holes materialize to inserted payloads
- materialize gate runs against the selected effective tree

Owned areas:

- `src/astichi/materialize/api.py`
- `src/astichi/path_resolution.py`, only if block-hole extraction needs a shared
  helper
- focused build/materialize tests

Tests:

- unfilled fallback return
- filled fallback replacement
- multi-edge ordering
- class-body fallback
- nested-suite fallback
- selected fallback with unresolved mandatory state rejects and names the
  original defaulted hole
- discarded fallback with unresolved mandatory state does not reject

Verification:

```bash
uv run --with pytest pytest tests/test_build_merge.py tests/test_materialize.py -q -k defaulted
```

Tag after success: `defaulted-block-hole-r2-materialize`.

### R3: Comments, Emission, Unroll, And Round Trip

Goal:

- `emit()` preserves the defaulted marker shape before materialization
- `emit_commented()` renders selected fallback comments and discards filled
  fallback comments
- unroll copies and suffixes defaulted block-hole occurrences correctly
- emitted source/provenance round trips remain stable

Owned areas:

- `src/astichi/materialize/api.py`
- `src/astichi/lowering/unroll.py`, only if existing call-renaming is not enough
- comment/unroll/emit tests

Tests:

- pre-materialize emit preserves
  `with astichi_hole(name) as astichi_fallback`
- selected fallback `astichi_comment(...)` renders through `emit_commented()`
- filled branch discards fallback comments
- one unrolled synthetic hole filled and another unfilled
- provenance round trip on built and materialized outputs

Verification:

```bash
uv run --with pytest pytest tests/test_comments.py tests/test_emit.py tests/test_unroll.py tests/test_build_merge.py -q -k defaulted
```

Tag after success: `defaulted-block-hole-r3-emit-unroll`.

### R4: Reference Docs, Snippets, And Active Summary

Goal:

- document the public surface and sentinel semantics
- add reference snippets and generated outputs
- update active summary state

Owned areas:

- `dev-docs/AstichiSingleSourceSummary.md`
- `docs/reference/marker-holes.md`
- `docs/reference/marker-overview.md`
- `docs/reference/README.md`
- `docs/reference/ReferenceGuide.md`
- `docs/guide/using-the-api.md`
- `docs/reference/snippets/statement/defaulted_block_hole_empty/`
- `docs/reference/snippets/statement/defaulted_block_hole_filled/`

Verification:

```bash
uv run python scripts/generate_reference_snippet_outputs.py
uv run --with pytest pytest tests/test_ast_goldens.py -q
```

Tag after success: `defaulted-block-hole-r4-docs`.

### R5: Closeout Verification

Goal:

- close the Astichi slice only after full regression coverage passes

Verification:

```bash
uv run --with pytest pytest -q
uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q
```

Tag after success: `defaulted-block-hole-r5-closeout`.

## Verification

Focused verification:

```bash
uv run --with pytest pytest tests -q -k defaulted_hole
```

Full verification before closing the Astichi slice:

```bash
uv run --with pytest pytest -q
```

Run the Python-version matrix if the lowering/materialize changes touch
version-sensitive AST shapes:

```bash
uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q
```

## Acceptance Criteria

- Authored source can use
  `with astichi_hole(name) as astichi_fallback: fallback` for block holes.
- Empty defaulted holes materialize to the fallback suite.
- Filled defaulted holes materialize to inserted payloads and discard fallback.
- Descriptor APIs expose that the hole has a fallback.
- Existing mandatory-hole behavior is unchanged for normal `astichi_hole(name)`.
- No post-render cleanup is required to remove orphan `pass` statements.

## YIDL Dependency

YIDL better-merge work should wait for this Astichi support before removing pass
placeholder contributions from lifecycle YIDL. Production phases can be parsed
without this feature, but generated code quality and phase split ergonomics are
much cleaner once empty block extension points have real Astichi semantics.
