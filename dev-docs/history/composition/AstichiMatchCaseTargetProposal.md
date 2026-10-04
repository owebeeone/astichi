# Astichi Match Case Target Proposal

Status: proposal.

This proposal defines an initial Astichi surface for composing additional
Python `match` cases. The goal is to support additive case-list targets while
preserving Astichi's current round-trip and hygiene contracts.

The motivating shape is:

```python
match value:
    case astichi_case(routes):
        pass
```

where `routes` is a multiple target. Many case contributions can be added to
the same target and will lower to multiple `case` clauses at materialize time.

## Goals

1. Add a target shape for `match_case` lists.
2. Let many contributions add cases to one target.
3. Keep authored source parseable Python.
4. Preserve pre-materialize round-tripping by emitting inserted cases as
   `astichi_insert`-decorated functions.
5. Run normal Astichi hygiene on each case contribution before lowering it
   into Python `match_case` nodes.
6. Keep Phase 1 intentionally narrow: wildcard cases with guards and bodies.

## Non-Goals

1. Do not introduce general pattern composition in the first slice.
2. Do not support generated case patterns that bind new names in Phase 1.
3. Do not support `elif` or `else` in case contribution functions.
4. Do not make `astichi_case(...)` a runtime function.
5. Do not make authored `astichi_insert(kind="case")` public API.

## Authored Target Surface

A match case target is declared by a marker-like case pattern:

```python
match event_type:
    case astichi_case(routes):
        pass
```

Rules:

- `astichi_case` is only valid as the outer call in a `match` case pattern.
- The argument must be a bare capture name. It names the case-list target.
- The target is multiple: zero or more inserted cases can target it before
  materialization, and materialization rejects unresolved mandatory targets
  unless an explicit optional-target policy is added later.
- The marker case body must be empty-equivalent in Phase 1: `pass` and
  Astichi comments are allowed; real runtime statements are rejected.
- The marker case is removed when materialized. Contributions replace it at
  the same case-list position.

This keeps the target visually located where the generated cases should land.
Ordinary fallback cases remain ordinary Python:

```python
match event_type:
    case astichi_case(routes):
        pass
    case _:
        raise ValueError(event_type)
```

## Authored Contribution Surface

A case contribution is a normal Astichi snippet whose root body contains one
function named `astichi_case`:

```python
def astichi_case():
    astichi_import(event_type)
    astichi_import(payload)
    if event_type == "create":
        result = build_create(payload)
        astichi_export(result)
```

The function form is intentional. It gives the contribution a concrete AST
scope that can later be serialized as an internal `astichi_insert` shell.

Rules:

- The function must be named `astichi_case`.
- It must have no parameters, decorators, return annotation, or type params.
- The body may start with statement-prefix boundary markers such as
  `astichi_import(...)`.
- After the prefix, the body must contain exactly one `if` statement.
- The `if.test` becomes the generated match-case guard.
- The `if.body` becomes the generated match-case body.
- `if.orelse` is rejected in Phase 1.
- The generated pattern is wildcard (`case _ if <guard>:`).

Phase 1 therefore maps the contribution above to:

```python
case _ if event_type == "create":
    result = build_create(payload)
    astichi_export(result)
```

before the residual marker strip removes `astichi_export`.

This guard-only shape is deliberately conservative. It covers dispatch cases
that test the match subject or imported context without introducing Python
pattern-binding hygiene yet.

## Builder Surface

Case targets should behave like other additive targets:

```python
builder = astichi.build()
builder.add.Root(astichi.compile(root_source))
builder.add.Create(astichi.compile(create_case_source))
builder.add.Delete(astichi.compile(delete_case_source))

builder.Root.routes.add.Create(order=0)
builder.Root.routes.add.Delete(order=10)
```

The descriptor and data-driven builder APIs should expose the same target as a
multiple target with shape `case`.

## Pre-Materialized Representation

`build()` must preserve round-trip information. It should not directly edit the
`match.cases` list into final Python cases. Instead, it should add internal
case insert shells near the match statement, using the same source-kind
contract as existing block and parameter insert shells:

```python
match event_type:
    case astichi_case(routes):
        pass
    case _:
        raise ValueError(event_type)

@astichi_insert(routes, kind="case", order=0, ref=Root.Create)
def __astichi_case__Root__routes__0__Create():
    astichi_import(event_type)
    astichi_import(payload)
    if event_type == "create":
        result = build_create(payload)
        astichi_export(result)

@astichi_insert(routes, kind="case", order=10, ref=Root.Delete)
def __astichi_case__Root__routes__10__Delete():
    astichi_import(event_type)
    astichi_import(payload)
    if event_type == "delete":
        result = build_delete(payload)
        astichi_export(result)
```

These shells are internal metadata, not runtime functions. Emitted
pre-materialized source remains parseable and re-ingestable with
`source_kind="astichi-emitted"`.

Placement can be immediately after the owning `match` statement in Phase 1.
The implementation should retain enough ref/path metadata to distinguish
descendant match targets the same way block insert shells do today.

## Materialized Lowering

At materialize time:

1. Validate each `case astichi_case(target)` has all required case insert
   shells and that every case insert shell has a matching target.
2. Run hygiene while marker cases and case insert shells are still present.
3. For each target marker case, collect matching case shells in order.
4. For each shell:
   - remove leading boundary marker statements from the shell body after they
     have served hygiene
   - peel the single `if`
   - convert `if.test` to `match_case.guard`
   - convert `if.body` to `match_case.body`
   - use wildcard pattern `MatchAs(name=None)`
5. Replace the marker case with the generated `match_case` list.
6. Remove the case insert shell functions.
7. Strip residual Astichi markers as usual.

Example materialized result:

```python
match event_type:
    case _ if event_type == "create":
        result = build_create(payload)
    case _ if event_type == "delete":
        result__astichi_scoped_1 = build_delete(payload)
    case _:
        raise ValueError(event_type)
```

The second `result` may be hygiene-renamed because both contributions assign
into the same final Python scope.

## Hygiene Contract

Case contributions must participate in hygiene as fresh Astichi scopes, just
like block insertions.

Important details:

- The internal `@astichi_insert(..., kind="case")` function is the fresh scope
  boundary before materialization.
- `astichi_import(...)`, `astichi_pass(...)`, `astichi_export(...)`,
  `astichi_keep(...)`, explicit `arg_names=`, and builder identifier bindings
  should behave inside a case contribution the same way they behave inside a
  block contribution.
- The guard expression and the case body are both owned by the case
  contribution's fresh Astichi scope during hygiene.
- After hygiene, lowering into `match_case` must reuse the already-renamed AST
  nodes; it must not reparse source or run a second rename pass.
- Multiple case contributions targeting the same marker are sibling Astichi
  scopes. Stores with the same spelling should be renamed apart unless the
  user explicitly keeps/imports/passes them according to existing boundary
  rules.
- The match subject expression remains in the target/root scope. A contribution
  that needs a subject name should import that name explicitly:

```python
match event_type:
    case astichi_case(routes):
        pass
```

```python
def astichi_case():
    astichi_import(event_type)
    if event_type == "create":
        ...
```

If the match subject is not a simple name, Phase 1 does not provide an implicit
subject alias. Users can bind one in the root before the match.

### Pattern Binding Deferred

Python match patterns can bind names in ways that are not normal expression
stores. Phase 1 avoids that by always generating wildcard patterns.

Later pattern support must extend scope analysis to collect pattern bindings
as synthetic bindings for each generated case, including:

- `case Name():` class patterns
- capture patterns
- `as` patterns
- mapping and sequence pattern captures

Until that work is specified, case contributions must not introduce generated
pattern binders.

## Documentation Snippets

Reference docs should add a new marker page or section, tentatively
`docs/reference/marker-case-targets.md`, linked from marker overview and
builder/addressing pages.

### Minimal Route Example

Root:

```python
def dispatch(event_type, payload):
    match event_type:
        case astichi_case(routes):
            pass
        case _:
            raise ValueError(event_type)
```

Create contribution:

```python
def astichi_case():
    astichi_import(event_type)
    astichi_import(payload)
    if event_type == "create":
        return ("create", payload)
```

Builder:

```python
builder.add.Root(astichi.compile(root_source))
builder.add.Create(astichi.compile(create_source))
builder.Root.routes.add.Create()
```

Generated materialized shape:

```python
def dispatch(event_type, payload):
    match event_type:
        case _ if event_type == "create":
            return ("create", payload)
        case _:
            raise ValueError(event_type)
```

### Hygiene Example

Two case contributions both assign `result`:

```python
def astichi_case():
    astichi_import(event_type)
    if event_type == "create":
        result = "created"
        return result
```

```python
def astichi_case():
    astichi_import(event_type)
    if event_type == "delete":
        result = "deleted"
        return result
```

Materialized output should rename one sibling case's local:

```python
match event_type:
    case _ if event_type == "create":
        result = "created"
        return result
    case _ if event_type == "delete":
        result__astichi_scoped_1 = "deleted"
        return result__astichi_scoped_1
```

## Golden Test Specs

Add canonical golden fixtures rather than only bespoke unit tests.

Suggested source:

```text
tests/data/gold_src/match_case_targets.py
```

Suggested goldens:

```text
tests/data/goldens/pre_materialized/match_case_targets.py
tests/data/goldens/materialized/match_case_targets.py
```

The fixture should build:

1. A root function with a `match` statement containing
   `case astichi_case(routes): pass`.
2. Two case contributions added to `routes` with distinct `order` values.
3. A fallback ordinary `case _:` after the marker case.
4. Case contributions that import the match subject and assign same-spelled
   locals so hygiene behavior is visible.
5. Runtime assertions that:
   - `"create"` dispatches to the first case
   - `"delete"` dispatches to the second case
   - an unknown value reaches the fallback

The pre-materialized golden should assert:

- the marker case remains in the `match`
- inserted case contributions appear as
  `@astichi_insert(routes, kind="case", ...)` shells
- the shell bodies retain `astichi_import(...)` and the single `if`
- shell `ref=` metadata is present for staged addressing

The materialized golden should assert:

- no `astichi_case`, `astichi_insert`, or `astichi_import` remains
- the marker case is replaced by two real `case _ if ...:` clauses
- case order follows edge order and insertion order
- sibling same-name locals are hygienically renamed
- fallback cases authored after the marker remain after the inserted cases

Focused non-golden tests should cover diagnostics:

- `astichi_case(...)` outside a `match` case pattern rejects
- `case astichi_case("routes")` rejects because target is not a bare name
- marker case body with real statements rejects
- contribution missing the `def astichi_case():` wrapper rejects
- contribution function with parameters/decorators rejects
- contribution function with zero or multiple non-prefix `if` statements
  rejects
- contribution `if` with `else` rejects in Phase 1
- dangling case insert shell rejects at materialize
- unresolved mandatory case target rejects at materialize
- emit/compile/build-more round-trip preserves case insert metadata

## Implementation Slices

1. Marker recognition and diagnostics:
   - recognize `case astichi_case(target): pass`
   - add a `case` target shape to inventory/ports
   - reject invalid target and contribution forms early
2. Build merge:
   - collect case contributions from `def astichi_case(): ...`
   - emit `@astichi_insert(..., kind="case", ref=...)` shells
   - sort multiple case contributions by order and edge index
3. Hygiene integration:
   - treat case insert shells as fresh Astichi scopes
   - ensure boundary imports/passes/exports work in guards and bodies
4. Materialize lowering:
   - validate target/shell matching
   - peel `if` into `match_case.guard` and `match_case.body`
   - replace marker case with generated cases
   - remove case insert shells
5. Docs and goldens:
   - add reference docs and snippets
   - add golden fixture and diagnostics tests

## Open Questions

1. Should unresolved `astichi_case` targets ever be optional, or should they
   follow mandatory block-hole behavior?
2. Should the marker case body be allowed to provide default/fallback body
   statements, or should fallback always be an ordinary neighboring case?
3. Should Phase 2 support explicit patterns through a nested mini-surface, for
   example `match astichi_pattern(): case <pattern> if <guard>: ...`?
4. Should the builder expose a typed `.cases` descriptor in addition to fluent
   `.routes.add.X()` for discoverability?
5. How should duplicate target names inside one `match` or structural body be
   handled: same behavior as duplicate block holes, or reject for clarity?
