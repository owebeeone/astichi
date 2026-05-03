# Astichi Import Proposal Detailed Coding Plan

Status: pre-implementation analysis.

Primary design docs:

- [`AstichiImportProposal.md`](AstichiImportProposal.md)
- [`AstichiImportProposalPlan.md`](AstichiImportProposalPlan.md)

This document is intentionally more cautious than an implementation checklist.
The purpose is to decide how `astichi_pyimport(...)` should fit into existing
Astichi code paths before writing production code. The preferred outcome is a
small, consistent extension to the existing marker / hygiene / materialize
pipeline, with consolidation where the current implementation already has
duplicate paths.

## 1. Implementation Principle

Do not build an import subsystem parallel to Astichi's existing machinery.

`astichi_pyimport(...)` should be modeled as:

- a marker recognized by the existing marker registry
- a lexical binding source visible to the existing hygiene pass
- a readable local binding that can be explicitly exported or boundary-wired
  through existing mechanisms
- source-visible metadata that survives `emit()` / recompile round trips
- materialize-time AST synthesis of ordinary Python imports

The implementation should prefer:

- augmenting existing semantic objects and collectors
- parameterizing existing traversal helpers
- extracting shared helpers from duplicated traversal code
- keeping `emit_source(...)` as a simple AST renderer

The implementation should avoid:

- a second pyimport-specific hygiene pass
- a second pyimport-specific descriptor system
- raw string search after hygiene to infer renamed imports
- hidden state in provenance or builder records that cannot round-trip through
  source
- new passive tag strings where a behavior-bearing object is needed

## 2. Existing Surfaces To Change Or Audit

### 2.1 Marker Recognition

Current files:

- `src/astichi/lowering/markers.py`
- `src/astichi/frontend/api.py`
- `src/astichi/frontend/source_kind.py`
- `src/astichi/lowering/boundaries.py`
- `src/astichi/lowering/unroll.py`

Current shape:

- marker capabilities live on `MarkerSpec`
- `ALL_MARKERS` is the canonical registry
- recognition derives `MARKERS_BY_NAME` from `ALL_MARKERS`
- marker validation is mostly per-marker
- some placement validation lives outside marker specs, for example boundary
  markers in `lowering/boundaries.py`

Recommended approach:

1. Add a behavior-bearing pyimport marker spec to `markers.py`.
2. Put simple call-shape validation on the marker spec.
3. Put pyimport-specific structural validation in a dedicated lowering helper
   only if the marker spec becomes too large.
4. Keep the marker in `ALL_MARKERS` so existing recognition, unroll checks, and
   marker enumeration can see it.
5. Do not create a separate pyimport marker registry.

Consolidation consideration:

- `_BoundaryIdentifierMarker` already owns custom keyword validation for
  boundary markers. If pyimport needs nontrivial keyword validation, it may be
  cleaner to add a small marker subclass rather than expand `_SimpleMarker`.
- Avoid adding pyimport placement logic to `boundaries.py` unless it truly
  shares the boundary-prefix rule. Pyimport is a declaration marker, but it is
  not an alias-through boundary marker.

Resolved design choice:

- In v1, pyimport is a contiguous top-of-Astichi-scope block declaration.
- Expression-prefix support is deferred.

Recommendation:

- Treat `astichi_pyimport` as a top-of-Astichi-scope declaration for block
  snippets in v1.
- Defer expression-prefix directive support until after the block-scope path is
  stable.
- Do not route it through the `astichi_import` interaction matrix; create or
  generalize a "scope prefix declaration" concept if needed.

Locked v1 validation:

- `names=` is a non-empty tuple of bare identifiers.
- `names=` elements must be direct `ast.Name` nodes. Reject attributes, calls,
  subscripts, starred expressions, constants, and nested sequence nodes.
- duplicate names inside one marker reject.
- alias dicts such as `names={a: a2}` reject.
- wildcard and relative imports reject.
- managed `__future__` imports reject.
- dotted plain imports without `as_=` reject.
- `astichi_pyimport(...)` inside `astichi_for(...)` bodies rejects.
- `as_=` must be a bare identifier.
- pyimport may interleave with direct statement-form `astichi_import`,
  `astichi_bind_external`, `astichi_keep`, and `astichi_export` in the
  top-of-Astichi-scope prefix; the first non-prefix statement closes the
  prefix.
- pyimport is valid at the prefix of its Astichi owner scope, including when
  that scope root is a function/class insert shell.
- pyimport nested inside a real user-authored function/class body inside the
  owner scope rejects.

### 2.2 Module Reference Parsing

Current files:

- `src/astichi/lowering/external_ref.py`
- `src/astichi/materialize/api.py`

Current shape:

- `astichi_ref(...)` lowers at materialize time by evaluating a restricted
  compile-time expression to a dotted identifier path.
- direct dotted source like `package.submodule` is ordinary `ast.Attribute`
  / `ast.Name` AST, not currently a reusable module-path model.

Recommended approach:

1. Extract or expose a small helper that converts an AST expression into a
   dotted reference path without lowering it into a value expression.
2. Reuse the existing `astichi_ref` restricted evaluator for
   `module=astichi_ref(...)`.
3. Add a direct AST-reference extractor for:
   - `ast.Name("foo")`
   - nested `ast.Attribute(..., attr="bar")`
4. Reject anything else.

Additional decisions:

- `module=astichi_ref(external=module_path)` is valid when `module_path` is a
  bound string such as `"pkg.mod"`.
- invalid reduced paths, including empty segments and non-identifier segments,
  should reuse the existing dotted-path diagnostics where practical.
- `astichi_ref(...)` remains value-form; using it as a pyimport keyword value
  does not make it a new standalone marker context.
- Pyimport does not add special transparent-sentinel semantics. It consumes the
  absolute `ast.Name` / `ast.Attribute` chain left after existing external-ref
  lowering; if the existing lowering does not produce such a chain, pyimport
  rejects the module expression.

Consolidation consideration:

- `external_ref.py` currently has private helpers for path validation and chain
  construction. Pyimport needs path evaluation without expression replacement.
  This is a good time to split "evaluate a path expression" from "rewrite an
  AST expression into a `Name` / `Attribute` chain."
- Do not duplicate the dotted-path validation logic. If necessary, move the
  path validation helper to a small public-internal function in
  `lowering/external_ref.py`.

Recommended helper shape:

```python
def evaluate_reference_path_expression(node: ast.expr) -> tuple[str, ...]:
    ...

def extract_direct_reference_path(node: ast.expr) -> tuple[str, ...]:
    ...
```

The exact names can change, but there should be one canonical path validator.

### 2.3 Name Classification And Local Bindings

Current files:

- `src/astichi/hygiene/api.py`
- `src/astichi/path_resolution.py`

Current shape:

- `_BindingCollector` collects module-wide local bindings for
  `analyze_names`.
- `_ScopeBindingCollector` and `_SingleScopeBindingCollector` collect bindings
  per Python scope for scope identity.
- `collect_identifier_suppliers_in_body` separately collects readable supplier
  names for builder assignment / descriptors.
- all three already know ordinary `ast.Import` and `ast.ImportFrom`.

Risk:

Adding pyimport by copy/pasting logic into all three collectors will create
another consistency burden.

Recommended approach:

1. Before adding pyimport behavior, extract a shared concept for "binding names
   introduced by this statement/expression in this context."
2. Use that shared helper from:
   - `_BindingCollector`
   - `_SingleScopeBindingCollector`
   - `collect_identifier_suppliers_in_body`
   - any future pyimport descriptor/supply collection
3. For pyimport, the shared helper should return the local binding name:
   - from-import tuple: every imported symbol name
   - from-import alias dict: every local alias name, if implemented
   - plain import without alias: first module segment
   - plain import with alias: alias name

Consolidation candidate:

- ordinary import binding behavior is already duplicated between
  `_BindingCollector`, `_SingleScopeBindingCollector`, and
  `collect_identifier_suppliers_in_body`.
- pyimport should force this consolidation rather than adding a fourth
  implementation.

Likely helper location:

- `hygiene/api.py` is currently too broad, but adding a new module just for one
  helper may also be churn.
- A small internal module such as `astichi.asttools.bindings` or
  `astichi.hygiene.bindings` may be justified if it replaces duplicate logic in
  at least two existing files.

Decision rule:

- If the helper is used by only one call path, do not extract it yet.
- If pyimport requires updating three or more binding collectors, extract it
  first.

### 2.4 Astichi Scope Ownership

Current files:

- `src/astichi/hygiene/api.py`
- `src/astichi/lowering/boundaries.py`
- `src/astichi/path_resolution.py`
- `src/astichi/materialize/api.py`

Current shape:

- `lowering/boundaries.py` has `_NodeScopeMap`.
- `hygiene/api.py` has two local `_enter(...)` walkers to map marker nodes to
  scope nodes:
  - `_collect_fresh_scope_trust_declarations`
  - `_collect_fresh_scope_imports`
- `path_resolution.py` has `ShellIndex` and shell traversal for addressable
  shell paths.
- `materialize/api.py` has multiple visitors/mixins that skip
  `astichi_insert` shells.

Risk:

Pyimport needs to know "which Astichi scope owns this marker." Adding a third
or fourth local scope-map walker will make future scope semantics brittle.

Recommended approach:

1. Promote the existing `_NodeScopeMap` idea into a reusable internal helper.
2. Use one helper to answer:
   - scope containing a marker node
   - whether a scope is root or fresh insert shell
   - body associated with a scope when needed
3. Refactor `_collect_fresh_scope_trust_declarations` and
   `_collect_fresh_scope_imports` to use it if practical.
4. Use the same helper for pyimport owner-scope assignment.

Consolidation candidate:

- This is the strongest pre-implementation consolidation candidate.
- Current duplicated scope walkers already encode subtle rules about decorators,
  function arguments, class bases, expression inserts, and shell bodies.
- Pyimport should not add another copy of those rules.

Minimal acceptable fallback:

- If extracting a shared scope map is too risky for the first pyimport phase,
  implement the scope map helper beside the existing code and switch only
  pyimport plus one existing helper to it. Then migrate the rest in a later
  cleanup phase.

### 2.5 Hygiene Scope Identity

Current file:

- `src/astichi/hygiene/api.py`

Current shape:

- `assign_scope_identity(...)` builds a `ScopeAnalysis` of
  `LexicalOccurrence` records.
- `rename_scope_collisions(...)` mutates `ast.Name` and `ast.arg` occurrences
  based on `ScopeAnalysis`.
- `astichi_import` uses `fresh_scope_imported_names` to alias names through to
  an enclosing Astichi scope.
- synthetic expression insert scopes use `fresh_scope_local_bindings`.

Required pyimport semantics:

- pyimport is not an alias-through import.
- pyimport creates a local binding in the marker's Astichi scope.
- same-scope uses should bind to that local binding before hygiene.
- after hygiene, import emission needs the final local name for that binding.

Potential implementation options:

Option A: synthetic AST node occurrence

- temporarily insert real `ast.Import` / `ast.ImportFrom` nodes before hygiene
- let existing ordinary import binding collectors do most of the work
- remove / hoist them after hygiene

Pros:

- reuses ordinary Python import binding semantics
- minimal changes to binding collectors

Cons:

- marker source position and source round-trip need care
- hoisting/merging while preserving binding identity is nontrivial
- temporary AST mutation may be confusing around pre-materialized output

Option B: synthetic lexical occurrences passed to `assign_scope_identity`

- collect pyimport binding records before hygiene
- pass them into `assign_scope_identity`
- visitor appends `LexicalOccurrence` records for pyimport local bindings
- track final renamed local names from those synthetic occurrences

Pros:

- keeps marker AST in place until materialize consumes it
- matches current `LexicalOccurrence` / `rename_scope_collisions` model
- avoids pretending pyimport is a real Python import at the original location

Cons:

- `rename_scope_collisions` currently mutates only `ast.Name` and `ast.arg`
- synthetic occurrences need a way to receive final emitted names
- requires a small extension to `LexicalOccurrence` or a parallel result record

Option C: add pyimport names to local binding sets only

- make `_collect_local_bindings` and `_ScopeBindingCollector` include pyimport
  locals
- rely on existing `visit_Name` for uses
- separately infer final names from renamed `ast.Name` uses

Pros:

- smallest apparent change

Cons:

- unreliable when a pyimport binding has no use
- raw string inference after hygiene is unsafe
- does not give emission a robust binding identity

Recommendation:

- Prefer Option B if the code change stays small.
- Consider Option A only if it reduces total code by reusing ordinary import
  binding paths cleanly.
- Reject Option C as too implicit; it risks making import emission depend on
  raw-name search rather than binding identity.

Likely small extension:

- add an optional `synthetic_occurrences` or `synthetic_bindings` parameter to
  `assign_scope_identity(...)`
- each synthetic binding carries:
  - raw name
  - owner scope node / scope key
  - collision domain source
  - marker-owned `ast.Name` node used as the final-name sink
- `rename_scope_collisions(...)` may continue mutating AST nodes in v1; the
  pyimport declaration can read the final local spelling from its marker-owned
  local-name node after hygiene

Consolidation consideration:

- A structured rename result may still be useful later, but it is not a v1
  prerequisite.
- Avoid making Phase A touch every hygiene caller solely to support pyimport.

Recommended first refactor:

1. Add marker-owned-name extraction.
2. Add synthetic occurrences whose `node` is the marker-owned local `ast.Name`.
3. Existing tests should remain green.
4. Pyimport emission reads final local names from those nodes, not from raw
   string search.

### 2.6 Identifier Supplies And Descriptors

Current files:

- `src/astichi/model/ports.py`
- `src/astichi/model/basic.py`
- `src/astichi/model/descriptors.py`
- `src/astichi/path_resolution.py`

Current shape:

- explicit `astichi_export` creates identifier supplies.
- `collect_identifier_suppliers_in_body` also considers readable names,
  including ordinary imports, function/class defs, and store names.
- descriptors build `identifier_supplies` by intersecting collected supplier
  names with supply ports.
- supply ports come from marker specs, not from arbitrary local bindings.

Risk:

Pyimport imported names may be readable suppliers for `builder.bind_identifier`
or `builder.assign`, but the current descriptor pipeline may not expose them
unless they have supply ports.

Analysis:

- Existing `collect_identifier_suppliers_in_body` collects ordinary import
  names, but descriptor output only includes names with a matching supply port
  in `supply_by_name`.
- Ordinary local assignments may be collectable by path resolution but may not
  become descriptor supplies unless a supply port exists.
- `astichi_export` is the current explicit public supply marker.

Decision:

- Pyimport names do not automatically become descriptor-visible identifier
  supplies in v1.

Recommendation:

- Use explicit `astichi_export(name)` when a pyimport local must be published as
  an identifier supply.
- If automatic descriptor visibility is approved later, add a distinct
  behavior-bearing pyimport supply origin. Do not reuse `EXPORT_ORIGIN`.

Consolidation consideration:

- Do not generalize the `MarkerSpec` port-template ABC in v1 for pyimport.
- Keep pyimport ports outside marker-port extraction unless and until automatic
  descriptor-visible pyimport supplies are explicitly added.
- If that later surface lands, prefer a dedicated helper that appends pyimport
  ports from parsed declarations over an ABC-wide refactor unless multiple
  marker families need multi-port extraction.

Important deferred design issue:

- automatic descriptor-visible
  `astichi_pyimport(module=foo, names=(a, b))` would need multiple supply ports
  from one marker occurrence.
- Do not contort `name_id` to hold multiple names.

Test guard:

- Existing marker/port behavior should remain unchanged in v1 unless explicit
  `astichi_export(...)` is used.

### 2.7 Materialization Pipeline

Current file:

- `src/astichi/materialize/api.py`

Current shape:

Materialization currently does:

1. gate unresolved holes / binds / arg identifiers / inserts
2. copy tree
3. resolve arg/boundary demands
4. realize parameter wrappers
5. lower `astichi_ref`
6. recognize markers
7. compute hygiene pin sets
8. assign scope identity
9. rename collisions
10. realize expression inserts
11. flatten block inserts
12. re-recognize / re-extract ports
13. strip residual markers
14. final reclassify

Recommended pyimport insertion points:

1. After arg/boundary resolution and before `apply_external_ref_lowering`, parse
   pyimport declarations enough to validate static surfaces.
2. After `apply_external_ref_lowering`, evaluate the resulting dotted
   module-path expression uniformly. Dynamic module refs should already have
   lowered into ordinary `ast.Name` / `ast.Attribute` chains by this point.
3. Before `assign_scope_identity`, build pyimport synthetic binding records and
   pass them to hygiene.
4. After `rename_scope_collisions`, read final local names from marker-owned
   local-name nodes.
5. Before or during `_strip_residual_markers`, remove pyimport marker
   statements.
6. Before returning, synthesize the module-head import block into `tree.body`.
7. Assert that no `astichi_pyimport(...)` marker or internal pyimport carrier
   survives final materialized output.
8. If marker removal empties a Python suite, insert `ast.Pass`; module bodies
   may remain empty.

Consolidation consideration:

- `materialize/api.py` is already large and has many local helper classes.
- Pyimport should not add a large nested subsystem to this file if it can be
  isolated behind small helper functions.

Recommended module split:

- Add `src/astichi/lowering/pyimport.py` or
  `src/astichi/materialize/pyimport.py`.

Choose based on ownership:

- parsing and validation of marker shapes belongs in `lowering/pyimport.py`
- materialize-time collection / synthesis likely belongs in
  `materialize/pyimport.py`

Avoid:

- putting all pyimport logic in `materialize/api.py`
- putting materialize-only AST insertion logic in `lowering/markers.py`

### 2.8 Expression Insert Metadata

Current files:

- `src/astichi/materialize/api.py`
- `src/astichi/path_resolution.py`
- `src/astichi/lowering/markers.py`

Current shape:

- expression inserts are internal `astichi_insert(target, expr)` calls.
- `_ExpressionInsert` stores expression/payload/order metadata.
- `_make_expression_insert_call(...)` creates expression insert calls with no
  pyimport metadata.
- `_InsertMarker.validate_node(...)` currently rejects unknown keywords and
  allows keywords mostly for decorator-form inserts.

Deferred requirement:

- expression-shaped snippets may have pyimport prefix declarations before the
  final expression.
- pre-materialized emitted source must carry those declarations in source form.

Recommended approach:

1. Extend `_ExpressionInsert` with `pyimports`.
2. Extend `_implicit_expression_supply_after_boundary_prefix(...)` or a new
   generalized prefix parser so it returns prefix metadata, not just
   `(expr, index)`.
3. Extend `_make_expression_insert_call(...)` to emit a source-visible pyimport
   carrier keyword.
4. Extend `_InsertMarker.validate_node(...)` to accept that carrier only for
   expression-form emitted metadata and only in `source_kind="astichi-emitted"`
   if the frontend distinction can be preserved cleanly.
5. On materialize, extract pyimport carrier data from expression inserts and
   treat it as if declared in the expression contribution's Astichi scope.
6. Ensure the carrier is rejected in `source_kind="authored"` and stripped
   before final materialized output.

Consolidation consideration:

- Current prefix handling is named `_BOUNDARY_EXPR_PREFIX_NAMES`, but it now
  includes all marker specs with `is_expression_prefix_directive()`.
- Pyimport should not become an expression-prefix directive in v1; add that
  behavior only with the deferred carrier phase.
- If prefix metadata grows beyond boundary directives, rename the concept in
  code from "boundary prefix" to "expression prefix directives" in a separate
  refactor.

Suggested refactor:

```python
ExpressionPrefix(
    statements=...,
    boundary_directives=...,
    pyimports=...,
)
```

This is cleaner than adding more tuple return values to
`_implicit_expression_supply_after_boundary_prefix`.

### 2.9 Import Emission Location

Current file:

- `src/astichi/emit/api.py`

Current shape:

- `emit_source` simply calls `ast.unparse`.
- materialize returns an AST that should already be final Python.

Recommendation:

- Do not add pyimport logic to `emit_source`.
- Synthesize import AST nodes during materialize so `emit_source` remains a
  generic renderer.

Placement helper:

- Add a materialize helper to insert managed imports after:
  - module docstring, if present
  - ordinary `from __future__ import ...`
- Reject managed `__future__` imports in v1.

Ordering:

- Deterministic Python-style ordering should be encoded in the import synthesis
  helper, not in `emit_source`.

### 2.10 Ordinary Imports

Current shape:

- ordinary imports already participate in Python binding collectors.
- docs will discourage ordinary imports for generated-file managed imports.

Recommendation:

- Do not rewrite ordinary imports in v1.
- Do not collect them into the managed import block.
- Do not infer pyimport descriptor supply records from ordinary imports. The
  separate `__astichi_arg__` import-position feature remains deferred.

Consistency note:

- Since ordinary imports already count as local bindings, a managed pyimport
  collision with an ordinary import should be handled by normal hygiene if both
  are in composition-managed scopes. The detailed tests should include at least
  one ordinary-import interaction if it reveals a semantic ambiguity.

### 2.11 `__astichi_arg__` Inside Imports

Current files:

- `src/astichi/lowering/markers.py`
- `src/astichi/materialize/api.py`
- `src/astichi/path_resolution.py`

Current shape:

- suffix markers are recognized on `FunctionDef`, `ClassDef`, `Name`, and
  `ast.arg` surfaces.
- ordinary `ast.ImportFrom.module` is a string, not an AST `Name`.
- `ast.alias.name` and `ast.alias.asname` are strings, not AST `Name`.

Important implication:

- `from package__astichi_arg__ import thing__astichi_arg__` cannot be handled
  by the existing identifier suffix visitor without additional import-specific
  string-field recognition.

Recommendation:

- Defer this until the base pyimport marker is stable, as the plan already
  says.
- When implemented, do not shoehorn import string fields into `ast.Name`-based
  suffix logic.
- Add a small import-string suffix parser that creates demand records, then
  route resolution through the same identifier binding map where possible.

Consolidation consideration:

- The existing suffix parsing function `strip_identifier_suffix(...)` can be
  reused for string fields.
- The recognition result may need a marker whose `node` is the containing
  `ast.ImportFrom` or `ast.alias`, because there is no AST node for the string
  itself.
- Diagnostics should include the import statement line.

### 2.12 Existing Marker Interactions

Locked v1 rules:

- `astichi_keep(a)` and `astichi_pyimport(..., names=(a,))` in the same scope:
  keep wins. The imported local spelling is pinned as `a`; colliding non-kept
  bindings rename away.
- `a__astichi_keep__` may refer to a same-scope pyimport local after suffix
  stripping and pins the final spelling.
- `a__astichi_arg__` is not automatically satisfied by a same-scope pyimport.
  It remains an explicit identifier demand; use bare `a` for the local
  imported binding.
- child-scope `astichi_import(a, outer_bind=True)` may bind to an enclosing
  pyimport local because the pyimport creates a readable enclosing binding.
- child-scope `astichi_pass(a)` may likewise read the enclosing pyimport local
  when explicitly wired.
- `astichi_export(a)` in the same scope explicitly publishes the pyimport local
  through the existing export supply mechanism. Pyimport alone does not create
  descriptor-visible identifier supplies in v1.

### 2.13 Unroll Interaction

V1 recommendation:

- reject `astichi_pyimport(...)` inside `astichi_for(...)` bodies.

Reason:

- pyimport has marker-owned AST `Name` nodes that act as hygiene sinks.
- unroll also has per-iteration rename rules for marker-owned identifiers.
- deciding whether an import is invariant, per-iteration, or merged after
  unroll is a separate semantic design.

Future support must decide whether local binding nodes are renamed per
iteration and whether dynamic module paths may depend on the unroll domain.

## 3. Recommended Refactors Before Pyimport

These are candidates, not mandatory blockers. The guiding rule is: if a refactor
can be made behavior-preserving and existing tests cover it, do it before
pyimport rather than duplicating code.

### 3.1 Shared Astichi Scope Map

Problem:

- scope ownership is reimplemented in multiple places
- the rules are subtle and pyimport needs the same answer

Recommendation:

- extract a reusable internal scope map based on `_NodeScopeMap`
- use it first for pyimport
- then migrate `_collect_fresh_scope_imports` and
  `_collect_fresh_scope_trust_declarations` if the diff stays manageable

Minimum API:

```python
scope_map = AstichiScopeMap.from_tree(tree)
scope = scope_map.scope_for(node)
scope.is_root()
scope.root_node
scope.label
```

### 3.2 Shared Binding Name Collector

Problem:

- ordinary import binding logic is duplicated
- pyimport binding logic would otherwise be duplicated too

Recommendation:

- extract helper(s) for local binding names from ordinary statements and
  pyimport marker statements
- reuse from hygiene and path-resolution supplier collection

### 3.3 Rename Result From Hygiene

Problem:

- current hygiene mutates AST nodes but does not return a map from binding
  identity to final local name
- pyimport emission needs final local names, but v1 can get them from
  marker-owned local-name sink nodes

Recommendation:

- do not make a `rename_scope_collisions(...)` return-object refactor a v1
  prerequisite
- use marker-owned local `ast.Name` nodes as synthetic occurrence sinks
- consider a structured rename result later only if broader callers need it

This keeps Phase A smaller and still avoids raw string inference after hygiene.

### 3.4 Expression Prefix Model

Problem:

- expression-prefix handling is currently narrow and named around boundary
  markers
- pyimport adds another prefix declaration that must carry metadata

Recommendation:

- defer pyimport expression-prefix carriers until the block-scope path is
  stable
- when that phase starts, introduce an `ExpressionPrefix` internal model before
  adding pyimport carriers
- keep current behavior green, then add pyimport fields

## 4. Recommended Implementation Sequence

### Phase A: Behavior-Preserving Consolidation

Goal: reduce duplicated traversal/binding code before adding pyimport behavior.

Tasks:

1. Extract reusable Astichi scope map or scope-owner helper.
2. Migrate at least one existing helper to prove equivalence and give the
   helper coverage from existing tests.
3. Extract shared binding-name helper for ordinary imports if pyimport would
   otherwise require touching three collectors.
4. Add marker-owned-name extraction support for marker metadata identifiers.
5. Do not refactor `rename_scope_collisions(...)` to return a result object in
   this phase unless another behavior-preserving cleanup independently needs
   it.

Verification:

```bash
uv run --with pytest pytest -q
```

Risk:

- This phase can break many tests if overdone. Keep each refactor independently
  revertible and behavior-preserving.

### Phase B: Pyimport Marker Parse Model

Goal: recognize and validate pyimport declarations without changing final
materialization semantics.

Tasks:

1. Add marker spec.
2. Add parsed declaration model.
3. Validate marker surfaces:
   - non-empty tuple `names=`
   - no duplicate `names=`
   - no alias dicts in v1
   - no dotted plain imports without `as_=`
   - no managed `__future__`
   - no wildcard or relative imports
   - no pyimport inside `astichi_for(...)`
4. Add rejection tests only.

Do not:

- add import emission yet
- add pyimport descriptor supplies yet
- add hygiene special cases yet

### Phase C: Hygiene Binding Integration

Goal: make pyimport locals participate in scope identity as local bindings.

Tasks:

1. Collect pyimport declarations with owner scopes.
2. Feed synthetic binding occurrences into hygiene.
3. Use marker-owned local-name nodes as final-name sinks.
4. Read final local names from those nodes after hygiene.
5. Add focused tests and first goldens for basic/hygiene cases.

Do not:

- infer final names from raw AST search
- add alias-through semantics

### Phase D: Materialize-Time Import Synthesis

Goal: remove marker statements and synthesize module-head imports.

Tasks:

1. Use post-hygiene pyimport binding records.
2. Merge from-imports by module/original symbol/final local binding.
3. Emit aliases from final local names.
4. Insert imports at module head in deterministic Python-style order.
5. Keep ordinary imports unmanaged.
6. Insert after module docstring and ordinary future imports.
7. Reject managed future imports.
8. Assert no pyimport marker/carrier metadata survives final output.

### Phase E: Deferred Expression Prefix And Internal Carrier

Goal: make expression-shaped pyimport snippets round-trip through existing
pre-materialized source.

Tasks:

1. Refactor expression prefix parsing if not already done.
2. Extend expression insert metadata with pyimport carrier.
3. Ensure `source_kind="astichi-emitted"` accepts the internal carrier.
4. Ensure `source_kind="authored"` rejects the internal carrier.
5. Strip the carrier before final materialized output.
6. Let the golden harness validate recompile/materialize.

### Phase F: Deferred Descriptor Supplies And Cross-Scope Wiring

Goal: expose pyimport locals as automatic identifier supplies only if that
surface is explicitly approved after v1.

Tasks:

1. Keep v1 behavior as explicit `astichi_export(...)` for descriptor-visible
   supplies.
2. If automatic visibility is approved later, add a distinct pyimport supply
   origin.
3. Prefer a separate pyimport port helper over an ABC-wide marker-template
   generalization unless multiple marker families need multi-port extraction.
4. Ensure builder identifier binding can target pyimport supplies only after
   the public descriptor behavior is documented.

### Phase G: Import-Position `__astichi_arg__`

Goal: support suffix arguments in ordinary import statements.

Tasks:

1. Parse suffixes in `ast.ImportFrom.module`, `ast.alias.name`, and
   `ast.alias.asname` string fields as needed.
2. Reuse `strip_identifier_suffix(...)`.
3. Route resolution through existing identifier binding surfaces.
4. Add focused tests; add goldens only for success-path behavior that is not
   already covered.

## 5. Consistency Questions To Resolve Before Coding

### 5.1 Should Pyimport Names Be Descriptor Supplies By Default?

Recommendation: no for v1.

Reason:

- pyimport creates a readable local binding in its originating Astichi scope
- explicit child-scope sharing can bind to that name through existing boundary
  mechanisms
- descriptor-visible publication remains explicit through `astichi_export(...)`
- automatic descriptor visibility would require a separate pyimport supply
  origin and multi-supply extraction design; defer that until the surface is
  explicitly approved

### 5.2 Should Pyimport Names Be Trusted Or Preserved?

Recommendation: no.

Reason:

- `astichi_keep` is the trust/preserve surface
- pyimport creates ordinary local bindings that can be renamed on collision
- preserving by default would weaken hygiene

### 5.3 Should Identical Sibling Pyimports Share One Binding Identity?

Recommendation: no.

Reason:

- Astichi scope isolation says sibling contributions own their locals
- physical import declarations may merge, but binding identity remains per
  originating scope

### 5.4 Should Import Emission Live In `emit_source`?

Recommendation: no.

Reason:

- `emit_source` renders the AST it is given
- materialize should produce final Python AST
- import ordering and alias synthesis are semantic materialization steps

### 5.5 Should Existing Ordinary Imports Be Hoisted?

Recommendation: no for v1.

Reason:

- ordinary imports are unmanaged
- docs should discourage them for generated-file imports
- hoisting ordinary imports would be a separate codemod-like feature

## 6. Line-Count And Bloat Guidance

The goal is not minimum diff size. The goal is minimum long-term surface area.

Preferred changes:

- small shared helpers replacing duplicated visitors
- behavior-preserving refactors with tests already covering them
- extending existing semantic objects
- returning richer data from existing passes

Suspicious changes:

- new visitors that duplicate `@astichi_insert` scope traversal
- new collectors that duplicate ordinary import binding rules
- pyimport-specific descriptor logic parallel to existing supply descriptors
- materialize helper code that infers hygiene names by string matching
- adding broad pyimport-specific state to `BasicComposable` unless it must
  survive as part of the public semantic carrier
- diagnostics that bypass the existing Astichi diagnostic/error formatting
  conventions, including helpers from `src/astichi/diagnostics/formatting.py`
  where applicable

Acceptable new modules:

- `lowering/pyimport.py` for marker-shape parsing and validation
- `materialize/pyimport.py` for post-hygiene import synthesis
- shared scope/binding helper modules if they replace duplicated code

Avoid adding a module if it only hides five lines of one-off logic.

## 7. Existing Consistency Drift To Watch

Astichi is still young enough that the right implementation may require small
behavior-preserving or behavior-normalizing refactors before pyimport lands.
The test suite is broad enough to support that, but changes should be explicit.

Potential drift already visible:

- Multiple code paths define what "the Astichi scope containing this node"
  means.
- Multiple collectors define what counts as a local binding.
- Ordinary import binding rules are duplicated in hygiene and path-resolution
  collectors.
- Expression-prefix handling is named around boundary markers even though the
  marker registry already has a broader `is_expression_prefix_directive()`
  concept.
- Hygiene computes the information needed for final names but currently exposes
  it mostly through AST mutation.
- Descriptor supplies depend on both marker-derived ports and body-level
  supplier collection, which can diverge if a new binding source is added in
  only one place.

Preferred response:

- consolidate the concept before adding pyimport to every duplicate path
- keep refactors small enough that test failures identify real semantic
  differences
- update tests/goldens when the new behavior is more consistent with documented
  semantics, but document the reason in `AstichiSingleSourceSummary.md` and the
  relevant reference page

Acceptable test/golden changes:

- deterministic import ordering replacing occurrence-order output for managed
  imports
- normalized diagnostics when they come from a shared validator
- source formatting changes caused by existing `ast.unparse` paths after a
  semantic refactor

Suspicious test/golden changes:

- changed scope identity for existing `astichi_import` / `astichi_pass`
  behavior without an explicit design update
- changed keep/trust behavior
- changed descriptor-visible supplies without documenting the new rule
- changed pre-materialized round-trip shape without source-visible replacement
  metadata

When a refactor breaks tests in a way that reveals inconsistent old behavior,
pause and decide whether the consistency improvement belongs in the pyimport
rollout or should be a separate preparatory change.

## 8. Test Strategy

Before behavior:

- add or adjust focused rejection tests for marker validation
- do not create xfail success tests

For success:

- use goldens under `tests/data/gold_src/`
- rely on the existing golden harness for pre-materialized recompile /
  materialize round-trip
- augment the harness only if pyimport creates a real hole not caught by final
  materialized equality

For refactors:

- run focused existing tests first
- then run full suite
- avoid changing goldens during behavior-preserving consolidation unless the
  emitted source was already inconsistent and the design explicitly accepts the
  normalization

## 9. Proposed First Engineering Spike

Before implementing pyimport, perform a small branch/phase with no public
behavior change:

1. Extract or prototype a reusable Astichi scope map.
2. Extract ordinary import binding-name helper if the diff is small.
3. Add marker-owned-name extraction support without changing existing marker
   behavior.
4. Run the full suite.

Success criteria:

- no public behavior changes
- tests stay green
- code paths needed by pyimport are clearer
- no `rename_scope_collisions(...)` return-object refactor is required for v1
- if the refactor increases complexity, stop and reassess before continuing

This spike is intentionally valuable even if pyimport is deferred, because it
targets existing consistency drift in scope traversal and binding collection.
