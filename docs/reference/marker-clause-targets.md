# Marker: `astichi_elif`

`astichi_elif(name)` declares an additive target inside an existing
`if` / `elif` chain. Builder edges add real `elif` branches at that point.

## Target Form

```python
def dispatch(event_type, payload):
    if event_type == "":
        raise ValueError("empty event_type")
    elif astichi_elif(branches):
        pass
    else:
        return ("fallback", event_type)
```

Rules:

- `astichi_elif(...)` is valid only as a real `elif` test.
- The argument is one bare identifier and names the target.
- The marker body must be empty-equivalent: `pass` plus optional
  `astichi_comment(...)` statements.
- The target is mandatory. `materialize()` rejects if no branch contribution
  has been wired.
- The target is multi-addable. Many contributions may target the same marker.

## Contribution Form

```python
def astichi_elif():
    astichi_import(event_type)
    astichi_import(payload)
    if event_type == "create":
        return ("create", payload)
```

Rules:

- The contribution is a source snippet whose root body contains exactly one
  `def astichi_elif(): ...` function when wired to an elif target.
- The function has no parameters, decorators, return annotation, or type
  parameters.
- Its body may begin with the same statement-prefix boundary markers used by
  other Astichi scopes, including `astichi_import`, `astichi_export`,
  `astichi_keep`, `astichi_bind_external`, `astichi_pyimport`, and
  `astichi_comment`.
- After the prefix, the body contains exactly one `if` statement.
- That `if.test` becomes the generated `elif` test, and `if.body` becomes the
  generated branch body.
- `if.orelse`, walrus in the branch test, `yield`, `yield from`, `await`,
  `break`, and `continue` reject in this phase.
- `return` is allowed only when the target chain is inside a function.

## Builder Use

```python
builder = astichi.build()
builder.add.Root(astichi.compile(root_source))
builder.add.Create(astichi.compile(create_branch_source))
builder.add.Delete(astichi.compile(delete_branch_source))

builder.Root.branches.add.Create(order=10)
builder.Root.branches.add.Delete(order=20)

source = builder.build().materialize().emit(provenance=False)
```

The materialized shape is ordinary Python:

```python
def dispatch(event_type, payload):
    if event_type == "":
        raise ValueError("empty event_type")
    elif event_type == "create":
        return ("create", payload)
    elif event_type == "delete":
        return ("delete", payload)
    else:
        return ("fallback", event_type)
```

Before materialization, build emits internal `kind="elif"` insert shells as
siblings of the owning `if` chain. Those shells are Astichi metadata and are
only valid when re-ingesting emitted source with
`source_kind="astichi-emitted"`.

## Descriptors

`Composable.describe()` exposes an elif target as a `ComposableHole` whose
port shape is `ELIF_CLAUSE`, add policy is `MULTI_ADD`, and
`when_empty` is `REJECT_EMPTY`.

Elif payload snippets expose `production.elif` inventory records and
`ProductionDescriptor` entries compatible only with `ELIF_CLAUSE` holes.

## See Also

- [marker-overview.md](marker-overview.md)
- [marker-holes.md](marker-holes.md)
- [builder-api.md](builder-api.md)
- [descriptor-api.md](descriptor-api.md)
