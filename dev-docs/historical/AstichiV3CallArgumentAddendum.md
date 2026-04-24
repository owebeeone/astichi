# Astichi V3 addendum: call-argument payloads

Status: design addendum for V3.

This note captures the current V3 direction for composing Python call
arguments. It narrows and supersedes the older V1 expression-insert wording for
this specific surface.

## 1. Core rule

Call-argument composition uses:

- authored payloads
- generated placement

The authored source describes the argument payload itself. The builder/merge
machinery decides where that payload lands and records placement/order as
generated Astichi metadata.

For this surface, user-authored `astichi_insert(...)` is not the intended
source form.

## 1a. Compatibility decision

The compatibility decision for this surface is:

- `astichi_funcargs(...)` is **call-site-only**
- for call-argument composition, authored `astichi_insert(target, expr)` is
  **generated-only metadata**, not an accepted authored source surface

Implications:

- build/merge may still synthesize `astichi_insert(target, expr)` internally as
  placement metadata while assembling a composable
- any current authored acceptance of `astichi_insert(target, expr)` for this
  surface is legacy behavior to remove, not compatibility to preserve
- user-authored call-argument payloads should be written as
  `astichi_funcargs(...)`, with placement supplied externally by the builder
  graph

## 2. Authored payload form

The source-level payload form is:

```python
astichi_funcargs(...)
```

Examples:

```python
astichi_funcargs(1, 2, y=4)
astichi_funcargs(*a1, a2, **b1, foo=2)
```

Semantics:

- the payload is target-agnostic
- it does not name the destination hole
- it may carry positional arguments, starred arguments, named keyword
  arguments, and `**mapping` arguments

## 3. Target-side holes

`astichi_hole(...)` may appear any number of times in a call surface.

Examples:

```python
func(astichi_hole(a))
func(astichi_hole(a), x, *astichi_hole(b), y=2, **astichi_hole(c))
```

Rules:

- the order of hole occurrences in the target source is authoritative
- same hole name repeated in one compiled snippet remains illegal
- multiple distinct holes in one call are allowed and define structural
  ordering regions
- all three call-target forms are allowed:
  - `func(astichi_hole(a))`
  - `func(*astichi_hole(a))`
  - `func(**astichi_hole(a))`

## 4. Hole interpretation

The surrounding syntax constrains how a hole is interpreted.

### 4.1 Plain call-argument hole

```python
func(astichi_hole(a))
```

This is a general call-argument region.

Best-effort lowering:

- positional and starred payload items lower into the positional portion of the
  call
- named keyword and `**mapping` payload items lower into the keyword portion of
  the call
- in a plain call-position hole, generated keyword-region items append after
  the authored explicit keyword / `**` region of the enclosing call
- if surrounding fixed syntax forces Astichi to choose an ordering, hole
  occurrence order is respected first, then contribution order within the hole

In other words: plain holes are permissive convenience regions.

### 4.2 Starred hole

```python
func(*astichi_hole(a))
```

This is a starred/positional-expansion region. The surrounding `*` is
authoritative and constrains the legal lowering for that hole.

### 4.3 Double-starred hole

```python
func(**astichi_hole(a))
```

This is a keyword-mapping expansion region. The surrounding `**` is
authoritative and constrains the legal lowering for that hole.

## 5. Ordering contract

Ordering is defined in three layers:

1. target hole occurrence order
2. contribution order within each hole
3. best-effort canonical lowering inside that hole

This means:

- if the user needs exact placement boundaries, they should split the call into
  multiple holes
- Astichi preserves structural order between holes first
- within a single hole, Astichi is allowed to normalize into legal Python call
  form using a simple deterministic rule

## 6. Duplicate keywords

Duplicate statically-known emitted keyword names are a hard error at build time.

Example:

```python
astichi_funcargs(x=1)
astichi_funcargs(x=2)
```

targeting the same effective keyword region must fail during build.

## 7. Boundary and value markers inside payload snippets

For this surface, not every marker-like call has the same role.

- `astichi_pass(name)` is the value-level boundary form. It may appear where
  an argument expression is valid, including inside `astichi_funcargs(...)`.
- `astichi_import(name)` is a non-emitting directive. It brings an outer name
  into the payload scope; it does not itself add a call argument.
- `astichi_export(name)` is a non-emitting directive. It publishes a payload
  binding outward; it does not itself add a call argument.
- `astichi_bind_external(name)` is a value-level external-literal demand. It
  behaves like a normal emitted argument expression and remains part of the
  final call after external binding is applied.

Because expression payload scope lives inside the generated expression-insert
wrapper, import/export directives for a payload must be carried **inside**
`astichi_funcargs(...)`, not only as surrounding sibling statements.

The keyword name `_` is the special carrier **only** for payload-local
`astichi_import(...)` / `astichi_export(...)` directives:

```python
astichi_funcargs(
    (tmp := astichi_pass(source)),
    y=tmp,
    _=astichi_import(source),
    _=astichi_export(tmp),
)
```

Rules:

- `_=astichi_import(name)` and `_=astichi_export(name)` are non-emitting
  directive entries for `astichi_funcargs(...)`
- those directive entries do not contribute a runtime call argument
- allowed directive values in special `_=` entries are:
  - `astichi_import(name)`
  - `astichi_export(name)`
- `astichi_pass(name)` is **not** valid in `_=`; it is the value-level form and
  belongs in a real argument expression
- `_=` with any other value is an ordinary emitted `_` keyword argument
- `name=astichi_import(...)` and `name=astichi_export(...)` are invalid for this
  surface because import/export are not value forms
- only direct `_=astichi_import(name)` / `_=astichi_export(name)` forms are
  special; wrapped container forms are rejected
- payload-local `astichi_import(name)` / `astichi_export(name)` on the same name
  as `astichi_bind_external(name)` are rejected to avoid mixed-mode name
  ambiguity
- repeated `_=` is allowed at the Astichi source level because Astichi markers
  only need to survive parse-to-AST; they do not need to compile as ordinary
  Python before Astichi consumes them
- no `_=` carrier survives materialize / emit

In the example above:

- `astichi_pass(source)` is the emitted value that participates in the walrus
  and the final call
- `astichi_bind_external(name)` would likewise be an emitted value if used in a
  real argument position
- `astichi_import(source)` binds the outer source name into the payload scope
- `astichi_export(tmp)` publishes the inner walrus binding outward
- only the real positional / keyword arguments survive to emitted Python

## 8. Hygiene and boundary timing

`astichi_funcargs(...)` payloads still need a fresh Astichi scope per
contribution.

Therefore generated placement wrappers must exist before hygiene and boundary
resolution run.

The required pipeline is:

1. authored payload is parsed (`astichi_funcargs(...)`)
2. build/merge attaches generated placement metadata
3. that generated wrapper provides the fresh Astichi scope boundary
4. boundary markers in the payload snippet resolve relative to that generated
   insert scope
   - `astichi_import(...)` / `astichi_export(...)` are carried in `_=` slots
   - `astichi_pass(...)` may participate as an emitted value expression
5. materialize lowers the payload into concrete call arguments and strips the
   generated metadata, including `_=` directive carriers

This keeps the payload source clean while preserving the existing hygiene and
cross-boundary model.

## 9. Practical guidance

Use one hole when convenience is enough:

```python
func(astichi_hole(args))
```

Use multiple holes when ordering or region boundaries matter:

```python
func(x, *astichi_hole(a), y=2, **astichi_hole(b))
```

That is the intended escape hatch. Astichi does best effort within a hole; the
user controls exact structural boundaries by adding more holes.

## 10. Related but separate: function binding surfaces

This addendum is about call sites, not function definitions.

Function-signature composition is a separate design surface and must not be
treated as "the same problem" as call-argument composition.

Reasons:

- Python function bindings are split into structural categories:
  - positional-only
  - positional-or-keyword
  - var-positional (`*args`)
  - bare `*` sentinel
  - keyword-only
  - var-keyword (`**kwargs`)
- `/` and `*` are binding markers, not ordinary values
- defaults and annotations attach to specific parameter positions
- parameter names must remain unique
- only one var-positional and one var-keyword parameter are legal

If Astichi adds a source-authored payload for function definitions, it should be
a separate carrier with its own rules. The call-site payload form
`astichi_funcargs(...)` should not be reused as the definition-side model by
default.
