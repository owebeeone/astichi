# Astichi Inventory Design

This document specifies the Astichi inventory concept.

Inventory exists for one reason: make discovery of bindable Astichi points
cheap and explicit. It is not a broad description API, a serialized cache, or
a replacement for Astichi markers.

Bindable points include target holes, identifier demands and supplies,
external binds, and other port-like surfaces that a builder or assembler needs
to discover by name. Comment markers are not bindable and are not included in
the inventory maps.

## Goals

- Build inventory during `astichi.compile()` as part of marker recognition.
- Store records for bindable resources only.
- Keep enough location data to get back to the relevant AST node without
  rescanning the tree.
- Keep build identity separate from Python code identity.
- Provide lookup maps for common bindable-resource questions.
- Support a mutable inventory shape while a build is assembling records, then
  freeze to the public immutable value.

The performance rule is:

```text
one scan per AST version, then map-backed lookups
```

## Build Path And Code Path

Inventory records distinguish two paths.

The build path is builder or assembler identity. It says which named build
product or contribution owns a bindable resource.

Examples:

```text
Root
Root/Facade
Root/Facade/GetUser
```

The code path is Python AST structure. It says where a bindable resource lives
inside the Python code.

Examples:

```text
UserClass
UserClass/__init__
UserClass/__init__/params
```

These paths must not be collapsed. A build operation prefixes or rebases the
build path. A code-binding operation, such as binding
`cname__astichi_arg__` to `UserClass`, changes code identity by changing the
underlying AST node name.

## Logical Names

Inventory uses logical Astichi names, not raw Python AST names.

For AST-backed names, wrappers read the current AST node name and strip
Astichi suffixes such as `__astichi_arg__` and
`__astichi_param_hole__`.

For marker-backed names, the record stores the logical marker name.

This means descendant records do not need string surgery when an owning class
or function is renamed. Their code-path wrappers read the current logical
names from the AST nodes.

Wrappers compare and hash by stripped logical name, not by AST node identity.
This makes `CodePath` equality a comparison of logical path names. Exact AST
node identity is handled by `NodeLocator`, not by `CodePath`.

## Resource Kinds

Kind tokens are boundary strings in the inventory grammar, not implementation
enums.

Initial bindable kind tokens:

```text
hole.block
hole.expr
hole.params
identifier.demand
identifier.supply
external.bind
```

Comment markers are intentionally excluded from bindable kind maps.

Implementation code should still prefer semantic behavior objects and query
methods internally. The kind token is the serialized resource namespace.

## Conceptual Types

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import ast


PathStep = str | int
InventoryRecordId = str


class CodePathNode(ABC):
    @abstractmethod
    def logical_name(self) -> str: ...

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, CodePathNode)
            and self.logical_name() == other.logical_name()
        )

    def __hash__(self) -> int:
        return hash(self.logical_name())


@dataclass(frozen=True, eq=False)
class ClassCodePathNode(CodePathNode):
    node: ast.ClassDef

    def logical_name(self) -> str:
        return strip_astichi_name_suffix(self.node.name)


@dataclass(frozen=True, eq=False)
class FunctionCodePathNode(CodePathNode):
    node: ast.FunctionDef | ast.AsyncFunctionDef

    def logical_name(self) -> str:
        return strip_astichi_name_suffix(self.node.name)


class ResourceName(ABC):
    @abstractmethod
    def logical_name(self) -> str: ...

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, ResourceName)
            and self.logical_name() == other.logical_name()
        )

    def __hash__(self) -> int:
        return hash(self.logical_name())


@dataclass(frozen=True, eq=False)
class StaticResourceName(ResourceName):
    name: str

    def logical_name(self) -> str:
        return self.name


@dataclass(frozen=True, eq=False)
class CodeNodeResourceName(ResourceName):
    node: CodePathNode

    def logical_name(self) -> str:
        return self.node.logical_name()


@dataclass(frozen=True)
class CodePath:
    nodes: tuple[CodePathNode, ...]


@dataclass(frozen=True)
class ResourcePath:
    parts: tuple[str, ...]


@dataclass(frozen=True)
class NodeLocator:
    ast_path: tuple[PathStep, ...]


class InventoryPayload:
    """Resource-specific semantic payload."""


@dataclass(frozen=True)
class InventoryRecord:
    record_id: InventoryRecordId
    build_path: ResourcePath
    code_owner: CodePath
    name: ResourceName
    kind: str
    locator: NodeLocator
    payload: InventoryPayload
```

`record_id` is the stable inventory-local record designation. It is formatted
as `#1`, `#2`, and so on for records produced directly by one compile scan.
When an inventory is merged under a build path, incoming record IDs are
prefixed with that build path, such as `Root/#1` or `Root/Step/#1`. IDs are the
values stored in the resource maps.

`build_path` is builder or assembler identity.

`code_owner` is the live Python-code owner path. Its nodes are wrappers around
AST owner nodes.

`name` is the bindable resource name. Static marker names use
`StaticResourceName`. Class/function identifier resources can use
`CodeNodeResourceName` so the record follows AST name changes.

`kind` is the bindable resource namespace.

`locator` is the structural path back to the resource node in the AST. It is
not a direct node cache.

`payload` contains the resource-specific semantic data needed for validation
and compatibility checks.

`describe()` projects bindable descriptor sections from immutable inventory
records. Payloads carry the data exposed through those descriptor objects:

- hole placement and shape
- target address ingredients derivable from build path, code owner, name, and
  locator
- add policy/cardinality for target holes
- external bind value metadata needed by `ExternalBindDescriptor`
- identifier demand/supply metadata, including ref path and placement
- production/source compatibility data needed to validate a source against a
  target

Payloads should reuse existing semantic objects where practical rather than
introducing parallel tags.

Production descriptors are still derived from the existing body/payload checks
because they describe what a composable can contribute, not a bindable point.

## Node Location

`NodeLocator.ast_path` is a path from the composable tree root to the marker,
hole call, shell, or other relevant AST node. It uses AST field names and list
indexes.

Example path shape:

```text
body / 3 / value / args / 0
```

`NodeLocator` is for the bindable resource node. `CodePathNode` wrappers are
for live code-owner names. They are separate mechanisms.

When a composable wrapper containing both `ast_root` and `inventory` is copied
with `copy.deepcopy()`, the AST and wrapper-held AST references are copied as
one object graph. The copied code-path wrappers point at the copied AST owner
nodes, and strings are reused because they are immutable.

## Inventory API

```python
@dataclass(frozen=True)
class Inventory:
    records: dict[InventoryRecordId, InventoryRecord]
    resource_map: dict[str, tuple[InventoryRecordId, ...]]
    port_map: dict[str, tuple[InventoryRecordId, ...]]
    hole_map: dict[str, tuple[InventoryRecordId, ...]]
    identifier_map: dict[str, tuple[InventoryRecordId, ...]]

    def find_resource(
        self,
        *,
        build_path: ResourcePath | None,
        code_owner: CodePath | None,
        name: str,
        kind: str,
    ) -> tuple[InventoryRecord, ...]: ...

    def prefix_build_path(
        self,
        prefix: ResourcePath,
        merge_inventory: Inventory,
    ) -> Inventory: ...

    def records_for_ids(
        self,
        record_ids: tuple[InventoryRecordId, ...],
    ) -> tuple[InventoryRecord, ...]: ...

    def resource_record_ids(self, name: str) -> tuple[InventoryRecordId, ...]: ...
    def port_record_ids(self, name: str) -> tuple[InventoryRecordId, ...]: ...
    def hole_record_ids(self, name: str) -> tuple[InventoryRecordId, ...]: ...
    def identifier_record_ids(self, name: str) -> tuple[InventoryRecordId, ...]: ...
```

`records` are the authoritative inventory contents.

`resource_map` maps logical bindable names to all bindable record IDs with that
name.

`port_map` maps logical port names to port-like record IDs. It includes holes,
identifier demands and supplies, external binds, and other port-like bindable
surfaces.

`hole_map` maps logical hole names to targetable hole record IDs.

`identifier_map` maps logical identifier names to identifier demand and supply
record IDs.

There is no comment map. Comments are not bindable.

`records_for_ids()` resolves record IDs through `records` and returns records
in stable inventory order.

The `*_record_ids()` helpers expose the public map accessors for tools that
already know which resource namespace they need.

`find_resource()` starts from the logical resource name, resolves IDs through
`records`, then applies build-path, code-owner, and kind constraints.

`prefix_build_path()` returns `merge_inventory` with `prefix` prepended to the
merge records' build paths. It does not rescan the AST and does not rewrite
code paths.

Record IDs are inventory-local until a build prefix is applied. The merge rule
is: for every record imported from `merge_inventory`, keep the incoming record
number and prefix the ID with `prefix`. For example, incoming `#1` under prefix
`Root/Step` becomes `Root/Step/#1`. Merge does not renumber imported records.
If the prefixed ID would collide with an existing output ID, the build path is
not unique enough and the caller must use a more specific prefix, such as an
occurrence segment.

## Mutable Build Form

Build code may use an unfrozen form while constructing or merging inventory
records.

```python
@dataclass
class MutableInventory:
    records: dict[InventoryRecordId, InventoryRecord]
    resource_map: dict[str, list[InventoryRecordId]]
    port_map: dict[str, list[InventoryRecordId]]
    hole_map: dict[str, list[InventoryRecordId]]
    identifier_map: dict[str, list[InventoryRecordId]]
    next_record_number: int

    def add_inventory(self, prefix: ResourcePath, inventory: Inventory) -> None: ...
```

The mutable form is an implementation convenience. It should be frozen to
`Inventory` before being attached to a composable.

`next_record_number` allocates `#n` designations while new records are being
collected from an AST scan. Merging an existing inventory does not allocate new
record numbers; it prefixes the incoming IDs.

Initial compile allocation follows deterministic marker discovery order. The
implementation must not rely on dictionary, set, or hash iteration order for
ID allocation.

## Pretty Printing

`Inventory.__str__()` and `Inventory.__repr__()` return the same stable
pretty-printed inventory snapshot. Tests compare `str(inventory)`
directly when validating inventory contents.

The `records` section always prints, even when empty. Records print one record
per line:

```text
records:
  #1 build_path=. code_owner=. name=cname kind=identifier.demand locator=body[0]
  #2 build_path=. code_owner=cname name=fname kind=identifier.demand locator=body[0]/body[0]
  #3 build_path=. code_owner=cname/fname name=params kind=hole.params locator=body[0]/body[0]/args/args[1]
```

Maps print only when non-empty. Map entries print one logical name per line,
with the record IDs listed on that line:

```text
resource_map:
  cname: #1
  fname: #2
  params: #3

hole_map:
  params: #3

identifier_map:
  cname: #1
  fname: #2
```

Empty maps are omitted. Maps should not print whole records inline; they print
`#n` record IDs so large inventories stay readable.

Pretty-print order:

- records sort by record ID, with numeric ordering for `#n`
- prefixed IDs sort by prefix path, then numeric `#n`
- map names sort lexicographically
- record IDs inside one map entry sort by the same record-ID ordering

This keeps snapshot tests stable across Python versions.

## Lookup Rules

Direct map access uses the explicit `*_record_ids()` helpers. Use
`hole_record_ids()` for targetable holes, `identifier_record_ids()` for
identifier demands and supplies, `port_record_ids()` for port-like bindables,
and `resource_record_ids()` for all bindable resources with a logical name.

`find_resource()` resolves candidates through `resource_map` and filters by
build path, code owner, logical name, and kind.

## Resource Lifecycle

Inventory contains currently bindable resources only.

`__astichi_keep__` names are not inventoried because keep directives are not
bindable.

When a `__astichi_arg__` demand is resolved to a concrete name, that demand is
no longer bindable. The AST occurrence is rewritten into a keep-preserved
name, and the original identifier-demand record must be removed from the
inventory maps and from `records` in the resulting composable.

## Example

For this authored source:

```python
class cname__astichi_arg__:
    def fname__astichi_arg__(
        self,
        params__astichi_param_hole__,
    ):
        self.ready = True
```

the pre-build inventory records are:

```text
record_id=#1
build_path=()
code_owner=()
name=cname
kind=identifier.demand

record_id=#2
build_path=()
code_owner=(cname)
name=fname
kind=identifier.demand

record_id=#3
build_path=()
code_owner=(cname, fname)
name=params
kind=hole.params
```

If binding rewrites the AST class name to `UserClass` and the function name to
`__init__`, the same records report code owners and names as:

```text
record_id=#1
build_path=()
code_owner=()
name=UserClass
kind=identifier.demand

record_id=#2
build_path=()
code_owner=(UserClass)
name=__init__
kind=identifier.demand

record_id=#3
build_path=()
code_owner=(UserClass, __init__)
name=params
kind=hole.params
```

The records do not need descendant path rewrites because `CodePathNode` and
`CodeNodeResourceName` read current logical names from the AST.

## Build Plan

### Slice 1: Inventory On Composable

- Add the `Inventory`, `MutableInventory`, `InventoryRecord`, record ID, path,
  name-provider, locator, and payload skeleton types.
- Attach immutable `Inventory` to composables.
- Populate inventory during compile marker recognition.
- Add pretty printing for records and maps.
- Add focused tests that compare `str(inventory)` to expected snapshots.

Status: implemented in `inventory/slice-1`.

### Slice 2: Builder Merge Inventory

- Use `MutableInventory` while builder/build code combines composables.
- When an instance is added to the builder, prefix or rebase the incoming
  records' build paths.
- Preserve code paths and node locators when AST shape is copied unchanged.
- Preserve existing output inventory IDs and prefix merged record IDs with the
  merged records' build-path prefix while keeping the original record number.
- Reject or disambiguate any merge that would create a duplicate record ID.
- Freeze the mutable inventory onto the built composable.

Status: implemented in `inventory/slice-2`. The current builder path follows
the tree-shaped instance occurrence path and preserves original record numbers
for records that survive the build.

### Slice 3: Describe Over Inventory

- Change `describe()` to derive its current public results from immutable
  inventory records.
- Keep the existing `describe()` API shape and behavior.
- Add explicit accessors for the inventory maps where the public surface needs
  them.
- Add parity tests proving old `describe()` results match inventory-derived
  results.

Status: implemented in `inventory/slice-3` for holes, external binds, and
identifier demand/supply descriptors. Production descriptors remain
body/payload-derived.

### Slice 4: Documentation

- Update public describe documentation after the implementation is moved over.
- Document inventory map accessors and pretty-print output.
- Remove stale documentation that implies independent describe traversal.

### Slice 5: Invalidation And Copy Checks

- Add tests for `copy.deepcopy()` of a composable containing AST and inventory.
- Verify code-path wrappers point at copied AST nodes.
- Verify string fields are safe and record IDs are preserved after copy.
- Add tests for AST-name binding where records report updated logical names
  without descendant record rewrites.
- Add tests that resolved `__astichi_arg__` demands are removed from inventory
  when they become keep-preserved names.

Status: implemented in `inventory/slice-5`.
