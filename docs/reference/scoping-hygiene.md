# Scoping and hygiene

Astichi composes Python snippets that may eventually materialize into the same
module body, function body, class body, call, or expression. Plain string-level
composition would push those snippets into one Python namespace and make
accidental name collisions easy:

```python
total = 0
total = 1
```

Astichi's hygiene model makes cross-snippet collisions impossible by default.
Ordinary locals from independent composition scopes are renamed apart when they
would otherwise collide. If two snippets are meant to share a variable, the
user must wire that relationship explicitly.

This gives Astichi a resilient stitching surface: names are private by default,
and sharing is intentional.

## Core rule

By default, a local binding introduced by one snippet is not the same binding as
a same-spelled local introduced by another snippet. During materialization,
Astichi may rewrite one binding and all of its matching references:

```python
total = 0
total__astichi_scoped_1 = 1
```

Use explicit keep or boundary wiring when the exact spelling or cross-snippet
identity matters.

## Astichi scopes

Astichi tracks composition scopes in addition to ordinary Python scopes.

- Each compiled root starts with its own Astichi scope.
- Each builder-added contribution is isolated as a fresh Astichi scope.
- Builder-generated insertion shells preserve those scope boundaries in
  pre-materialized source.
- Ordinary Python scopes still apply: modules, classes, functions, lambdas, and
  comprehensions keep their normal Python meaning.

The final materialized Python may be a flat block, but Astichi does not treat
all source snippets as one flat namespace while composing them.

## Local renaming

Ordinary locals can be renamed when composition would otherwise create a
collision. Loads, stores, deletes, parameters, class names, and function names
that belong to the renamed binding are rewritten consistently.

Example: two independent inserted snippets both define `total`; one remains
`total` and the other becomes `total__astichi_scoped_1`.

See:

- [scope/colliding_locals_two_inserts](snippets/scope/colliding_locals_two_inserts/)

## Preserved names

A preserved name keeps its spelling. Competing locals are renamed away from it
instead.

Preserve a name with:

- `astichi_keep(name)`
- `name__astichi_keep__`
- `compile(..., keep_names={...})`
- `builder.add.Name(piece, keep_names={...})`

Use `astichi_keep(name)` for an existing identifier in expression/statement
source. Use `name__astichi_keep__` when the marker must be part of an
identifier slot, such as a class name, function name, parameter, assignment
target, or reference.

Example: an outer snippet keeps `value`; an inserted snippet also defines
`value`, so the inserted local is renamed and the final `result` still reads the
outer spelling:

```python
value = 1
value__astichi_scoped_1 = 2
result = value
```

See:

- [scope/outer_hole_inner_insert_keep](snippets/scope/outer_hole_inner_insert_keep/)
- [marker-keep.md](marker-keep.md)

## Identifier demands

If a snippet is meant to use a variable supplied by composition context, declare
an identifier demand instead of relying on a coincidental same-spelled local.

Identifier demand surfaces:

- `name__astichi_arg__`
- `astichi_import(name)`
- value-form `astichi_pass(name)`

Resolve demands with:

- `compile(..., arg_names={"slot": "target"})`
- `.bind_identifier(slot="target")`
- `builder.add.Name(piece, arg_names={"slot": "target"})`
- `builder.assign...`

Unresolved identifier demands fail at materialize time. That failure is
intentional: it prevents a snippet from silently binding to the wrong
same-spelled name.

## Boundary markers

Use boundary markers when a snippet needs to pass a name across an Astichi
scope boundary.

- `astichi_import(name)` is declaration-form: it declares a whole-scope
  identifier demand.
- `astichi_pass(name)` is value-form: it participates in an expression.
- `astichi_export(name)` supplies a binding from a snippet.
- `outer_bind=True` is the explicit same-name immediate outer-scope form.
- `builder.assign...` is the preferred explicit wiring surface for nontrivial
  cross-instance composition.

Boundary markers make sharing source-visible, which keeps generated code
reviewable and round-trippable.

## What hygiene does not do

Astichi hygiene is about composition-time identifier safety.

It does not:

- import modules for you
- execute arbitrary Python to decide names
- infer that two same-spelled names should share state
- preserve a name unless you requested preservation or wiring
- remove Python's runtime scope rules

When a snippet needs shared state, make that relationship explicit. When it does
not, Astichi keeps independent locals from colliding.

## See also

- [classification-modes.md](classification-modes.md)
- [marker-keep.md](marker-keep.md)
- [marker-binds-and-exports.md](marker-binds-and-exports.md)
- [ReferenceGuide.md](ReferenceGuide.md)
