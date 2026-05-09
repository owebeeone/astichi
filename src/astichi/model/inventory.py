"""Inventory records for bindable Astichi resources."""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field

from astichi.asttools import is_astichi_insert_call
from astichi.lowering import (
    RecognizedMarker,
    extract_funcargs_payload,
    is_astichi_funcargs_call,
)
from astichi.lowering.call_argument_payloads import FuncArgPayload
from astichi.lowering.markers import ALL_MARKERS, strip_identifier_suffix
from astichi.lowering.parameters import has_params_payload
from astichi.model.ports import DemandPort, SupplyPort
from astichi.path_resolution import effective_root_body

InventoryRecordId = str
ResourceKind = str


class CodePathNode(ABC):
    """AST-backed node in a logical code-owner path."""

    @abstractmethod
    def logical_name(self) -> str:
        """Return the Astichi-visible name for this node."""

    def __eq__(self, other) -> bool:
        if not isinstance(other, CodePathNode):
            return NotImplemented
        return self.logical_name() == other.logical_name()

    def __hash__(self) -> int:
        return hash(self.logical_name())

    def __str__(self) -> str:
        return self.logical_name()


@dataclass(frozen=True, eq=False)
class ClassCodePathNode(CodePathNode):
    """Logical class owner backed by an ``ast.ClassDef`` node."""

    class_ast_node: ast.ClassDef

    def logical_name(self) -> str:
        return _strip_astichi_suffix(self.class_ast_node.name)


@dataclass(frozen=True, eq=False)
class FunctionCodePathNode(CodePathNode):
    """Logical function owner backed by an ``ast.FunctionDef``-family node."""

    function_ast_node: ast.FunctionDef | ast.AsyncFunctionDef

    def logical_name(self) -> str:
        return _strip_astichi_suffix(self.function_ast_node.name)


class ResourceName(ABC):
    """Name of a bindable resource."""

    @abstractmethod
    def logical_name(self) -> str:
        """Return the Astichi-visible resource name."""

    def __eq__(self, other) -> bool:
        if not isinstance(other, ResourceName):
            return NotImplemented
        return self.logical_name() == other.logical_name()

    def __hash__(self) -> int:
        return hash(self.logical_name())

    def __str__(self) -> str:
        return self.logical_name()


@dataclass(frozen=True, eq=False)
class StaticResourceName(ResourceName):
    """Resource name stored directly on a marker call."""

    name: str

    def logical_name(self) -> str:
        return _strip_astichi_suffix(self.name)


@dataclass(frozen=True, eq=False)
class CodeNodeResourceName(ResourceName):
    """Resource name backed by a class/function/identifier node."""

    node: CodePathNode

    def logical_name(self) -> str:
        return self.node.logical_name()


@dataclass(frozen=True)
class CodePath:
    """Logical owner path through class/function code nodes."""

    nodes: tuple[CodePathNode, ...] = ()

    def __str__(self) -> str:
        if not self.nodes:
            return "."
        return "/".join(str(node) for node in self.nodes)


@dataclass(frozen=True)
class ResourcePath:
    """Builder-side resource path."""

    parts: tuple[str, ...] = ()

    def prefixed(self, prefix: ResourcePath) -> ResourcePath:
        return ResourcePath(prefix.parts + self.parts)

    def __bool__(self) -> bool:
        return bool(self.parts)

    def __str__(self) -> str:
        if not self.parts:
            return "."
        return "/".join(self.parts)


@dataclass(frozen=True)
class NodeLocator:
    """Path to an AST node inside the composable tree."""

    parts: tuple[str, ...] = ()

    def __str__(self) -> str:
        if not self.parts:
            return "."
        return "/".join(self.parts)


class InventoryPayload(ABC):
    """Base class for inventory-specific payload data."""


@dataclass(frozen=True)
class PortInventoryPayload(InventoryPayload):
    """Payload for a record backed by an Astichi port."""

    port: DemandPort | SupplyPort


@dataclass(frozen=True)
class BlockProductionInventoryPayload(InventoryPayload):
    """Payload for the default block production."""


@dataclass(frozen=True)
class ExpressionProductionInventoryPayload(InventoryPayload):
    """Payload for an implicit expression production."""

    expression: ast.expr


@dataclass(frozen=True)
class FuncargsProductionInventoryPayload(InventoryPayload):
    """Payload for an ``astichi_funcargs`` production."""

    payload: FuncArgPayload


@dataclass(frozen=True)
class InventoryRecord:
    """One bindable resource discovered in a composable."""

    record_id: InventoryRecordId
    build_path: ResourcePath
    code_owner: CodePath
    name: ResourceName
    kind: ResourceKind
    locator: NodeLocator
    payload: InventoryPayload


@dataclass(frozen=True)
class Inventory:
    """Immutable lookup structure for bindable resources."""

    records: dict[InventoryRecordId, InventoryRecord] = field(default_factory=dict)
    resource_map: dict[str, tuple[InventoryRecordId, ...]] = field(default_factory=dict)
    port_map: dict[str, tuple[InventoryRecordId, ...]] = field(default_factory=dict)
    hole_map: dict[str, tuple[InventoryRecordId, ...]] = field(default_factory=dict)
    identifier_map: dict[str, tuple[InventoryRecordId, ...]] = field(
        default_factory=dict
    )
    production_map: dict[str, tuple[InventoryRecordId, ...]] = field(
        default_factory=dict
    )

    def find_resource(
        self,
        *,
        build_path: ResourcePath | None,
        code_owner: CodePath | None,
        name: str,
        kind: str,
    ) -> tuple[InventoryRecord, ...]:
        """Return records matching the supplied resource filters."""
        candidates = self.resource_map.get(name, ())
        records: list[InventoryRecord] = []
        for record_id in candidates:
            record = self.records[record_id]
            if build_path is not None and record.build_path != build_path:
                continue
            if code_owner is not None and record.code_owner != code_owner:
                continue
            if record.kind != kind:
                continue
            records.append(record)
        return tuple(records)

    def records_for_ids(
        self, record_ids: tuple[InventoryRecordId, ...]
    ) -> tuple[InventoryRecord, ...]:
        """Return records for ``record_ids`` in inventory sort order."""
        return tuple(
            self.records[record_id]
            for record_id in sorted(record_ids, key=_record_id_sort_key)
        )

    def resource_record_ids(self, name: str) -> tuple[InventoryRecordId, ...]:
        """Return resource record IDs for ``name``."""
        return self.resource_map.get(name, ())

    def port_record_ids(self, name: str) -> tuple[InventoryRecordId, ...]:
        """Return port record IDs for ``name``."""
        return self.port_map.get(name, ())

    def hole_record_ids(self, name: str) -> tuple[InventoryRecordId, ...]:
        """Return hole record IDs for ``name``."""
        return self.hole_map.get(name, ())

    def identifier_record_ids(self, name: str) -> tuple[InventoryRecordId, ...]:
        """Return identifier record IDs for ``name``."""
        return self.identifier_map.get(name, ())

    def production_record_ids(self, name: str) -> tuple[InventoryRecordId, ...]:
        """Return production record IDs for ``name``."""
        return self.production_map.get(name, ())

    def prefix_build_path(
        self, prefix: ResourcePath, merge_inv: Inventory
    ) -> Inventory:
        """Return ``merge_inv`` with all record IDs and build paths prefixed."""
        mutable = MutableInventory()
        mutable.add_inventory(prefix, merge_inv)
        return mutable.freeze()

    def __str__(self) -> str:
        lines = ["records:"]
        for record in _sorted_records(self.records.values()):
            lines.append(
                "  "
                f"{record.record_id} "
                f"build_path={record.build_path} "
                f"code_owner={record.code_owner} "
                f"name={record.name.logical_name()} "
                f"kind={record.kind} "
                f"locator={record.locator}"
            )
        for label, record_map in (
            ("resource_map", self.resource_map),
            ("port_map", self.port_map),
            ("hole_map", self.hole_map),
            ("identifier_map", self.identifier_map),
            ("production_map", self.production_map),
        ):
            if not record_map:
                continue
            lines.append("")
            lines.append(f"{label}:")
            for name in sorted(record_map):
                record_ids = ", ".join(
                    sorted(record_map[name], key=_record_id_sort_key)
                )
                lines.append(f"  {name}: {record_ids}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return str(self)


@dataclass
class MutableInventory:
    """Mutable inventory builder used while compiling or merging."""

    records: dict[InventoryRecordId, InventoryRecord] = field(default_factory=dict)
    resource_map: dict[str, list[InventoryRecordId]] = field(default_factory=dict)
    port_map: dict[str, list[InventoryRecordId]] = field(default_factory=dict)
    hole_map: dict[str, list[InventoryRecordId]] = field(default_factory=dict)
    identifier_map: dict[str, list[InventoryRecordId]] = field(default_factory=dict)
    production_map: dict[str, list[InventoryRecordId]] = field(default_factory=dict)
    next_record_number: int = 1

    def add_record(
        self,
        *,
        build_path: ResourcePath,
        code_owner: CodePath,
        name: ResourceName,
        kind: ResourceKind,
        locator: NodeLocator,
        payload: InventoryPayload,
    ) -> InventoryRecord:
        record = InventoryRecord(
            record_id=f"#{self.next_record_number}",
            build_path=build_path,
            code_owner=code_owner,
            name=name,
            kind=kind,
            locator=locator,
            payload=payload,
        )
        self.next_record_number += 1
        self.add_existing_record(record)
        return record

    def add_existing_record(self, record: InventoryRecord) -> None:
        self.records[record.record_id] = record
        name = record.name.logical_name()
        _append_map_value(self.resource_map, name, record.record_id)
        _append_map_value(self.port_map, name, record.record_id)
        if record.kind.startswith("hole."):
            _append_map_value(self.hole_map, name, record.record_id)
        if record.kind.startswith("identifier."):
            _append_map_value(self.identifier_map, name, record.record_id)
        if record.kind.startswith("production."):
            _append_map_value(self.production_map, name, record.record_id)

    def add_inventory(self, prefix: ResourcePath, inventory: Inventory) -> None:
        """Add all records from ``inventory`` under ``prefix``."""
        for record in _sorted_records(inventory.records.values()):
            self.add_existing_record(
                InventoryRecord(
                    record_id=_prefixed_record_id(prefix, record.record_id),
                    build_path=record.build_path.prefixed(prefix),
                    code_owner=record.code_owner,
                    name=record.name,
                    kind=record.kind,
                    locator=record.locator,
                    payload=record.payload,
                )
            )

    def freeze(self) -> Inventory:
        return Inventory(
            records=dict(self.records),
            resource_map=_freeze_map(self.resource_map),
            port_map=_freeze_map(self.port_map),
            hole_map=_freeze_map(self.hole_map),
            identifier_map=_freeze_map(self.identifier_map),
            production_map=_freeze_map(self.production_map),
        )


def empty_inventory() -> Inventory:
    """Return an empty immutable inventory."""
    return Inventory()


def build_inventory(
    tree: ast.Module,
    markers: tuple[RecognizedMarker, ...],
    demand_ports: tuple[DemandPort, ...],
    supply_ports: tuple[SupplyPort, ...],
) -> Inventory:
    """Build a compile-time inventory from recognized marker and port data."""
    index = _AstIndex.from_tree(tree)
    demand_by_name = {port.name: port for port in demand_ports}
    supply_by_name = {port.name: port for port in supply_ports}
    inventory = MutableInventory()
    for marker in markers:
        name_id = marker.name_id
        if name_id is None:
            continue
        demand_port = demand_by_name.get(name_id)
        if demand_port is not None:
            kind = _kind_for_demand_port(demand_port)
            if kind is not None:
                _add_marker_record(
                    inventory,
                    index=index,
                    marker=marker,
                    name_id=name_id,
                    kind=kind,
                    payload=PortInventoryPayload(demand_port),
                )
        supply_port = supply_by_name.get(name_id)
        if supply_port is not None:
            kind = _kind_for_supply_port(supply_port)
            if kind is not None:
                _add_marker_record(
                    inventory,
                    index=index,
                    marker=marker,
                    name_id=name_id,
                    kind=kind,
                    payload=PortInventoryPayload(supply_port),
                )
    _add_production_records(inventory, index=index, tree=tree, supply_ports=supply_ports)
    return inventory.freeze()


def build_production_inventory(
    tree: ast.Module,
    supply_ports: tuple[SupplyPort, ...],
) -> Inventory:
    """Build inventory records for the composable's production surface."""
    index = _AstIndex.from_tree(tree)
    inventory = MutableInventory()
    _add_production_records(inventory, index=index, tree=tree, supply_ports=supply_ports)
    return inventory.freeze()


@dataclass(frozen=True)
class _AstIndex:
    locators: dict[int, NodeLocator]
    owners: dict[int, CodePath]

    @classmethod
    def from_tree(cls, tree: ast.AST) -> _AstIndex:
        locators: dict[int, NodeLocator] = {}
        owners: dict[int, CodePath] = {}

        def visit(
            node: ast.AST,
            locator_parts: tuple[str, ...],
            owner_nodes: tuple[CodePathNode, ...],
        ) -> None:
            locators[id(node)] = NodeLocator(locator_parts)
            owners[id(node)] = CodePath(owner_nodes)
            child_owner_nodes = owner_nodes
            if isinstance(node, ast.ClassDef):
                child_owner_nodes = owner_nodes + (ClassCodePathNode(node),)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child_owner_nodes = owner_nodes + (FunctionCodePathNode(node),)

            for field_name, value in ast.iter_fields(node):
                if isinstance(value, ast.AST):
                    visit(value, locator_parts + (field_name,), child_owner_nodes)
                    continue
                if isinstance(value, list):
                    for index, child in enumerate(value):
                        if isinstance(child, ast.AST):
                            visit(
                                child,
                                locator_parts + (f"{field_name}[{index}]",),
                                child_owner_nodes,
                            )

        visit(tree, (), ())
        return cls(locators=locators, owners=owners)

    def locator_for(self, node: ast.AST) -> NodeLocator:
        return self.locators.get(id(node), NodeLocator())

    def owner_for(self, node: ast.AST) -> CodePath:
        return self.owners.get(id(node), CodePath())


def _add_marker_record(
    inventory: MutableInventory,
    *,
    index: _AstIndex,
    marker: RecognizedMarker,
    name_id: str,
    kind: ResourceKind,
    payload: InventoryPayload,
) -> None:
    inventory.add_record(
        build_path=ResourcePath(),
        code_owner=index.owner_for(marker.node),
        name=_resource_name_for_marker(marker, name_id),
        kind=kind,
        locator=index.locator_for(marker.node),
        payload=payload,
    )


def _resource_name_for_marker(
    marker: RecognizedMarker, name_id: str
) -> ResourceName:
    if isinstance(marker.node, ast.ClassDef):
        return CodeNodeResourceName(ClassCodePathNode(marker.node))
    if isinstance(marker.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return CodeNodeResourceName(FunctionCodePathNode(marker.node))
    return StaticResourceName(name_id)


def _kind_for_demand_port(port: DemandPort) -> ResourceKind | None:
    if port.is_parameter_hole_demand():
        return "hole.params"
    if port.is_additive_hole_demand():
        if port.shape.is_block():
            return "hole.block"
        if port.shape.is_scalar_expr():
            return "hole.expr"
        return f"hole.{port.shape.name}"
    if port.is_external_bind_demand():
        return "external.bind"
    if port.is_identifier_demand():
        return "identifier.demand"
    return None


def _kind_for_supply_port(port: SupplyPort) -> ResourceKind | None:
    if port.origins.is_identifier_supply():
        return "identifier.supply"
    if port.is_signature_parameter_supply() or port.is_expression_family_supply():
        return "production.supply"
    return None


def _add_production_records(
    inventory: MutableInventory,
    *,
    index: _AstIndex,
    tree: ast.Module,
    supply_ports: tuple[SupplyPort, ...],
) -> None:
    root_body = effective_root_body(tree.body)
    if _is_funcargs_payload_body(root_body):
        payload = _extract_funcargs_payload_from_body(root_body)
        if payload is not None:
            _add_static_production_record(
                inventory,
                name="__funcargs__",
                kind="production.funcargs",
                locator=index.locator_for(root_body[0].value),
                payload=FuncargsProductionInventoryPayload(payload),
            )
        return
    if has_params_payload(root_body):
        return
    expression = _implicit_expression_after_boundary_prefix(root_body)
    if expression is not None:
        _add_static_production_record(
            inventory,
            name="__expr__",
            kind="production.expression",
            locator=index.locator_for(expression),
            payload=ExpressionProductionInventoryPayload(expression),
        )
    _add_static_production_record(
        inventory,
        name="__block__",
        kind="production.block",
        locator=NodeLocator(),
        payload=BlockProductionInventoryPayload(),
    )


def _add_static_production_record(
    inventory: MutableInventory,
    *,
    name: str,
    kind: ResourceKind,
    locator: NodeLocator,
    payload: InventoryPayload,
) -> None:
    inventory.add_record(
        build_path=ResourcePath(),
        code_owner=CodePath(),
        name=StaticResourceName(name),
        kind=kind,
        locator=locator,
        payload=payload,
    )


def _is_funcargs_payload_body(body: list[ast.stmt]) -> bool:
    return (
        len(body) == 1
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Call)
        and is_astichi_funcargs_call(body[0].value)
    )


def _extract_funcargs_payload_from_body(body: list[ast.stmt]) -> FuncArgPayload | None:
    if _is_funcargs_payload_body(body):
        return extract_funcargs_payload(body[0].value)
    return None


def _implicit_expression_after_boundary_prefix(body: list[ast.stmt]) -> ast.expr | None:
    boundary_prefix_names = frozenset(
        marker.source_name
        for marker in ALL_MARKERS
        if marker.is_expression_prefix_directive()
    )
    expression_seen = False
    expression: ast.expr | None = None
    for statement in body:
        if _is_boundary_prefix_statement(statement, boundary_prefix_names):
            continue
        if expression_seen:
            return None
        if isinstance(statement, ast.Expr):
            expression_seen = True
            expression = statement.value
            continue
        return None
    if is_astichi_insert_call(expression):
        return None
    return expression


def _is_boundary_prefix_statement(
    statement: ast.stmt, boundary_prefix_names: frozenset[str]
) -> bool:
    if not isinstance(statement, ast.Expr):
        return False
    call = statement.value
    if not isinstance(call, ast.Call):
        return False
    if not isinstance(call.func, ast.Name):
        return False
    return call.func.id in boundary_prefix_names


def _strip_astichi_suffix(name: str) -> str:
    stripped, _marker = strip_identifier_suffix(name)
    return stripped


def _append_map_value(
    mapping: dict[str, list[InventoryRecordId]],
    name: str,
    record_id: InventoryRecordId,
) -> None:
    mapping.setdefault(name, []).append(record_id)


def _freeze_map(
    mapping: dict[str, list[InventoryRecordId]]
) -> dict[str, tuple[InventoryRecordId, ...]]:
    return {
        name: tuple(sorted(record_ids, key=_record_id_sort_key))
        for name, record_ids in sorted(mapping.items())
    }


def _sorted_records(
    records: Iterable[InventoryRecord],
) -> tuple[InventoryRecord, ...]:
    return tuple(sorted(records, key=lambda record: _record_id_sort_key(record.record_id)))


def _record_id_sort_key(record_id: InventoryRecordId) -> tuple[tuple[int, str], ...]:
    parts = record_id.split("/")
    key: list[tuple[int, str]] = []
    for part in parts:
        if part.startswith("#") and part[1:].isdigit():
            key.append((0, f"{int(part[1:]):020d}"))
            continue
        key.append((1, part))
    return tuple(key)


def _prefixed_record_id(
    prefix: ResourcePath, record_id: InventoryRecordId
) -> InventoryRecordId:
    if not prefix:
        return record_id
    return "/".join(prefix.parts + (record_id,))
