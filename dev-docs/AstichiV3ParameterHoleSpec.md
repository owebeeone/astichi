# Astichi V3 parameter hole spec

Status: draft spec before implementation

This note defines function-definition parameter insertion for Astichi. It
narrows one item from `AstichiV3TargetAdditionalHoleShapes.md`: adding function
parameters as a typed list-field target.

The feature is needed when generated snippets must extend a callable signature
and then let inserted body code intentionally refer to those added parameters.

## 1. Why this is a separate shape

Function parameters are not expressions and not statements. Python stores them
in `ast.arguments`, split across several aligned fields:

- `posonlyargs`
- `args`
- `vararg`
- `kwonlyargs`
- `kw_defaults`
- `kwarg`
- `defaults`

The existing block and expression insertion machinery cannot represent a
parameter entry. The new feature therefore needs a typed parameter-hole target
and a parameter-payload supply.

The hardest part is not only syntax. Parameter insertion changes the binding
environment of the target function body. Body snippets inserted into the same
function must be able to bind deliberately to parameters that were inserted by
other snippets.

## 2. Public authored target surface

Use an identifier suffix marker in a real function signature:

```python
def run(
    self,
    params__astichi_param_hole__,
):
    astichi_hole(body)
```

`params__astichi_param_hole__` declares a parameter-list insertion target named
`params`. The suffix is a marker, not a runtime parameter name. It is removed
when the signature is materialized.

This authored form stays valid Python and follows the existing identifier
suffix pattern used by `__astichi_arg__` and `__astichi_keep__`.

Initial constraints:

- the marker may appear only as an ordinary positional-or-keyword parameter in
  `arguments.args`
- a target function may declare multiple named parameter holes, but each hole
  must be unambiguous by name
- a parameter-hole marker cannot have a default value or annotation in the
  target signature
- a parameter-hole marker cannot be the `*args` or `**kwargs` parameter itself

Future work may add explicit markers for keyword-only or positional-only
regions if the plain initial target is not enough.

## 3. Public authored payload surface

Use a dummy function whose signature is the payload:

```python
def astichi_params(
    name: str,
    count__astichi_arg__: int = 0,
    *args,
    **kwds,
):
    pass
```

The function name `astichi_params` is a marker. Its body is ignored and should
be empty-equivalent (`pass`, `...`, or possibly no meaningful statements after
formatting decisions are made). Its `ast.arguments` supplies parameter entries
to a parameter hole.

The payload may include:

- ordinary positional-or-keyword parameters
- keyword-only parameters
- a `*args` parameter
- a `**kwds` parameter
- annotations
- defaults
- identifier suffix markers such as `__astichi_arg__`
- default or annotation expression holes such as `astichi_hole(default_name)`

The payload is still normal Python syntax. Defaults remain aligned through
Python's existing `ast.arguments.defaults` / `kw_defaults` model.

## 4. Builder wiring

Builder use mirrors existing hole wiring:

```python
builder.add.Root(astichi.compile(root_src))
builder.add.Params(astichi.compile(params_src))
builder.Root.params.add.Params(order=0)
```

The target path points at a parameter hole, not a block or expression hole.
Ordering follows existing additive ordering:

- lower `order` first
- equal `order` keeps first-added edge first

Parameter insertion is additive. It does not replace existing authored
parameters except for removing the parameter-hole marker itself.

## 5. Internal emitted form

`astichi_insert(...)` remains internal-only. Authored snippets must not use it.
The builder may emit internal parameter-insert metadata so pre-materialized
source is inspectable and can round-trip through
`compile(..., source_kind="astichi-emitted")`.

Proposed internal form:

```python
@astichi_insert(params, kind="params", ref=Root.Params)
def __astichi_param_contrib__Root__params__0__Params(
    name: str,
    count__astichi_arg__: int = 0,
):
    pass
```

The wrapper function's signature is the payload. The body is ignored. The
`kind="params"` keyword is required so diagnostics can distinguish parameter
payload shells from block insertion shells.

`kind="params"` wrappers are not block insert shells. They do not introduce a
runtime function body, and their parameter names are not hygienic locals owned by
the wrapper. The wrapper's `ast.arguments` are harvested as signature
contributions for the target function. Defaults and annotations inside that
signature remain normal expression subtrees and still participate in marker
recognition, identifier binding, and expression-hole resolution.

Materialization consumes the internal wrapper by splicing its harvested
`ast.arguments` entries into the target signature and removing the wrapper.

## 6. Signature merge rules

Parameter insertion has a signature merge layer separate from scope hygiene.

The merge layer must:

- remove the target `name__astichi_param_hole__` marker
- insert ordinary payload parameters at that marker's position in
  `arguments.args`
- preserve payload order by edge order and payload signature order
- preserve annotations and defaults
- rebuild `arguments.defaults` so Python's tail-default alignment remains
  valid
- preserve `kwonlyargs` and aligned `kw_defaults`
- add at most one `vararg` total
- add at most one `kwarg` total
- reject a payload `*args` when the target function already has `*args` or a
  previous payload added one
- reject a payload `**kwds` when the target function already has `**kwds` or a
  previous payload added one
- reject duplicate parameter names in the final effective signature
- reject signatures that Python would reject, including a non-default ordinary
  parameter after a defaulted ordinary parameter

The `*args` and `**kwds` cases do not have special binding semantics. They are
just parameter names introduced into the function scope. Their special rules
are insertion/cardinality rules.

Parameter-name collisions are never resolved by hygiene. The final effective
signature is an API boundary, so duplicate names across authored target
parameters, inserted ordinary parameters, inserted keyword-only parameters,
inserted `*args`, and inserted `**kwds` are a hard error. If a payload parameter
uses an identifier suffix such as `count__astichi_arg__`, the suffix must be
resolved to its final name before duplicate checking; unresolved identifier
demands reject before final materialization.

## 7. Scope environment rules

Parameter payloads mutate the target function's runtime binding environment.
This must happen before body-insert boundary resolution and hygiene. The scope
model is signature-aware: inserted parameter names belong to the target Python
function scope, not to the emitted parameter wrapper.

Pipeline requirement:

1. collect parameter contributions for each function parameter hole
2. build the effective signature for each target function
3. reject duplicate final parameter names before hygiene can rename anything
4. register all resulting parameter names as target function-scope suppliers
5. resolve body boundary markers and hygiene using that enriched function scope
6. materialize by removing parameter holes and internal parameter insert shells

This matters for inserted function bodies:

```python
def run(params__astichi_param_hole__):
    astichi_hole(body)
```

with inserted params:

```python
def astichi_params(session):
    pass
```

and inserted body:

```python
value = astichi_pass(session, outer_bind=True)
```

The body snippet must be able to bind `session` to the inserted function
parameter. This is not a simple post-order tree walk: the effective signature
must be known before resolving the function body's inserted snippets.

Rules:

- every final parameter name is a runtime supplier in the target function scope
- inserted parameter names are protected signature bindings for that target
  function; hygiene must not rename them to avoid a collision
- inserted body code can refer to those suppliers through ordinary Python
  lookup or explicit boundary markers
- if an inserted body independently binds the same spelling as an inserted
  parameter, hygiene renames the body-local binding unless the user explicitly
  wires or preserves the relationship
- parameter wrappers do not create a fresh Astichi scope for their parameter
  names; the names are lifted into the target function's scope environment
- default and annotation expressions remain payload expression subtrees; marker
  handling inside those expressions still follows the normal import/pass/export,
  bind-external, identifier-suffix, and expression-hole rules that apply before
  final materialization
- the scope pass should use an effective-parameter side table keyed by target
  function node, so it can see inserted parameters while the pre-materialized
  source still contains internal `kind="params"` wrappers

## 8. Default and annotation holes

Default values and annotations are expression positions, but they need slightly
different materialization rules inside parameter payloads:

```python
def astichi_params(
    limit: astichi_hole(limit_type) = astichi_hole(limit_default),
):
    pass
```

Default-value holes are ordinary required scalar expression holes. If the final
materialization reaches `= astichi_hole(limit_default)` with no contribution,
materialize rejects just like any other unresolved expression hole.

Annotation holes are optional scalar annotation slots. If the final
materialization reaches `: astichi_hole(limit_type)` with no contribution, the
whole annotation is removed and the emitted parameter has no `:` annotation.
This keeps a parameter payload able to say "annotate this if a later stage
supplies a type".

Both default and annotation holes can be wired any time before final
materialize. The payload owns the holes, but staged builds may wire them before
the parameter payload is inserted or later through the emitted descendant path,
as long as the final materialize step sees a legal resolved shape.

Annotation holes keep scalar-hole cardinality:

- zero contributions removes the annotation
- one contribution becomes the annotation expression
- more than one contribution rejects

Astichi does not auto-combine annotation contributions. In particular, it does
not synthesize `int | str` from two inserts. If a union is wanted, supply it as
one annotation expression:

```python
int | str
```

Automatic annotation unioning would bake type-system policy into the stitcher
and is not valid for all annotation forms (`Annotated[...]`, string forward
refs, version-specific syntax, or domain-specific annotation objects).

## 9. Rejection cases

Compile-time or build-time diagnostics should reject:

- malformed target suffix use, including no base name before
  `__astichi_param_hole__`
- a parameter-hole marker outside a function signature
- a parameter-hole marker with annotation/default
- a parameter payload whose function name is not the expected marker
- meaningful statements in the payload function body, once body policy is
  finalized
- payloads wired into non-parameter holes
- non-parameter payloads wired into parameter holes
- duplicate final parameter names
- any attempt to rely on hygiene to disambiguate duplicate parameter names
- multiple inserted `*args`
- multiple inserted `**kwds`
- inserted `*args` or `**kwds` when the target already has one
- invalid default ordering in the final ordinary parameter list
- unresolved default expression holes
- more than one contribution to an annotation hole
- unresolved identifier demands in parameter names/defaults/annotations

## 10. Implementation notes

This feature should be implemented test-first.

1. Add initial failing tests and `tests/data/gold_src` cases before starting
   implementation.
   - marker recognition for `__astichi_param_hole__`
   - target port shape for parameter holes
   - payload recognition for `def astichi_params(...): pass`
   - basic signature merge
   - duplicate final parameter-name rejection before hygiene
   - duplicate `*args` / `**kwds` rejection
   - effective-parameter side table used by boundary/hygiene checks
   - pre-materialized emitted form with internal `@astichi_insert(...,
     kind="params")`

2. After the main implementation, add broader behavior tests and goldens.
   - ordinary parameters with annotations and defaults
   - keyword-only parameters and `kw_defaults`
   - inserted `*args` and inserted `**kwds`
   - duplicate final parameter-name rejection
   - body snippets binding to inserted parameters through
     `astichi_pass(..., outer_bind=True)`
   - body snippets that accidentally bind the same spelling as an inserted
     parameter and get renamed by hygiene
   - round-trip `emit()` -> `compile(..., source_kind="astichi-emitted")`
   - Python-version matrix goldens

3. Add reference snippets and reference docs.
   - `docs/reference/snippets/params/...`
   - generated examples for basic params, defaults/annotations, `*args`,
     `**kwds`, and body-scope binding
   - a `docs/reference/marker-params.md` page or equivalent section
   - updates to `docs/reference/README.md`, `ReferenceGuide.md`,
     `marker-overview.md`, `scoping-hygiene.md`, `classification-modes.md`,
     and `errors.md`

4. Update developer docs and summaries.
   - link this spec from `AstichiSingleSourceSummary.md`
   - update `AstichiV3TargetAdditionalHoleShapes.md` to mark parameter holes as
     split into this focused spec
   - add any implementation caveats to the relevant progress register
