# Astichi API design V1: expression insertion

This document isolates the expression-position insertion problem for Astichi
V1.

It exists because "expression insertion" is not one thing in Python. Different
syntactic positions impose different structural, binding, ordering, and hygiene
requirements.

This note is directional. It is meant to prevent semantic drift before the V1
surface is extended.

Related documents:

- `astichi/dev-docs/AstichiApiDesignV1.md`
- `astichi/dev-docs/IdentifierHygieneRequirements.md`

## 1. Problem statement

Astichi already supports expression-position holes.

That does **not** mean Astichi already has a complete model for
expression-position **insertion wrappers**.

The missing problem is:

- how inserted expression-shaped code survives in source form
- how materialize finds the correct scope boundary for that inserted code
- how inserted expression forms interact with binding sites, variadic sites,
  ordering, and decomposition

Before adding a general expression-form `astichi_insert(...)`, Astichi must
state the full set of expression insertion categories and the semantics for
each.

## 2. What V1 already supports

V1 hole support currently covers these expression-shaped forms:

### 2.1 Scalar expression hole

```python
value = astichi_hole(value_slot)
```

Meaning:

- one scalar expression value

### 2.2 Positional variadic hole

```python
func(*astichi_hole(arg_list))
items = (*astichi_hole(item_list),)
class Subject(*astichi_hole(parent_list)):
    pass
```

Meaning:

- ordered positional expansion

### 2.3 Named variadic hole

```python
func(**astichi_hole(kwarg_list))
class Subject(**astichi_hole(class_kwarg_list)):
    pass
```

Meaning:

- ordered named expansion

### 2.4 Scalar keyword-value hole

```python
class Subject(metaclass=astichi_hole(class_meta)):
    pass
```

Meaning:

- one scalar expression in a keyword-value slot

### 2.5 Block-position statement hole

```python
astichi_hole(body)
```

when used as a standalone statement in a block.

Meaning:

- ordered block/member insertion site

## 3. Expression insertion is wider than ordinary expression holes

The full insertion surface must distinguish at least these categories.

### 3.1 Scalar value position

Examples:

```python
x = value
return value
f(value)
```

### 3.2 Positional variadic expansion

Examples:

```python
f(*args)
items = (*values,)
class Subject(*bases):
    pass
```

### 3.3 Named variadic expansion

Examples:

```python
f(**kwargs)
class Subject(**class_kwargs):
    pass
```

### 3.4 Keyword-value position

Examples:

```python
f(name=value)
class Subject(metaclass=value):
    pass
```

### 3.5 Binding expression position

Examples:

```python
if (x := value):
    ...
```

This is expression syntax, but it creates bindings.

### 3.6 Assignment/decomposition target-adjacent position

Examples:

```python
a, b = value
a, b = 1, 2
```

This is not expression syntax in Python's AST category, but it is part of the
same insertion-design family because the inserted form may affect binding shape.

### 3.7 Literal-element position

Examples:

```python
items = [value, 1, 2]
items = (value, 1, 2)
items = {value, 1, 2}
```

These are scalar element positions inside ordered/iterated literal structure.

### 3.8 Literal mapping-entry position

Examples:

```python
d = {1: 2}
d = {key: value, 1: 2}
```

This is distinct from scalar expression insertion because a dict entry is a
pair-shaped structural unit and dict order is preserved.

### 3.9 Subscript and slice position

Examples:

```python
obj[index]
obj[start:stop]
obj[a, b]
```

These are not just ordinary scalar expression positions. They have distinct AST
shapes and may impose duplication, ordering, or arity constraints.

### 3.10 Comprehension and generator position

Examples:

```python
[value for value in items]
{value for value in items}
(value for value in items)
```

Expression positions inside comprehensions and generators are not ordinary RHS
slots. They interact with comprehension-local scope rules and must not be
treated as interchangeable with plain expression insertion.

### 3.11 Decorator position

Examples:

```python
@decorator
@decorator(arg)
class Subject:
    pass
```

Decorator expressions are evaluated in a special structural position and should
not be treated as ordinary inline call sites.

### 3.12 Special statement expression positions

Examples:

```python
raise value
assert cond, value
with value as name:
    ...
import mod as name
from mod import name as alias
```

These use expression-shaped or identifier-adjacent positions, but they impose
type, arity, or binding constraints that a generic expression insertion model
would get wrong.

### 3.13 f-string expression position

Examples:

```python
f"{value}"
```

f-string expression slots are constrained and should not be assumed to behave
like ordinary scalar expression positions.

### 3.14 Pattern and match position

Examples:

```python
match value:
    case pattern:
        ...
```

Pattern positions belong to the same broad family as decomposition and binding
positions, but they are not ordinary value-expression sites.

### 3.15 Compare-chain position

Examples:

```python
a < value < b
```

A compare operand looks scalar, but compare chains have extra structural and
evaluation constraints.

### 3.16 Annotation position

Examples:

```python
x: annotation = value
```

The annotation slot and the value slot are different contracts and should not be
collapsed into one generic expression insertion category.

### 3.17 Attribute-base position

Examples:

```python
base.attr
```

The base expression is a normal expression-shaped site. The attribute name
string is not. Astichi must keep those distinct.

## 4. Missing wrapper problem

Astichi currently has:

- `astichi_hole(...)`
- `@astichi_insert(...)`

but does not yet have a complete written-down source model for
expression-position inserted wrappers.

This matters because expression insertion wrappers must survive in source form
long enough for:

- scope-boundary discovery
- hygiene/materialize closure
- ordering-sensitive insertion
- reconstruction of the intended inserted unit shape

The design omission is not just syntax. It is also:

- what structural unit is being wrapped
- what boundary that wrapper introduces
- whether the wrapper is scalar, variadic, binding, or mapping-entry shaped

## 5. Direction for V1

V1 should not add "one generic expression insert form" until the structural
categories are explicit.

The minimum safe rule is:

- ordinary holes remain as they are now
- expression insertion wrappers must be classified by the structural slot they
  occupy
- materialize/hygiene must not guess the slot after the fact from loose syntax

## 6. Dict literal hole form

Astichi is currently missing a dict-literal-specific hole form.

This should be treated as a distinct hole shape.

Candidate source form:

```python
d = {astichi_hole(dict_hole): 0, 1: 2}
```

Interpretation:

- the hole stands in for one mapping-entry key position placeholder
- the surrounding dict still has stable traversal order
- ordering remains significant because Python dict preserves insertion order

This is easier than a fully general mapping-entry insertion wrapper because:

- it provides a concrete placeholder anchor in valid Python syntax
- it preserves ordering semantics naturally
- it avoids pretending dict-entry insertion is just an ordinary scalar value

However, it should still be modeled distinctly from a plain scalar expression
hole.

Recommended V1 treatment:

- record dict-entry-hole support as a separate missing/needed hole shape
- do not collapse it into ordinary scalar expression semantics

## 7. Open questions (resolved)

These questions were open when this document was first written. They are
resolved by the proposal in section 10 and the resolution table in section 12.

- What is the exact expression-form insertion wrapper syntax?
- Does expression-form insertion require an `order` parameter in all cases or
  only variadic/multi-entry cases?
- How are binding-expression insertions represented?
- How are decomposition-target insertions represented?
- Are subscript/slice positions supported in V1, and if so which exact forms?
- Are comprehension/generator expression positions supported in V1?
- Are decorator positions supported in V1?
- Are f-string expression positions supported in V1?
- Are pattern/match positions supported in V1?
- Is dict-entry insertion modeled as:
  - scalar key placeholder only
  - full key/value entry placeholder
  - variadic mapping-entry expansion
- What is the exact scope-boundary rule for expression insertion wrappers?

## 8. Out of scope for V1

The following positions are out of scope for V1 expression insertion unless a
later V1 design update explicitly adds them with tests:

- subscript and slice insertion forms
- comprehension and generator expression positions
- decorator insertion forms
- f-string expression positions
- pattern and match positions
- special statement expression positions such as `raise`, `assert`, `with`, and
  import-adjacent forms
- annotation-slot insertion
- binding expression insertion (walrus `:=`)
- assignment/decomposition target-adjacent insertion
- compare-chain operand insertion

## 9. Standing rules

The following rules apply regardless of the proposal:

- prefer explicit tests for each supported expression-insert context
- treat unsupported expression positions as hard errors, not silent fallthrough
- do not widen V1 expression insertion semantics beyond the positions listed in
  section 10.6

## 10. V1 expression-insert proposal

This section provides a concrete design for expression-position insertion in
V1. It uses the existing `astichi_insert` marker name, extended to call-
expression contexts.

### 10.1 Source form

Expression-position insertion uses the same marker name as the block-position
decorator form, in call-expression syntax:

```python
astichi_insert(target, expr)
astichi_insert(target, expr, order=10)
```

Parameters:

- `target`: bare identifier naming the target hole (same convention as the
  decorator form and `astichi_hole`)
- `expr`: the expression being inserted
- `order`: optional keyword argument, same semantics as the decorator form

For named variadic targets, `expr` is a dict display with bare identifier keys
providing the keyword names and values:

```python
astichi_insert(target, {keyword_name: value})
```

### 10.2 Shape semantics

The expression-insert form always creates an expression-placement (`"expr"`)
supply port.

The insert does not carry the target hole's variadic/scalar sub-shape. Shape
compatibility is resolved at composition time by comparing the insert's
placement against the target hole's placement and shape.

Rules:

- An expression insert can feed any expression-placement demand (scalar,
  positional variadic, or named variadic).
- An expression insert cannot feed a block-placement demand. Use the decorator
  form for block insertion.
- A block insert (decorator form) cannot feed an expression-placement demand.

Materialization semantics depend on the target hole's shape:

| Target hole shape | Single insert | Multiple inserts |
|---|---|---|
| Scalar expression | Direct substitution | Error |
| Positional variadic | One positional element | Ordered positional elements |
| Named variadic | Dict entries expanded | Ordered dict entries expanded |

For scalar expression holes, at most one insert is allowed. Multiple inserts
targeting the same scalar hole are a hard error.

For positional variadic holes, each insert adds one positional element.
The `order` parameter controls element ordering.

For named variadic holes, each insert's expression must be a dict display with
bare identifier keys providing keyword arguments. Using identifiers rather than
string literals ensures the compiler validates that each key is a legal
identifier, and the form round-trips cleanly through source emission. Each
insert adds the entries from its dict. The
`order` parameter controls keyword ordering across inserts.

### 10.3 Scope boundary rule

Each expression insert introduces a fresh Astichi-level scope boundary.

This is not a Python scope (no function or class is created). It is an Astichi
scope object for hygiene purposes, following H5: "Each loop unroll or each
injected AST chunk introduces a new scope object for that structural unit."

An expression insert is an injected AST chunk. It must receive a fresh scope
object.

Rules:

- Internal names (bindings created within the expression, including walrus
  bindings) receive the new scope object (H6).
- External/free names in the expression retain their original scope identity
  (H7).
- Two expression inserts from the same composable get distinct scope objects,
  preventing collision between their internal bindings.

Rationale:

- H5 requires it: injected AST chunks must introduce fresh scope objects.
- Without per-insert scope boundaries, walrus bindings inside an inserted
  expression would pollute the target composable's namespace.
- Without per-insert scope boundaries, multiple inserts from the same
  composable targeting the same variadic hole would share internal bindings,
  causing silent collision.
- The composable boundary separates different composables but does not separate
  multiple inserts within the same composable. Per-insert scope boundaries
  close this gap.

The decorator form also introduces a scope boundary, but through a different
mechanism: the def/class it wraps has its own Python scope. The expression
form introduces an Astichi-level scope boundary without a Python-level scope.

### 10.4 Order parameter

Same rules as the decorator form:

- lower `order` comes first
- equal `order` on the same target preserves insertion order (first come,
  first served)

For scalar expression holes, `order` is not meaningful because at most one
insert is allowed. Supplying `order` for a scalar target is accepted but has
no effect.

For variadic holes, `order` controls the position of the inserted element
within the expansion.

### 10.5 Port model

Expression insert creates a supply port on the containing composable:

- name: the target hole name (first argument)
- shape: `SCALAR_EXPR`
- placement: `"expr"`
- mutability: `"const"`
- source: `"insert"`

Port compatibility validation checks placement compatibility: `"expr"` supply
matches `"expr"` demand, `"block"` supply matches `"block"` demand.

Fine-grained cardinality constraints (scalar hole rejects multiple inserts,
named variadic hole requires dict-valued inserts) are enforced by the builder
at composition time, not by the port-pair validator.

### 10.6 V1 supported positions

The following positions from section 3 are supported for V1 expression insert:

- 3.1 Scalar value position
- 3.2 Positional variadic expansion (target hole shape)
- 3.3 Named variadic expansion (target hole shape, dict display with bare
  identifier keys)
- 3.4 Keyword-value position (subset of scalar expression)
- 3.7 Literal-element position (subset of scalar expression)
- 3.8 Literal mapping-entry position (via named variadic in dict context)
- 3.17 Attribute-base position (the base expression is a scalar insert
  concern; the attribute name string is not)

### 10.7 V1 excluded positions

The following positions are excluded from V1 expression insertion. These must
be hard errors if an expression insert is detected in these contexts:

- 3.5 Binding expression position (walrus `:=`)
- 3.6 Assignment/decomposition target-adjacent position
- 3.9 Subscript and slice position
- 3.10 Comprehension and generator position
- 3.11 Decorator position
- 3.12 Special statement expression positions
- 3.13 f-string expression position
- 3.14 Pattern and match position
- 3.15 Compare-chain position
- 3.16 Annotation position

### 10.8 Relationship to decorator form

| Property | Decorator form | Expression form |
|---|---|---|
| Syntax | `@astichi_insert(target)` | `astichi_insert(target, expr)` |
| Context | Decorator on def/class | Call expression |
| Positional args | 1 (target) | 2 (target, expr) |
| Target hole shape | Block | Any expression shape |
| Scope boundary | Yes (Python scope from def/class) | Yes (Astichi-level scope, H5) |
| Creates supply port | Yes | Yes |
| Supports `order` | Yes | Yes |

Both forms use the same marker name. The distinction is syntactic context:
decorator position vs call-expression position.

### 10.9 Dict-entry insertion

Dict-entry insertion uses the named variadic mechanism.

Demand side (hole in dict display):

```python
d = {**astichi_hole(entries), fixed_key: 1}
```

Supply side (expression insert with dict display):

```python
astichi_insert(entries, {inserted_key: value})
```

This uses the existing `NAMED_VARIADIC` shape for the hole and the standard
expression-insert form for the supply. No new shape is required.

A scalar expression hole in dict key position:

```python
d = {astichi_hole(single_key): sentinel}
```

remains valid under existing scalar expression hole rules and does not require
new shape machinery.

### 10.10 Marker recognition changes

The current implementation registers `astichi_insert` with
`decorator_only=True` and `positional_args=1`. The expression form requires:

- recognizing `astichi_insert` in call-expression context (not only decorator
  context)
- accepting 2 positional arguments (target, expr) in call context
- accepting 1 positional argument (target) in decorator context
- shape for expression-form inserts is always `SCALAR_EXPR` regardless of the
  call's own syntactic position (overriding the normal `_infer_shape` rule that
  would assign `BLOCK` to a standalone expression statement)

### 10.11 Examples

Scalar expression insert:

```python
snippet_a = astichi.compile("""
x = astichi_hole(value)
print(x)
""")

snippet_b = astichi.compile("""
astichi_insert(value, 42)
""")
```

Positional variadic insert (multiple inserts, ordered):

```python
snippet_a = astichi.compile("""
result = func(*astichi_hole(args))
""")

snippet_b = astichi.compile("""
astichi_insert(args, first_arg)
""")

snippet_c = astichi.compile("""
astichi_insert(args, second_arg, order=20)
""")
```

Named variadic insert:

```python
snippet_a = astichi.compile("""
result = func(**astichi_hole(kwargs))
""")

snippet_b = astichi.compile("""
astichi_insert(kwargs, {name: some_value})
""")
```

Dict-entry insert:

```python
snippet_a = astichi.compile("""
d = {**astichi_hole(entries), fixed: 1}
""")

snippet_b = astichi.compile("""
astichi_insert(entries, {dynamic_key: computed_value})
""")
```

Keyword-value insert:

```python
snippet_a = astichi.compile("""
class Subject(metaclass=astichi_hole(meta)):
    pass
""")

snippet_b = astichi.compile("""
astichi_insert(meta, ABCMeta)
""")
```

Block insert (existing decorator form, unchanged):

```python
snippet_a = astichi.compile("""
class Subject:
    astichi_hole(body)
""")

snippet_b = astichi.compile("""
@astichi_insert(body)
def method(self):
    return 42
""")
```

## 11. Interaction with milestone 4d-4f

Expression inserts introduce fresh Astichi-level scope boundaries
(section 10.3). This has direct implications for milestones 4d-4f:

- **4d (scope object attachment)**: the scope-identity model must recognize
  expression-insert markers as scope-boundary-introducing sites, alongside
  def/class boundaries and loop-expansion sites.
- **4e (structural expansion scope freshness)**: each expression insert is an
  injected AST chunk under H5 and must receive a fresh scope object during
  structural expansion, the same way loop-unrolled bodies do.
- **4f (scope-collision renaming)**: internal bindings within an expression
  insert (including walrus bindings) must be renamed if they collide with
  names in the target scope or in sibling inserts targeting the same hole.

The decorator form continues to introduce a scope boundary through Python's
own def/class scope mechanism. The expression form introduces a scope boundary
through Astichi's scope-object machinery. Both mechanisms produce fresh scope
objects; they differ only in where the boundary originates.

## 12. Resolution of section 7 open questions

**What is the exact expression-form insertion wrapper syntax?**

`astichi_insert(target, expr, order=N)` — see section 10.1.

**Does expression-form insertion require an `order` parameter in all cases or
only variadic/multi-entry cases?**

`order` is optional in all cases. It is meaningful only for variadic and block
targets. For scalar targets it is accepted but has no effect. See section 10.4.

**How are binding-expression insertions represented?**

Excluded from V1. See section 10.7.

**How are decomposition-target insertions represented?**

Excluded from V1. See section 10.7.

**Are subscript/slice positions supported in V1, and if so which exact forms?**

Excluded from V1. See section 10.7.

**Are comprehension/generator expression positions supported in V1?**

Excluded from V1. See section 10.7.

**Are decorator positions supported in V1?**

Excluded from V1 for expression insert. Decorator position is served by the
existing `@astichi_insert` decorator form. See section 10.7.

**Are f-string expression positions supported in V1?**

Excluded from V1. See section 10.7.

**Are pattern/match positions supported in V1?**

Excluded from V1. See section 10.7.

**Is dict-entry insertion modeled as scalar key placeholder only, full
key/value entry placeholder, or variadic mapping-entry expansion?**

Variadic mapping-entry expansion using the existing `NAMED_VARIADIC` shape.
The expression-insert form uses a dict display with bare identifier keys as
the expression parameter.
See section 10.9.

**What is the exact scope-boundary rule for expression insertion wrappers?**

Each expression insert introduces a fresh Astichi-level scope boundary per H5.
Internal bindings get the new scope object (H6). Free variables retain their
original scope (H7). See section 10.3.
