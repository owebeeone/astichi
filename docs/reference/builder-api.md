# Builder API

## Entry

```python
from astichi import build

builder = build()
```

**`build()`** returns a **mutable builder** graph. The builder holds **named
instances** of `Composable`, **ties** (edges from supply to demand ports), and
**ordering** metadata for variadic insertion sites.

## Fluent API (preferred)

Chaining registers instances and performs inserts in one expression:

```python
result = (
    build()
    .add.A(loop_example)
    .add.B(print_example)
    .A.init.add.B(order=10)
    .A.first[0].add.B(order=10)
    .A.third.add.B(order=10)
    .build()
)
```

## Handle-oriented API (equivalent semantics)

The same graph can be built with **stable handle objects** instead of a single
chain:

```python
b = build()
b.add.A(loop_example)
b.add.B(print_example)

a = b.A
a.init.add.B(order=10)
a.first[0].add.B(order=10)
a.third.add.B(order=10)

result = b.build()
```

Fluent and handle styles **must** behave identically (**[§8](../../dev-docs/AstichiApiDesignV1.md)**).

## Raw / assembler layer

A lower-level explicit API (instance ids, `PortId`, `tie`, …) exists for tooling
and tests; it is **semantics-equivalent** to fluent/handle surfaces with more
boilerplate.

## `build()` on the graph

Calling **`.build()`** on the builder **folds** the graph into one **new**
`Composable`. The result **may still contain**:

- open **boundary** holes (if optional demands were left unwired)  
- **loops** from `astichi_for` if they were not unrolled  
- **exports** and other marker-lowered structure  

**`build()`** does **not** force eager loop unrolling merely because a loop
exists (**[§10.1](../../dev-docs/AstichiApiDesignV1.md)**).

## Variadic `order`

When multiple inserts target the same variadic hole, each edge carries an
**`order`** value: **lower sorts first**. **Equal `order` on the same target is
an error** (**[§5.8](../../dev-docs/AstichiApiDesignV1.md)**).

## See also

- [Addressing](addressing.md)
- **[§8 — Builder API](../../dev-docs/AstichiApiDesignV1.md)**
