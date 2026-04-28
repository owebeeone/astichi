"""Behavior-bearing semantic singleton objects for Astichi models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from astichi.asttools import (
    BLOCK,
    IDENTIFIER,
    NAMED_VARIADIC,
    PARAMETER,
    POSITIONAL_VARIADIC,
    MarkerShape,
)


class SemanticSingleton(ABC):
    """Common protocol for stable semantic singleton objects."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable diagnostic / serialization name."""

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.name == other
        return self is other

    def __hash__(self) -> int:
        return hash(self.name)


class Compatibility(ABC):
    """Result of a semantic compatibility check."""

    @abstractmethod
    def is_accepted(self) -> bool:
        """Return whether the compatibility check passed."""

    def requires_coercion(self) -> bool:
        return False

    @abstractmethod
    def error_message(self) -> str:
        """Return a user-facing error message for rejected compatibility."""


@dataclass(frozen=True)
class AcceptedCompatibility(Compatibility):
    """Singleton-compatible accepted result."""

    def is_accepted(self) -> bool:
        return True

    def error_message(self) -> str:
        return ""


@dataclass(frozen=True)
class RejectedCompatibility(Compatibility):
    """Rejected compatibility with diagnostic detail."""

    reason: str

    def is_accepted(self) -> bool:
        return False

    def error_message(self) -> str:
        return self.reason


ACCEPTED = AcceptedCompatibility()


class PortPlacement(SemanticSingleton):
    """Where a port is satisfied in Python structure."""

    def accepts_supply(self, demand: object, supply: object) -> Compatibility:
        demand_placement = getattr(demand, "placement")
        supply_placement = getattr(supply, "placement")
        if demand_placement is not supply_placement:
            return RejectedCompatibility(
                f"incompatible port placement for {getattr(demand, 'name')}: "
                f"{demand_placement.name} != {supply_placement.name}"
            )
        return ACCEPTED

    def is_expression_family(self) -> bool:
        return False

    def is_signature_parameter_family(self) -> bool:
        return False


@dataclass(frozen=True, eq=False)
class _BlockPlacement(PortPlacement):
    name: str = "block"


@dataclass(frozen=True, eq=False)
class _ExpressionPlacement(PortPlacement):
    name: str = "expr"

    def is_expression_family(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _CallArgumentPlacement(PortPlacement):
    name: str = "call_arg"

    def accepts_supply(self, demand: object, supply: object) -> Compatibility:
        supply_placement = getattr(supply, "placement")
        if supply_placement.is_expression_family():
            return ACCEPTED
        return RejectedCompatibility(
            f"incompatible port placement for {getattr(demand, 'name')}: "
            f"{self.name} != {supply_placement.name}"
        )

    def is_expression_family(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _IdentifierPlacement(PortPlacement):
    name: str = "identifier"


@dataclass(frozen=True, eq=False)
class _SignatureParameterPlacement(PortPlacement):
    name: str = "params"

    def is_signature_parameter_family(self) -> bool:
        return True


BLOCK_PLACEMENT = _BlockPlacement()
EXPRESSION_PLACEMENT = _ExpressionPlacement()
CALL_ARGUMENT_PLACEMENT = _CallArgumentPlacement()
IDENTIFIER_PLACEMENT = _IdentifierPlacement()
SIGNATURE_PARAMETER_PLACEMENT = _SignatureParameterPlacement()


def placement_for_shape(shape: MarkerShape) -> PortPlacement:
    """Return the default port placement for a marker shape."""
    if shape is BLOCK:
        return BLOCK_PLACEMENT
    if shape is IDENTIFIER:
        return IDENTIFIER_PLACEMENT
    if shape is PARAMETER:
        return SIGNATURE_PARAMETER_PLACEMENT
    if shape is POSITIONAL_VARIADIC or shape is NAMED_VARIADIC:
        return CALL_ARGUMENT_PLACEMENT
    return EXPRESSION_PLACEMENT


def normalize_port_placement(
    placement: PortPlacement | str,
) -> PortPlacement:
    """Normalize compatibility constructor inputs to placement objects."""
    if isinstance(placement, PortPlacement):
        return placement
    if placement == BLOCK_PLACEMENT.name:
        return BLOCK_PLACEMENT
    if placement == EXPRESSION_PLACEMENT.name:
        return EXPRESSION_PLACEMENT
    if placement == CALL_ARGUMENT_PLACEMENT.name:
        return CALL_ARGUMENT_PLACEMENT
    if placement == IDENTIFIER_PLACEMENT.name:
        return IDENTIFIER_PLACEMENT
    if placement == SIGNATURE_PARAMETER_PLACEMENT.name:
        return SIGNATURE_PARAMETER_PLACEMENT
    raise ValueError(f"unknown port placement: {placement!r}")


class PortMutability(SemanticSingleton):
    """Mutability compatibility for ports."""

    def accepts_supply_mutability(
        self, supply: "PortMutability"
    ) -> Compatibility:
        if self is supply:
            return ACCEPTED
        return RejectedCompatibility(
            f"incompatible port mutability: {self.name} != {supply.name}"
        )


@dataclass(frozen=True, eq=False)
class _ConstMutability(PortMutability):
    name: str = "const"


@dataclass(frozen=True, eq=False)
class _NamedMutability(PortMutability):
    _name: str

    @property
    def name(self) -> str:
        return self._name


CONST_MUTABILITY = _ConstMutability()


def normalize_port_mutability(
    mutability: PortMutability | str,
) -> PortMutability:
    """Normalize compatibility constructor inputs to mutability objects."""
    if isinstance(mutability, PortMutability):
        return mutability
    if mutability == CONST_MUTABILITY.name:
        return CONST_MUTABILITY
    return _NamedMutability(mutability)


class PortOrigin(SemanticSingleton):
    """Where a port came from in authored or emitted Astichi source."""

    def is_additive_hole_demand(self) -> bool:
        return False

    def is_external_bind_demand(self) -> bool:
        return False

    def is_identifier_demand(self) -> bool:
        return False

    def is_identifier_supply(self) -> bool:
        return False

    def is_parameter_hole_demand(self) -> bool:
        return False


@dataclass(frozen=True, eq=False)
class _HoleOrigin(PortOrigin):
    name: str = "hole"

    def is_additive_hole_demand(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _BindExternalOrigin(PortOrigin):
    name: str = "bind_external"

    def is_external_bind_demand(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _ArgIdentifierOrigin(PortOrigin):
    name: str = "arg"

    def is_identifier_demand(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _ImportOrigin(PortOrigin):
    name: str = "import"

    def is_identifier_demand(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _PassOrigin(PortOrigin):
    name: str = "pass"

    def is_identifier_demand(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _ExportOrigin(PortOrigin):
    name: str = "export"

    def is_identifier_supply(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _ParameterHoleOrigin(PortOrigin):
    name: str = "param_hole"

    def is_parameter_hole_demand(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _ParameterPayloadOrigin(PortOrigin):
    name: str = "params"


@dataclass(frozen=True, eq=False)
class _InsertOrigin(PortOrigin):
    name: str = "insert"


@dataclass(frozen=True, eq=False)
class _ImpliedDemandOrigin(PortOrigin):
    name: str = "implied"


HOLE_ORIGIN = _HoleOrigin()
BIND_EXTERNAL_ORIGIN = _BindExternalOrigin()
ARG_IDENTIFIER_ORIGIN = _ArgIdentifierOrigin()
IMPORT_ORIGIN = _ImportOrigin()
PASS_ORIGIN = _PassOrigin()
EXPORT_ORIGIN = _ExportOrigin()
PARAMETER_HOLE_ORIGIN = _ParameterHoleOrigin()
PARAMETER_PAYLOAD_ORIGIN = _ParameterPayloadOrigin()
INSERT_ORIGIN = _InsertOrigin()
IMPLIED_DEMAND_ORIGIN = _ImpliedDemandOrigin()


@dataclass(frozen=True)
class PortOrigins:
    """Frozen set of behavior-bearing origins for a merged port."""

    items: frozenset[PortOrigin]

    @classmethod
    def of(cls, *origins: PortOrigin) -> "PortOrigins":
        return cls(frozenset(origins))

    @property
    def names(self) -> frozenset[str]:
        return frozenset(origin.name for origin in self.items)

    def is_external_bind_demand(self) -> bool:
        return any(origin.is_external_bind_demand() for origin in self.items)

    def is_identifier_demand(self) -> bool:
        return any(origin.is_identifier_demand() for origin in self.items)

    def is_identifier_supply(self) -> bool:
        return any(origin.is_identifier_supply() for origin in self.items)

    def is_additive_hole_demand(self) -> bool:
        return any(origin.is_additive_hole_demand() for origin in self.items)

    def is_parameter_hole_demand(self) -> bool:
        return any(origin.is_parameter_hole_demand() for origin in self.items)
