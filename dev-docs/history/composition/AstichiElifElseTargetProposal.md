# Astichi Elif Target Proposal

Status: proposal.

This proposal defines an Astichi surface for composing additional `elif`
branches into an existing `if`/`elif` chain.

`else:` clause elision is intentionally deferred. It probably wants a separate
design rather than being treated as an ordinary block-hole variant.

The motivating shape is:

```python
if condition:
    pass
elif astichi_elif(branches):
    pass
else:
    fallback()
```

where `branches` is a multi-add elif target. Many elif contributions can be
added to the same target and lower to multiple real `elif` branches.

## Goals

1. Add a clause-shape target for additive `elif` chains.
2. Let many contributions add elif branches to one chain target.
3. Keep authored source parseable Python.
4. Preserve pre-materialize round-tripping by emitting inserted branches as
   `astichi_insert`-decorated functions.
5. Run normal Astichi hygiene on each contribution before lowering it into
   final `If` / `If.orelse` AST.
6. Define scope/index tools so target markers and production shells match
   correctly in nested and staged compositions.
7. Expose the new shape in `Composable.describe()` as new `MarkerShape`,
   `HoleDescriptor`, and `ProductionDescriptor` records, reusing existing
   `MULTI_ADD` add-policy semantics.

## Non-Goals

1. Do not implement `astichi_else(...)` in this slice.
2. Do not generalize optional/elidable block holes.
3. Do not relax the existing rule that ordinary unresolved
   `astichi_hole(...)` rejects.
4. Do not introduce a standalone-`if`-position extensible chain target.
   `astichi_elif(...)` is valid only in true elif position.
5. Do not make authored `astichi_insert(kind="elif")` public API.
6. Do not support generated `if.orelse` inside elif contribution bodies in
   Phase 1.
7. Do not introduce optional empty-tolerant `astichi_elif(...)` policy in
   Phase 1; unresolved elif targets reject like mandatory holes.
8. Do not introduce cross-branch `astichi_export` join semantics in Phase 1.

## Authored Target Surface

An elif chain target is declared by a marker call in elif test position:

```python
if cond1:
    body1
elif astichi_elif(branches):
    pass
```

Rules:

- `astichi_elif(...)` is valid only as the `test` of an `If` that is the
  sole statement of an enclosing `If.orelse`, i.e. real Python elif
  position.
- Standalone `if astichi_elif(...):` rejects.
- The argument must be a single bare capture name. It names the chain target.
  String literals, multiple positional args, keyword arguments, and `_`
  reject.
- The target is multiple: zero or more inserted elif branches can target it
  before materialization. Materialization rejects unresolved mandatory elif
  targets.
- The marker body must be empty-equivalent: `pass` plus optional
  `astichi_comment(...)` markers. Other statements reject.
- A chain may contain non-marker `elif` branches before or after the marker;
  lowering preserves their relative order.
- Phase 1 rejects duplicate `astichi_elif(...)` target names within the same
  Astichi structural scope/ref path. This avoids ambiguous matching between
  inserted productions and marker nodes. Use distinct target names for
  multiple insertion points.

## Authored Contribution Surface

An elif contribution is a normal Astichi snippet whose root body contains
exactly one function named `astichi_elif`:

```python
def astichi_elif():
    astichi_import(event_type)
    astichi_import(payload)
    if event_type == "create":
        result = build_create(payload)
        return result
```

The function form is intentional. It gives the contribution a concrete AST
scope that can be serialized as an internal `astichi_insert` shell.

Rules:

- The function must be named `astichi_elif`.
- It must have no parameters, decorators, return annotation, or type params.
- The body may start with statement-prefix boundary markers accepted at
  Astichi-scope roots: `astichi_import`, `astichi_export`, `astichi_keep`,
  `astichi_bind_external`, `astichi_pyimport`, and `astichi_comment`.
- `astichi_pass(...)` is not a statement-prefix marker. It remains available in
  its existing value-form positions, including inside the generated branch test
  or branch body where ordinary expressions are legal.
- After the prefix, the body must contain exactly one `if` statement.
- The `if.test` becomes the generated elif test.
- The `if.body` becomes the generated elif body.
- `if.orelse` rejects in Phase 1.
- Statements other than prefix markers and the single `if` reject outside the
  `if.body`.
- Inside `if.body`, normal Python statements are allowed, but Phase 1 rejects
  `yield`, `yield from`, `await`, `break`, and `continue`. Context-aware
  validation for those control-flow forms can be added later.
- `return` is allowed only when the owning elif target is inside a
  `FunctionDef` or `AsyncFunctionDef`; module-level targets with generated
  returns reject before materialized source is emitted.
- `raise` is allowed.
- A walrus expression `(name := value)` in `if.test` rejects in Phase 1
  because the binding would leak into the enclosing function scope through the
  generated elif test.

## Builder Surface

Elif targets behave like other additive targets:

```python
builder = astichi.build()
builder.add.Root(astichi.compile(root_source))
builder.add.Create(astichi.compile(create_elif_source))
builder.add.Delete(astichi.compile(delete_elif_source))

builder.Root.branches.add.Create(order=0)
builder.Root.branches.add.Delete(order=10)
```

The descriptor and data-driven builder APIs should expose the same target as a
multi-add hole with shape `ELIF_CLAUSE`.

## Pre-Materialized Representation

`build()` must preserve round-trip information. It must not directly mutate
the chain structure pre-materialize.

For each elif contribution, build emits an internal
`@astichi_insert(..., kind="elif", ref=..., order=...)` shell adjacent to the
owning outermost `If`:

```python
if cond1:
    body1
elif astichi_elif(branches):
    pass
else:
    fallback()

@astichi_insert(branches, kind="elif", order=0, ref=Root.Create)
def __astichi_elif__Root__branches__0__Create():
    astichi_import(event_type)
    astichi_import(payload)
    if event_type == "create":
        result = build_create(payload)
        return result
```

The `ref=` encoding follows the existing fluent form used by other insert
shells (see `astichi.shell_refs`) and keeps that existing meaning: it identifies
the source/contribution path, not the target-site path. Target matching must not
use `ref=` as the target locator.

Shell placement is a sibling of the outermost owning `If` statement, appended at
the end of the same enclosing suite. This rule applies regardless of whether
the chain is nested inside a function body, `try` body, `with` body, outer `if`
body, or loop body.

Pre-materialize emitted source remains parseable and re-ingestable with
`source_kind="astichi-emitted"`.

## Scope Tools For Target/Production Matching

Target name alone is not enough to match elif holes with productions. The
implementation needs explicit scope/index tools for clause targets, similar in
spirit to the existing shell/ref path indexing used for block targets.

Phase 1 should add an internal `ClauseTargetIndex` or equivalent that records
each recognized `astichi_elif(target)` marker as:

- `shape`: `ELIF_CLAUSE`
- `target_name`
- current Astichi target `ref_path`
- target `leaf_path`
- owning structural suite identity / locator
- outermost owning `If`
- marker `If`
- marker ordinal within the chain/suite

The matching key for Phase 1 should be:

```text
(shape, target_ref_path, target_name, leaf_path)
```

with duplicate `(ELIF_CLAUSE, target_ref_path, target_name, leaf_path)` targets
rejected during recognition or build. This conservative rule avoids matching
one production to two unrelated markers in the same Astichi structural scope.
Existing block-hole duplicate semantics do not need to be reused for clause
targets.

Build merge should also maintain an `ElifProductionIndex` for
`@astichi_insert(..., kind="elif", ref=...)` shells:

- `target_name`
- target structural suite locator inherited from shell placement
- target `ref_path` derived from the current traversal position, not from
  `ref=`
- target `leaf_path`
- source `ref_path` from `ref=` for provenance and diagnostics only
- `order`
- edge index / registration index
- shell node

Materialize should use the same key to validate:

- every `ELIF_CLAUSE` target has at least one matching production
- every `production.elif` shell has exactly one matching target
- no production crosses into a sibling or nested suite with the same textual
  target name

The current-ref traversal should mirror `_replace_targets_in_tree`: when the
walk enters a staged insert/root shell, it updates the ref path; targets and
productions inside that shell are keyed against the promoted descendant path.
For elif shells, the traversal key is the target-side key derived from shell
placement and current traversal state; the `ref=` keyword remains source-side
metadata.

## Unroll And Indexed Target Behavior

`astichi_elif(target)` is renamed per iteration inside `astichi_for(...)`, using
the same suffix convention as `astichi_hole(target)`.

```python
for item in astichi_for((1, 2)):
    if item < 0:
        pass
    elif astichi_elif(branches):
        pass
```

unrolls the target names to `branches__iter_0` and `branches__iter_1`.

Builder indexed edges therefore use the existing leaf-path convention:

```python
builder.Root.branches[0].add.First()
builder.Root.branches[1].add.Second()
```

During build with unroll enabled, the target address
`target_name="branches", leaf_path=(0,)` is resolved to the post-unroll target
name `branches__iter_0`. As with current unrolled block holes, descriptor output
after unroll may expose the source-visible synthetic name rather than reverse
projecting it back to `target_name="branches", leaf_path=(0,)`; reverse
projection is deferred unless Astichi later retains explicit unroll provenance.

Golden tests should include nested suites and staged builds specifically to
prove that `branches` in one nested `if` does not accidentally receive
productions meant for another `branches` marker.

## Materialized Lowering

Given the marker structure:

```text
parent_If = If(
    test=cond1,
    body=body1,
    orelse=[
        marker_If = If(
            test=astichi_elif(branches),
            body=[Pass()],
            orelse=tail_orelse,        # may be [], else body, or another elif If
        ),
    ],
)
```

Materialize:

1. Validate target/production matching with the clause target index.
2. Run hygiene with the marker `If` and elif insert shells still in place.
   Each contribution is its own Astichi scope.
3. For each elif insert shell, sorted by `order` then edge index, peel the
   `def astichi_elif():` wrapper and inner `if`; yield
   `(test_expr, body_stmts)`.
4. Right-fold contributions into a nested `If` chain whose deepest `orelse`
   is the original `marker_If.orelse`:

   ```text
   chain = marker_If.orelse
   for contribution in reversed(contributions):
       chain = [If(test=contribution.test,
                   body=contribution.body,
                   orelse=chain)]
   ```

5. Replace `marker_If` with the head of `chain` in `parent_If.orelse`.
6. Remove the elif insert shells.
7. Strip residual Astichi markers as usual; if a generated branch body becomes
   empty after stripping, materialize inserts an explicit `pass`.

Example materialized result:

```python
def dispatch(event_type, payload):
    if event_type == "":
        raise ValueError("empty event_type")
    elif event_type == "create":
        return build_create(payload)
    elif event_type == "delete":
        return build_delete(payload)
    else:
        return ("fallback", event_type)
```

## Hygiene Contract

Elif contributions participate in hygiene as fresh Astichi scopes, just like
block insertions.

- Each `@astichi_insert(..., kind="elif")` function is a fresh Astichi-scope
  boundary before materialization.
- Boundary markers and value-form boundary surfaces behave inside an elif
  contribution the same way they behave inside ordinary block contributions:
  `astichi_import`, value-form `astichi_pass(...)`, `astichi_export`,
  `astichi_keep`, `astichi_bind_external`, `astichi_pyimport`,
  `__astichi_arg__` / `__astichi_keep__` suffixes, builder identifier
  bindings, and `arg_names=` overlays.
- The elif test expression and elif body are both owned by the contribution's
  fresh scope during hygiene.
- After hygiene, lowering must reuse already-renamed AST nodes; no reparse and
  no second rename pass.
- Multiple contributions targeting the same marker are sibling Astichi scopes.
  Stores with the same spelling rename apart according to existing sibling
  insertion rules.
- Non-marker `If` test expressions and the surrounding function body remain in
  the enclosing scope. A contribution that needs an outer name must import it
  with `astichi_import(name)`.
- `astichi_pyimport(...)` inside a contribution hoists to module head at
  materialize, identical to block-contribution behavior.

### Export Semantics Deferred

Phase 1 does not add special cross-branch join semantics for
`astichi_export(name)`. Export markers inside elif contributions should follow
the existing supply/strip behavior only.

A later proposal can define an explicit branch-join feature for publishing one
logical name from mutually exclusive branches. That feature needs dedicated
hygiene rules and tests and should not be coupled to the first elif target
implementation.

## Describe API

Elif targets surface as a new shape on `Composable.describe()`.

### `MarkerShape` Addition

Add one behavior-bearing singleton:

- `ELIF_CLAUSE` — clause-shape; lowering is right-fold into `If.orelse`;
  contribution shape is `def astichi_elif(): if expr: body`.

The singleton owns validation, lowering, and descriptor projection, matching
the pattern used for existing `MarkerShape` / `AddPolicy` /
`PortMutability` singletons.

### Descriptor And Inventory Layering

Descriptor data follows the current Astichi layering:

- `HoleDescriptor` remains structural compatibility data only. For elif
  targets it exposes a port whose `shape` is `ELIF_CLAUSE`.
- `ComposableHole` carries user-facing target data: `name`, `address`,
  `port`, `add_policy=MULTI_ADD`, and the clause empty policy.
- Inventory carries the persistent metadata used to reconstruct descriptors.
  Add a clause-specific hole payload such as
  `ClauseHoleInventoryPayload(PortInventoryPayload)` with
  `when_empty=REJECT_EMPTY`. The inventory-to-descriptor adapter projects that
  payload onto `ComposableHole`.

Do not put `name`, `add_policy`, or empty-policy state directly on
`HoleDescriptor`.

### `ProductionDescriptor`

Elif contributions produce `production.elif` records.

### Inventory `kind` Strings

New inventory `kind` strings:

- `hole.elif`
- `production.elif`

### `ComposableHole` And `TargetAddress`

`TargetAddress` is unchanged structurally. Address resolution uses the same
`root_instance` / `ref_path` / `target_name` / `leaf_path` model as every other
hole.

`ComposableHole` gains or exposes clause empty-policy metadata, e.g.
`when_empty=REJECT_EMPTY`, for `ELIF_CLAUSE` targets. Ordinary block holes do
not gain elif-specific empty semantics.

`productions_compatible_with(hole)` returns only `production.elif` records for
an elif hole.

## Documentation Snippets

Reference docs should add a new marker page or section, tentatively
`docs/reference/marker-clause-targets.md`, linked from marker overview and
builder/addressing pages.

### Minimal Elif Example

Root:

```python
def dispatch(event_type, payload):
    if event_type == "":
        raise ValueError("empty event_type")
    elif astichi_elif(branches):
        pass
    else:
        return ("fallback", event_type)
```

Create contribution:

```python
def astichi_elif():
    astichi_import(event_type)
    astichi_import(payload)
    if event_type == "create":
        return ("create", payload)
```

Builder:

```python
builder.add.Root(astichi.compile(root_source))
builder.add.Create(astichi.compile(create_source))
builder.Root.branches.add.Create()
```

Generated materialized shape:

```python
def dispatch(event_type, payload):
    if event_type == "":
        raise ValueError("empty event_type")
    elif event_type == "create":
        return ("create", payload)
    else:
        return ("fallback", event_type)
```

### Hygiene Example

Two elif contributions both assign `result`:

```python
def astichi_elif():
    astichi_import(event_type)
    if event_type == "create":
        result = "created"
        return result
```

```python
def astichi_elif():
    astichi_import(event_type)
    if event_type == "delete":
        result = "deleted"
        return result
```

Materialized output renames sibling locals apart:

```python
if event_type == "":
    raise ValueError("empty event_type")
elif event_type == "create":
    result = "created"
    return result
elif event_type == "delete":
    result__astichi_scoped_1 = "deleted"
    return result__astichi_scoped_1
```

## Golden Test Specs

Canonical successful coverage uses goldens. Bespoke tests cover recognition
and diagnostics only, per the repository test-coverage rule.

Suggested gold source:

```text
tests/data/gold_src/elif_targets.py
```

Suggested goldens:

```text
tests/data/goldens/pre_materialized/elif_targets.py
tests/data/goldens/materialized/elif_targets.py
```

The fixture should build:

1. A root function with a chain containing a hand-authored leading `if`, an
   `astichi_elif(branches)` marker, an additional hand-authored `elif` after
   the marker, and an ordinary `else` fallback.
2. Two elif contributions with distinct `order` values.
3. A nested-suite variant where the chain lives inside an outer `if`, `try`,
   `with`, and `for` body, to exercise shell placement and scope-index
   matching.
4. A staged-build variant where two nested chains both use the textual target
   name `branches` but different target ref paths, proving target/production
   matching does not cross scopes.
5. Contributions that import the same outer name to exercise scope isolation.
6. Runtime assertions for each chain shape.

The pre-materialized golden asserts:

- chain markers remain in place
- inserted contributions appear as `@astichi_insert(..., kind="elif", ...)`
  shells with source-side `ref=...` metadata in the standard fluent form
- shells appear as siblings of the outermost owning `If`, regardless of
  enclosing nesting
- duplicate textual target names in different target ref paths stay distinct

The materialized golden asserts:

- no `astichi_elif`, `astichi_insert`, `astichi_import`, `astichi_export`,
  `astichi_keep`, or other authored markers remain
- the marker elif is replaced by a real nested chain in the correct position
- non-marker `elif` branches before and after the marker keep their relative
  order
- ordinary authored `else` fallback remains
- ordering follows edge order and insertion order
- sibling locals rename apart under existing hygiene rules

Focused bespoke tests cover diagnostics that goldens cannot express:

- `astichi_elif(...)` in a non-elif position rejects
- invalid target argument shapes reject
- elif marker body contains real statements: rejects
- duplicate `(target_ref_path, target_name, leaf_path)` elif markers reject
- contribution missing `def astichi_elif():` wrapper rejects
- contribution wrapper has parameters / decorators / return annotation /
  type params: rejects
- contribution body lacks the single trailing `if`: rejects
- contribution body has multiple non-prefix `if` statements: rejects
- contribution `if.orelse` present: rejects
- contribution `if.test` contains walrus: rejects
- contribution body contains forbidden top-level statements outside the
  single `if`: rejects
- contribution body contains `yield`, `yield from`, `await`, `break`, or
  `continue`: rejects in Phase 1
- contribution body contains `return` but owning target is not inside a
  function: rejects
- dangling elif insert shell at materialize: rejects
- unresolved mandatory elif target at materialize: rejects
- `source_kind="authored"` rejects user-written
  `@astichi_insert(..., kind="elif", ...)`

Success-path round-trip (`emit` -> `compile` -> build-more -> materialize) is
asserted by the golden alone; no bespoke duplicate.

## Implementation Slices

0. Baseline:
   - start from a clean tree and tag the start point
   - run focused baseline tests for marker recognition, descriptors,
     build/materialize, unroll, and goldens
1. Marker recognition and diagnostics:
   - recognize `astichi_elif(target)` in real elif position
   - add `ELIF_CLAUSE` to `MarkerShape`
   - reject invalid target and contribution forms
   - reject duplicate `(ELIF_CLAUSE, target_ref_path, target_name, leaf_path)`
     markers
   - define `astichi_elif(target)` as renamed per iteration by unroll
2. Describe and inventory:
   - expose `ELIF_CLAUSE` hole descriptors
   - expose `production.elif` records
   - add clause empty-policy metadata to inventory and project it to
     `ComposableHole`
   - update `Composable.describe()` projection and inventory string snapshot
3. Scope/index tools:
   - add clause target indexing for marker `If` nodes
   - add elif production indexing for `kind="elif"` insert shells
   - validate one-target-to-many-productions matching by
     `(shape, target_ref_path, target_name, leaf_path)`
   - keep `ref=` as source/contribution provenance, not target identity
   - add nested-suite and staged-target-ref focused coverage
4. Build merge:
   - collect elif contributions from `def astichi_elif(): ...`
   - emit `@astichi_insert(..., kind="elif", ref=...)` shells
   - place shells as siblings of the outermost owning `If`
   - sort contributions by `order`, then edge index
5. Core materialize lowering and hygiene:
   - treat elif insert shells as fresh Astichi scopes
   - ensure boundary imports, value-form passes, pyimports, and suffixes work
     in elif tests and bodies
   - validate target / shell matching
   - peel elif contribution wrappers and right-fold into chain
   - remove insert shells; strip residual Astichi markers; pass-fill emptied
     suites
6. Staged, nested, and unroll integration:
   - prove staged target refs do not cross-wire duplicate textual names
   - prove nested suites place and match shells correctly
   - prove indexed `branches[i]` edges target post-unroll clause markers
   - prove sibling contribution locals rename apart under existing hygiene
7. Docs and goldens:
   - add reference docs and snippets
   - add golden fixture and diagnostic tests
   - update `dev-docs/AstichiSingleSourceSummary.md` marker table
8. Closeout:
   - run the full pytest suite
   - run the Python-version matrix
   - tag the final verified checkpoint

## Deferred Else Design

`else` elision is deferred. Defaulted block holes prove that Astichi can model a
whole branch marker as the target and lower a filled site to an ordinary
block-hole anchor before flattening. The reason to defer `else` is semantic
scope, not lack of an anchor mechanism.

A later design should decide whether else needs:

- a dedicated `kind="else"` internal insert shell
- a more general optional-suite target shape
- explicit empty-policy descriptors
- broader support for `for` / `while` / `try` `else` and `finally` suites
- replacement, elision, and fallback-selection semantics distinct from additive
  `elif` chains

## Open Questions

1. Should `astichi_elif(...)` ever support a later `ALLOW_EMPTY` policy that
   elides the marker entirely if no contributions arrive?
2. Should cross-branch publication be supported by a new explicit join marker
   or option, rather than overloading `astichi_export`?
3. Should `astichi_elif(...)` permit a leading-if-position usage in a later
   phase?
4. Should match-case Phase 1 be deferred until real pattern support is
   designed, with `astichi_elif` taking the first branch-composition role?
