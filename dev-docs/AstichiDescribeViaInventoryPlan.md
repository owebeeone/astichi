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
`describe()`. For expression and function-arguments productions, this means the
payload must carry either the AST expression/payload data already needed by the
descriptor or a locator-backed reference that can be resolved without walking the
tree.

### External Bind Bound-State

Inventory-only `describe()` should not need `BasicComposable.bound_externals`.

Preferred direction: when an external bind is resolved, remove that demand record
from inventory. That matches the current direction for resolved identifier
demands and keeps inventory as "what remains externally bindable".

If a legacy descriptor must continue reporting already-bound externals, the
bound-state should live in the inventory payload. That is a compatibility path,
not the preferred long-term shape.

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

Decide and enforce how production records are represented after a build merge.

Bindable occurrence records use build paths like `Root` or `Pipeline/Step`.
Composable-level productions describe what the resulting composable can provide
to a future builder. These may need a separate convention so they are not
confused with child occurrence resources.

Candidate rule: final composable productions use build path `.` and occurrence
resources use concrete build paths.

This slice should include tests for a built composable being added to a later
builder stage.

### Slice 4: Remove Bound-External Describe Dependency

Update bind operations so resolved external binds disappear from inventory when
they are no longer externally bindable.

Once this is done, `describe().external_binds` can be derived from inventory
without consulting `bound_externals`.

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

## Open Design Decisions

### Production Payload Shape

The main unresolved design detail is how much AST data a production record should
carry. The important constraint is that `describe()` must not perform a fresh AST
walk.

### Production Build Path

Production records need a clear build-path convention. They are not the same as
occurrence records, because they describe the resulting composable's future
builder surface.

### Bound External Compatibility

If existing users depend on seeing already-bound externals in
`describe().external_binds`, removing resolved external bind records will be a
behavior change. If that compatibility matters, use inventory payload state as a
transition.

## Non-Goals

This plan does not change the public meaning of `ComposableDescription`.

This plan does not introduce partial loop unroll.

This plan does not move diagnostics into inventory. Diagnostics can be layered on
later once the raw descriptor mechanism is stable.
