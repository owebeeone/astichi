"""Concrete immutable composable carrier for Astichi V1."""

from __future__ import annotations

import ast
import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from astichi.lowering import RecognizedMarker, apply_external_bindings, recognize_markers
from astichi.model.composable import Composable
from astichi.model.external_values import validate_external_value
from astichi.model.origin import CompileOrigin
from astichi.model.ports import (
    DemandPort,
    SupplyPort,
    extract_demand_ports,
    extract_supply_ports,
)

if TYPE_CHECKING:
    from astichi.hygiene import NameClassification


@dataclass(frozen=True)
class BasicComposable(Composable):
    """First concrete immutable composable implementation."""

    tree: ast.Module
    origin: CompileOrigin
    markers: tuple[RecognizedMarker, ...] = field(default_factory=tuple)
    classification: NameClassification | None = None
    demand_ports: tuple[DemandPort, ...] = field(default_factory=tuple)
    supply_ports: tuple[SupplyPort, ...] = field(default_factory=tuple)
    bound_externals: frozenset[str] = field(default_factory=frozenset)

    def emit(self, *, provenance: bool = True) -> str:
        from astichi.emit import emit_source

        return emit_source(self.tree, provenance=provenance)

    def materialize(self) -> "BasicComposable":
        from astichi.materialize import materialize_composable

        return materialize_composable(self)

    def bind(
        self,
        mapping: Mapping[str, object] | None = None,
        /,
        **values: object,
    ) -> "BasicComposable":
        """Apply external bindings and return a new immutable composable."""

        resolved = _resolve_bindings(mapping, values)
        if not resolved:
            return _rebuild_composable(
                tree=copy.deepcopy(self.tree),
                origin=self.origin,
                bound_externals=self.bound_externals,
            )

        bind_external_demands = {
            port.name
            for port in self.demand_ports
            if port.sources == frozenset({"bind_external"})
        }
        known_demands = tuple(sorted(bind_external_demands))

        for key in resolved:
            if key in bind_external_demands:
                continue
            if key in self.bound_externals:
                raise ValueError(
                    f"cannot re-bind `{key}`: the external binding has already "
                    "been applied to this composable"
                )
            raise ValueError(
                f"no astichi_bind_external({key}) site found; known bind-external "
                f"demands on this composable: {known_demands!r}"
            )

        for value in resolved.values():
            validate_external_value(value)

        rebound_tree = copy.deepcopy(self.tree)
        apply_external_bindings(rebound_tree, resolved)
        return _rebuild_composable(
            tree=rebound_tree,
            origin=self.origin,
            bound_externals=frozenset(set(self.bound_externals) | set(resolved)),
        )


def _resolve_bindings(
    mapping: Mapping[str, object] | None,
    values: dict[str, object],
) -> dict[str, object]:
    if mapping is None:
        resolved: dict[str, object] = {}
    else:
        if not isinstance(mapping, Mapping):
            raise TypeError("bind mapping must implement Mapping")
        resolved = {}
        for key, value in mapping.items():
            if not isinstance(key, str) or not key.isidentifier():
                raise ValueError(f"binding key `{key}` is not a valid Python identifier")
            resolved[key] = value
    resolved.update(values)
    return resolved


def _rebuild_composable(
    *,
    tree: ast.Module,
    origin: CompileOrigin,
    bound_externals: frozenset[str],
) -> BasicComposable:
    from astichi.hygiene import analyze_names

    markers = recognize_markers(tree)
    provisional = BasicComposable(
        tree=tree,
        origin=origin,
        markers=markers,
        bound_externals=bound_externals,
    )
    classification = analyze_names(provisional, mode="permissive")
    return BasicComposable(
        tree=tree,
        origin=origin,
        markers=markers,
        classification=classification,
        demand_ports=extract_demand_ports(markers, classification),
        supply_ports=extract_supply_ports(markers),
        bound_externals=bound_externals,
    )
