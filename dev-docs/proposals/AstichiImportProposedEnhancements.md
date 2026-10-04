# Astichi Import Proposed Enhancements

This file tracks import-related surfaces that were discussed during pyimport
planning but are not current behavior. The archived design notes live under
`dev-docs/history/`; this file is the active enhancement list.

## Alias Dictionaries For From-Imports

Current behavior rejects `names={a: local_a}`.

Possible enhancement:

```python
astichi_pyimport(module=foo, names={a: local_a, b: local_b})
```

The implementation would need to parse dict keys as imported symbol names,
parse dict values as local binding names, feed the local aliases into hygiene,
and merge emitted imports by module, original symbol, and final local binding
identity.

## Automatic Descriptor Supplies

Current behavior requires explicit publication:

```python
astichi_pyimport(module=foo, names=(tool,))
astichi_export(tool)
```

Possible enhancement: pyimport locals could become descriptor-visible supplies
without an explicit `astichi_export(...)`.

This should not reuse `EXPORT_ORIGIN` silently. If added, use a distinct
pyimport supply origin and a deliberate multi-supply extraction path, so
descriptor behavior stays distinguishable from ordinary exports.

## Managed Imports Inside Unroll Bodies

Current behavior rejects `astichi_pyimport(...)` inside `astichi_for(...)`
bodies.

Possible enhancement: allow managed imports in unrolled bodies with a clear
rule for per-iteration local binding identity and rename behavior. The design
must decide whether imports are hoisted once, replicated then merged, or renamed
per iteration before synthesis.

## Function-Local Or Class-Local Managed Imports

Current behavior rejects pyimport markers nested inside real user-authored
function or class bodies. Pyimport is allowed only at the prefix of its Astichi
owner scope, including insert-shell owner scopes.

Possible enhancement: allow managed imports local to authored functions or
classes, with explicit placement and hoisting rules. This needs a separate
design because Python import placement inside function/class suites has
different execution and scoping behavior from module-head import synthesis.

## Managed Relative Imports

Current pyimport behavior rejects relative managed module references. Ordinary
Python import statements with `__astichi_arg__` suffixes may be relative.

Possible enhancement: add relative module support to `astichi_pyimport(...)`
with an explicit representation for import level, validation for package
context, and emission rules that preserve Python's `from .pkg import name`
semantics.

## Import Formatting And Grouping

Current behavior emits deterministic managed imports after the module docstring
and ordinary future imports, without stdlib / third-party / local grouping.

Possible enhancement: add formatter-configurable grouping, sorting, or spacing.
This should be kept separate from pyimport binding semantics.

## Diagnostics Polish

Current behavior uses the existing Astichi validation and materialize error
style.

Possible enhancement: add more specialized diagnostics for import-specific
unresolved identifiers, invalid dynamic module reductions, or merge conflicts
if users hit ambiguous failures in real code.
