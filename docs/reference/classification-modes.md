# Name classification modes

Astichi classifies identifiers in snippets before lowering. **Lexical hygiene**
must follow
**[`IdentifierHygieneRequirements.md`](../../dev-docs/IdentifierHygieneRequirements.md)**.

## Name classes

- Local / generated bindings
- Explicit **`astichi_keep`**
- Explicit **`__astichi_keep__`** identifier suffix
- Explicit **`__astichi_arg__`** identifier suffix
- Explicit **`__astichi_param_hole__`** parameter-target suffix
- Explicit **`astichi_bind_external`**
- Unresolved **free** identifiers

Context may supply **`preserved_names`** (ambient roots like `print`, `sys`) and
**`external_values`** (compile-time map for externals).

## Identifier suffix forms

Astichi also recognizes identifier-shaped marker suffixes:

```python
class Client__astichi_keep__:
    pass

def step__astichi_arg__(item__astichi_arg__):
    return item__astichi_arg__ + 1

def run(params__astichi_param_hole__):
    return None
```

Use these when the marker must sit in an identifier position, such as a class
name, function name, argument name, assignment target, or reference. Call-form
markers like `astichi_keep(Client)` cannot mark a declaration name itself.

- `name__astichi_keep__` pins the base spelling `name` through hygiene. The
  suffix is stripped during materialization.
- `name__astichi_arg__` creates an identifier demand named `name`. It must be
  resolved before materialization through `arg_names=`,
  `.bind_identifier(...)`, builder `arg_names=`, or `builder.assign...`.
- `name__astichi_param_hole__` creates a parameter-list demand target named
  `name`. It is valid only on an ordinary function parameter and is consumed
  by parameter materialization.

Suffix forms classify by their base identifier (`name` above), not by the
literal suffixed spelling.

Parameter-hole suffixes are different from arg/keep suffixes. They do not name
a runtime parameter and they do not participate in hygiene repair. Inserted
final parameter names are signature API names; duplicate final names reject.

## Reference-produced identifiers

`astichi_ref(...)` is not a name-class marker like `__astichi_arg__` or
`__astichi_keep__`, but it can produce identifiers. At materialize time,
after external binds and unroll substitution, Astichi lowers a reference path
into ordinary `Name` / `Attribute` nodes:

```python
value = astichi_ref("pkg.mod.attr")
astichi_ref(path).astichi_v = 42
```

The lowered identifiers then participate in the usual hygiene/classification
pass as normal Python names. `astichi_ref(external=path)` is sugar for an inner
`astichi_bind_external(path)`, so `path` itself is classified and validated as
an external bind demand before the reference path is lowered.

## Strict mode

Unresolved frees → **error**, unless kept, declared external, or in the
preserved-name set. Unresolved `__astichi_arg__` slots are also an error at
materialization.

## Permissive mode

Unresolved frees may become **implied named demands**.

## Classification order

1. Collect locals  
2. Collect explicit `astichi_keep` and `__astichi_keep__`  
3. Collect identifier demands from `__astichi_arg__`  
4. Merge context preserved names  
5. Collect explicit externals  
6. Classify remaining frees (per mode)

Local colliding with a preserved name: **strict** → error; **permissive** →
hygiene-rename the **local** and its references.

## See also

- [scoping-hygiene.md](scoping-hygiene.md)
- [marker-params.md](marker-params.md)
- [marker-keep.md](marker-keep.md)
- [marker-ref.md](marker-ref.md)
- [ReferenceGuide.md](ReferenceGuide.md)
- **[§6](../../dev-docs/AstichiApiDesignV1.md)**
