# Astichi API design V1: expression insertion

This document isolates the expression-position insertion problem for Astichi
V1.

It exists because “expression insertion” is not one thing in Python. Different
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

This is not expression syntax in Python’s AST category, but it is part of the
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

V1 should not add “one generic expression insert form” until the structural
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

## 7. Open questions

These need answers before extending the V1 source surface:

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

## 8. Out of scope for V1 unless explicitly added

The following positions must be treated as out of scope for V1 unless a later
V1 design update explicitly adds them with tests:

- subscript and slice insertion forms
- comprehension and generator expression positions
- decorator insertion forms
- f-string expression positions
- pattern and match positions
- special statement expression positions such as `raise`, `assert`, `with`, and
  import-adjacent forms
- annotation-slot insertion

## 9. Interim rule

Until the above is resolved:

- do not widen V1 expression insertion semantics casually
- prefer explicit tests for each supported expression-hole context
- treat expression-position insertion wrappers as an unresolved design surface,
  not as “obviously the same as holes”
