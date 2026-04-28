"""Public self-description value objects for composables."""

from __future__ import annotations

from dataclasses import dataclass

import ast

from astichi.asttools import BLOCK, SCALAR_EXPR, MarkerShape
from astichi.lowering.call_argument_payloads import (
    DOUBLE_STAR_FUNC_ARG_REGION,
    STARRED_FUNC_ARG_REGION,
    FuncArgPayload,
    validate_payload_for_region,
)
from astichi.model.ports import DemandPort, SupplyPort
from astichi.model.semantics import (
    BLOCK_PLACEMENT,
    Compatibility,
    CONST_MUTABILITY,
    EXPRESSION_PLACEMENT,
    PortMutability,
    PortOrigins,
    PortPlacement,
    RejectedCompatibility,
    SemanticSingleton,
)
from astichi.shell_refs import RefPath, normalize_ref_path


class AddPolicy(SemanticSingleton):
    """Cardinality policy for an additive hole."""

    def is_multi_addable(self) -> bool:
        return False

    def accepts_next_addition(self, current_count: int) -> bool:
        if current_count < 0:
            raise ValueError("current_count must be non-negative")
        return current_count == 0


@dataclass(frozen=True, eq=False)
class _SingleAddPolicy(AddPolicy):
    name: str = "single"


@dataclass(frozen=True, eq=False)
class _MultiAddPolicy(AddPolicy):
    name: str = "multi"

    def is_multi_addable(self) -> bool:
        return True

    def accepts_next_addition(self, current_count: int) -> bool:
        if current_count < 0:
            raise ValueError("current_count must be non-negative")
        return True


SINGLE_ADD = _SingleAddPolicy()
MULTI_ADD = _MultiAddPolicy()


def add_policy_for_demand(port: DemandPort) -> AddPolicy:
    """Return the current additive cardinality policy for a demand port."""
    if port.shape.is_block():
        return MULTI_ADD
    if port.shape.is_positional_variadic() or port.shape.is_named_variadic():
        return MULTI_ADD
    if port.is_parameter_hole_demand():
        return MULTI_ADD
    return SINGLE_ADD


@dataclass(frozen=True)
class TargetAddress:
    """Generic data-driven address for a builder target hole."""

    target_name: str
    root_instance: str | None = None
    ref_path: RefPath = ()
    leaf_path: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_name, str) or not self.target_name:
            raise ValueError("target_name must be a non-empty string")
        if self.root_instance is not None and not isinstance(self.root_instance, str):
            raise TypeError("root_instance must be a string or None")
        object.__setattr__(self, "ref_path", normalize_ref_path(self.ref_path))
        object.__setattr__(self, "leaf_path", _normalize_leaf_path(self.leaf_path))

    def with_root_instance(self, root_instance: str) -> "TargetAddress":
        return TargetAddress(
            root_instance=root_instance,
            ref_path=self.ref_path,
            target_name=self.target_name,
            leaf_path=self.leaf_path,
        )


@dataclass(frozen=True)
class PortDescriptor:
    """Public immutable view of a demand or supply port."""

    name: str
    shape: MarkerShape
    placement: PortPlacement
    mutability: PortMutability
    origins: PortOrigins

    @classmethod
    def from_demand(cls, port: DemandPort) -> "PortDescriptor":
        return cls(
            name=port.name,
            shape=port.shape,
            placement=port.placement,
            mutability=port.mutability,
            origins=port.origins,
        )

    @classmethod
    def from_supply(cls, port: SupplyPort) -> "PortDescriptor":
        return cls(
            name=port.name,
            shape=port.shape,
            placement=port.placement,
            mutability=port.mutability,
            origins=port.origins,
        )

    def is_external_bind_demand(self) -> bool:
        return self.origins.is_external_bind_demand()

    def is_identifier_demand(self) -> bool:
        return self.origins.is_identifier_demand()

    def is_identifier_supply(self) -> bool:
        return self.origins.is_identifier_supply()

    def accepts_supply(self, supply: "PortDescriptor") -> Compatibility:
        demand = DemandPort(
            name=self.name,
            shape=self.shape,
            placement=self.placement,
            mutability=self.mutability,
            origins=self.origins,
        )
        supplied = SupplyPort(
            name=supply.name,
            shape=supply.shape,
            placement=supply.placement,
            mutability=supply.mutability,
            origins=supply.origins,
        )
        return demand.accepts_supply(supplied)


@dataclass(frozen=True)
class HoleDescriptor:
    """Structural requirements for an additive hole."""

    port: PortDescriptor

    @property
    def shape(self) -> MarkerShape:
        return self.port.shape

    @property
    def placement(self) -> PortPlacement:
        return self.port.placement

    def accepts(self, production: "ProductionDescriptor") -> Compatibility:
        demand = DemandPort(
            name=self.port.name,
            shape=self.port.shape,
            placement=self.port.placement,
            mutability=self.port.mutability,
            origins=self.port.origins,
        )
        supply = SupplyPort(
            name=production.port.name,
            shape=production.port.shape,
            placement=production.port.placement,
            mutability=production.port.mutability,
            origins=production.port.origins,
        )
        return demand.accepts_supply(supply)


@dataclass(frozen=True)
class ProductionDescriptor:
    """Surface a composable can contribute to a compatible hole."""

    name: str
    port: PortDescriptor
    payload: FuncArgPayload | None = None
    expression: ast.expr | None = None

    def satisfies(self, hole: HoleDescriptor) -> Compatibility:
        if self.payload is not None:
            return _funcargs_payload_compatibility(self.payload, hole)
        compatibility = hole.accepts(self)
        if not compatibility.is_accepted():
            return compatibility
        if hole.shape.is_named_variadic() and self.expression is not None:
            if not isinstance(self.expression, ast.Dict):
                return RejectedCompatibility(
                    f"named variadic target {hole.port.name} requires "
                    "dict-display expression inserts"
                )
        return compatibility

    def is_identifier_supply(self) -> bool:
        return self.port.is_identifier_supply()


def block_production(name: str = "__block__") -> ProductionDescriptor:
    """Return a production descriptor for an ordinary block contribution."""
    return ProductionDescriptor(
        name=name,
        port=PortDescriptor(
            name=name,
            shape=BLOCK,
            placement=BLOCK_PLACEMENT,
            mutability=CONST_MUTABILITY,
            origins=PortOrigins(frozenset()),
        ),
    )


def expression_production(name: str = "__expr__") -> ProductionDescriptor:
    """Return a production descriptor for an implicit expression contribution."""
    return ProductionDescriptor(
        name=name,
        port=PortDescriptor(
            name=name,
            shape=SCALAR_EXPR,
            placement=EXPRESSION_PLACEMENT,
            mutability=CONST_MUTABILITY,
            origins=PortOrigins(frozenset()),
        ),
    )


def expression_ast_production(
    expression: ast.expr,
    *,
    name: str = "__expr__",
) -> ProductionDescriptor:
    """Return a production descriptor for a specific implicit expression."""
    production = expression_production(name)
    return ProductionDescriptor(
        name=production.name,
        port=production.port,
        expression=expression,
    )


def funcargs_production(
    payload: FuncArgPayload,
    *,
    name: str = "__funcargs__",
) -> ProductionDescriptor:
    """Return a production descriptor for an ``astichi_funcargs`` payload."""
    production = expression_production(name)
    return ProductionDescriptor(
        name=production.name,
        port=production.port,
        payload=payload,
    )


def _funcargs_payload_compatibility(
    payload: FuncArgPayload,
    hole: HoleDescriptor,
) -> Compatibility:
    if hole.shape.is_positional_variadic():
        region = STARRED_FUNC_ARG_REGION
    elif hole.shape.is_named_variadic():
        region = DOUBLE_STAR_FUNC_ARG_REGION
    else:
        return RejectedCompatibility(
            f"astichi_funcargs payload cannot satisfy non-variadic target {hole.port.name}"
        )
    try:
        validate_payload_for_region(payload, region=region, hole_name=hole.port.name)
    except ValueError as exc:
        return RejectedCompatibility(str(exc))
    return hole.accepts(
        ProductionDescriptor(
            name="__funcargs__",
            port=PortDescriptor(
                name="__funcargs__",
                shape=SCALAR_EXPR,
                placement=EXPRESSION_PLACEMENT,
                mutability=CONST_MUTABILITY,
                origins=PortOrigins(frozenset()),
            ),
        )
    )


@dataclass(frozen=True)
class ComposableHole:
    """Additive hole exposed by a composable."""

    name: str
    descriptor: HoleDescriptor
    address: TargetAddress
    port: PortDescriptor
    add_policy: AddPolicy

    def with_root_instance(self, root_instance: str) -> "ComposableHole":
        return ComposableHole(
            name=self.name,
            descriptor=self.descriptor,
            address=self.address.with_root_instance(root_instance),
            port=self.port,
            add_policy=self.add_policy,
        )

    def is_multi_addable(self) -> bool:
        return self.add_policy.is_multi_addable()


@dataclass(frozen=True)
class ExternalBindDescriptor:
    """External value that must be supplied with ``bind(...)``."""

    name: str
    port: PortDescriptor
    already_bound: bool = False


@dataclass(frozen=True)
class IdentifierDemandDescriptor:
    """Identifier binding demand addressable with builder assignment."""

    name: str
    port: PortDescriptor
    ref_path: RefPath = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_path", normalize_ref_path(self.ref_path))


@dataclass(frozen=True)
class IdentifierSupplyDescriptor:
    """Identifier supply exposed for builder assignment."""

    name: str
    port: PortDescriptor
    ref_path: RefPath = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_path", normalize_ref_path(self.ref_path))


@dataclass(frozen=True)
class ComposableDescription:
    """Immutable public description of a composable."""

    holes: tuple[ComposableHole, ...] = ()
    demand_ports: tuple[PortDescriptor, ...] = ()
    supply_ports: tuple[PortDescriptor, ...] = ()
    external_binds: tuple[ExternalBindDescriptor, ...] = ()
    identifier_demands: tuple[IdentifierDemandDescriptor, ...] = ()
    identifier_supplies: tuple[IdentifierSupplyDescriptor, ...] = ()
    productions: tuple[ProductionDescriptor, ...] = ()

    def holes_named(self, name: str) -> tuple[ComposableHole, ...]:
        return tuple(hole for hole in self.holes if hole.name == name)

    def single_hole_named(self, name: str) -> ComposableHole:
        matches = self.holes_named(name)
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one composable hole named {name!r}, found {len(matches)}"
            )
        return matches[0]

    def productions_compatible_with(
        self, hole: ComposableHole
    ) -> tuple[ProductionDescriptor, ...]:
        return tuple(
            production
            for production in self.productions
            if production.satisfies(hole.descriptor).is_accepted()
        )


def _normalize_leaf_path(value: tuple[int, ...]) -> tuple[int, ...]:
    if not isinstance(value, tuple):
        raise TypeError("leaf_path must be a tuple of integers")
    if any(not isinstance(item, int) for item in value):
        raise TypeError("leaf_path must be a tuple of integers")
    return value
