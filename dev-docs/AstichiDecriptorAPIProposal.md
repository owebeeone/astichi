# Astichi Descriptor API Proposal

Status: proposal.

Note: the filename intentionally follows the requested spelling
`AstichiDecriptorAPIProposal.md`.

## 1. Problem

Astichi can already derive useful composition metadata from marker-bearing
source. Internally, compiled and built composables carry demand ports, supply
ports, marker shapes, source tags, builder refs, and insertion metadata.

That information is not currently exposed as a stable public descriptor API.
Higher-level generators therefore have two poor choices:

1. know Astichi internals such as `BasicComposable.demand_ports`
2. maintain a parallel metadata system that can drift from the actual source

The desired API is a self-description surface:

```python
description = composable.describe()
```

The description should answer:

- which holes can receive additions
- which holes are single-add vs multi-add
- what shape each hole requires
- what ports the composable demands or supplies
- what external values must be bound
- what data-driven builder address should be used to target each hole
- what production surfaces this composable can contribute to another
  composable

## 2. Design Rules

This API must follow the Astichi coding rules:

- no enums for semantic shape concepts
- no passive string tags as the public semantic model
- prefer behavior-bearing objects and semantic queries
- do not expose compiler internals as the normal author-facing surface
- keep authoring syntax, builder metadata, and runtime/materialization helpers
  separate

The existing `MarkerShape` objects are the correct foundation:

```python
SCALAR_EXPR
POSITIONAL_VARIADIC
NAMED_VARIADIC
BLOCK
IDENTIFIER
PARAMETER
```

Descriptors may carry strings for diagnostic display, source tags, or
round-trippable names, but compatibility must be owned by descriptor/shape
objects rather than implemented through scattered string comparisons.

## 3. Public Surface

Add `describe()` to the public `Composable` interface:

```python
class Composable(ABC):
    @abstractmethod
    def emit(self, *, provenance: bool = True) -> str: ...

    @abstractmethod
    def materialize(self) -> object: ...

    @abstractmethod
    def describe(self) -> "ComposableDescription": ...
```

The method returns immutable value objects. The value objects describe the
current composable exactly as Astichi would compose it at this pipeline stage.

## 4. Target Addresses

The data-driven builder already has the generic address for additive target
holes:

```python
@dataclass(frozen=True)
class TargetAddress:
    root_instance: str | None
    ref_path: tuple[str | int, ...] = ()
    target_name: str = ""
    leaf_path: tuple[int, ...] = ()
```

`root_instance` is `None` when the composable is not attached to a builder
instance yet. A rule engine that has registered the composable can fill the
root instance name:

```python
registered = hole.with_root_instance("Root")
builder.target(registered).add("Step", order=0)
```

Open question: whether `TargetAddress` should allow `target_name=""` at the
type level. The implementation may instead require an explicit constructor and
validate that `target_name` is non-empty.

The address maps directly to the existing direct builder helper:

```python
builder.target(
    root_instance=address.root_instance,
    ref_path=address.ref_path,
    target_name=address.target_name,
    leaf_path=address.leaf_path,
)
```

## 5. Builder API Adjustment

The data-driven API should accept descriptor target data directly.

Current direct helper:

```python
builder.target(
    *,
    root_instance: str,
    target_name: str,
    ref_path: tuple[str | int, ...] = (),
    leaf_path: int | tuple[int, ...] | None = None,
) -> TargetHandle
```

Proposed compatible extension:

```python
builder.target(
    address: TargetAddress | ComposableHole | None = None,
    *,
    root_instance: str | None = None,
    target_name: str | None = None,
    ref_path: tuple[str | int, ...] = (),
    leaf_path: int | tuple[int, ...] | None = None,
) -> TargetHandle
```

Rules:

1. Passing a `TargetAddress` is equivalent to passing its fields.
2. Passing a `ComposableHole` is equivalent to passing
   `composable_hole.address`.
3. Explicit keyword overrides are rejected when they conflict with descriptor
   data.
4. `root_instance` must be resolved before a `TargetHandle` can be returned.
5. `leaf_path` normalizes through the same helper as the existing named API.

Usage:

```python
hole = root.describe().single_hole_named("body")

builder.add("Root", root)
builder.add("Step", step)

builder.target(hole.with_root_instance("Root")).add("Step", order=0)
```

The existing keyword-only form remains supported:

```python
builder.target(
    root_instance="Root",
    ref_path=("Previous",),
    target_name="body",
).add("Step", order=0)
```

## 6. Hole Descriptors

Holes are demand-side additive targets addressable by `builder.target(...)`.

```python
@dataclass(frozen=True)
class ComposableHole:
    name: str
    descriptor: HoleDescriptor
    address: TargetAddress
    port: PortDescriptor
    add_policy: "AddPolicy"

    def with_root_instance(self, root_instance: str) -> "ComposableHole": ...
```

`name` is the public target name from marker source, such as `body`, `args`,
or `params`.

`address` is the data-driven builder target address:

```python
TargetAddress(
    root_instance=None,
    ref_path=("Previous", "Inner"),
    target_name="body",
    leaf_path=(),
)
```

`port` is the structural demand port for this hole.

`add_policy` records whether the hole can accept multiple contributions.

## 7. Add Policy

Do not model cardinality as an enum. Use behavior-bearing policy objects:

```python
class AddPolicy(ABC):
    @abstractmethod
    def accepts_next_addition(self, current_count: int) -> bool: ...

    @abstractmethod
    def describe_limit(self) -> str: ...


class SingleAddPolicy(AddPolicy):
    def accepts_next_addition(self, current_count: int) -> bool:
        return current_count == 0


class MultiAddPolicy(AddPolicy):
    def accepts_next_addition(self, current_count: int) -> bool:
        return True
```

Initial policy mapping:

- block holes are multi-addable
- positional variadic holes are multi-addable
- named variadic holes are multi-addable
- parameter holes are multi-addable, subject to final signature collision rules
- scalar expression holes are single-add
- identifier demand ports are not additive holes; they are wiring ports
- external binds are not additive holes; they are value bindings

The policy is advisory for planning and diagnostics. Build/materialize remains
authoritative and must still reject illegal multiple contributions or invalid
merged outputs.

## 8. Hole Descriptor Objects

`HoleDescriptor` owns compatibility logic for target holes:

```python
class HoleDescriptor(ABC):
    @property
    @abstractmethod
    def shape(self) -> MarkerShape: ...

    @property
    @abstractmethod
    def placement(self) -> str: ...

    @abstractmethod
    def accepts(self, production: "ProductionDescriptor") -> "Compatibility": ...
```

`Compatibility` should also be behavior-bearing. A minimal version can be:

```python
class Compatibility(ABC):
    @abstractmethod
    def is_accepted(self) -> bool: ...

    @abstractmethod
    def requires_coercion(self) -> bool: ...
```

Concrete compatibility objects may carry a diagnostic reason and a coercion
plan. Avoid passive `"exact"`, `"coercible"`, or `"incompatible"` string tags
as the semantic API.

Initial hole descriptor families:

- block hole descriptor
- scalar expression hole descriptor
- positional variadic expression hole descriptor
- named variadic expression hole descriptor
- parameter-list hole descriptor

Identifier demands and external binds are ports, not additive holes, so they
should not appear in `ComposableDescription.holes`.

## 9. Production Descriptors

A production is something this composable can add to another composable's hole.

```python
@dataclass(frozen=True)
class ProductionDescriptor:
    descriptor: ProductionShapeDescriptor
    port: PortDescriptor | None = None
    source_name: str | None = None

    def is_compatible_with(self, hole: ComposableHole) -> Compatibility:
        return hole.descriptor.accepts(self)
```

`ProductionShapeDescriptor` should be behavior-bearing:

```python
class ProductionShapeDescriptor(ABC):
    @property
    @abstractmethod
    def shape(self) -> MarkerShape: ...

    @property
    @abstractmethod
    def placement(self) -> str: ...

    @abstractmethod
    def can_supply(self, hole: HoleDescriptor) -> Compatibility: ...
```

Initial production sources:

- ordinary statement/block composables can supply block holes
- scalar expression composables can supply scalar expression holes
- `astichi_funcargs(...)` payload composables can supply positional or named
  variadic call holes according to their payload shape
- `astichi_params(...)` payload composables can supply parameter-list holes
- `astichi_export(...)` supplies identifier wiring ports, not additive holes
- `astichi_bind_external(...)` does not supply another composable; it creates
  an external value demand

Expression-to-block insertion should be represented as a compatibility
decision with an explicit coercion plan if supported. It should not be treated
as the same shape.

## 10. Ports

Expose stable port descriptors instead of asking users to read internal
`DemandPort` and `SupplyPort` objects directly.

```python
@dataclass(frozen=True)
class PortDescriptor:
    name: str
    shape: MarkerShape
    placement: PortPlacement
    mutability: PortMutability
    origins: PortOrigins

    def accepts_supply(self, supply: "PortDescriptor") -> Compatibility: ...
```

This intentionally mirrors the semantic internal port model:

```python
DemandPort(
    name: str,
    shape: MarkerShape,
    placement: PortPlacement,
    mutability: PortMutability,
    origins: PortOrigins,
)

SupplyPort(
    name: str,
    shape: MarkerShape,
    placement: PortPlacement,
    mutability: PortMutability,
    origins: PortOrigins,
)
```

The public descriptor should be stable even if the internal dataclass names
change. Descriptors should expose behavior-bearing placement, mutability, and
origin objects. They should not require callers to branch on string tags.

Description should separate ports by role:

```python
@dataclass(frozen=True)
class ComposableDescription:
    holes: tuple[ComposableHole, ...] = ()
    productions: tuple[ProductionDescriptor, ...] = ()
    demand_ports: tuple[PortDescriptor, ...] = ()
    supply_ports: tuple[PortDescriptor, ...] = ()
    external_binds: tuple[ExternalBindDescriptor, ...] = ()
    identifier_demands: tuple[IdentifierDemandDescriptor, ...] = ()
    identifier_supplies: tuple[IdentifierSupplyDescriptor, ...] = ()
```

Convenience lookup methods are useful, but should not replace the tuple fields:

```python
class ComposableDescription:
    def holes_named(self, name: str) -> tuple[ComposableHole, ...]: ...
    def single_hole_named(self, name: str) -> ComposableHole: ...
    def productions_compatible_with(
        self,
        hole: ComposableHole,
    ) -> tuple[ProductionDescriptor, ...]: ...
```

Avoid storing a mutable `holes_by_name` dict as the primary representation
because duplicate descendant refs or repeated names may be meaningful during
diagnostics. A computed lookup is fine.

## 11. External Bind Descriptors

External binds are not holes. They are compile-time value demands.

```python
@dataclass(frozen=True)
class ExternalBindDescriptor:
    name: str
    port: PortDescriptor
    already_bound: bool = False
```

Example:

```python
for bind in piece.describe().external_binds:
    piece = piece.bind({bind.name: values[bind.name]})
```

The supported value policy remains owned by `bind(...)` and the external value
validator. The descriptor may expose the current supported policy later, but it
should not duplicate validator logic in phase one.

## 12. Identifier Wiring Descriptors

Identifier demands and supplies should be visible because they are a major
attachment surface.

```python
@dataclass(frozen=True)
class IdentifierDemandDescriptor:
    name: str
    port: PortDescriptor
    ref_path: tuple[str | int, ...] = ()


@dataclass(frozen=True)
class IdentifierSupplyDescriptor:
    name: str
    port: PortDescriptor
    ref_path: tuple[str | int, ...] = ()
```

The data-driven builder already wires these through:

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

An optional follow-up could introduce an `AssignAddress` descriptor, but phase
one can reuse `ref_path` plus the existing named `builder.assign(...)` API.

## 13. Built Composables And Descendant Refs

For a raw compiled composable, holes are normally root-level:

```python
TargetAddress(
    root_instance=None,
    ref_path=(),
    target_name="body",
    leaf_path=(),
)
```

For a staged/built composable that preserves descendant shell refs, `describe()`
must include the full descendant ref path:

```python
TargetAddress(
    root_instance=None,
    ref_path=("Root", "Inner"),
    target_name="slot",
    leaf_path=(),
)
```

After registering that built composable:

```python
builder.add("Pipeline", built)

for hole in built.describe().holes:
    builder.target(hole.with_root_instance("Pipeline")).add("Step")
```

This must be equivalent to fluent:

```python
builder.Pipeline.Root.Inner.slot.add.Step()
```

## 14. Indexed Holes

Indexed holes produced by unrolled loops should describe their leaf path:

```python
TargetAddress(
    root_instance=None,
    ref_path=("Root", "Loop"),
    target_name="step",
    leaf_path=(2,),
)
```

The builder call should be direct:

```python
builder.target(hole.with_root_instance("Pipeline")).add("Step", order=0)
```

which is equivalent to:

```python
builder.Pipeline.Root.Loop.step[2].add.Step(order=0)
```

## 15. Compatibility With Existing Ports

Phase one should derive descriptors from existing data:

- `demand_ports`
- `supply_ports`
- recognized markers
- preserved shell refs in built composables
- current target path validation

The descriptor API should not become a second source of truth.

Recommended internal flow:

1. compile/lowering continues to recognize markers and produce ports
2. build continues to preserve shell refs and target metadata
3. `describe()` projects those facts into public descriptor objects
4. builder APIs accept descriptor addresses but continue validating through
   existing graph/handle logic

## 16. Example

```python
root = astichi.compile(
    """
def run(params__astichi_param_hole__):
    astichi_hole(body)
"""
)

step = astichi.compile("print(value)\n")
params = astichi.compile(
    """
def astichi_params(value):
    pass
"""
)

root_desc = root.describe()

body = root_desc.single_hole_named("body")
params_hole = root_desc.single_hole_named("params")

builder = astichi.build()
builder.add("Root", root)
builder.add("Step", step)
builder.add("Params", params)

builder.target(body.with_root_instance("Root")).add("Step", order=0)
builder.target(params_hole.with_root_instance("Root")).add("Params", order=0)
```

## 17. Non-Goals

This proposal does not:

- add replacement semantics
- make descriptors editable
- make builder graph internals public
- remove the fluent builder API
- replace marker source syntax
- infer semantic intent beyond what source and build metadata provide
- guarantee that descriptor compatibility replaces materialize-time validation

## 18. Implementation Plan

Phase one:

1. Add descriptor dataclasses and behavior-bearing policy/compatibility
   classes.
2. Add `Composable.describe()` to the abstract interface.
3. Implement `BasicComposable.describe()` by projecting current ports and
   marker/build metadata.
4. Add `TargetAddress` and `ComposableHole.with_root_instance(...)`.
5. Extend `builder.target(...)` to accept `TargetAddress` and `ComposableHole`
   directly.
6. Add focused tests that descriptor-derived target calls produce the same
   graph records as explicit data-driven calls.

Phase two:

1. Add richer production descriptors for `astichi_funcargs(...)` payload
   variants.
2. Add compatibility diagnostics with source-origin context.
3. Add docs examples for rule engines that auto-connect composables based on
   descriptors.

## 19. Test Plan

Focused tests:

1. `describe()` on a root block hole returns a multi-addable hole with a
   root-level `TargetAddress`.
2. `describe()` on a scalar expression hole returns a single-add hole.
3. `describe()` on positional and named variadic holes returns multi-addable
   holes.
4. `describe()` on a parameter hole returns a multi-addable parameter hole.
5. `describe()` exposes external bind descriptors.
6. `describe()` exposes identifier demand and supply descriptors.
7. A built composable with descendant refs returns holes with full `ref_path`.
8. `builder.target(hole.with_root_instance("Root")).add("Step")` produces the
   same graph edge as `builder.target(root_instance=..., ...).add("Step")`.
9. Conflicting keyword overrides when passing descriptor data to
   `builder.target(...)` reject with a clear diagnostic.

Integration/golden coverage:

1. Build a small composed function by selecting holes from `describe()`.
2. Build a staged composable, inspect descendant hole descriptors, and attach
   into one descendant hole using descriptor target data.
3. Build a parameterized function using descriptor-derived parameter and body
   holes.

## 20. Documentation Plan

If implemented:

1. Add `docs/reference/descriptor-api.md`.
2. Update `docs/reference/composable-api.md` with `describe()`.
3. Update `docs/reference/builder-api.md` to show `builder.target(address)`.
4. Update `AstichiSingleSourceSummary.md`.
5. Keep `AstichiComposableSelfDescription.md` as the broader inventory, or
   merge it into this proposal once the descriptor API is accepted.
