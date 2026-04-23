# Parameter holes

Function parameter lists are a typed insertion surface. They are not expression
holes and not block holes, because Python stores signatures in
`ast.arguments`.

## Target marker

Declare a parameter-list target with an identifier suffix in an ordinary
positional-or-keyword parameter slot. Both `def` and `async def` targets are
supported:

```python
def run(params__astichi_param_hole__):
    astichi_hole(body)
```

`params__astichi_param_hole__` names the parameter target `params`. The marker
parameter is removed during materialization.

Rules:

- The marker may appear only in `FunctionDef.args.args` or
  `AsyncFunctionDef.args.args`.
- The marker cannot be positional-only, keyword-only, `*args`, or `**kwargs`.
- The marker cannot have an annotation or default.
- Multiple parameter holes are allowed in one signature only when their target
  names are distinct.

```python
def foo(p1__astichi_param_hole__, user_param, p2__astichi_param_hole__):
    user_code(user_param)
```

Ordinary parameters inserted into `p1` appear before `user_param`; ordinary
parameters inserted into `p2` appear after it.

## Payload marker

Supply parameters with a dummy function named `astichi_params`:

```python
def astichi_params(session, limit: int = 10, *, debug=False, **options):
    pass
```

`async def astichi_params(...): pass` is also accepted. Only the signature is
used. The body must be empty-equivalent: `pass` or `...`. Astichi supports
ordinary parameters, keyword-only parameters, defaults, annotations, `*args`,
and `**kwargs`. Positional-only payload parameters are rejected.

Wire the payload through the builder:

```python
builder.add.Root(astichi.compile(root_src))
builder.add.Params(astichi.compile(params_src))
builder.Root.params.add.Params(order=0)
```

## Merge rules

Parameter insertion is additive:

- Ordinary payload parameters are inserted at the marker position.
- Keyword-only payload parameters are appended in contribution order.
- Existing keyword-only target parameters stay before inserted keyword-only
  parameters.
- Lower `order` runs first; equal `order` keeps first-added edge order.
- At most one final `*args` parameter is allowed.
- At most one final `**kwargs` parameter is allowed.
- Duplicate final parameter names reject.
- Hygiene does not rename parameters to make a signature valid.

Parameter names are API bindings. If two payloads both add `session`, the build
must be changed; Astichi will not repair that collision with a scoped suffix.

## Defaults and annotations

Defaults and annotations inside `def astichi_params(...)` are normal expression
subtrees. They can use expression holes, binds, refs, and identifier suffixes.

Default holes are required scalar expression holes:

```python
def astichi_params(limit: int = astichi_hole(limit_default)):
    pass
```

Annotation holes are optional scalar annotation slots:

```python
def astichi_params(limit: astichi_hole(limit_type) = 10):
    pass
```

Annotation-hole cardinality:

- zero contributions: remove the whole annotation
- one contribution: use it as the annotation expression
- more than one contribution: reject

Astichi does not combine multiple annotation contributions. If you want a union,
provide one annotation expression such as `int | str`.

## Scope and hygiene

Inserted parameters become bindings in the target function scope before body
boundary markers and hygiene run. That lets body snippets intentionally refer
to inserted parameters:

```python
value = astichi_pass(session, outer_bind=True)
```

If an inserted body snippet also creates a local named `session`, that body
local is renamed away from the inserted parameter. The parameter keeps its API
name.

## Internal emitted form

Astichi may emit inspectable parameter metadata in pre-materialized output:

```python
@astichi_insert(params, kind="params", ref=Root.Params)
def __astichi_param_contrib__Root__params__0__Params(session):
    pass
```

This is internal emitted source only. Do not author `astichi_insert(...)`
directly. Re-ingest emitted source with:

```python
astichi.compile(source, source_kind="astichi-emitted")
```

## See also

- [marker-overview.md](marker-overview.md)
- [scoping-hygiene.md](scoping-hygiene.md)
- [ReferenceGuide.md](ReferenceGuide.md)
- [historical AstichiV3ParameterHoleSpec.md](../../dev-docs/historical/AstichiV3ParameterHoleSpec.md)
