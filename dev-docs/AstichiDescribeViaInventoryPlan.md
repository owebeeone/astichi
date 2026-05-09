# Astichi Describe Via Inventory Plan

## Goal

`Composable.describe()` should become a direct view over `Inventory`.

The intended end state is that inventory is the authoritative data structure for
every descriptor fact exposed by `ComposableDescription`. `describe()` should not
scan the AST, inspect marker tuples, or read parallel `BasicComposable` port
fields to rediscover descriptor data.

## Current State

Inventory is already authoritative for most bindable resource discovery:

- hole descriptors
- external bind descriptors
- identifier demand descriptors
- identifier supply descriptors
- build paths used by those descriptors

`BasicComposable.describe()` still reads non-inventory state for:

- aggregate `demand_ports`
- aggregate `supply_ports`
- production descriptors
- external bind bound-state

Production descriptors are the largest remaining gap. They are currently derived
from the composable root body shape and supply port descriptors at describe time.

## Target Contract

The target contract is:

- Inventory records describe every externally visible bindable or producible
  resource.
- Resolved demands are absent from inventory whenever the existing build step can
  remove them precisely.
- `ComposableDescription` is reconstructed from inventory records and maps only.
- AST inspection happens during inventory construction or rebuild, not during
  `describe()`.
- Build-time inventory prefixing remains a structural operation over inventory
  records.

## Inventory Additions

### Aggregate Ports

The aggregate `demand_ports` and `supply_ports` fields in
`ComposableDescription` should be derived from inventory records with port
payloads.

This probably does not need new record kinds. The existing resource records
already carry `PortInventoryPayload`; the describe wrapper can collect unique
ports from those records in deterministic order.

### Productions

Inventory needs production records for every production currently returned by
`describe()`:

- block production named `__block__`
- implicit expression production named `__expr__`
- function-arguments production named `__funcargs__`
- non-identifier supply-backed productions

These records should use string resource kinds, consistent with the rest of the
inventory design. Candidate kinds:

- `production.block`
- `production.expression`
- `production.funcargs`
- `production.supply`

The inventory should gain a production map keyed by production name, with values
as record ids.

Production records need payload data sufficient to rebuild the corresponding
`ProductionDescriptor`. The payload should not force a source re-scan during
`describe()`.

"How much AST" means this specific question: should a production record carry a
direct AST payload, or should it carry only metadata and force `describe()` to
look back into the tree?

Accepted direction: carry the data the descriptor needs.

- Block production records do not need an AST payload.
- Supply-backed production records can carry a port payload.
- Expression production records should carry the expression AST used by the
  production descriptor.
- Function-arguments production records should carry the extracted function
  argument payload used by the descriptor.

This keeps `describe()` as a pure inventory adapter. Inventory construction and
rebuild paths are responsible for any AST inspection needed to produce those
payloads.

### External Bind Bound-State

Inventory-only `describe()` should not need `BasicComposable.bound_externals`.

Accepted direction: when an external bind is resolved, remove that demand record
from inventory. That matches the current direction for resolved identifier
demands and keeps inventory as "what remains externally bindable".

## Work Slices

### Slice 1: Describe Aggregate Ports From Inventory

Change `describe()` so aggregate `demand_ports` and `supply_ports` are collected
from inventory records instead of `BasicComposable.demand_ports` and
`BasicComposable.supply_ports`.

Keep the existing fields on `BasicComposable` during this slice. They still feed
current inventory construction and several internal transforms.

Tests should compare the existing `describe()` output shape before and after the
change, and should include staged-build inventory cases.

### Slice 2: Add Production Records

Extend inventory construction to add production records during compile and
rebuild.

Move the current production detection logic out of `describe()` and into the
inventory build path:

- root body production fallback
- implicit expression detection
- params payload suppression
- function-arguments payload detection
- non-identifier supply productions
- boundary-prefix marker filtering

Tests should compare full inventory strings for representative production
shapes, not only descriptor tuples.

### Slice 3: Build-Path Semantics For Productions

Enforce how production records are represented after a build merge.

Bindable occurrence records use build paths like `Root` or `Pipeline/Step`.
Composable-level productions describe what the resulting composable can provide
to a future builder. These use build path `.` because they belong to the
resulting composable surface, not to one nested occurrence inside it.

Example:

- Compile `Step` from the source expression `make_step()`.
- `Step` has a production record for `__expr__` at build path `.`.
- Build `Pipeline` by adding `Step` into `Root.body`.
- The resulting built composable may still contain occurrence records under
  `Root/Step` for bindable resources that remain inside that occurrence.
- The resulting built composable's own productions are still at build path `.`,
  because a later builder sees the built composable as one source named by the
  later builder, not as `Root/Step`.

This slice should include tests for a built composable being added to a later
builder stage.

### Slice 4: Remove Bound-External Describe Dependency

Update bind operations so resolved external binds disappear from inventory when
they are no longer externally bindable.

Once this is done, `describe().external_binds` can be derived from inventory
without consulting `bound_externals`.

There is no compatibility requirement to keep already-bound externals visible in
`describe().external_binds`.

### Slice 5: Make `describe()` A Thin Wrapper

Replace `BasicComposable.describe()` internals with a call into an inventory
descriptor adapter.

The adapter should construct:

- holes
- aggregate demand ports
- aggregate supply ports
- external binds
- identifier demands
- identifier supplies
- productions

This is the point where `describe()` stops inspecting AST body shape.

### Slice 6: Retire Parallel Descriptor Sources

After the wrapper is stable, reduce or remove parallel state that is only kept
for `describe()`.

`demand_ports` and `supply_ports` may still be useful internally for lowering,
validation, and compatibility. Do not remove them until those call sites are
audited separately.

## Accepted Decisions

### Production Payload Shape

Production payloads carry the descriptor data directly. `describe()` does not
walk the AST to recover expression or function-arguments production payloads.

### Production Build Path

Composable-surface production records use build path `.`. Occurrence records use
their concrete build path.

### Bound External Records

Resolved external bind records are removed from inventory. Already-bound
externals do not need to remain visible in `describe().external_binds`.

## Implementation Plan

This should not be implemented as one large change. The behavior spans inventory
shape, descriptor reconstruction, compile-time inventory creation, build-merge
inventory creation, and bind mutation behavior.

### Plan Slice 1: Ports From Inventory

Make `describe().demand_ports` and `describe().supply_ports` derive from
inventory records.

This slice should not add production records. It should only prove that aggregate
ports can be reconstructed from existing `PortInventoryPayload` records in a
deterministic order.

Expected result:

- `BasicComposable.describe()` still has production-specific logic.
- Holes, external binds, identifier resources, and aggregate ports are
  inventory-backed.
- Existing descriptor output remains equivalent.

### Plan Slice 2: Production Records

Add production record kinds, production payloads, and `production_map`.

Inventory construction should create production records for:

- `__block__`
- `__expr__`
- `__funcargs__`
- non-identifier supply-backed productions

Compile and rebuild paths should populate those records. Inventory string tests
should pin the record ids, build paths, kinds, names, and maps for representative
production shapes.

Expected result:

- Production data exists in inventory.
- `describe().productions` can be reconstructed from inventory.
- AST inspection for production detection happens before `describe()`.

### Plan Slice 3: Staged Build Production Semantics

Pin production build-path behavior across staged builds.

Composable-surface productions should remain at build path `.`. Occurrence
resources inside built graphs should keep concrete build paths such as `Root` or
`Root/Step`.

Expected result:

- A built composable added to a later builder stage exposes its own productions
  as that composable's surface.
- Nested occurrence resources remain addressable through their build paths.
- Production inventory does not accidentally describe one nested occurrence as
  the final composable's future builder surface.

### Plan Slice 4: Remove Bound-External Describe Dependency

Update bind operations so resolved external bind records are removed from
inventory.

Expected result:

- `describe().external_binds` is derived only from inventory.
- `BasicComposable.bound_externals` is no longer needed by `describe()`.

### Plan Slice 5: Thin Describe Wrapper

Move descriptor reconstruction into an inventory adapter and reduce
`BasicComposable.describe()` to a call into that adapter.

Expected result:

- `describe()` does not walk AST body shape.
- `describe()` does not read parallel descriptor source fields.
- `ComposableDescription` is reconstructed from inventory records and maps.

### Plan Slice 6: Audit Parallel Port Fields

Audit `BasicComposable.demand_ports` and `BasicComposable.supply_ports` after
`describe()` stops using them.

Expected result:

- Fields that are still useful for lowering, validation, or transforms remain.
- Fields that only existed for descriptor output can be retired in a separate
  cleanup.

## Non-Goals

This plan does not change the public meaning of `ComposableDescription`.

This plan does not introduce partial loop unroll.

This plan does not move diagnostics into inventory. Diagnostics can be layered on
later once the raw descriptor mechanism is stable.
