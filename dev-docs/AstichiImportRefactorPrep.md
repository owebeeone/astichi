# Astichi Import Refactor Prep

This document specifies the existing-code refactors to complete before adding
`astichi_pyimport` or any pyimport-specific production behavior. The work here
is intentionally limited to current Astichi features. Each step should be
behavior-preserving for the public API and should make later import support use
shared machinery instead of copying another specialized path.

The word "pyimport" below names the future consumer only. Do not add the
`astichi_pyimport` marker, pyimport validation, pyimport descriptor behavior, or
managed Python import emission during these preparatory phases.

## Ground Rules

- Keep each refactor independently reviewable.
- Prefer existing module boundaries and local helper styles.
- Preserve existing diagnostics unless the phase explicitly documents a
  formatting-only cleanup.
- Use existing canonical/golden coverage for success paths where possible.
- Add bespoke tests only for narrow mechanics that current fixtures do not
  exercise.
- Do not make descriptor-port or hygiene-result refactors prerequisites.

## Roll-Build Discipline

When using the repository roll-build method, treat each numbered prep section
below as its own candidate checkpoint. Complete the section, run the focused
tests named in that section, confirm its acceptance criteria, then commit and
tag that phase before starting the next one. If a phase exposes a semantic
ambiguity or would require changing current public behavior, stop and update the
design rather than folding that change into a "prep" commit.

## Recommended Order

1. Shared Astichi scope ownership helper.
2. Ordinary Python import binding-name helper.
3. Marker-owned metadata node helper.
4. Top-of-scope prefix classifier.
5. Residual marker stripping suite preservation.
6. Dotted-reference path helpers.
7. Diagnostics formatting alignment.
8. Guardrail check for intentionally deferred refactors.

The first four phases reduce drift in the areas that future managed imports
will touch most heavily. The suite-preservation and reference-path phases then
make the existing materialize/lowering pipeline less fragile without adding new
public semantics.

## 1. Shared Astichi Scope Ownership Helper

### Problem

Astichi currently has several walkers that independently decide which AST nodes
belong to which Astichi owner scope. The `_NodeScopeMap` idea in
`src/astichi/lowering/boundaries.py` is the closest shared shape, while hygiene
and materialize still have local walkers for fresh-scope import/trust
collection and collision analysis. These walkers are easy to drift apart around
insert-shell bodies, expression insert payloads, decorators, arguments,
defaults, returns, and class bases.

### Target Invariant

There is one internal helper that can answer:

- which Astichi owner scope owns a node,
- where a fresh inserted scope begins,
- which nested real Python function/class roots exist inside an owner scope,
- and which AST regions are still part of a scope boundary surface, including
  decorators, function arguments, defaults, returns, and class bases.

This helper must describe existing semantics only. It must not introduce a new
scope kind for future imports.

### Proposed Code Shape

Add a helper module under `src/astichi/asttools/`, for example
`src/astichi/asttools/scopes.py`. Keep the types object-based rather than enum
based.

Suggested internal API:

```python
class AstichiScope:
    root: ast.AST
    parent: AstichiScope | None

    def owns(self, node: ast.AST) -> bool: ...
    def is_root(self, node: ast.AST) -> bool: ...


class AstichiScopeMap:
    @classmethod
    def from_tree(cls, tree: ast.AST) -> AstichiScopeMap: ...

    def scope_for(self, node: ast.AST) -> AstichiScope: ...
    def parent_scope_for(self, scope: AstichiScope) -> AstichiScope | None: ...
```

The exact class names may change, but the helper should own traversal rules
rather than exposing a loose dictionary that every caller interprets
differently.

### Traversal Rules To Preserve

- A module root is an Astichi owner scope.
- A function/class insert shell body can be a fresh Astichi scope while
  signature metadata remains owned by the enclosing scope where current
  boundary handling requires that.
- Function decorators, argument annotations, defaults, return annotations, and
  class bases/keywords stay visible to the same owner-scope rules used today.
- Expression insert payloads are included in the ownership map so materialize
  and hygiene do not need their own special walker later.
- Real nested Python function/class bodies inside an owner scope are distinct
  from the owner-scope prefix.

### Composition With Prefix Scanning

The scope helper alone should not grow a bespoke method for every placement
question. For future validators that need to know whether a marker-like node is
inside a real nested Python function/class body within its owner scope, compose
two helpers:

1. use `AstichiScopeMap.scope_for(node)` to find the owner scope,
2. use the top-of-scope prefix scanner from section 4 on that owner's body.

A node owned by scope `S` but outside `scan_statement_prefix(S.body)` is not in
the owner-scope prefix. If the ownership map also records that the node is under
a nested real Python function/class root inside `S`, the validator can reject
that condition without inventing a second scope walker.

### Implementation Steps

1. Copy the behavior of `_NodeScopeMap` into the new helper without changing its
   public callers.
2. Extend the copied traversal to cover every current hygiene/materialize
   boundary surface identified above.
3. Add focused tests for the helper itself only where no existing test would
   fail on a traversal regression.
4. Migrate at least one existing caller before declaring the phase complete.
   Good first candidates are `_collect_fresh_scope_imports(...)` or
   `_collect_fresh_scope_trust_declarations(...)` in
   `src/astichi/hygiene/api.py`.
5. Leave other callers in place until follow-up phases unless the migration is
   trivial and low risk.

### Coverage

- Run the existing boundary and hygiene tests after the first caller migration:
  `tests/test_boundaries.py` and `tests/test_hygiene.py`.
- Before declaring this phase complete, confirm that existing tests or new
  focused tests exercise each subtle boundary surface through the migrated
  caller: decorator region, argument annotation, default expression, return
  annotation, and class base/keyword expression.
- If adding helper-specific tests, keep them structural and narrow. They should
  assert ownership of current surfaces, not future import behavior.

### Acceptance Criteria

- At least one existing production caller uses the helper.
- Existing tests exercise the migrated caller.
- No public materialized output changes.
- `_NodeScopeMap` either delegates to the new helper or is clearly marked as
  pending migration, so future work does not copy it again.

### Non-Goals

- Do not add pyimport placement rules.
- Do not redefine Python lexical scoping.
- Do not refactor the full hygiene pipeline in this phase.

## 2. Ordinary Python Import Binding-Name Helper

### Problem

Several collectors independently extract the local binding name created by
ordinary Python `ast.Import` and `ast.ImportFrom` statements. The duplicated
logic appears in hygiene collectors, path-resolution suppliers, external bind
lowering, and materialize helpers. Future import work should consume one
ordinary-import binding helper instead of adding another copy.

### Target Invariant

All existing code that asks "which local names does this ordinary Python import
statement bind?" should use one helper.

For current Python semantics:

- `import package.module` binds `package`.
- `import package.module as alias` binds `alias`.
- `from package import name` binds `name`.
- `from package import name as alias` binds `alias`.
- `from package import *` does not provide a precise local binding name and
  should keep the current caller behavior.

### Proposed Code Shape

Add a helper under `src/astichi/asttools/`, for example
`src/astichi/asttools/imports.py`.

Suggested API:

```python
def import_alias_binding_name(alias: ast.alias, *, from_import: bool) -> str | None:
    ...


def import_statement_binding_names(
    node: ast.Import | ast.ImportFrom,
    *,
    include_star: bool = False,
) -> tuple[str, ...]:
    ...
```

Callers that currently ignore star imports should keep doing so. Do not invent
new star-import semantics in the helper.

### Implementation Steps

1. Add the helper and unit tests covering plain import, aliased import,
   from-import, aliased from-import, dotted names, and star import.
2. Replace the duplicated logic in the smallest safe set of existing callers.
   Start with:
   - `_BindingCollector.visit_Import(...)` and
     `_BindingCollector.visit_ImportFrom(...)` in `src/astichi/hygiene/api.py`,
   - `_SingleScopeBindingCollector` in the same file,
   - ordinary supplier extraction in `src/astichi/path_resolution.py`.
3. If the first migration is clean, also replace the copies in
   `src/astichi/lowering/external_bind.py` and
   `src/astichi/materialize/api.py`.
4. Keep caller-specific filtering at the call site. The shared helper should
   answer only Python binding-name facts.

### Coverage

- Add focused helper tests in an existing AST-tools or lowering test file, or a
  new narrow test file if needed.
- Run `tests/test_hygiene.py`, `tests/test_external_bind.py`,
  `tests/test_materialize.py`, and `tests/test_boundaries.py`.

### Acceptance Criteria

- At least hygiene and path-resolution use the shared helper.
- Existing behavior for dotted imports and alias imports is unchanged.
- No caller starts treating star imports as precise suppliers unless it already
  did so before this refactor.

### Non-Goals

- Do not add managed import emission.
- Do not sort, group, or normalize import statements.
- Do not change how Astichi boundary imports work.

## 3. Marker-Owned Metadata Node Helper

### Problem

Current ignored-name handling mostly assumes markers have one name-bearing
positional argument. That assumption works for today's simple cases, but it is
already encoded in hygiene rather than in marker-specific metadata knowledge.
The result is a narrow hidden contract between marker recognition and hygiene.

### Target Invariant

Marker metadata AST nodes that are not ordinary runtime loads are reported
through one shared helper path. Hygiene should ask that path which nodes to
exclude from load-demand analysis instead of pattern-matching every marker
shape locally.

### Proposed Code Shape

Prefer a helper in `src/astichi/lowering/markers.py` or a nearby lowering module
that can be used by hygiene without creating import cycles.

Suggested API:

```python
def marker_metadata_name_nodes(
    markers: Iterable[RecognizedMarker],
) -> tuple[ast.Name, ...]:
    ...


def marker_metadata_name_node_ids(markers: Iterable[RecognizedMarker]) -> set[int]:
    ...
```

If a spec-level method fits cleanly, it can be added with a default
implementation:

```python
class MarkerSpec:
    def metadata_name_nodes(self, marker: RecognizedMarker) -> tuple[ast.Name, ...]:
        return ()
```

Only add the spec-level method if it reduces existing special cases. A
standalone helper is acceptable for the prep phase. The canonical return shape
is AST node objects. The id-set helper is only an adapter for hygiene's current
lookup style.

### Existing Metadata To Preserve

- Marker function names are marker syntax, not runtime loads.
- Name-bearing marker arguments for `astichi_keep`, `astichi_export`,
  `astichi_import`, `astichi_pass`, and `astichi_bind_external` remain metadata
  where current hygiene treats them that way.
- Existing `astichi_insert(ref=...)` metadata remains excluded from runtime load
  analysis.
- Existing marker behavior and diagnostics do not change.

### Implementation Steps

1. Move the current `_ignored_name_nodes(...)` logic out of
   `src/astichi/hygiene/api.py` into the shared helper, preserving exact
   behavior.
2. Make marker-specific handling data-driven through `MarkerSpec` only if that
   is smaller than a centralized helper. Avoid broad ABC churn for no current
   benefit.
3. Update hygiene to consume the id-set adapter, leaving the node-object helper
   as the shared semantic API.
4. Add narrow tests for the helper if existing hygiene tests do not pin the
   current metadata exclusions.

### Coverage

- Run `tests/test_hygiene.py`, `tests/test_lowering_markers.py`, and
  `tests/test_materialize.py`.
- Add a focused test that marker metadata names are not counted as runtime
  demands for at least one name-bearing marker and for `astichi_insert(ref=...)`
  if not already covered.

### Acceptance Criteria

- Hygiene no longer owns marker metadata-node shape knowledge directly.
- Current marker-owned name exclusions are unchanged.
- The helper can later accept multi-name marker metadata without rewriting
  hygiene.

### Non-Goals

- Do not add a descriptor-port generalization.
- Do not add future marker shapes.
- Do not change marker recognition or public validation surfaces.

## 4. Top-Of-Scope Prefix Classifier

### Problem

Astichi has several concepts of "prefix" statements: boundary prefix
directives, expression prefix handling, and direct statement-form marker
directives. Without one classifier, each new feature is tempted to reimplement
"scan from the start of the owner-scope body until the first non-prefix
statement."

### Target Invariant

There is one reusable helper that classifies direct statement-form prefix
directives and returns the prefix region for an Astichi owner scope. Existing
prefix behavior remains unchanged.

### Proposed Code Shape

Add a helper near marker recognition, for example in
`src/astichi/lowering/markers.py` or `src/astichi/lowering/marker_contexts.py`.

Suggested API:

```python
class PrefixScan:
    body: tuple[ast.stmt, ...]
    prefix_statements: tuple[ast.Expr, ...]
    first_non_prefix_index: int


def scan_statement_prefix(
    body: Sequence[ast.stmt],
    *,
    recognized_markers: Mapping[int, RecognizedMarker],
    allowed_specs: Container[MarkerSpec],
) -> PrefixScan:
    ...
```

The helper should classify only direct `ast.Expr(ast.Call(...))` statement
markers. It should not look inside nested statements.

### Prefix Family For Existing Code

Across current and future callers, the relevant direct statement-form prefix
directives are:

- `astichi_bind_external(...)` where current placement permits it,
- `astichi_import(...)`,
- `astichi_keep(...)`,
- `astichi_export(...)`.

When migrating an existing caller, `allowed_specs` must match that caller's
current accepted prefix set exactly. Do not widen a caller's accepted prefix
family as part of this refactor. If `astichi_bind_external(...)` is not accepted
by a current boundary-prefix consumer today, that migrated consumer must not
start accepting it merely because the shared scanner can classify it. Future
validators can pass their own `allowed_specs` later.

### Implementation Steps

1. Add the scanner with tests for:
   - an empty body,
   - a body with only prefix directives,
   - a body where the first non-prefix statement closes the prefix,
   - a prefix directive after a non-prefix statement remaining outside the
     prefix.
2. Migrate one existing prefix consumer. A good first target is boundary-prefix
   validation or expression prefix scanning, whichever can use the helper with
   the least semantic risk.
3. Preserve marker-context validation. The scanner should not become a second
   marker recognizer.
4. Verify the migrated caller's `allowed_specs` against its current accepted
   marker set before changing the call site.
5. Document in code comments that this helper is about current direct
   statement-prefix classification, not future import placement.

### Coverage

- Run `tests/test_boundaries.py`, `tests/test_expression_insert_pipeline.py`,
  `tests/test_lowering_markers.py`, and `tests/test_materialize.py`.
- Prefer existing golden coverage for any materialized-output behavior.

### Acceptance Criteria

- At least one current caller uses the scanner.
- Existing prefix directives remain accepted/rejected in the same places as
  before.
- The scanner exposes the close-on-first-non-prefix rule directly.

### Non-Goals

- Do not add future import prefix rules.
- Do not allow prefix directives in new marker contexts.
- Do not change expression insert semantics.

## 5. Residual Marker Stripping Preserves Valid Python Suites

### Problem

Residual marker stripping can remove statement-form markers. If a Python suite
becomes empty after stripping, the resulting AST can be invalid for suites such
as function bodies, class bodies, `if` bodies, loops, `try` blocks, and `with`
blocks. Future removable markers would increase the chance of hitting this, so
the existing stripper should guarantee valid suites first.

### Target Invariant

After residual marker stripping:

- module bodies may be empty,
- every non-module Python suite body that Python requires to be non-empty has at
  least one `ast.Pass`,
- inserted `ast.Pass` nodes have reasonable source locations copied from the
  suite owner or nearest removed statement where practical,
- and no public marker behavior changes except that previously invalid
  marker-only suites now materialize to valid Python AST.

### Proposed Code Shape

Keep the logic close to materialize stripping, either inside
`src/astichi/materialize/api.py` or as a small AST utility if another caller
already needs it.

Suggested helper:

```python
def ensure_nonempty_python_suites(tree: ast.AST) -> ast.AST:
    ...
```

The helper should know Python AST body fields explicitly. Avoid a generic
"every list named body" rule unless the current AST node set is audited, because
`orelse`, `finalbody`, and exception handler bodies have distinct placement and
location expectations.

### Suites To Handle

At minimum:

- `ast.FunctionDef` and `ast.AsyncFunctionDef`,
- `ast.ClassDef`,
- `ast.If`,
- `ast.For` and `ast.AsyncFor`,
- `ast.While`,
- `ast.With` and `ast.AsyncWith`,
- `ast.Try` and `ast.TryStar` on Python versions that expose `ast.TryStar`,
- `ast.ExceptHandler`,
- `ast.Match` and `ast.match_case` on Python versions that expose them.

For `ast.Try` and `ast.TryStar`, preserve Python validity: `body`, handler
bodies, `orelse`, and `finalbody` should be handled according to whether the
field exists and becomes empty after stripping.

### Implementation Steps

1. Add focused tests that currently removable markers can leave marker-only
   suites and the final AST remains compilable.
2. Add the suite-preservation helper and invoke it after residual marker
   stripping.
3. Use `ast.copy_location(...)` and `ast.fix_missing_locations(...)` in the same
   style as the surrounding materialize code.
4. Confirm module-level all-marker bodies can still materialize to an empty
   module body where current behavior allows that.

### Coverage

- Add focused materialize tests for marker-only function, class, and conditional
  suites using existing markers.
- Run `tests/test_materialize.py` and `tests/test_ast_goldens.py`.
- Run `python -m compileall` only if the repository already uses such a check;
  otherwise compile the resulting AST in the focused tests.

### Acceptance Criteria

- Existing marker-only non-module suites materialize to compilable AST.
- Module bodies are not forced to contain `pass`.
- The pass-insertion step must not re-introduce or fail to strip any Astichi
  marker statement.

### Non-Goals

- Do not change which markers are stripped.
- Do not add new marker placement permissions.
- Do not alter emit formatting beyond the necessary `pass` statement when a
  suite would otherwise be invalid.

## 6. Reusable Dotted-Reference Path Helpers

### Problem

`src/astichi/lowering/external_ref.py` has internals for extracting and lowering
`astichi_ref(...)` paths. Future callers need two smaller capabilities without
performing the full rewrite:

- validate or extract a direct dotted `ast.Name` / `ast.Attribute` chain,
- evaluate a restricted compile-time path expression using the same rules and
  diagnostics as existing external refs.

If those capabilities stay private to the full lowering function, later code
will either duplicate validation or accidentally change `astichi_ref(...)`
behavior.

### Target Invariant

The external-ref lowering module exposes reusable internal helpers for path
evaluation and direct dotted-chain extraction, while current `astichi_ref(...)`
lowering behavior remains unchanged.

### Proposed Code Shape

Keep the helpers in `src/astichi/lowering/external_ref.py` unless import cycles
force a tiny adjacent module.

Suggested API:

```python
def evaluate_restricted_path_expression(node: ast.AST) -> tuple[str, ...]:
    ...


def extract_dotted_reference_chain(node: ast.AST) -> tuple[str, ...]:
    ...
```

The helpers should keep the same accepted shapes and error formatting that
existing `astichi_ref(...)` lowering uses.

If a current caller already hand-builds dotted AST chains, a
`build_dotted_reference_chain(...)` helper may be extracted as part of this
phase. Otherwise leave chain synthesis as a private external-ref detail; it is a
future-use affordance, not a prep requirement.

### Implementation Steps

1. Rename or wrap the current private helpers rather than rewriting them.
2. Preserve existing `_extract_ref_segments(...)` behavior by making it call the
   new helpers.
3. Add direct tests for accepted and rejected path expressions only if current
   external-ref tests do not cover them at helper granularity.
4. Extract a chain builder only if one current caller is migrated to it in the
   same phase.
5. Do not add new valid path expression shapes during this phase.

### Coverage

- Run `tests/test_external_ref.py`, `tests/test_external_bind.py`, and
  `tests/test_staged_build_refs_and_bindings.py`.
- Include rejection coverage for invalid dotted segments if current tests do not
  already pin the diagnostic.

### Acceptance Criteria

- Existing external-ref tests pass unchanged.
- New helper names make it possible to validate/evaluate paths without lowering
  the AST expression.
- Existing diagnostics for invalid paths are unchanged.

### Non-Goals

- Do not add pyimport module-path support.
- Do not widen accepted `astichi_ref(...)` syntax.
- Do not add sentinel-postfix semantics beyond the existing lowering order.

## 7. Diagnostics Formatting Alignment

### Problem

Astichi already has a diagnostics formatting path in
`src/astichi/diagnostics/formatting.py`, and existing validators follow local
patterns around `format_astichi_error(...)`. Future validation should not add ad
hoc error string formatting. Before adding new validators, the relevant existing
helper pattern should be identified and, where current code is already drifting,
made explicit.

### Target Invariant

New validation code can reuse an obvious existing diagnostic formatting pattern
for compile/materialize errors without inventing a separate error style.

### Implementation Steps

1. Audit marker validators and lowering validators that currently raise
   `ValueError`, `TypeError`, or Astichi-specific errors.
2. Identify the canonical helper/import pattern for new validation code:
   `format_astichi_error(...)`, phase labels, construct/problem wording,
   optional source string, and hints. The expected shape is:

   ```python
   raise ValueError(
       format_astichi_error(
           "compile",
           "astichi_marker(...): problem description",
           source="short source spelling or location string",
           hint="short corrective hint",
       )
   )
   ```
3. If a tiny helper would prevent repeated boilerplate in existing validators,
   add it and migrate one current validation site.
4. Do not rewrite broad diagnostics as a cleanup project. This phase should
   establish the pattern future work follows, not reword the whole package.

### Coverage

- Run `tests/test_diagnostics_formatting.py`.
- Run focused tests for any migrated validator.
- If diagnostic text changes are intentional, update only the exact affected
  assertions.

### Acceptance Criteria

- The intended diagnostic path for future validation is clear in code.
- At least one current validation site demonstrates the pattern if a helper was
  added.
- There is no parallel ad hoc formatting helper for future work to copy.

### Non-Goals

- Do not rewrite all diagnostics.
- Do not add pyimport diagnostics.
- Do not change diagnostic phases or provenance policy.

## 8. Explicitly Deferred Refactors

These refactors are intentionally not prerequisites for managed Python import
support.

### Descriptor-Port Generalization

Do not generalize `MarkerSpec.supply_template(...)` to a multi-template API
before future import work unless a current non-import feature already needs it.
That change touches every marker spec and is not required for the first import
strategy if descriptor-visible managed imports remain deferred or are handled
through explicit export/pass semantics.

Guardrail:

- no preparatory phase should change `MarkerSpec.supply_template(...)` solely
  for future import support,
- no preparatory phase should migrate all marker specs to a list-returning
  supply API without an immediate current caller.

### Hygiene Result Object

Do not refactor `rename_scope_collisions(...)` to return a structured result
object before future import work. The intended first strategy for marker-owned
local-name sinks is to give hygiene real AST nodes to rename where practical,
not to broaden the hygiene return contract up front.

Guardrail:

- `rename_scope_collisions(...)` should remain behaviorally stable during these
  prep phases,
- any result-object refactor must be justified by a current bug or a current
  caller need, not by speculative future import support.

## Final Prep Gate

Before starting implementation of `astichi_pyimport`, confirm:

- at least one current caller uses the shared scope ownership helper,
- at least hygiene and path-resolution use the ordinary import binding helper,
- hygiene consumes the shared marker metadata-node helper,
- one current prefix consumer uses the top-of-scope prefix classifier,
- residual marker stripping preserves valid non-module Python suites,
- external-ref path helpers can be used without rewriting the AST expression,
- new validation work has a clear diagnostics formatting pattern,
- `MarkerSpec.supply_template(...)` and `rename_scope_collisions(...)` were not
  broadened solely for future import support.

The prep work is complete when these conditions hold and the focused tests for
the migrated areas pass. The full test suite should be run before the first
pyimport-specific production phase begins.
