# Builder API

## Entry

```python
from astichi import build

builder = build()
```

**`build()`** returns a **mutable builder** graph. The builder holds **named
instances** of `Composable`, **ties** (edges from supply to demand ports), and
**ordering** metadata for variadic insertion sites.

## Fluent API

The current handle API is fluent at the **operation** level, but not as one
long expression across repeated `.add.<Name>(...)` calls. A working pattern is:

```python
builder = build()
builder.add.A(loop_example)
builder.add.B(print_example)
builder.A.init.add.B(order=10)
builder.A.first[0].add.B(order=10)
builder.A.third.add.B(order=10)

result = builder.build()
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

## `build(unroll="auto")` on the graph

Calling **`.build()`** on the builder **folds** the graph into one **new**
`Composable`. The result **may still contain**:

- open **boundary** holes that were left unwired
- **loops** from `astichi_for` when unrolling was not requested or needed
- **exports** and other marker-lowered structure  

`BuilderHandle.build` currently accepts `unroll=True | False | "auto"`:

- `"auto"` (default) unrolls iff indexed target paths such as `A.slot[0]`
  require it
- `True` always unrolls `astichi_for(...)` loops before edge resolution
- `False` never unrolls and rejects indexed edges that require unrolled targets

## Variadic `order`

When multiple inserts target the same variadic hole, each edge carries an
**`order`** value: **lower sorts first**. **Equal `order`** ties resolve by
**first-added edge first**.

## See also

- [Addressing](addressing.md)
- **[§8 — Builder API](../../dev-docs/AstichiApiDesignV1.md)**
