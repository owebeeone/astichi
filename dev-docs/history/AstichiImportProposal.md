# Astichi Import Proposal

Status: proposal.

## 1. Problem

Astichi snippets need a source-visible way to declare ordinary Python imports
without leaving those imports at the original insertion site.

Today a snippet can write an ordinary Python import:

```python
from foo import a, b
print(a() + b())
```

but ordinary import statements do not express Astichi composition semantics:

- import declarations should be collected near the top of the materialized
  module
- same-module imports from independent snippets should be merged
- imported identifiers should be shared where the import originated, without
  requiring manual `astichi_import` / `astichi_pass` boilerplate for each symbol
- final local spellings should still participate in hygiene
- generated output should remain normal Python

The goal is an authored marker surface for imports. A snippet declares the
imports it needs, Astichi collects and emits them at the head of the generated
source, and the imported names are available in the Astichi scopes where those
declarations originated.

## 2. Design Constraints

- Authored marker syntax must be valid Python.
- Emitted source must use ordinary Python import statements.
- Import collection must not use provenance or hidden non-source state.
- Import declarations remain scoped to the Astichi scope that authored them.
- Imported local names participate in normal Astichi hygiene.
- Same resolved import module plus compatible imported symbols should merge.
- Ordinary user-authored Python imports may be ignored initially; users should
  prefer `astichi_pyimport` markers when they want Astichi-managed imports.

## 3. Marker Shape

Use one marker for both `from ... import ...` and plain `import ...` forms:

```python
astichi_pyimport(module=xxx, names=(a, b))
astichi_pyimport(module=numpy, as_=np)
```

The marker uses valid Python keyword names:

- `module=` for the imported module path
- `names=` for `from module import ...` symbols
- `as_=` for plain `import module as alias`

`module=` accepts an absolute Python reference path directly:

```python
astichi_pyimport(module=os)
astichi_pyimport(module=package.submodule, names=(thing,))
astichi_pyimport(module=package.submodule, as_=submodule)
```

For v1, plain unaliased imports accept only a single-segment module path such
as `module=os`. Dotted plain imports must use `as_=` because Python binds
`import package.submodule` as local name `package`, while
`import package.submodule as renamed` binds the alias to the submodule object.
Astichi cannot hygienically rename the unaliased root package binding with
ordinary import alias syntax without changing what the name denotes.

`astichi_ref(...)` is only needed when the module path is computed from a
compile-time binding or another supported reducible value:

```python
astichi_pyimport(module=astichi_ref(external=module_path), names=(thing,))
```

An externally bound module path may be a dotted string such as `"pkg.mod"`.
That string is reduced through the same dotted-path validator as direct
`module=pkg.mod` syntax.

## 4. Proposed Marker Surfaces

### 4.1 From-Import Marker

Authored source:

```python
astichi_pyimport(module=xxx, names=(a, b))
print(a() + b())
```

Materialized source:

```python
from xxx import a, b

print(a() + b())
```

Rules:

- `module=` is required.
- `module=` must be an absolute module reference path such as `foo` or
  `foo.bar`, or an `astichi_ref(...)` form that reduces to such a path.
- `names=` is a non-empty tuple of bare identifiers.
- Duplicate names inside one marker reject.
- The marker is statement-only and emits no runtime statement at its original
  location.
- The imported local identifiers are visible in the same Astichi scope as the
  marker occurrence.
- The imported local identifiers are readable local bindings in that scope.
- Uses of those names in the same originating Astichi scope bind to the import
  binding unless an explicit stronger binding rule applies.

### 4.2 From-Import Alias Marker

Alias support is desirable later, but it is rejected in v1.

Candidate authored source:

```python
astichi_pyimport(module=foo, names={a: a2, b: b2})
print(a2() + b2())
```

Materialized source:

```python
from foo import a as a2, b as b2

print(a2() + b2())
```

Rules:

- Dict keys are imported names.
- Dict values are local names.
- Keys and values must be bare identifiers.
- `names={a: a, b: b}` is equivalent to `names=(a, b)`.
- The local alias name is the hygiene-managed binding in the originating
  Astichi scope.

This should be documented as a later goal. Do not add a v1 success path for it.

### 4.3 Plain Import Marker

Astichi also needs a form for:

```python
import numpy as np
```

Recommended authored source:

```python
astichi_pyimport(module=numpy, as_=np)
print(np.array([1, 2, 3]))
```

Materialized source:

```python
import numpy as np

print(np.array([1, 2, 3]))
```

Rules:

- `module=` is required.
- `as_=` is optional.
- If `as_=` is present, it must be a bare identifier and becomes the local
  hygiene-managed binding.
- If `as_=` is absent, the local binding is the first segment of the module
  path, matching Python import semantics.
- If `as_=` is absent in v1, `module=` must be a single-segment module path.
  Dotted plain imports without `as_=` reject.
- This form cannot be combined with `names=`.

Examples:

```python
astichi_pyimport(module=os)
astichi_pyimport(module=numpy, as_=np)
astichi_pyimport(module=package.submodule, as_=submodule)
```

Materializes as:

```python
import os
import numpy as np
import package.submodule as submodule
```

## 5. Deferred: `__astichi_arg__` Inside Ordinary Imports

After the base pyimport marker is stable, Astichi may recognize
`__astichi_arg__` suffix identifiers inside ordinary Python import statements.

Authored source:

```python
def x():
    from package__astichi_arg__ import thing__astichi_arg__
    thing__astichi_arg__(1, 2, 3)
```

Intended behavior:

- `package__astichi_arg__` creates a module-path demand.
- `thing__astichi_arg__` in the import alias creates an imported-symbol demand.
- matching uses of `thing__astichi_arg__` in the same Astichi scope are part of
  the same demand and are stripped/resolved together.
- after resolution, the import statement is normal Python and the local imported
  name participates in hygiene.

Example after resolving:

```python
def x():
    from resolved.package import resolved_thing
    resolved_thing(1, 2, 3)
```

Open point: a module path is not the same shape as an identifier. If the module
demand can resolve to dotted paths such as `resolved.package`, it should use a
dedicated module-path demand kind rather than overloading ordinary identifier
demands too far.

## 6. Import Collection And Merging

Astichi-managed imports are collected during materialization and emitted before
the non-import generated body.

Two from-import markers with the same resolved module path merge:

```python
astichi_pyimport(module=foo, names=(a, b))
astichi_pyimport(module=foo, names=(b, c))
```

Materialized source:

```python
from foo import a, b, c
```

Merge rules:

- The merge key for from-imports is the resolved absolute module path.
- Imported symbols are merged by original imported name plus final local
  binding name.
- Duplicate identical imports collapse.
- Conflicting aliases for the same original imported symbol are allowed only if
  they produce distinct local bindings and hygiene can represent them.
- Emitted ordering should follow normal Python import style:
  - managed imports are emitted as a coherent module-head import block
  - module docstrings and ordinary future imports keep their required leading
    positions
  - v1 uses deterministic lexicographic ordering by resolved module path
  - plain `import ...` declarations appear before `from ... import ...`
    declarations inside the managed block
  - imported symbols within one `from ... import ...` declaration are ordered
    deterministically by original imported name, with aliases preserved
  - stdlib / third-party / local grouping may be added later if Astichi gains
    package classification or formatting configuration

Plain imports use a separate merge family:

```python
astichi_pyimport(module=numpy, as_=np)
astichi_pyimport(module=numpy, as_=np)
```

Materialized source:

```python
import numpy as np
```

Plain import declarations should not merge with from-import declarations even
when they mention the same module.

If two sibling scopes import the same symbol and hygiene keeps distinct local
bindings, one emitted `from` statement may contain both entries:

```python
from foo import a, a as a__astichi_scoped_1
```

For plain imports with divergent final aliases, v1 should prefer separate
statements for clarity:

```python
import numpy as np
import numpy as np__astichi_scoped_1
```

## 7. Scope And Hygiene Semantics

Each `astichi_pyimport` marker creates imported local bindings in the Astichi
scope that contains the marker. Those imported names are automatically shared
within that originating Astichi scope.

For example:

```python
astichi_pyimport(module=foo, names=(a, b))
print(a() + b())
```

The names `a` and `b` bind to the imported locals in that snippet's Astichi
scope. Another inserted snippet that imports `b` and `c` from the same module
gets its own local imported bindings for `b` and `c`, but materialization may
merge the physical import declaration:

```python
from foo import a, b, c
```

The physical import declaration is shared; the Astichi name bindings remain
attached only to the scopes that declared the corresponding symbols.

If imported local names collide with other bindings after composition, hygiene
renames the local import binding using Python import alias syntax:

```python
from foo import a as a__astichi_scoped_1
```

and all uses belonging to that Astichi import binding are rewritten to:

```python
a__astichi_scoped_1(...)
```

Important distinction:

- original imported name: `a`
- local hygiene-managed binding: `a` or `a__astichi_scoped_1`
- module key used for merge: resolved module path, e.g. `foo`

The merge must preserve this distinction so hygiene can rename local bindings
without changing the imported symbol being requested from the module.

### 7.1 Binding Identity

`astichi_pyimport` is a binding declaration, not an alias-through boundary
demand.

That distinction matters:

- `astichi_import(name)` says "this fresh Astichi scope uses a binding supplied
  by an enclosing Astichi scope."
- `astichi_pyimport(module=foo, names=(a,))` says "this Astichi scope owns a
  binding whose value is supplied by Python import `from foo import a`."

Therefore pyimport local names should be modeled as local binding occurrences
owned by the marker's Astichi scope. They should not be added to the
`astichi_import` alias-through set and should not resolve to an ancestor scope
just because an ancestor also imports the same spelling.

If two sibling inserted snippets both declare:

```python
astichi_pyimport(module=foo, names=(a,))
```

then they create two Astichi binding identities. The final physical import may
still collapse to one Python import declaration:

```python
from foo import a
```

but the hygiene binding identity remains per-originating Astichi scope. If no
collision forces a rename, both scopes may emit the same local spelling `a` and
share the same physical import line. If a collision does force separation, one
scope can emit:

```python
from foo import a as a__astichi_scoped_1
```

and only that scope's uses are rewritten to `a__astichi_scoped_1`.

### 7.2 Occurrence Model

Each managed import symbol contributes a synthetic lexical occurrence at the
marker location.

For `from` imports:

```python
astichi_pyimport(module=foo, names=(a, b))
```

Astichi records:

- module path: `foo`
- imported symbol `a`, local binding raw name `a`
- imported symbol `b`, local binding raw name `b`
- owner Astichi scope: the scope containing the marker

For unaliased plain imports:

```python
astichi_pyimport(module=os)
```

Astichi records:

- module path: `os`
- import kind: plain import
- local binding raw name `os`, matching Python's normal unaliased import
  binding rule
- owner Astichi scope: the scope containing the marker

For alias imports:

```python
astichi_pyimport(module=numpy, as_=np)
```

Astichi records:

- module path: `numpy`
- import kind: plain import
- local binding raw name `np`
- owner Astichi scope: the scope containing the marker

The synthetic occurrence participates in the same collision domain as the
marker's surrounding Python/Astichi location. It should be classified as a
binding occurrence with ordinary internal lexical role unless a future surface
explicitly says the imported name is preserved/trusted.

### 7.3 Same-Scope Use Binding

After a pyimport marker declares local names, ordinary `Load` occurrences of
those names in the same Astichi scope bind to the synthetic import binding.

This must happen before final hygiene renaming. Conceptually, the marker is
equivalent to an import statement at the authored location for lexical binding
purposes:

```python
astichi_pyimport(module=foo, names=(a,))
result = a()
```

has the same local binding relation as:

```python
from foo import a
result = a()
```

except the physical import statement is later hoisted and merged.

### 7.4 Cross-Scope Sharing

Pyimport names are automatically shared only within the Astichi scope that
declared them. They are not automatically visible across Astichi insertion
boundaries.

If an inserted child snippet needs to use an imported name from an enclosing
snippet, it should still use the normal explicit boundary mechanisms such as
`astichi_import`, `astichi_pass`, or builder identifier binding. The pyimport
binding can serve as the outer readable binding, but the boundary crossing remains
explicit.

Example:

```python
astichi_pyimport(module=foo, names=(a,))
astichi_hole(body)
```

and inserted child:

```python
astichi_import(a, outer_bind=True)
value = a()
```

The child import aliases through to the parent Astichi scope's pyimport binding.
Final hygiene still owns the spelling.

### 7.5 Collision And Emission Feedback

Hygiene needs to communicate final local names back to import emission. Import
emission cannot be a simple pre-hygiene collection pass because it must know
whether a local import binding was renamed.

The materialization pipeline should therefore preserve a pyimport binding record
containing at least:

- owner Astichi scope identity or equivalent binding identity
- resolved module path
- import kind: plain or from-import
- original imported symbol for from-imports
- original local raw name
- final hygiene local name
- source occurrence order for diagnostics and stable tie-breaking

After hygiene, the import collector uses these records to synthesize Python AST
import declarations:

- if final local name equals original imported/local name, emit a normal alias
- if final local name differs, emit `as <final local name>`

For example:

```python
from foo import a as a__astichi_scoped_1
```

The AST `alias.name` remains `a`; only `alias.asname` receives the hygiene
rename.

### 7.6 Marker Removal

`astichi_pyimport` marker statements are removed only after their binding
records have been created and made available to hygiene/import emission.

For block-shaped snippets, the marker statement can remain in pre-materialized
Astichi source and be consumed during materialize. For expression-shaped
snippets, marker records must be carried by internal source-visible insert
metadata so the recompiled pre-materialized source recreates the same binding
records.

### 7.7 Marker Interaction Matrix

V1 interaction rules:

- `astichi_keep(a)` plus `astichi_pyimport(..., names=(a,))` in the same scope:
  keep wins. The pyimport local spelling is pinned as `a`; colliding non-kept
  bindings rename away.
- `a__astichi_keep__` in the same scope pins the final spelling after suffix
  stripping, and may refer to the pyimport local binding.
- `a__astichi_arg__` is not automatically satisfied by a same-scope pyimport.
  It remains an explicit identifier demand; use bare `a` to reference the
  imported local in the same scope.
- `astichi_import(a, outer_bind=True)` in a child Astichi scope may bind through
  to an enclosing pyimport local because the pyimport creates a readable
  enclosing binding.
- `astichi_pass(a)` in a child Astichi scope may likewise read the enclosing
  pyimport binding when explicitly wired.
- `astichi_export(a)` in the same scope explicitly exports the pyimport local
  through the existing export supply mechanism. Pyimport alone does not create
  descriptor-visible identifier supplies in v1.

## 8. Placement

Astichi-managed import declarations are emitted at the beginning of the
materialized module body.

Initial version:

- authored `astichi_pyimport(...)` markers are valid only in the contiguous
  top-of-Astichi-scope statement prefix
- that prefix may interleave direct statement-form `astichi_pyimport(...)`,
  `astichi_bind_external(...)`, `astichi_import(...)`, `astichi_keep(...)`,
  and `astichi_export(...)` directives; the first non-prefix statement closes
  the prefix
- a pyimport is valid at the prefix of its Astichi owner scope, including an
  Astichi insert-shell scope whose root is a function/class shell
- a pyimport nested inside a real user-authored function/class body within that
  owner scope rejects in v1
- managed imports are inserted after a module docstring and after ordinary
  `from __future__ import ...` statements
- managed `__future__` imports reject in v1
- if stripping pyimport marker statements empties a Python suite, materialize
  inserts `pass`; module bodies may remain empty

Future placement policy may need to account for:

- comments and provenance
- imports inside generated functions or classes, which are not supported for v1

For the initial goal, Astichi-managed imports should be treated as module-level
generated imports for final emitted source.

## 9. Expression Snippets And Round Trip

Expression-prefix pyimport support is deferred until the block-scope marker,
hygiene, and import-synthesis path is stable. The intended later surface is a
prefix declaration before an expression snippet:

```python
astichi_pyimport(module=foo, names=(a,))
astichi_pyimport(module=bar, names=(b,))
a() + b()
```

This is an expression-shaped contribution whose executable expression is
`a() + b()`, plus import declarations that must remain attached to the snippet
through build, emit, recompile, and materialize.

Block snippets can preserve the marker statements directly in pre-materialized
source. Expression snippets need a carrier because the inserted expression is
normally wrapped in internal `astichi_insert(...)` metadata. A likely emitted
shape is an additional internal insert keyword, for example:

```python
astichi_insert(target, expr, pyimport=(astichi_pyimport(...), astichi_pyimport(...)))
```

The exact internal spelling is an implementation detail. When this later phase
is implemented, the carrier must be accepted only in
`source_kind="astichi-emitted"` and must not survive final materialized output.

## 10. Ordinary User Imports

Initial recommendation: do not try to infer special Astichi sharing semantics
from ordinary authored `import` and `from ... import ...` statements.

Ordinary imports remain ordinary Python statements in v1. Import-position
`__astichi_arg__` suffixes are deferred until a later phase. Users who want
import collection, deduplication, merging, and hygiene-aware sharing should use
`astichi_pyimport`.

Documentation should discourage ordinary imports in authored Astichi snippets
for generated modules. Ordinary imports are still valid Python, but they stay
where they are authored and do not participate in managed import collection,
merge, module-head placement, or pyimport hygiene semantics. Use
`astichi_pyimport(...)` for imports that are part of the generated-file import
surface.

This keeps the first implementation narrow:

- `astichi_pyimport` means Astichi-managed import
- ordinary import means ordinary Python import
- ordinary import with `__astichi_arg__` remains deferred until the dedicated
  import-position suffix phase

## 11. Requirements

1. Encode import declarations with authored marker syntax, not by requiring
   snippets to place final import statements directly.
2. Materialization emits Astichi-managed import declarations at the beginning of
   generated source.
3. Same resolved module from-imports are collected into one import scope and
   one emitted `from ... import ...` declaration where possible.
4. Imported symbols are automatically shared within the Astichi scope where the
   marker originated.
5. `from foo import a as a2, b as b2` support may be allowed through
   `names={a: a2, b: b2}` later, but alias dicts are rejected in v1.
6. Plain imports such as `import numpy as np` should be represented with
   `astichi_pyimport(module=numpy, as_=np)`.
7. If an imported local name needs a hygiene rename, emit that rename through
   Python import alias syntax such as `from foo import a as a__astichi_scoped_1`.
8. Ordinary user imports do not need collection or Astichi import-scope sharing
   in the initial version; documentation should discourage them in favor of
   `astichi_pyimport` for managed generated-file imports.
9. Wildcard imports are rejected in v1.
10. Relative imports are rejected in v1.
11. Function-local/class-local Astichi-managed import placement is not
    supported in v1; managed imports emit at module head.
12. Dotted plain imports without `as_=` are rejected in v1.
13. Managed `__future__` imports are rejected in v1.
14. `astichi_pyimport(...)` inside `astichi_for(...)` bodies is rejected in v1.
15. Expression snippets carrying `astichi_pyimport` prefix declarations are
    deferred until after block-scope pyimport behavior is stable.
16. Invalid `names=` payload shapes are rejected in v1. `names=` must be a
    non-empty tuple of bare identifiers.
17. Duplicate names inside one `names=` tuple are rejected in v1.
18. Mixed `names=` and `as_=` are rejected in v1.
19. Expression-insert pyimport carrier metadata is rejected in authored source
    and is not part of V1 authored behavior.
20. Pyimport diagnostics should use the existing Astichi diagnostic/error
    formatting style.
21. Emitted managed imports follow normal Python import style: module-head
    import block, deterministic ordering, plain imports before from-imports,
    and deterministically ordered imported symbols.

## 12. Resolved Direction

- Use one marker: `astichi_pyimport(...)`.
- Accept direct absolute module references: `module=foo.bar`.
- Use `astichi_ref(...)` only for externally bound or otherwise reducible
  dynamic module paths.
- Accept externally bound dotted strings such as `"pkg.mod"` as dynamic module
  path values.
- Reject dotted plain imports without `as_=` in v1.
- Reject expression-snippet pyimport carriers in v1.
- Treat pyimport declarations as scoped synthetic import bindings at their
  authored marker location before the main hygiene decision is finalized.
- Materialize removes marker statements from their original position only after
  extracting the import metadata needed to synthesize module-head imports.
- Preserve pyimport marker data in pre-materialized source for block-shaped
  snippets in v1; expression-shaped carriers are a later phase.
- Emit managed imports in deterministic Python-style order rather than marker
  occurrence order.
- Do not support function-local/class-local managed import placement in v1.
- Reject wildcard imports in v1.
- Reject relative imports in v1.
- Dedicated unresolved-import diagnostics are optional. A normal unresolved
  identifier diagnostic is acceptable for v1 if that is easier.

## 13. Initial Implementation Shape

Suggested first implementation:

1. Add marker recognition for statement-form `astichi_pyimport(...)`.
2. Validate exactly one of:
   - `module=<absolute-ref>, names=(...)`
   - `module=<absolute-ref>, as_=<identifier>`
   - `module=<single-segment-ref>` for plain unaliased imports
3. Accept `astichi_ref(external=...)` as the dynamic-module variant of
   `<absolute-ref>`.
4. Reject wildcard imports and relative imports.
5. Represent import declarations as scoped synthetic import bindings before
   hygiene.
6. Let hygiene choose final local names.
7. Emit collected imports at module head using alias syntax when hygiene renamed
   a local import binding.
8. Merge compatible from-import declarations by resolved module path and final
   local binding identity.
9. Add expression-insert carriers only after the block-scope path is stable.
10. Add `__astichi_arg__` recognition in `ast.ImportFrom` module and alias-name
   positions after the base marker is working.
