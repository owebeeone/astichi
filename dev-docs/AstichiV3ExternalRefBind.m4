# Astichi V3 addendum: external reference bind

Status: design addendum for V3.

This note defines a small expression-only surface for supplying Python
references, including dotted references, from external bind values or other
payload expressions.

## 1. Core rule

Use:

```python
astichi_ref(value)
astichi_ref(external=name)
```

Semantics:

- `astichi_ref(value)` interprets `value` as a Python reference path
- `astichi_ref(external=name)` is sugar for:

```python
astichi_ref(astichi_bind_external(name))
```

- this surface is **expression-only**
- it does **not** replace identifier-slot binding for true identifier-only
  syntax positions

## 2. Accepted values

The resolved value must be a string.

Accepted final strings:

- `foo`
- `a.b`
- `pkg.mod.attr`

The authored source may supply that string as:

- a string literal
- an f-string whose formatted parts are reducible from Astichi-controlled
  compile-time sources

Allowed compile-time formatted parts:

- bare `astichi_for` loop variables
- bare externally bound values
- compile-time subscript lookups over those values

Examples:

```python
astichi_ref(f"var_{i}")
astichi_ref(f"{prefix}.field")
astichi_ref(f"{mapping[key]}")
```

Reduction rules:

- Astichi reduces the expression with a restricted compile-time evaluator
- Astichi does **not** execute arbitrary Python code to compute ref strings
- the evaluator is limited to:
  - string literals
  - f-strings
  - formatted values drawn from the allowed compile-time sources above

Validation of the resolved string:

- the string must not be empty
- segments are split on `.`
- every segment must be a valid Python identifier
- empty segments are rejected

## 3. Lowering

Lowering is expression-shaped:

- `foo` lowers to `ast.Name("foo")`
- `a.b.c` lowers to nested `ast.Attribute(...)`

Examples:

```python
value = astichi_ref(path)
value = astichi_ref(external=path)
call(astichi_ref(path))
```

With:

```python
.bind(path="pkg.mod.attr")
```

materialized result:

```python
value = pkg.mod.attr
```

## 3a. LHS, AugAssign, and Delete sites

Python's grammar rejects a bare `Call` as the target of `Assign`,
`AugAssign`, or `Delete`. To use `astichi_ref(...)` in those positions,
wrap it in a sentinel attribute access:

```python
astichi_ref(path).astichi_v = value      # Store:    lowers to <path> = value
astichi_ref(path).astichi_v += 1         # AugStore: lowers to <path> += 1
del astichi_ref(path).astichi_v          # Delete:   lowers to del <path>
```

`._` is accepted as a shorthand synonym of `.astichi_v`, mirroring the
`_=` carrier in `astichi_funcargs(...)`.

Recognition is structural. Astichi recognises the shape

```
Attribute(value=Call(Name("astichi_ref"), ...), attr=SENTINEL)
```

where `SENTINEL` is one of `astichi_v` or `_`. The wrapping `Attribute`
node is stripped and its `ctx` (`Load`, `Store`, `Del`) is propagated
onto the lowered reference node from §3. The sentinel attr is never
observed at runtime because astichi removes the wrapper before emit.

Examples after lowering with `bind(path="self.f0")`:

```python
astichi_ref(path).astichi_v = 42         #  ->  self.f0 = 42
total += astichi_ref(path).astichi_v     #  ->  total += self.f0
astichi_ref(path).astichi_v ^= 1         #  ->  self.f0 ^= 1
del astichi_ref(path).astichi_v          #  ->  del self.f0
```

Constraints:

- the wrapping `Attribute` must use one of the recognised sentinel
  attr names (`astichi_v` or `_`); any other attr name is preserved
  literally and treated as a real attribute lookup on the lowered
  reference (e.g. `astichi_ref("pkg.mod").other` lowers to
  `pkg.mod.other`)
- the sentinel form may NOT be chained (`astichi_ref(p).astichi_v.x`
  is rejected because the resolved write/read target would be
  ambiguous between the lowered ref and the trailing `.x`)
- the sentinel form does not introduce any new value semantics; the
  resulting node is the same as the value-form `astichi_ref(path)`
  with the surrounding grammatical position's `ctx` attached

## 4. Scope

`astichi_ref(...)` is a value-form expression.

Implications:

- it can appear anywhere a normal expression is legal
- it participates in normal expression hygiene and lowering
- it is not itself a name-declaration marker
- the §3a sentinel-attribute wrapper extends reachability to
  `Assign`/`AugAssign`/`Delete` target positions without changing
  the value-form semantics

## 5. Relationship to identifier slots

`astichi_ref(...)` does **not** solve true identifier-only grammar positions,
including:

- function names
- class names
- parameter names
- keyword argument names

Those continue to use the identifier-slot / identifier-bind machinery.

Rule of thumb:

- if the target position expects an expression, `astichi_ref(...)` may be used
- if the target position expects a literal identifier token, use identifier
  binding instead

## 6. Non-goals

This surface does not:

- accept arbitrary Python expressions as path text
- evaluate arbitrary Python code to compute path text
- accept non-string runtime values
- change the identifier-slot model
- imply import execution; it only lowers a reference expression shape
- accept general formatted expressions such as:
  - attribute reads like `obj.attr`
  - function calls like `make_name()`
  - arbitrary arithmetic or boolean expressions
  - slicing or other general Python expression forms beyond the restricted
    compile-time subscript rule above

## 7. Examples

External bind:

```python
target = astichi_ref(external=path)
```

Equivalent to:

```python
target = astichi_ref(astichi_bind_external(path))
```

Loop/unroll:

```python
for path in astichi_for(("a.b", "c.d")):
    target = astichi_ref(path)
```

Loop/external composition:

```python
for key in astichi_for(("left", "right")):
    target = astichi_ref(f"{mapping[key]}")
```

Loop with read-and-write on the same path (per §3a):

```python
for spec in astichi_for(_FIELDS):
    if not (m & spec[0]):
        astichi_ref(spec[1]).astichi_v = spec[2]   # write
        m |= spec[0]
    total ^= astichi_ref(spec[1])                  # read
```

## 8. Rejection cases

Reject:

- `astichi_ref()`
- `astichi_ref(external=path, other=x)`
- `astichi_ref(external="pkg.mod")`
- `astichi_ref("a..b")`
- `astichi_ref("")`
- `astichi_ref(f"{obj.attr}")`
- `astichi_ref(f"{make_name()}")`

The `external=` form is specifically a shortcut for an external bind slot name,
so its value must be a bare identifier.

Reject for the §3a sentinel-attribute wrapper:

- `astichi_ref(path).astichi_v.x`           — chained access after the sentinel
- `astichi_ref(path).astichi_v(...)`         — the sentinel wrapper may not be
  called; the lowered ref is a value, not a callable wrapper
- `astichi_ref(path)._ .other = v`           — chaining via the `_` shorthand
  is rejected for the same reason as `.astichi_v.x`
- assignment targets that combine the sentinel form with tuple/list
  unpacking targets where the sentinel is itself one of the elements
  (the lowering rule applies element-by-element; mixing is permitted
  as long as each sentinel-wrapped element is independently lowerable)
