# Astichi Single-Source Summary

This is the active summary document for Astichi.

Use this first. It is intentionally self-contained. It should be enough for a
new AI or engineer to continue the project without reading the rest of
`dev-docs/`.

`dev-docs/AstichiSingleSourceSummary.md` and `dev-docs/AstichiCodingRules.md`
are the only active dev-docs. Everything else under `dev-docs/historical/` is
archival context only: frozen, non-authoritative, and not required for active
work.

## 1. Current snapshot

- Goal: composable assembly of Python source snippets via valid-Python
  marker syntax, additive builder wiring, build-time merge, materialize-time
  hygiene, and emit-time round-trip support.
- Public package exports today: `astichi.compile`, `astichi.build`,
  `astichi.Composable`, `astichi.ComposableDescription`,
  `astichi.ComposableHole`, and `astichi.TargetAddress`.
- Implemented V3 parameter holes:
  - `name__astichi_param_hole__` declares a function-parameter insertion
    target in an ordinary `FunctionDef.args` parameter slot.
  - `def astichi_params(...): pass` and
    `async def astichi_params(...): pass` supply parameter payloads.
  - Build emits internal `@astichi_insert(name, kind="params", ref=...)`
    wrappers in pre-materialized source; final materialize consumes them into
    clean signatures.
  - Duplicate final parameter names reject instead of being repaired by
    hygiene; inserted parameters become target-function bindings before body
    boundary markers and hygiene run.
  - Real `def` / `async def` sites open normal Python function scopes:
    parameter names are function-scope bindings and hygiene must not rename
    them to repair a signature; body-local collisions rename away from the
    parameter binding.
- Managed Python import support is implemented:
  - `astichi_pyimport(module=..., names=(...))` declares managed
    `from module import name` bindings. `names=` must be a non-empty tuple of
    bare identifiers.
  - `astichi_pyimport(module=..., as_=alias)` declares managed plain imports.
    `astichi_pyimport(module=os)` is valid for a single-segment module; dotted
    plain imports require `as_=`.
  - `module=` accepts absolute dotted `Name` / `Attribute` paths and externally
    bound dotted strings via `astichi_ref(external=...)`.
  - Markers are valid only in the contiguous top-of-Astichi-scope statement
    prefix. That prefix may interleave direct statement-form
    `astichi_bind_external`, `astichi_import`, `astichi_keep`, and
    `astichi_export`.
  - Pyimport locals are real local bindings for name analysis and hygiene.
    Collisions are renamed through the same hygiene path, and final imports use
    Python alias syntax when needed.
  - Final materialize strips pyimport markers/carriers and emits ordinary
    Python imports at module head after a module docstring and ordinary
    `from __future__ import ...` statements.
  - Staged block and expression inserts preserve pyimport metadata. Expression
    payloads use internal `astichi_insert(..., pyimport=(...))` metadata before
    final stripping.
  - Child scopes can explicitly read an enclosing pyimport local with
    `astichi_import(..., outer_bind=True)` or
    `astichi_pass(..., outer_bind=True)`. Explicit `astichi_export(...)`
    publishes a pyimport local through normal export semantics.
  - Same-scope `name__astichi_arg__` is not automatically satisfied by a
    pyimport local; bind the arg explicitly or use the imported local name.
  - Ordinary Python `import` / `from ... import ...` statements support
    `__astichi_arg__` suffixes in import module strings, imported symbol names,
    and aliases, including relative `from .module__astichi_arg__ import ...`
    forms.
- Comment marker support is implemented:
  - `astichi_comment("...")` is a statement-only, literal-string marker for
    generated comments. It has no port, hygiene, descriptor, or runtime
    semantics.
  - ordinary `emit()` preserves comment markers for marker-bearing round trip.
  - `materialize()` strips comment markers for executable ASTs and inserts
    `pass` if stripping would empty a non-module suite.
  - `emit_commented()` is the narrow final-source surface: it materializes with
    comment preservation, renders preserved markers as same-indentation `#`
    comments, and does not accept a provenance option.
  - comment payloads replace exact `{__file__}` and `{__line__}` substrings
    only; other braces pass through. Source files are carried on private
    `_astichi_src_file` AST metadata attached during `compile(...)` and
    propagated by `copy_astichi_location(...)`.
- Implemented V2 work:
  - V2 Phase 1 external bind is complete.
  - V2 Phase 2 loop unroll: `2a`–`2e` complete. Phase 2 gate closed.
  - V2 Phase 3 polish has not started.
  - Identifier cluster `005` `5a` complete: the legacy `__astichi__` suffix
    and `astichi_definitional_name` call form are retired; new class/def
    suffix markers `__astichi_keep__` (hygiene directive, strip pass after
    hygiene) and `__astichi_arg__` (IDENTIFIER-shape demand port + gate
    before hygiene) are live.
  - Identifier cluster `005` `5b` complete: suffix recognition widened to
    `ast.Name` (Load/Store/Del) and `ast.arg` occurrences on top of
    class/def names; the arg gate and keep-strip pass scan the same
    surface; per-logical-slot port merging via the existing demand-port
    collapse by stripped name.
  - Identifier cluster `005` `5c` + `5d` complete: arg-resolver pass in
    materialize (runs after the gate, before hygiene) atomically
    substitutes every occurrence of a resolved slot; post-strip invariant
    asserts no `__astichi_arg__` survives. Public surface includes
    `astichi.compile(source, *, arg_names=..., keep_names=...,
    source_kind=...)`,
    `BasicComposable.bind_identifier(**names)`,
    `BasicComposable.with_keep_names(...)`, and
    `builder.add.<Name>(piece, *, arg_names=..., keep_names=...)`.
    Target-adder overlays are now edge-local:
    `builder.<Target>.<hole>.add.<Name>(..., arg_names=..., keep_names=..., bind=...)`
    specializes only that additive edge and does not mutate the registered
    instance record. Strict Astichi scope isolation is implemented.
    `wire_identifier(...)` on builder slot handles remains deferred;
    `ast.Attribute` identifier-slot positions are deferred until a concrete
    consumer appears. Issue 005 scope complete.
- Test status as of 2026-05-05:
  - full suite: `608 passed`
  - Python-version matrix: last recorded green for 3.12, 3.13, 3.14, and 3.15;
    not rerun for the comment-marker change
  - strict scope isolation is a contract, not a gap (§5.4, §9.3)
- Current next concrete action:
  - Treat Phase 2 unroll, the 005 identifier cluster, 006 cross-scope
    threading, V3 call-argument payloads, and V3 parameter holes as
    implemented.
  - The no-enum semantic singleton refactor is implemented for port placement,
    mutability, origins, marker contexts, call-argument regions, source kind,
    hygiene mode/roles, binding occurrence kind, and insert metadata kind.
    Implementation logic should use semantic methods such as
    `port.is_external_bind_demand()` and `marker.context.is_call_context()`
    rather than string-tag comparisons. Existing public/source boundary
    strings such as `source_kind="authored"` and emitted
    `kind="params"` metadata remain accepted and are normalized at the
    boundary.
  - The descriptor API is implemented as current public behavior. See §3.4.
  - Keep new behavior reflected in this summary, `docs/reference/`, snippets,
    and goldens. Do not maintain archived specs/plans as active docs.
  - Remaining work is polish/deferred surface area: Phase 3 cleanup,
    `wire_identifier(...)` shorthand if still wanted, `ast.Attribute`
    identifier-slot coverage when a concrete consumer exists, and any desired
    hard-error gate for unresolved implied/free names.

## 2. Governing principle and non-negotiable rules

### 2.1 Governing composition model

Astichi composes Python source at build time. Composition is recursive and may
remain partial.

The governing rule is:

- every input to a piece is in one of three states:
  - undefined: supply me from outside
  - defined: I have this; do not isolate me from it
  - free: neither; hygiene manages it
- markers exist to enumerate those states
- a state without a marker is an undocumented affordance
- a marker without a state is dead weight
- both are bugs

This is the framework behind the identifier-shape and cross-scope work:

- Issue 005 fills in the within-scope identifier state grid
- Issue 006 fills in the boundary crossings between Astichi scopes
- Issue 004 is the soundness gate that rejects silent crossings or silent
  undefined state

### 2.2 Non-negotiable rules

These are the rules that should not be re-litigated during implementation.

- Source is authoritative.
  - If emitted source is edited, the edited source wins.
  - Provenance may restore AST/source-location information only.
  - Provenance must not carry holes, binds, inserts, exports, builder graph
    state, or hidden semantic payloads.
- Emitted source must remain valid Python.
- Marker arguments are identifier-like references, not string literals.
- The builder is additive-first.
  - No replacement semantics.
  - No deep descendant traversal.
  - No optional-offer semantics.
- The fluent builder is a DSL over a plain raw API.
  - Every fluent operation should have a raw equivalent.
- Hygiene runs once, inside `materialize()`, when markers are in final
  position.
- A recognized marker with no consumer is a bug.
  - Reject it at the materialize gate rather than silently tolerating it.
- Preserve lexical keep semantics.
  - `astichi_keep(name)` means that spelling is pinned and must not be renamed.
- Scope isolation is strict.
  - Every Astichi scope owns its own lexical name space.
  - Cross-scope wiring is explicit: `astichi_import` / `astichi_pass`
    / `astichi_export`, or the builder-level `arg_names=` /
    `keep_names=` / `builder.assign`.
  - Free-name references inside a shell that are not wired across the
    boundary are local to that shell. Astichi does not guess.
  - See §5.4 for the full contract.
- Pre-materialize `emit()` and `materialize()` have different contracts.
  - pre-materialize `emit()` preserves markers and supports marker-bearing
    round-trip via `emit()` -> `compile()`
  - `materialize()` closes hygiene, strips executable-only markers, and rejects
    unresolved mandatory state
- `materialize().emit(provenance=False)` must be executable Python with no
  surviving marker call sites
- `emit_commented()` is a peer final-output surface to `materialize()`: it
  renders `astichi_comment(...)` markers as real Python comments and does not
  add Astichi provenance
- Implementation stays layered.
  - `frontend -> lowering -> hygiene -> model -> builder -> materialize -> emit`
- Do not store absolute filesystem paths in committed docs/config/examples/tests.

## 3. Public surface that exists today

### 3.1 Compile

`astichi.compile(source, file_name=None, line_number=1, offset=0)`

- Parses source into a composable.
- Uses ghost-padding rather than AST line-number rewriting:
  - prepend `line_number - 1` newlines
  - prepend `offset` spaces only for single-line snippets
- If the single-line offset causes `IndentationError`, parse again without the
  column padding.
- Returns a `FrontendComposable`, which is also a `Composable`.

This behavior is locked. Do not replace it with post-parse AST walks to rewrite
locations.

### 3.2 Build

`astichi.build() -> BuilderHandle`

- `builder.add.A(comp)` registers root instance `A`.
- `builder.add.Step[i](comp)` registers indexed family members such as
  `Step[0]`, `Step[1]`, ... as distinct root instances under one stem.
- `builder.A` returns a handle for a registered root; **`A` is the stable graph
  id** (not a hygiene output name from inside a piece).
- If a stem has indexed family members and no base instance of the same stem,
  `builder.Step[i]` selects that family member for later wiring; after
  selection it behaves like an ordinary root instance handle.
- `builder.A.slot.add.B(order=0)`, `builder.A.slot[i, ...]` — additive wiring and
  indexed hole paths. On the target-adder surface, `arg_names=` /
  `keep_names=` / `bind=` are edge-local overlays, not mutations of the
  registered source instance.
- `builder.Root.slot.add.Step[i](...)` wires one indexed family member as the
  source instance for that edge.
- `builder.assign.<Src>… .to().<Dst>…` — cross-instance boundary wiring. The
  fluent chain can carry **ref paths** into nested insert shells (`AssignBinding`
  `source_ref_path` / `target_ref_path`), not only `Src` / `Dst` at the root.
- Data-driven named equivalents are available for fluent operations:
  `builder.add("Root", comp)`, `builder.instance("Root").target("slot").add("Step")`,
  `builder.target(root_instance="Root", target_name="slot", ...)`, and
  `builder.assign(source_instance=..., inner_name=..., target_instance=..., outer_name=...)`.
  The named API uses the same graph records and validation semantics as the
  fluent API, and is the intended surface for generated mappers.
- `builder.add("Step", piece, indexes=(2,), arg_names=..., keep_names=...)`
  is the named equivalent of `builder.add.Step[2](...)`.
- `builder.instance("Step", indexes=(2,))` selects indexed family members by
  data rather than by attribute/index syntax.
- `InstanceHandle.target(name)`, `TargetHandle.target(name)`, and
  `TargetHandle.index(*indexes)` are the named path-walk equivalents of
  fluent `.<name>` and `[i]` target chaining.
- `target.add("Step", indexes=(2,), order=..., arg_names=..., keep_names=...,
  bind=...)` is the named equivalent of
  `target.add.Step[2](...)`; `arg_names`, `keep_names`, and `bind` remain
  edge-local overlays.
- `builder.assign(...)` accepts `source_ref_path` and `target_ref_path` data
  directly and creates the same `AssignBinding` as the fluent
  `builder.assign.<Src>...to().<Dst>...` chain.
- Leading-underscore instance and target names are available through explicit
  named calls such as `builder.add("_Root", piece)` and
  `builder.instance("_Root").target("_slot")`; fluent attribute access still
  rejects leading underscores.
- `builder.target(...)` also accepts descriptor target data:
  `builder.target(hole.with_root_instance("Root"))` or a resolved
  `TargetAddress`. Unresolved descriptor addresses reject.
- `builder.build()` merges the graph to one composable.

**Merge ordering:** lower `order` inserts first; equal `order` uses first-registered
edge first.

**Indexed family rule:** a stem is either a base instance (`Step`) or an
indexed family (`Step[i]`), never both. Mixing the two rejects so `builder.Step`
and `builder.Step[i]` stay unambiguous.

**Names vs graph identity:** ref paths key off **composition structure** in the
graph. **Lexical** names in emitted Python can still be renamed by hygiene. For
multi-stage pipelines that must not depend on emitted spellings or on treating a
raw AST path string as the only long-lived id, **deferred: aliases** — bind a
stable logical name to a fully qualified build reference (instance + ref path +
role) that survives a `build()` stage.

### 3.3 Composable

Abstract surface:

- `emit(provenance: bool = True) -> str`
- `emit_commented() -> str`
- `materialize() -> object`
- `describe() -> ComposableDescription`

Concrete carrier:

- `BasicComposable`
  - immutable dataclass
  - fields: `tree`, `origin`, `markers`, `classification`,
    `demand_ports`, `supply_ports`, `bound_externals`
  - method: `bind(mapping=None, /, **values) -> BasicComposable`

### 3.4 Descriptor API

`Composable.describe()` is the stable public self-description surface for
data-driven composition. It returns immutable descriptor value objects and does
not expose the builder graph as the primary API.

Public package exports:

- `ComposableDescription`
- `ComposableHole`
- `TargetAddress`

Additional descriptor classes are exported from `astichi.model` for advanced
typing and tooling:

- `AddPolicy`, `SINGLE_ADD`, `MULTI_ADD`
- `PortDescriptor`
- `HoleDescriptor`
- `ProductionDescriptor`
- `ExternalBindDescriptor`
- `IdentifierDemandDescriptor`
- `IdentifierSupplyDescriptor`

Descriptor semantic fields use behavior-bearing singleton/value objects, not
enums or passive string tags:

- `MarkerShape`
- `PortPlacement`
- `PortMutability`
- `PortOrigin` / `PortOrigins`
- `AddPolicy`
- `Compatibility`

Diagnostic/source names remain strings where they are actual identifiers or
addresses (`name`, `target_name`, `root_instance`, etc.).

`ComposableDescription` fields:

- `holes`: additive target holes only
- `productions`: things this composable can add to compatible holes
- `demand_ports` / `supply_ports`: stable public port descriptors
- `external_binds`: `astichi_bind_external(...)` value demands
- `identifier_demands` / `identifier_supplies`: explicit identifier wiring
  surfaces with descendant `ref_path`

Convenience methods:

- `holes_named(name) -> tuple[ComposableHole, ...]`
- `single_hole_named(name) -> ComposableHole`
- `productions_compatible_with(hole) -> tuple[ProductionDescriptor, ...]`

`ComposableHole` describes one additive target:

- `name`: authored target name
- `descriptor`: `HoleDescriptor`
- `address`: `TargetAddress`
- `port`: `PortDescriptor`
- `add_policy`: `SINGLE_ADD` or `MULTI_ADD`

`TargetAddress` is the data-driven builder address:

- `root_instance: str | None`
- `ref_path: tuple[str | int, ...]`
- `target_name: str`
- `leaf_path: tuple[int, ...]`

`root_instance=None` is valid descriptor metadata, but not executable builder
input. Resolve it with `hole.with_root_instance("Root")` or
`hole.address.with_root_instance("Root")` after registering the composable.
`builder.target(...)` accepts either a `TargetAddress` or a `ComposableHole`
directly and rejects unresolved addresses. Keyword overrides are accepted only
when they match the descriptor address.

Descriptor addresses use the same shell-ref machinery as builder target
validation. For built/staged composables, preserved insert-shell refs become
the descriptor `ref_path`, so a hole inside `Pipeline.Root.Inner.slot` is
described as `ref_path=("Root", "Inner")`, `target_name="slot"`.

Unrolled holes currently describe the source-visible synthetic name rather than
reverse-projecting to `leaf_path`. For example, `slot__iter_0` is exposed as
`TargetAddress(target_name="slot__iter_0", leaf_path=())`. Reverse-projecting
that to `target_name="slot", leaf_path=(0,)` is intentionally not implemented:
the AST does not distinguish a generated `slot__iter_0` from an authored hole
with the same spelling unless Astichi later retains unroll provenance or
reserves `__iter_<n>` target suffixes.

Add policy mapping:

- block holes: `MULTI_ADD`
- positional variadic holes (`*astichi_hole(...)`): `MULTI_ADD`
- named variadic holes (`**astichi_hole(...)` / dict expansion): `MULTI_ADD`
- parameter holes: `MULTI_ADD`, still subject to final signature validation
- scalar expression holes: `SINGLE_ADD`
- identifier demands and external binds are not additive holes

Production descriptors mirror current materialize/build behavior:

- ordinary non-payload snippets expose block productions
- implicit expression snippets expose expression productions
- `astichi_funcargs(...)` payloads expose expression-family productions and
  compatibility is region-aware for `*` and `**` targets
- `astichi_params(...)` payloads expose parameter productions
- `astichi_export(...)` exposes identifier supply descriptors, not additive
  productions
- `astichi_bind_external(...)` exposes external value demands, not productions

Compatibility helpers are planning aids. Build/materialize remains
authoritative and still performs final shape, payload, duplicate-keyword,
signature, hygiene, and unresolved-demand validation.

Identifier wiring descriptors intentionally reuse the existing named
`builder.assign(...)` API:

```python
builder.assign(
    source_instance="Step",
    source_ref_path=source.ref_path,
    inner_name=source.name,
    target_instance="Root",
    target_ref_path=target.ref_path,
    outer_name=target.name,
)
```

No `AssignAddress` object exists today.

### 3.5 Emit, materialize, and provenance contract

Current implementation reality:

- pre-materialize `emit()` preserves markers and is intended to recompile into a
  structurally equivalent composable
- `materialize()` strips/realizes the executable marker surface and closes
  hygiene
- `emit_commented()` runs the materialize pipeline with comment preservation,
  renders preserved `astichi_comment(...)` statement markers as `#` comments,
  and returns source without provenance
- `materialize().emit(provenance=False)` is expected to be runnable Python
- `emit(provenance=True)` appends one trailing comment:
  - `# astichi-provenance: <payload>`
- round-trip helpers already exist in `src/astichi/emit/api.py`
- comment form is the tested implementation reality

## 4. Marker surface: current status

| Marker / surface | Status | Notes |
|---|---|---|
| `astichi_hole(name)` | implemented | Demand port. Shape inferred from AST position. |
| `@astichi_insert(name, order=...)` | internal/emitted | Block-form supply metadata. Must match a hole. Rejected by default authored `compile(...)`; only accepted with `source_kind="astichi-emitted"`. |
| `astichi_funcargs(...)` | implemented | Authored call-argument payload surface. Lowered through generated internal placement wrappers. |
| `astichi_insert(name, expr)` | internal/emitted | Generated placement metadata for expression targets. Rejected by default authored `compile(...)`; only accepted with `source_kind="astichi-emitted"`. |
| `name__astichi_param_hole__` | implemented | Function-parameter insertion target. Valid only on ordinary function parameters. |
| `def astichi_params(...): pass` / `async def astichi_params(...): pass` | implemented | Authored parameter payload surface. Body must be empty-equivalent. |
| `@astichi_insert(name, kind="params", ref=...)` | internal/emitted | Parameter placement metadata. Rejected by default authored `compile(...)`; consumed before final hygiene. |
| `astichi_keep(name)` | implemented | Pins lexical spelling; stripped during materialize. |
| `astichi_export(name)` | implemented | Supply-side export; stripped during materialize. |
| `astichi_bind_external(name)` | implemented | External literal bind demand. |
| `astichi_for(domain)` | implemented | Compile-time loop domain for `build(unroll=...)`; supports literal tuples/lists, literal `range(...)`, and bind-fed literal domains. |
| `astichi_pyimport(module=..., names=(...))` / `astichi_pyimport(module=..., as_=...)` | implemented | Managed Python import marker. Valid only in a top-of-Astichi-scope statement prefix. Materialize emits ordinary imports at module head after docstring/future imports. Expression-prefix carriers are implemented through internal expression-insert metadata. |
| `astichi_comment("...")` | implemented | Statement-only generated-comment marker. `emit()` preserves it, `materialize()` strips it, and `emit_commented()` renders it as same-indentation `#` comments. Payloads replace only exact `{__file__}` and `{__line__}` substrings. |
| `astichi_bind_once(name, expr)` | rejected | Reserved and obsolete; use ordinary Python assignment for single-evaluation reuse. |
| `astichi_bind_shared(name, expr)` | rejected | Reserved and obsolete; use enclosing Python state plus boundary wiring for shared state. |
| `name__astichi__` / `astichi_definitional_name` | retired | Not a supported marker surface. Use `__astichi_arg__`, `__astichi_keep__`, or explicit boundary wiring. |

Important distinction:

- `recognized` does not mean `semantically complete`
- do not build new features on top of recognized-only markers as if they are
  finished surface area

Current shape vocabulary in code:

- `SCALAR_EXPR`
- `BLOCK`
- `IDENTIFIER`
- `POSITIONAL_VARIADIC`
- `NAMED_VARIADIC`
- `PARAMETER`

Archived parameter-hole design and implementation notes:

- `dev-docs/historical/AstichiV3ParameterHoleSpec.md`
- `dev-docs/historical/AstichiV3ParameterHoleImplementationPlan.md`

**Future hole / clause shapes (non-normative):** the current vocabulary covers
block suites, scalar/`*`/`**` expression sites, identifier-shaped demands, and
function parameter-list targets. Composing **additional `except` / `elif` /
`match` `case` clauses**, typed `with` items, decorators, import pieces, and
similar **list-field** AST targets needs a broader shape inventory
(whole-clause supplies, optional `stmt` / `stmt_block`, and finer targets only
where justified). Design space and rationale — including “whole-unit” modeling
vs splitting clause headers and bodies — live in
`dev-docs/historical/AstichiV3TargetAdditionalHoleShapes.md` (brainstorm only,
not shipped).

## 5. What is already implemented and working

### 5.1 Core pipeline

The V1 core path exists and is exercised:

- compile
- marker recognition
- permissive hygiene classification
- immutable composable construction
- builder graph creation
- build merge
- materialize
- emit
- provenance encode/decode/verify

### 5.2 External bind (V2 Phase 1)

Shipped behavior:

- `BasicComposable.bind(mapping=None, /, **values)`
- kwargs win over positional mapping on key collision
- keys must be valid identifiers
- unknown keys reject
- rebinding an already-bound external rejects
- values are restricted to:
  - `None`
  - `bool`
  - `int`
  - `float`
  - `str`
  - recursive `tuple`
  - recursive `list`
  - recursive `dict`
- unsupported values reject:
  - `set`
  - `bytes`
  - callables
  - arbitrary objects
  - recursive containers
- bind substitution is scope-aware
- `materialize()` rejects unresolved `bind_external` demands

### 5.3 Materialize and gate behavior

Current materialize behavior that is already in place:

- unresolved `astichi_hole(...)` rejects
- unresolved `astichi_bind_external(...)` rejects
- unmatched block-form `@astichi_insert(name)` rejects
- unmatched bare statement `astichi_insert(name, expr)` rejects
- unmatched parameter-form `@astichi_insert(name, kind="params")` rejects
- user-authored `astichi_insert(...)` rejects in default
  `source_kind="authored"` compile mode; `astichi_hole(...)` plus builder
  wiring is the public composition surface, and `astichi_funcargs(...)` is the
  authored call-argument payload surface; parameter holes use
  `name__astichi_param_hole__` plus `def astichi_params(...): pass`
- authored `astichi_funcargs(...)` lowers through generated internal
  `astichi_insert(...)` wrappers before realization
- authored `def astichi_params(...): pass` lowers through generated internal
  `@astichi_insert(..., kind="params")` wrappers and realizes into the target
  function signature before boundary resolution and hygiene
- matched source-level inserts flatten into hole positions
- builder-added contributions become insert shells before materialize, then are
  flattened and hygienically renamed if needed
- the first immediate `.astichi_v` / `._` segment after
  `astichi_ref(...)` or `astichi_pass(name)` is transparent and strips exactly
  once during materialize; any later postfix syntax is real surface on the
  lowered result
- bare statement-form `astichi_ref(...)` / `astichi_pass(...)` rejects at
  compile time; both are value-form surfaces in authored code
- residual `astichi_keep`, `astichi_export`, `astichi_comment`, and current
  `astichi_definitional_name` markers are stripped by executable
  `materialize()`; if stripping empties a non-module Python suite, materialize
  leaves an explicit `pass` so emitted source stays valid Python

### 5.4 Hygiene

Implemented hygiene building blocks:

- permissive vs strict unresolved-name analysis
- keep-name preservation
- two-level trust / inheritance model for cross-scope names
  (soft-pin `preserved_names` vs hard-pin `trust_names`, tracked
  per-Astichi-scope for Store occurrences and module-wide for
  import occurrences; see §11.2 `006` `6c` for the full contract)
- scope identity assignment for fresh Astichi scopes
- rename-on-collision with suffix form:
  - `name__astichi_scoped_<n>`
- expression-form insert wrappers receive fresh Astichi scope treatment
- real `FunctionDef` / `AsyncFunctionDef` bodies are Python function scopes;
  their parameter names are scope bindings that stay stable, while ordinary
  function-local body bindings can still be renamed when inserted snippets
  collide with those parameters

Scope isolation is strict (and intentional):

- every Astichi scope (module root, every root instance under the
  merge-time root wrap, every builder contribution shell, every
  expression-form insert wrapper) owns its own lexical name space
- cross-scope wiring is *explicit*: declare intent via
  `astichi_import` (declaration-form consumer side),
  `astichi_pass` (value-form consumer side),
  `astichi_export` (supplier side, published to the composable
  boundary), `__astichi_arg__` / `__astichi_keep__` suffixes, or the
  builder-level equivalents `arg_names=`, `keep_names=`, and
  `builder.assign.<Src>.<inner>.to().<Dst>.<outer>`
- free-name references inside a shell that are not wired across the
  boundary are local to that shell — full stop
- whatever the user wrote on those names is preserved faithfully;
  astichi does not silently capture an outer binding. If the user
  wrote broken code on a purely-local name (e.g. `total = total + 1`
  in a shell with no `astichi_import(total)` and no prior local
  initialisation), the emitted program faithfully reflects that, and
  running it will raise `NameError` / `UnboundLocalError` at the
  user's own broken statement — astichi's job is lexical fidelity,
  not guessing user intent
- see §9.3 for the historical framing of this rule (formerly tracked
  as "004 Gap 3", now closed as intended behaviour)

## 6. Code map

These are the active ownership points in the codebase.

- `src/astichi/frontend/api.py`
  - public `compile`
  - origin padding
- `src/astichi/ast_provenance.py`
  - AST source-file metadata
  - Astichi-aware source-location copy helper
- `src/astichi/lowering/markers.py`
  - marker recognition
  - marker capability objects
- `src/astichi/lowering/parameters.py`
  - parameter-hole target validation
  - `def astichi_params(...): pass` payload validation and extraction
- `src/astichi/lowering/external_bind.py`
  - Phase 1 bind substitution engine
- `src/astichi/hygiene/api.py`
  - name classification
  - scope identity
  - rename pass
- `src/astichi/model/basic.py`
  - `BasicComposable`
  - `bind`
- `src/astichi/model/ports.py`
  - demand/supply extraction
  - compatibility checks
- `src/astichi/model/external_values.py`
  - bind-value validation and AST conversion
- `src/astichi/builder/graph.py`
  - raw graph structures
- `src/astichi/builder/handles.py`
  - fluent builder DSL; indexed paths; `builder.assign` ref-path chains
- `src/astichi/path_resolution.py`
  - emitted insert-shell metadata parsing
  - descendant ref-path resolution
- `src/astichi/materialize/api.py`
  - `build_merge`
  - materialize gate
  - insert flattening
  - parameter wrapper realization
  - comment-marker stripping / `emit_commented()` rendering
  - hygiene closure
- `src/astichi/emit/api.py`
  - source emission
  - provenance encoding/extraction/verification

Missing Phase 2 files that should be added next:

- `src/astichi/lowering/unroll_domain.py`
- `src/astichi/lowering/unroll.py`
- `tests/test_unroll_domain.py`
- `tests/test_unroll.py`

## 7. Current tests and where to extend them

Existing high-signal tests:

- `tests/test_frontend_compile.py`
  - compile origin padding and syntax-error origin behavior
- `tests/test_lowering_markers.py`
  - marker recognition
- `tests/test_hygiene.py`
  - name classification, scope identity, collision renaming
- `tests/test_model.py`
  - port extraction
- `tests/test_external_values.py`
  - bind value-shape policy
- `tests/test_external_bind.py`
  - scope-aware external substitution
- `tests/test_bind_external.py`
  - public `.bind(...)`
- `tests/test_parameter_holes.py`
  - parameter-hole marker recognition
  - parameter payload recognition and shape rejection
  - duplicate-name/cardinality rejection
  - optional annotation-hole overfill rejection
- `tests/test_build_merge.py`
  - builder merge behavior
- `tests/test_materialize.py`
  - materialize gate and end-to-end semantics
- `tests/test_emit.py`
  - source emission and provenance
- `tests/test_comments.py`
  - comment marker validation, stripping, source-location expansion, and
    `emit_commented()` rendering
- `tests/test_ast_goldens.py` plus `tests/data/gold_src/`
  - canonical successful behavior cases, pre-materialized provenance,
    emitted-source recompile/materialize round trip, and stable generated
    output

Focused test commands:

- full suite:
  - `uv run --with pytest pytest -q`
- Python-version matrix:
  - `uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q`
- typical focused runs:
  - `uv run --with pytest pytest tests/test_ast_goldens.py -q`
  - `uv run --with pytest pytest tests/test_unroll_domain.py -q`
  - `uv run --with pytest pytest tests/test_unroll.py -q`
  - `uv run --with pytest pytest tests/test_parameter_holes.py -q`
  - `uv run --with pytest pytest tests/test_build_merge.py -q`
  - `uv run --with pytest pytest tests/test_materialize.py -q`

## 8. Locked decisions that new work must respect

These decisions are already made and should be treated as stable.

- Compile origin padding is done by source padding, not AST coordinate rewrites.
- Column offset matters only for single-line snippets.
- Builder target addressing is root-instance-first.
- Indexed target addressing already uses `TargetHandle.__getitem__`.
  - Phase 2 must consume the stored path.
  - Phase 2 must not redesign the handle.
- Equal additive edge order resolves by insertion order.
- `bind()` is snapshot-based and returns a new immutable composable.
- `materialize()` currently returns another `BasicComposable`, not a code object.
- Provenance defaults to `True` on `emit`.
- Provenance is all-or-nothing from the public surface.
- Unroll is an additive V2 feature, not a reason to widen the surface into
  runtime parameter-dict domains or replacement semantics.

## 9. Current incomplete / deferred areas

This section is the active handoff. If it conflicts with historical docs, this
summary wins. Older issue write-ups and archived plans are rationale, not work
queues.

### 9.1 Phase 3 polish remains

Phase 2 unroll, the 005 identifier cluster, 006 cross-scope threading, V3
call-argument payloads, and V3 parameter holes are implemented. Remaining work
is polish and tightening:

- shared scope-boundary helper only where it removes real duplication
- user-facing docs and snippet polish as new surfaces settle
- source-origin diagnostics and error-timing documentation
- `compile_to_code` after emit/materialize behavior is stable
- final V2 exit-gate review

### 9.2 Deferred identifier conveniences

These are known deferrals, not current blockers:

- `wire_identifier(...)` on builder slot handles is not implemented. Use
  `arg_names=`, `.bind_identifier(...)`, target-adder `arg_names=`, or
  `builder.assign.<Src>.<inner>.to().<Dst>.<outer>` instead.
- `ast.Attribute` identifier-slot coverage is deferred until a concrete
  consumer requires it. Do not model attribute components as identifier slots
  speculatively.
- Address aliases remain deferred. Keep raw build/ref paths as the long-lived
  identity unless a real feature needs aliases.

### 9.3 Soundness diagnostics

Strict Astichi scope isolation is implemented and intentional: unwired names in
an inserted shell do not silently capture same-spelled names from another
Astichi scope. They are shell-local and may be renamed apart.

Possible future hardening is diagnostic, not a change to the scope contract:

- a materialize gate for unresolved implied/free names inside shells, if the
  product wants hard errors instead of faithfully emitted code that may raise a
  normal Python `NameError` / `UnboundLocalError` when run
- clearer diagnostics around missing `astichi_import(...)` / `astichi_pass(...)`
  wiring when user intent is likely cross-scope sharing

Self-referential unwired locals such as `total = total + 1` remain a strict
scope-isolation contract, not a bug: without `astichi_import(total)` or explicit
builder wiring, the name is local to that inserted scope.

### 9.4 Historical docs handling

Completed specs and implementation plans may be moved to `dev-docs/historical/`
and listed in `dev-docs/historical/README.md`. Do not maintain status, links,
or wording inside archived docs unless explicitly asked. The active truth belongs
in this summary, `docs/reference/`, reference snippets, tests, and goldens.

## 10. Delivery discipline

For each real substep:

- change only the owning layer unless the step explicitly spans layers
- add focused tests first or alongside the change
- prefer goldens / canonical fixtures for successful end-to-end behavior
- keep bespoke tests focused on recognition, diagnostics, and expected failures
- run focused tests
- run the full suite before declaring the step complete
- run the Python-version matrix for changes that affect emitted source,
  materialization, syntax, or version-sensitive AST behavior
- update this summary when the project state changes
- if following roll-build discipline, commit and tag by step

Soft implementation rule:

- keep each substep small enough that it can be reviewed and reverted
  independently

## 11. If you are taking over the project right now

Do this, in order:

1. Read this file.
2. Read `dev-docs/AstichiCodingRules.md`.
3. Confirm the current suite still passes:
   `uv run --with pytest pytest -q`.
4. For version-sensitive or emitted-source work, run:
   `uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q`.
5. Use `docs/reference/`, snippets, and goldens for current behavior.
6. Do not use archived docs as active plans. Only consult
   `dev-docs/historical/` for original rationale when a concrete question
   requires it.
7. When adding or changing behavior, update this summary, reference docs,
   snippets, and tests/goldens in the same change.
