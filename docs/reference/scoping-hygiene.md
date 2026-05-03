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

## Function scopes

Real `def` and `async def` bodies keep their normal Python function scope.
Parameter names and function-local names in one function do not collide with
same-spelled names in another function:

```python
def first(value):
    scratch = value
    return scratch

def second(value):
    scratch = value
    return scratch
```

Within one function, parameters are still bindings in that function scope. If a
builder-inserted body snippet binds the same spelling as a parameter, the body
local can be renamed away from the parameter.

## Inserted parameters

Function parameter holes extend the target function signature before body
boundary markers and hygiene are resolved:

```python
def run(params__astichi_param_hole__):
    astichi_hole(body)
    return session
```

If a payload inserts `session`, that name becomes a binding in `run`'s Python
function scope. Body snippets can intentionally use it with normal expression
surfaces:

```python
value = astichi_pass(session, outer_bind=True)
```

Parameter names are different from ordinary local bindings. They are public
signature names, so Astichi rejects duplicate final parameter names instead of
renaming one with `__astichi_scoped_*`. If an inserted body snippet creates a
local named `session`, that local may be renamed away from the parameter.

See:

- [marker-params.md](marker-params.md)
- [params/function_signature](snippets/params/function_signature/)

## Local renaming

Ordinary locals can be renamed when composition would otherwise create a
collision. Loads, stores, and deletes that belong to the renamed binding are
rewritten consistently. Final names inserted through parameter holes are the
exception: duplicate signature names reject instead of being renamed into a
valid signature.

Example: two independent inserted snippets both define `total`; one remains
`total` and the other becomes `total__astichi_scoped_1`.

See:

- [scope/colliding_locals_two_inserts](snippets/scope/colliding_locals_two_inserts/)

Managed pyimport locals are part of the same binding model. A marker such as
`astichi_pyimport(module=foo, names=(a,))` owns the local binding `a`; if hygiene
renames that binding, materialize emits an import alias and rewrites all matching
uses.

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
- `builder.Target.hole.add.Name(arg_names={"slot": "target"})`
- `builder.assign...`

Pin names with:

- `compile(..., keep_names={...})`
- `.with_keep_names(...)`
- `builder.add.Name(piece, keep_names={...})`
- `builder.Target.hole.add.Name(keep_names={...})`

Edge-local external values can be supplied with:

- `builder.Target.hole.add.Name(bind={...})`

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
- `astichi_pyimport(...)` can supply a local binding inside its owner scope; a
  child scope can read that binding with `astichi_import(..., outer_bind=True)`
  or `astichi_pass(..., outer_bind=True)`.
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
- [marker-pyimport.md](marker-pyimport.md)
- [ReferenceGuide.md](ReferenceGuide.md)
