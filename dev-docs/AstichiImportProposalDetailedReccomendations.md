# Astichi Import Proposal Detailed Reccomendations

Status: concise recommendations for the pre-implementation import proposal.

Input docs:

- `dev-docs/AstichiImportProposal.md`
- `dev-docs/AstichiImportProposalPlan.md`
- `dev-docs/AstichiImportProposalDetailedCodingPlan.md`
- `dev-docs/AstichiSingleSourceSummary.md`

## Bottom Line

The detailed coding plan has the right core instinct: do not create a parallel
import subsystem. `astichi_pyimport(...)` should extend the existing marker,
scope, hygiene, materialize, and golden-test paths.

The recommended adjustment is to ship a narrower, identity-driven V1 and defer
the widest surfaces until the base import model is proven.

Recommended V1 surface:

- `astichi_pyimport(module=foo, names=(a, b))`
- `astichi_pyimport(module=package.submodule, names=(thing,))`
- `astichi_pyimport(module=astichi_ref(...), names=(thing,))`
- `astichi_pyimport(module=numpy, as_=np)`
- `astichi_pyimport(module=os)` for a single-segment module path only

Defer:

- authored from-import alias dicts, such as `names={a: a2}`
- ordinary import-statement rewriting or hoisting
- `__astichi_arg__` inside ordinary import string fields
- descriptor-visible pyimport supplies
- expression-snippet pyimport prefix carriers
- pyimport inside `astichi_for(...)` bodies
- managed `__future__` imports

## Recommendations

### 1. Add A Marker-Owned Name Concept

Pyimport's identifier-looking payload is marker metadata, not ordinary runtime
loads:

- `module=foo`
- `module=package.submodule`
- `names=(a, b)`
- `as_=np`

Current name-ignore behavior mostly assumes one name-bearing positional
argument. That is insufficient here. Add one canonical marker-owned-name
extraction path and use it from name analysis, scope identity, and pyimport
parsing. Avoid scattered pyimport-specific ignore cases in individual passes.

### 2. Use Local Name Nodes As Hygiene Sinks

For V1, the marker usually contains a real AST `Name` node for the local import
binding:

- `names=(a, b)` gives local binding nodes `a` and `b`
- `as_=np` gives local binding node `np`
- `module=os` gives local binding node `os`

Use those marker-owned nodes as the final-name sink. Add synthetic binding
occurrences for them before `rename_scope_collisions(...)`, let hygiene mutate
them, then read the final local spelling from the same nodes when synthesizing
ordinary imports.

This avoids raw string search after hygiene and may avoid requiring a broad
`ScopeRenameResult` refactor before pyimport. A rename result can still be a
later cleanup.

### 3. Reject Dotted Plain Imports Without `as_=`

`import package.submodule` binds the local name `package`. If hygiene renames
that binding, `import package.submodule as package__astichi_scoped_1` does not
preserve the same semantics because the alias is bound to the submodule, not
to the root package binding authored code used.

V1 should reject:

```python
astichi_pyimport(module=package.submodule)
```

Require:

```python
astichi_pyimport(module=package.submodule, as_=submodule)
```

From-import with dotted modules remains valid.

### 4. Merge Imports Without Merging Binding Identity

Pyimport creates a local binding in the marker's Astichi scope. It is not an
`astichi_import(...)` alias-through demand.

Physical import declarations may merge, but binding identity must remain
per-originating Astichi scope. If two sibling scopes import the same symbol and
hygiene renames one local binding, final output may need both aliases:

```python
from foo import a, a as a__astichi_scoped_1
```

Merge exact duplicate emitted entries. Do not merge solely by
`(module, imported_symbol)` when final local names differ.

### 5. Build A Real Shared Scope Helper

Promote the `_NodeScopeMap` idea, but do not lift the boundary-local
implementation unchanged. The shared helper must model the same Astichi scope
boundaries as hygiene/materialize, including insert-shell bodies, expression
insert payloads, decorators, function arguments, defaults, returns, and class
bases.

Use it first for pyimport ownership and one existing helper. Migrate more
callers only after tests prove equivalence.

### 6. Centralize Python Import Binding Rules

Ordinary import binding rules appear in multiple collectors today. Extract one
helper before adding pyimport:

- `import a.b` -> `a`
- `import a.b as x` -> `x`
- `from a import b` -> `b`
- `from a import b as x` -> `x`

Then pyimport can share the same local-binding mechanics where it intentionally
matches Python import behavior.

### 7. Keep Import Synthesis In Materialize

`emit_source(...)` should stay a renderer. Materialize should produce the final
Python AST with ordinary import nodes already inserted.

Insert managed imports after the module docstring and after ordinary
`from __future__ import ...` statements. Reject managed `__future__` imports
in V1; their placement rules are not worth adding to the managed-import
surface.

### 8. Keep Descriptor Supplies Out Of The Critical Path

Descriptor-visible pyimport supplies are the broadest proposed surface. They
likely require either multi-port marker templates or a separate pyimport port
extraction path.

Recommendation: do not include them in the first implementation. First prove
authored-local use, hygiene, merging, materialization, and round trip. If
descriptor visibility is later required, add a distinct behavior-bearing
pyimport supply origin. Do not reuse `EXPORT_ORIGIN`.

### 9. Lock Existing Marker Interactions

V1 should explicitly document:

- `astichi_keep(a)` pins a same-scope pyimport local `a`.
- `a__astichi_keep__` may refer to and pin a same-scope pyimport local.
- `a__astichi_arg__` is not automatically satisfied by same-scope pyimport;
  use bare `a` for the imported local.
- child `astichi_import(a, outer_bind=True)` and `astichi_pass(a)` can bind to
  an enclosing pyimport local when explicitly wired.
- `astichi_export(a)` explicitly publishes a pyimport local through existing
  export semantics; pyimport alone is not descriptor-visible in V1.

### 10. Reject Pyimport In Unroll Bodies For V1

Do not permit `astichi_pyimport(...)` inside `astichi_for(...)` bodies in V1.
The interaction between marker-owned local-name sink nodes and per-iteration
renaming needs its own design.

### 11. Keep `astichi_ref(...)` As Value-Form Module Metadata

`module=astichi_ref(...)` should be allowed as a pyimport module-path value,
including externally bound strings such as `"pkg.mod"`. This is not a new
standalone marker context. Invalid reduced dotted paths should reuse the
existing path validation diagnostics.

## Existing-Code Fixes Before Pyimport

Complete these preparatory fixes in the existing codebase before adding the
`astichi_pyimport` marker or any pyimport-specific production behavior. These
steps should be behavior-preserving for current public features.

The detailed phase plan is in `dev-docs/AstichiImportRefactorPrep.md`.

1. Promote one shared Astichi scope ownership helper.
   - Start from the existing `_NodeScopeMap` idea, but make the helper cover
     the scope boundaries already used by hygiene/materialize: insert-shell
     bodies, expression insert payloads, decorators, function arguments,
     defaults, returns, and class bases.
   - Migrate at least one existing caller, such as a fresh-scope import/trust
     collector, so current tests exercise the helper before pyimport depends
     on it.

2. Centralize ordinary Python import binding-name extraction.
   - Provide one helper for existing `ast.Import` / `ast.ImportFrom` binding
     names.
   - Replace duplicated logic in the current hygiene and path-resolution
     collectors where the change is small and behavior-preserving.

3. Generalize marker-owned metadata node handling.
   - Current ignored-name handling mostly assumes one name-bearing positional
     argument.
   - Add or refactor a generic way for marker specs/lowering helpers to report
     AST nodes that are marker metadata rather than ordinary runtime loads.
   - Migrate existing markers through that path where practical without
     changing their public behavior.

4. Extract a reusable top-of-scope prefix classifier.
   - Existing boundary-prefix behavior should not be copied into another
     feature-specific validator.
   - The helper should classify direct statement-form prefix directives and
     expose the "first non-prefix statement closes the prefix" rule.
   - Keep existing `astichi_import` / `astichi_keep` / `astichi_export` behavior
     unchanged while making the prefix family explicit.

5. Make residual marker stripping preserve valid Python suites.
   - If an existing marker-strip path can remove every statement from a
     function, class, `if`, loop, or other Python suite, it should leave an
     `ast.Pass`.
   - Module bodies may remain empty.
   - Add focused coverage for existing marker-only suites before pyimport adds
     another removable statement marker.

6. Expose reusable dotted-reference path helpers.
   - Split existing external-ref internals enough that callers can validate a
     dotted `ast.Name` / `ast.Attribute` chain and evaluate a restricted
     compile-time path expression without directly rewriting the expression.
   - Keep existing `astichi_ref(...)` behavior and diagnostics unchanged.

7. Keep diagnostics on the existing formatting path.
   - Before adding pyimport diagnostics, identify the local helper pattern from
     `src/astichi/diagnostics/formatting.py` and the surrounding marker
     validators.
   - New validation should reuse that style instead of adding ad hoc error
     strings.

8. Do not make descriptor-port or hygiene-result refactors prerequisites.
   - Do not generalize `MarkerSpec.supply_template(...)` before pyimport unless
     a non-pyimport feature already needs it.
   - Do not refactor `rename_scope_collisions(...)` to return a result object
     before pyimport; marker-owned sink nodes are the intended first strategy.

## Suggested Phase Order

1. Preparation:
   Add shared import binding-name helper, marker-owned-name extraction, and a
   scoped ownership helper. Migrate at least one existing caller so existing
   tests exercise the helper before pyimport depends on it.

2. Block-scope core:
   Add marker recognition, declaration parsing, prefix placement validation,
   module-path validation, and rejection tests.

3. Hygiene and synthesis:
   Add synthetic pyimport binding occurrences, read final names from
   marker-owned nodes, strip marker statements, and synthesize deterministic
   module-head imports.

4. Goldens:
   Cover success paths with canonical goldens. Keep bespoke tests focused on
   validation, dotted plain-import rejection, merge identity, and diagnostics.
   Include a case where the imported name is unused except for the marker, so
   the marker-owned binding node is proven to participate in hygiene.

5. Optional surfaces:
   Add expression-prefix carriers, descriptor-visible supplies, authored import
   aliases, and import-position `__astichi_arg__` only after the block path is
   stable.

## Locked Decisions

1. Descriptor visibility:
   Defer automatic descriptor visibility. Require explicit `astichi_export(...)`
   for V1 cross-scope public supplies.

2. Expression snippets:
   Phase after block-scope pyimport. Do not include expression prefix support
   in the first shipped import checkpoint.

3. Dotted plain import without alias:
   Reject in V1.

4. Managed `__future__` imports:
   Reject in V1.

5. Hygiene final-name strategy:
   Use marker-owned AST local-name sink nodes in V1. Do not require a
   `ScopeRenameResult` refactor before implementation.
