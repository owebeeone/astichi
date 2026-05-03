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
astichi_pyimport(module=package.submodule)
```

`astichi_ref(...)` is only needed when the module path is computed from a
compile-time binding or another supported reducible value:

```python
astichi_pyimport(module=astichi_ref(external=module_path), names=(thing,))
```

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
- `names=` is a tuple of bare identifiers.
- The marker is statement-only and emits no runtime statement at its original
  location.
- The imported local identifiers are visible in the same Astichi scope as the
  marker occurrence.
- The imported local identifiers are treated as Astichi supplies in that scope.
- Uses of those names in the same originating Astichi scope bind to the import
  supply unless an explicit stronger binding rule applies.

### 4.2 From-Import Alias Marker

Alias support is desirable if it is easy, but it is not required for the first
implementation.

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

This should be documented as a later goal unless the implementation naturally
falls out of the tuple form.

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

## 5. `__astichi_arg__` Inside Ordinary Imports

Astichi should also recognize `__astichi_arg__` suffix identifiers inside
ordinary Python import statements.

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
- Imported symbols are merged by original imported name plus requested local
  alias.
- Duplicate identical imports collapse.
- Conflicting aliases for the same original imported symbol are allowed only if
  they produce distinct local bindings and hygiene can represent them.
- Stable ordering should be deterministic:
  - first module occurrence order for import declaration order
  - first occurrence order for imported symbol order within one declaration

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

## 7. Scope And Hygiene Semantics

Each `astichi_pyimport` marker creates import supplies in the Astichi scope that
contains the marker. Those imported names are automatically shared within that
originating Astichi scope.

For example:

```python
astichi_pyimport(module=foo, names=(a, b))
print(a() + b())
```

The names `a` and `b` bind to the import supply in that snippet's Astichi
scope. Another inserted snippet that imports `b` and `c` from the same module
gets its own local imported supplies for `b` and `c`, but materialization may
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

## 8. Placement

Astichi-managed import declarations are emitted at the beginning of the
materialized module body.

Initial version:

- put imports before all generated non-import statements
- preserve any module docstring before collected imports if module-docstring
  preservation is already represented cleanly
- otherwise treat docstring-sensitive placement as a polish item

Future placement policy may need to account for:

- `from __future__ import ...`
- module docstrings
- comments and provenance
- imports inside generated functions or classes, which are not supported for v1

For the initial goal, Astichi-managed imports should be treated as module-level
generated imports for final emitted source.

## 9. Expression Snippets And Round Trip

`astichi_pyimport(...)` should work as a prefix declaration for expression
snippets:

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

The exact internal spelling is an implementation detail, but the requirement is
source round-trip fidelity: pre-materialized Astichi output must carry the
import marker data in source, not only in hidden builder/provenance state.

## 10. Ordinary User Imports

Initial recommendation: do not try to infer special Astichi sharing semantics
from ordinary authored `import` and `from ... import ...` statements.

Ordinary imports can remain ordinary Python statements unless the source uses
`__astichi_arg__` suffixes inside them. Users who want import collection,
deduplication, merging, and hygiene-aware sharing should use
`astichi_pyimport`.

This keeps the first implementation narrow:

- `astichi_pyimport` means Astichi-managed import
- ordinary import means ordinary Python import
- ordinary import with `__astichi_arg__` means explicit argumentized import
  surface

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
   `names={a: a2, b: b2}` if it is straightforward; it is not required for the
   initial version.
6. Plain imports such as `import numpy as np` should be represented with
   `astichi_pyimport(module=numpy, as_=np)`.
7. If an imported local name needs a hygiene rename, emit that rename through
   Python import alias syntax such as `from foo import a as a__astichi_scoped_1`.
8. Ordinary user imports do not need collection or Astichi import-scope sharing
   in the initial version; encourage `astichi_pyimport` for managed imports.
9. Wildcard imports are rejected in v1.
10. Relative imports are rejected in v1.
11. Function-local/class-local Astichi-managed import placement is not
    supported in v1; managed imports emit at module head.
12. Expression snippets may carry `astichi_pyimport` prefix declarations and
    must preserve them through pre-materialized source round trip.

## 12. Resolved Direction

- Use one marker: `astichi_pyimport(...)`.
- Accept direct absolute module references: `module=foo.bar`.
- Use `astichi_ref(...)` only for externally bound or otherwise reducible
  dynamic module paths.
- Treat pyimport declarations as scoped synthetic import bindings at their
  authored marker location before the main hygiene decision is finalized.
- Materialize removes marker statements from their original position only after
  extracting the import metadata needed to synthesize module-head imports.
- Preserve pyimport marker data in pre-materialized source for both block and
  expression-shaped inserts.
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
   - `module=<absolute-ref>` for plain unaliased imports
3. Accept `astichi_ref(...)` as the dynamic-module variant of
   `<absolute-ref>`.
4. Reject wildcard imports and relative imports.
5. Represent import declarations as scoped synthetic import bindings before
   hygiene.
6. Let hygiene choose final local names.
7. Emit collected imports at module head using alias syntax when hygiene renamed
   a local import binding.
8. Merge compatible from-import declarations by resolved module path.
9. Preserve pyimport metadata through internal expression-insert carriers.
10. Add `__astichi_arg__` recognition in `ast.ImportFrom` module and alias-name
   positions after the base marker is working.
