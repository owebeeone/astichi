# Astichi Import Proposal Implementation Plan

Status: proposal plan.

Primary design document:
[`AstichiImportProposal.md`](AstichiImportProposal.md).

This plan implements `astichi_pyimport(...)` as a source-visible, hygiene-aware
managed import marker. The goal is to let snippets declare imports at their
authored location while final materialization emits ordinary Python imports at
module head.

## 1. Ground Rules

Follow:

- `AGENTS.md`
- `astichi/AGENTS.md`
- `astichi/dev-docs/AstichiCodingRules.md`
- `astichi/dev-docs/AstichiSingleSourceSummary.md`

Implementation constraints:

- Keep source authoritative.
- Do not preserve import semantics in provenance or hidden builder state only.
- Keep emitted source valid Python.
- Do not introduce enums.
- Prefer semantic objects/classes that own validation and lowering behavior.
- Keep the implementation layered:
  `frontend -> lowering -> hygiene -> model -> builder -> materialize -> emit`.
- Do not store absolute filesystem paths in committed files.
- Do not broaden public surface beyond the proposal without updating the
  proposal and reference docs.

Test constraints:

- All success-path behavior must be covered by canonical golden fixtures under
  `tests/data/gold_src/`.
- Each success fixture must have both:
  - `tests/data/goldens/pre_materialized/<case>.py`
  - `tests/data/goldens/materialized/<case>.py`
- Bespoke unit tests should cover narrow mechanics only:
  recognition, validation failures, diagnostics, and edge cases not expressed
  cleanly by goldens.
- Avoid duplicating the same success assertion in both bespoke tests and
  goldens.

## 2. Target User Surface

From-import:

```python
astichi_pyimport(module=foo, names=(a, b))
print(a() + b())
```

Final materialized output:

```python
from foo import a, b

print(a() + b())
```

Plain import:

```python
astichi_pyimport(module=numpy, as_=np)
print(np.array([1, 2, 3]))
```

Final materialized output:

```python
import numpy as np

print(np.array([1, 2, 3]))
```

Dynamic module path:

```python
astichi_bind_external(module_path)
astichi_pyimport(module=astichi_ref(external=module_path), names=(thing,))
print(thing())
```

After binding `module_path="pkg.mod"`:

```python
from pkg.mod import thing

print(thing())
```

V1 rejection cases:

- wildcard imports
- relative imports
- managed `__future__` imports
- dotted plain imports without `as_=`
- alias dicts, such as `names={a: a2}`
- duplicate names inside one marker, such as `names=(a, a)`
- function-local/class-local managed import placement
- `astichi_pyimport(...)` inside `astichi_for(...)` bodies
- expression-snippet pyimport prefix carriers
- invalid module reference expressions
- invalid `names=` payload shapes
- mixed `names=` and `as_=`

## 3. Golden Coverage Matrix

Every V1 success case below should be implemented as a `gold_src` fixture.
Deferred success surfaces should not get success goldens until their phase is
actually implemented.

### 3.1 Basic From-Import

Fixture: `pyimport_from_basic.py`

Exercise:

- `astichi_pyimport(module=foo, names=(a, b))`
- local uses of `a` and `b`
- final import emitted at module head
- marker removed from final materialized body
- pre-materialized output carries marker metadata in the ordinary golden
  harness path

### 3.2 Merge Same Module

Fixture: `pyimport_from_merge.py`

Exercise:

- two snippets import overlapping symbols from the same module
- physical import declaration merges to one `from foo import a, b, c`
- each snippet only auto-shares its own declared imported names in its own
  Astichi scope

### 3.3 Import Hygiene Collision

Fixture: `pyimport_hygiene_collision.py`

Exercise:

- imported local name collides with another binding after composition
- hygiene renames the imported local binding
- final import uses alias syntax:
  `from foo import a as a__astichi_scoped_1`
- all uses belonging to that import binding are rewritten consistently

### 3.4 Plain Import Alias

Fixture: `pyimport_plain_alias.py`

Exercise:

- `astichi_pyimport(module=numpy, as_=np)`
- final `import numpy as np`
- `np` is shared inside the originating Astichi scope
- `np` participates in hygiene if it collides

### 3.5 Plain Import Without Alias

Fixture: `pyimport_plain_no_alias.py`

Exercise:

- `astichi_pyimport(module=os)`
- final `import os`
- local binding is first module segment
- local `os` uses bind to the managed import binding

### 3.6 Dotted Module Reference

Fixture: `pyimport_dotted_module.py`

Exercise:

- `astichi_pyimport(module=package.submodule, names=(thing,))`
- final `from package.submodule import thing`
- no `astichi_ref(...)` required for ordinary absolute module paths

### 3.7 Dynamic Module Path

Fixture: `pyimport_dynamic_module_ref.py`

Exercise:

- `module=astichi_ref(external=module_path)`
- module path supplied by external binding or other supported reducible source
- final emitted import uses the resolved module path

### 3.8 Expression Snippet Prefix Imports

Deferred until after block-scope pyimport is stable.

Fixture: `pyimport_expression_prefix.py`

Exercise:

- expression-shaped contribution starts with one or more
  `astichi_pyimport(...)` prefix declarations
- executable expression inserts into a scalar expression hole
- pre-materialized source carries pyimport metadata through internal
  expression-insert metadata
- final materialized source emits imports at module head and expression at the
  target site

### 3.9 Staged Composition

Fixture: `pyimport_staged_composition.py`

Exercise:

- stage 1 builds a composable that still contains managed import declarations
- stage 2 inserts additional snippets
- final materialized output preserves import collection, merge, and hygiene
  across staged descendant scopes

Do not add a separate round-trip success case. The golden runner already
validates pre-materialized round-trip behavior for every golden fixture. The
staged fixture exists only if it covers a distinct staged composition shape.

### 3.10 Golden Harness Augmentation

The golden harness should be augmented if pyimport introduces new
pre-materialized surfaces that could leave open demands or unresolved marker
metadata after the normal recompile/materialize check.

The harness already verifies that pre-materialized output can be recompiled with
`source_kind="astichi-emitted"` and materialized to the expected final output.
Extend that existing path rather than adding standalone round-trip fixtures.

Potential additions:

- assert no managed `astichi_pyimport(...)` markers survive final materialized
  output
- assert no internal pyimport carrier metadata survives final materialized
  output
- assert the recompiled pre-materialized source closes any pyimport-created
  identifier/import demands that were closed in the original build
- add helper checks only if they catch a real class of pyimport regressions not
  already caught by final materialized source equality

### 3.11 Ordinary Import Stays Ordinary

Fixture: `pyimport_ordinary_import_unchanged.py`

Exercise:

- ordinary authored `import os` or `from foo import a` remains ordinary Python
- no collection/merge behavior is inferred
- managed imports in the same program still collect normally
- docs discourage ordinary imports for generated-file imports in favor of
  `astichi_pyimport`

### 3.12 Optional Alias Dict

Deferred fixture:
`pyimport_from_alias_dict.py`

Exercise:

- `astichi_pyimport(module=foo, names={a: a2, b: b2})`
- final `from foo import a as a2, b as b2`
- aliases are local hygiene-managed bindings

If alias dict support is deferred, do not create a success golden. Add focused
rejection/unsupported-shape coverage instead.

### 3.13 Marker Interaction Goldens

Add V1 success goldens only where the behavior is end-to-end rather than a
narrow validator check:

- `astichi_keep(a)` plus `astichi_pyimport(..., names=(a,))` keeps `a` and
  forces a colliding non-kept binding to rename away
- child `astichi_import(a, outer_bind=True)` can bind to an enclosing pyimport
- child `astichi_pass(a)` can read an enclosing pyimport when explicitly wired
- explicit `astichi_export(a)` publishes a pyimport local through the existing
  export mechanism

### 3.14 Insert-Shell Owner Scope

Fixture: `pyimport_insert_shell_owner_scope.py`

Exercise:

- pyimport appears at the prefix of an Astichi scope whose root is a
  function/class insert shell
- the marker is accepted because it belongs to that Astichi owner scope, not to
  a nested real user-authored function/class body
- final managed import is still hoisted to module head
- stripping the marker leaves a valid suite

### 3.15 Module Header Placement

Fixture: `pyimport_with_docstring_and_future.py`

Exercise:

- module docstring remains first
- ordinary `from __future__ import ...` remains before managed imports
- managed imports appear after those header statements
- body statements remain after the managed import block

## 4. Bespoke Unit Coverage

Add narrow unit tests outside the golden suite for validation failures and
diagnostic mechanics:

- `astichi_pyimport()` missing `module=`
- `module=` expression is not a valid module reference
- relative module reference is rejected
- wildcard `names=*` or equivalent wildcard shape is rejected
- `names=` is not a tuple
- `names=` is empty
- `names=` contains non-bare identifiers: attributes, calls, subscripts,
  starred expressions, constants, and nested sequence nodes all reject
- `names=` contains duplicate identifiers
- `as_=` is not a bare identifier
- `names=` and `as_=` are supplied together
- dotted plain import without `as_=` is rejected
- managed `__future__` import is rejected
- `astichi_pyimport(...)` inside `astichi_for(...)` is rejected
- alias dict form is rejected in v1
- statement marker appears in an invalid context
- unsupported function-local/class-local managed placement raises the intended
  v1 diagnostic if such detection is separate from general placement
- expression-snippet pyimport prefix carrier is rejected until its later phase
- same-scope `a__astichi_arg__` is not automatically satisfied by a pyimport
- pyimport diagnostics use the existing diagnostics/error-formatting style,
  including helpers from `src/astichi/diagnostics/formatting.py` where
  applicable

Use bespoke tests only for these narrow mechanics. Do not duplicate the
success-path output assertions covered by goldens.

## 5. Documentation Updates

### 5.1 Reference Docs

Add:

- `docs/reference/marker-pyimport.md`

Update:

- `docs/reference/README.md`
- `docs/reference/marker-overview.md`
- `docs/reference/scoping-hygiene.md`
- `docs/reference/materialize-and-emit.md`
- `docs/reference/errors.md`
- `docs/reference/compile-api.md` if compile-time recognition/validation
  changes are user-visible
- `docs/reference/marker-ref.md` to mention `astichi_ref(...)` as the dynamic
  module-path form for `astichi_pyimport`

The reference page should cover:

- from-import marker shape
- plain import marker shape
- direct module references
- dynamic `astichi_ref(...)` module references
- merge behavior
- hygiene alias behavior
- expression-snippet prefix behavior as deferred
- pyimport's binding-not-alias-through distinction from `astichi_import`
- marker interactions with `astichi_keep`, `astichi_import`, `astichi_pass`,
  `astichi_export`, and identifier suffixes
- v1 rejections
- ordinary user imports are unmanaged; `__astichi_arg__` import-position
  support is deferred to a later phase
- ordinary imports are allowed Python but discouraged in authored Astichi
  snippets when the import should belong to the generated module import surface
- emitted managed imports follow normal Python import style

### 5.2 Snippet Examples

Add examples under `docs/reference/snippets/pyimport/`.

Suggested examples:

- `from_basic/`
- `from_merge/`
- `hygiene_collision/`
- `plain_alias/`
- `staged_composition/`

Add `expression_prefix/` only when the deferred expression-carrier phase lands.

Each snippet directory should follow the existing reference snippet style:

- authored source files
- `snippet.json` where builder wiring is data-driven
- generated output file produced by the snippet generation script
- small, focused example text where appropriate

### 5.3 User-Facing Docs

Update:

- `docs/guide/using-the-api.md`
- `docs/README.md` if marker categories are summarized there
- `astichi/README.md`

`astichi/README.md` currently contains a brief marker list. Add
`astichi_pyimport(...)` to that list and include one short sentence explaining
that it declares managed imports collected at module head while preserving
scope/hygiene at the authored marker location.

Docs should consistently steer users toward `astichi_pyimport(...)` for imports
that should be managed by Astichi. Ordinary Python import statements may remain
valid, but they should be documented as unmanaged and discouraged for generated
module imports because they do not collect, merge, move to module head, or
participate in pyimport-specific sharing semantics.

### 5.4 Active Summary

Update:

- `dev-docs/AstichiSingleSourceSummary.md`

The summary should record:

- implemented marker surface
- supported v1 shapes
- rejected shapes
- pre-materialized source behavior covered by the golden harness
- test status after implementation

Do not update archived historical docs unless explicitly requested.

## 6. Implementation Sequence

### Phase 0: Behavior-Preserving Preparation

Goal: reduce duplicated traversal/binding risk before adding pyimport behavior.

Tasks:

1. Add or prototype a shared Astichi scope ownership helper.
2. Add a shared ordinary import binding-name helper.
3. Add marker-owned-name extraction support for marker metadata identifiers.
4. Migrate at least one existing scope-owner caller to the shared helper so the
   helper is covered by existing tests.
5. Keep the changes behavior-preserving.

Gate:

- Existing tests remain green.
- No pyimport behavior is claimed in this phase.

### Phase 1: Marker Recognition And Validation

Goal: recognize `astichi_pyimport(...)` and reject invalid authored shapes
without changing materialization yet.

Tasks:

1. Add a behavior-bearing marker spec for `astichi_pyimport`.
2. Validate statement-prefix placement:
   - pyimport may interleave with direct statement-form `astichi_import`,
     `astichi_bind_external`, `astichi_keep`, and `astichi_export` in the
     top-of-Astichi-scope prefix
   - the first non-prefix statement closes the prefix
   - pyimport at the prefix of its Astichi owner scope is valid even when the
     owner scope root is a function/class insert shell
   - pyimport nested in a real user-authored function/class body inside that
     owner scope rejects
3. Parse and validate:
   - `module=<absolute-ref>`
   - `module=astichi_ref(...)`
   - non-empty tuple `names=(...)`
   - `as_=...`
4. Reject wildcard imports, relative imports, managed `__future__` imports,
   dotted plain imports without `as_=`, duplicate names, alias dicts, mixed
   `names=` / `as_=`, and pyimport inside `astichi_for(...)`.
5. Add semantic model objects for parsed pyimport declarations rather than
   passive string tags.

Gate:

- Focused marker validation tests pass.
- No success behavior is claimed until materialization is implemented.

### Phase 2: Scoped Synthetic Import Bindings

Goal: make pyimport declarations visible to scope/hygiene as bindings at the
authored marker location.

Tasks:

1. Add a pyimport declaration model that records:
   - owner Astichi scope / binding identity
   - resolved or pending module path
   - import kind: plain import or from-import
   - original imported symbol for from-imports
   - local raw binding name
   - source occurrence order
2. Represent each imported local name as a scoped synthetic binding occurrence
   owned by the marker's Astichi scope.
3. Do not model pyimport local names as `astichi_import` alias-through names.
   `astichi_import` resolves to an enclosing Astichi scope; `astichi_pyimport`
   creates a binding in the current Astichi scope.
4. Teach name analysis/hygiene that pyimport local names are local bindings.
5. Bind same-scope `Load` uses to those bindings before final hygiene renaming.
6. Preserve the distinction between:
   - resolved module path
   - original imported symbol
   - local hygiene-managed name
7. Ensure collisions produce normal hygiene renames.
8. Use marker-owned local-name nodes as hygiene sinks:
   - synthetic `LexicalOccurrence.node` points at the marker-owned local
     `ast.Name`
   - `rename_scope_collisions(...)` mutates that node
   - import emission reads the final local name from that node
9. Do not require a `ScopeRenameResult` return object for V1. Keep that as a
   possible later cleanup if broader hygiene callers need it.

Gate:

- `pyimport_from_basic.py`
- `pyimport_hygiene_collision.py`
- `pyimport_plain_alias.py`
- `pyimport_plain_no_alias.py`

pass as goldens after materialized outputs are regenerated.

Implementation note:

- current hygiene already has an alias-through concept for `astichi_import` via
  fresh-scope imported names; pyimport must take a different path
- pyimport should be closer to ordinary `ast.Import` / `ast.ImportFrom` binding
  classification, except the physical import AST is synthesized later
- the final emitted import alias must be driven by the renamed binding identity,
  not by raw string search
- same-scope `a__astichi_arg__` is not automatically satisfied by a pyimport;
  use bare `a` for the local imported binding

### Phase 3: Import Collection And Emission

Goal: remove marker statements during materialization and emit collected imports
at module head.

Tasks:

1. Collect synthetic import binding records after module path resolution and
   hygiene naming decisions are available.
2. Merge compatible from-import declarations by resolved module path and final
   local binding name.
3. Merge duplicate plain imports.
4. Emit alias syntax when hygiene changed the local binding.
5. Emit the managed import block in normal Python import style:
   - insert after module docstring and ordinary future imports
   - reject managed future imports
   - plain `import ...` declarations before `from ... import ...`
   - deterministic lexicographic module ordering for v1
   - deterministic imported-symbol ordering within merged from-imports
   - leave stdlib / third-party / local grouping for future formatter/config
     work unless classification already exists
6. Place imports at module head.
7. Keep ordinary user imports unmanaged.
8. Copy source locations from the earliest contributing pyimport marker onto
   synthesized import AST nodes where practical; diagnostics should still cite
   the marker record.
9. If stripping pyimport marker statements empties a Python suite, insert
   `pass`; module bodies may remain empty.

Emission model:

- for from-imports, `alias.name` is always the original imported symbol
- for from-imports, `alias.asname` is `None` unless hygiene changed the local
  binding or an explicit alias form was authored
- for plain imports, `alias.name` is the full module path
- for plain imports, `alias.asname` is populated when an alias was authored or
  when hygiene changed the local binding
- from-import merge uses module/import-symbol/final-local identity
- final local spelling comes from the hygiene binding record
- plain imports with divergent final aliases may emit as separate statements

Gate:

- merge and ordinary-import goldens pass:
  - `pyimport_from_merge.py`
  - `pyimport_ordinary_import_unchanged.py`
- focused emit ordering tests pass if needed.

### Phase 4: Dynamic Module References

Goal: support `module=astichi_ref(...)` for externally bound or reducible
module paths.

Tasks:

1. Reuse the existing restricted reference-path evaluator where possible.
2. Ensure direct `module=foo.bar` does not require `astichi_ref(...)`.
3. Accept externally bound strings such as `"pkg.mod"` and validate them with
   the same dotted-path validator as direct module references.
4. Reject non-reducible dynamic module expressions and invalid path segments
   with a clear diagnostic.
5. Do not add pyimport-specific sentinel semantics. If existing external-ref
   lowering turns `astichi_ref(...).astichi_v...` into an absolute
   `Name`/`Attribute` chain, pyimport consumes that chain; otherwise it rejects.

Gate:

- `pyimport_dotted_module.py`
- `pyimport_dynamic_module_ref.py`

pass as goldens.

### Phase 5: Deferred Expression Prefix Import Carriers

Goal: preserve pyimport declarations attached to expression-shaped snippets
through build, emit, recompile, and materialize.

Tasks:

1. Allow expression snippets with pyimport prefix declarations followed by one
   executable expression.
2. Extend internal expression insert metadata with a source-visible pyimport
   carrier, such as `pyimport=(astichi_pyimport(...), ...)`.
3. Ensure `source_kind="astichi-emitted"` accepts and validates that carrier.
4. Ensure authored `source_kind="authored"` rejects that carrier.
5. Materialization extracts carrier imports as if the markers appeared at the
   expression snippet's authored location.
6. Ensure the carrier keyword is stripped before final materialized output.

Gate:

- `pyimport_expression_prefix.py` passes as a golden.
- `verify_round_trip(...)` remains green for pre-materialized output.

### Phase 6: Staged Composition And Golden Harness

Goal: support staged reuse and close any pyimport-specific gaps in the existing
golden harness.

Tasks:

1. Verify staged pyimport metadata survives built composables and descendant
   insertion.
2. Augment the golden harness if pyimport exposes new unresolved marker/demand
   states not caught by the existing pre-materialized recompile/materialize
   check.
3. Do not add standalone round-trip success fixtures; rely on the golden
   harness for round-trip validation.

Gate:

- `pyimport_staged_composition.py` passes as a golden if it covers a distinct
  staged composition shape.
- existing golden round-trip assertions cover all pyimport success fixtures.

### Phase 7: Deferred `__astichi_arg__` In Ordinary Imports

Goal: add ordinary import argumentization only after the base managed marker is
stable.

Tasks:

1. Add `__astichi_arg__` recognition in ordinary `ast.ImportFrom` module and
   alias-name positions.
2. Reject relative import forms until explicitly designed.
3. Resolve import suffix demands through the existing identifier binding
   surfaces where valid.
4. Add dedicated diagnostics only if they fall out naturally.

Gate:

- focused `__astichi_arg__` import tests pass.

### Phase 8: Optional Alias Dict

Goal: implement `names={a: a2, b: b2}` only if it is low-risk after the tuple
form is stable.

Tasks:

1. Parse dict keys as original imported symbols.
2. Parse dict values as local aliases.
3. Treat aliases as local hygiene-managed bindings.
4. Merge by original symbol plus local binding identity.

Gate:

- If implemented, `pyimport_from_alias_dict.py` passes as a golden.
- If deferred, docs clearly mark alias dict support as deferred and validation
  rejects the shape cleanly.

### Phase 9: Documentation And Summary

Goal: make the implemented behavior discoverable and keep docs in sync.

Tasks:

1. Add reference page.
2. Add reference snippets and generated outputs.
3. Update marker overview and reference index.
4. Update scoping/hygiene docs.
5. Update materialize/emit docs.
6. Update errors docs.
7. Update user guide.
8. Update `astichi/README.md` marker list.
9. Update `AstichiSingleSourceSummary.md`.

Gate:

- Docs match implemented behavior.
- Snippet generation passes.
- No archived docs are edited.

### Phase 10: Full Verification

Goal: close with the same confidence level as existing marker features.

Run:

```bash
uv run --with pytest pytest tests/test_ast_goldens.py -q
uv run --with pytest pytest -q
uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q
```

The Python-version matrix is precautionary for emitted-source/materialize
changes. Import-statement AST shapes are expected to be stable, but pyimport
changes the final emitted module header.

If goldens need regeneration:

```bash
uv run python tests/versioned_test_harness.py regen-goldens --python 3.14
```

Completion criteria:

- golden suite passes
- full suite passes
- Python-version matrix passes
- `AstichiSingleSourceSummary.md` records final test status

## 7. Main Risks

### 7.1 Hygiene Binding Identity

The highest-risk area is making imported symbols behave as real bindings at
the marker location while emitting the physical import elsewhere.

Mitigation:

- model pyimports as scoped synthetic bindings before hygiene
- keep original imported symbol and local hygiene name separate
- cover collision behavior with goldens

### 7.2 Expression Snippet Pre-Materialized Metadata

Expression snippets need pyimport metadata even though their executable payload
is wrapped by internal insert metadata.

Mitigation:

- carry pyimport marker syntax in emitted source
- rely on the golden harness recompile/materialize assertion for
  `source_kind="astichi-emitted"`
- cover with a dedicated expression golden

### 7.3 Import Placement Semantics

Module-head insertion is simple until module docstrings, future imports,
function-local imports, and comments matter.

Mitigation:

- scope v1 to module-head managed imports
- reject/defer function-local/class-local managed placement
- document ordinary imports as unmanaged and discouraged for generated-file
  imports
- define deterministic Python-style ordering for the managed import block

### 7.4 Staged Composition

Built composables must not lose import marker semantics or rely on hidden graph
state.

Mitigation:

- preserve pyimport in pre-materialized source
- add staged composition golden only if it covers distinct staged behavior
- keep source authoritative
