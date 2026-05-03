# Marker: `astichi_pyimport`

`astichi_pyimport(...)` declares a managed Python import for generated code.
Astichi treats the imported local name as a real local binding during hygiene,
then removes the marker and emits an ordinary Python `import` or `from ... import
...` statement during `materialize()`.

Use this marker when a snippet needs a module dependency and the final import
should be synthesized with the same name-collision rules as other Astichi
bindings.

## Surface

From-import form:

```python
astichi_pyimport(module=foo, names=(a, b))
value = a()
```

Materializes as:

```python
from foo import a, b
value = a()
```

Plain import forms:

```python
astichi_pyimport(module=numpy, as_=np)
astichi_pyimport(module=os)
value = (np.array([1]), os.getcwd())
```

Materializes as:

```python
import numpy as np
import os
value = (np.array([1]), os.getcwd())
```

The marker accepts keyword arguments only:

- `module=` is required and must be an absolute dotted module reference or an
  `astichi_ref(...)` module-path expression.
- `names=(...)` creates `from module import name` bindings. Elements must be
  bare identifiers.
- `as_=alias` creates `import module as alias` for plain imports. The alias
  must be a bare identifier.

`names=` and `as_=` are mutually exclusive.

## Module Paths

Static module paths use normal Python `Name` / `Attribute` syntax:

```python
astichi_pyimport(module=package.submodule, names=(thing,))
```

Dynamic module paths can come from an externally bound string:

```python
astichi_bind_external(module_path)
astichi_pyimport(module=astichi_ref(external=module_path), names=(thing,))
value = thing()
```

After binding `module_path="pkg.mod"`, materialization emits:

```python
from pkg.mod import thing
value = thing()
```

The bound string must reduce to a non-empty dotted path whose segments are valid
Python identifiers. `astichi_pyimport` does not add special
`.astichi_v` / `._` sentinel semantics; it consumes the absolute
`Name` / `Attribute` chain left by existing `astichi_ref(...)` lowering.

## Placement

`astichi_pyimport(...)` is a statement marker. It must appear in the contiguous
top-of-Astichi-scope prefix. At module scope, a module docstring and ordinary
`from __future__ import ...` statements may appear before that prefix.

The prefix can interleave direct statement-form prefix markers:

```python
astichi_bind_external(module_path)
astichi_pyimport(module=astichi_ref(external=module_path), names=(thing,))
astichi_import(dep)
astichi_keep(result)
```

The first non-prefix statement closes the prefix. A later
`astichi_pyimport(...)` in the same Astichi scope is rejected.

An insert-shell owner scope may have a pyimport at the top of its body. A
pyimport nested inside a real user-authored function or class body is rejected
in V1.

`astichi_pyimport(...)` is not permitted inside an `astichi_for(...)` body.

## Hygiene

Imported locals are binding names for Astichi hygiene. If two composition
scopes would otherwise collide, the imported local can be renamed and the
emitted import receives an alias:

```python
a = 1
astichi_hole(slot)

@astichi_insert(slot)
def shell():
    astichi_pyimport(module=foo, names=(a,))
    value = a()
```

Materializes as:

```python
from foo import a as a__astichi_scoped_1
a = 1
value = a__astichi_scoped_1()
```

`astichi_keep(a)` pins the spelling `a`; competing non-kept bindings rename
away from it.

## Boundary Wiring

A pyimport local is a binding inside its Astichi owner scope. A child insert
shell can intentionally read that binding through ordinary boundary markers:

```python
astichi_pyimport(module=foo, names=(tool,))
astichi_hole(body)

@astichi_insert(body)
def child():
    astichi_import(tool, outer_bind=True)
    result = tool()
```

`astichi_pass(tool, outer_bind=True)` works the same way in expression position.

`__astichi_arg__` demands are not automatically satisfied by a same-scope
pyimport. Resolve those demands through `arg_names=`, `.bind_identifier(...)`,
builder wiring, or use the ordinary imported local name directly.

Descriptor-visible automatic supplies for pyimport locals are deferred. Export
an imported local explicitly when a staged composition needs a public supply.

## Emission

Final `materialize().emit(provenance=False)` contains ordinary Python imports
and no `astichi_pyimport(...)` calls.

Managed imports are inserted at module head after a module docstring and after
ordinary `from __future__ import ...` statements. Plain imports and from-imports
are sorted deterministically. Duplicate equivalent import entries are collapsed.

Pre-materialized `emit()` preserves marker-bearing source for round-trip back
through `compile(...)`.

## V1 Rejections

The following shapes are rejected:

- positional arguments
- missing `module=`
- unknown or duplicate keywords
- `names=` values other than a non-empty tuple
- `names=` elements that are not bare identifiers, including attributes,
  calls, subscripts, starred expressions, constants, and nested sequences
- duplicate entries inside one `names=` tuple
- alias dictionaries in `names=`
- combining `names=` with `as_=`
- `as_=` values that are not bare identifiers
- wildcard imports
- relative imports
- managed `__future__` imports
- dotted plain imports without `as_=`
- dynamic plain imports without `as_=`
- statement placement outside the top-of-Astichi-scope prefix
- expression-insert carrier forms
- pyimports inside `astichi_for(...)` bodies
- pyimports nested inside real user-authored function or class bodies

Ordinary Python import statements still work as normal Python source, but they
are not managed by Astichi and do not participate in pyimport synthesis.

Reference snippets:

- [pyimport/from_import](snippets/pyimport/from_import.py)
- [pyimport/dynamic_module_ref](snippets/pyimport/dynamic_module_ref.py)

## See also

- [marker-ref.md](marker-ref.md)
- [marker-binds-and-exports.md](marker-binds-and-exports.md)
- [scoping-hygiene.md](scoping-hygiene.md)
- [materialize-and-emit.md](materialize-and-emit.md)
