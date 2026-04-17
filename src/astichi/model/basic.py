"""Concrete immutable composable carrier for Astichi V1."""

from __future__ import annotations

import ast
import copy
from collections.abc import Iterable, Mapping
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
    # Issue 005 §6 / 5d: user-supplied resolutions for `__astichi_arg__`
    # slots, keyed by stripped name -> target Python identifier. Stored as
    # a sorted tuple of pairs so the frozen dataclass stays hashable; use
    # `arg_bindings_map()` to consume as a mapping.
    arg_bindings: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    # Issue 005 §4 / 5d: names the user has pinned as hygiene-preserved
    # without rewriting source (the source-level counterpart of a
    # `__astichi_keep__` suffix). Additive across pipeline passes.
    keep_names: frozenset[str] = field(default_factory=frozenset)

    def arg_bindings_map(self) -> dict[str, str]:
        """Return the identifier-arg resolutions as a plain dict."""
        return dict(self.arg_bindings)

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
            arg_bindings=self.arg_bindings,
            keep_names=self.keep_names,
        )

    def with_keep_names(
        self, names: Iterable[str] | None = None, /, *positional: str
    ) -> "BasicComposable":
        """Pin additional identifiers as hygiene-preserved.

        Issue 005 §4 / 5d: names in the union of `names` and
        `positional` are added to the composable's keep set. The set is
        additive and idempotent; validation matches `keep_names=` on
        `astichi.compile`.
        """
        merged: set[str] = set(self.keep_names)
        iterable: Iterable[str] = ()
        if names is not None:
            iterable = names
        for collection in (iterable, positional):
            for name in collection:
                if not isinstance(name, str) or not name.isidentifier():
                    raise ValueError(
                        f"keep-name `{name}` is not a valid Python identifier"
                    )
                merged.add(name)
        new_keep_names = frozenset(merged)
        if new_keep_names == self.keep_names:
            return self
        return _rebuild_composable(
            tree=copy.deepcopy(self.tree),
            origin=self.origin,
            bound_externals=self.bound_externals,
            arg_bindings=self.arg_bindings,
            keep_names=new_keep_names,
        )

    def bind_identifier(
        self,
        mapping: Mapping[str, str] | None = None,
        /,
        **names: str,
    ) -> "BasicComposable":
        """Resolve `__astichi_arg__` slots to target identifiers.

        Issue 005 §6 / 5d. Keys must be IDENTIFIER-shape demand-port
        names on this composable; values must be valid Python
        identifiers. The resolution is recorded on the returned
        composable and applied by materialize via the arg-resolver
        pass; the source tree is not rewritten here.
        """
        resolved = _resolve_identifier_bindings(mapping, names)
        if not resolved:
            return self

        arg_demand_names = {
            port.name
            for port in self.demand_ports
            if "arg" in port.sources
        }
        existing = dict(self.arg_bindings)
        for key, value in resolved.items():
            if key not in arg_demand_names:
                known = tuple(sorted(arg_demand_names))
                raise ValueError(
                    f"no __astichi_arg__ slot named `{key}`; known "
                    f"identifier-arg demands on this composable: {known!r}"
                )
            if key in existing:
                raise ValueError(
                    f"cannot re-bind identifier arg `{key}`: already "
                    f"resolved to `{existing[key]}`"
                )
            existing[key] = value

        merged = tuple(sorted(existing.items()))
        return _rebuild_composable(
            tree=copy.deepcopy(self.tree),
            origin=self.origin,
            bound_externals=self.bound_externals,
            arg_bindings=merged,
            keep_names=self.keep_names,
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


def _resolve_identifier_bindings(
    mapping: Mapping[str, str] | None,
    values: dict[str, str],
) -> dict[str, str]:
    if mapping is None:
        resolved: dict[str, str] = {}
    else:
        if not isinstance(mapping, Mapping):
            raise TypeError("bind_identifier mapping must implement Mapping")
        resolved = {}
        for key, value in mapping.items():
            if not isinstance(key, str) or not key.isidentifier():
                raise ValueError(
                    f"identifier-arg slot name `{key}` is not a valid Python identifier"
                )
            resolved[key] = value
    resolved.update(values)
    for key, value in resolved.items():
        if not isinstance(value, str) or not value.isidentifier():
            raise ValueError(
                f"identifier-arg resolution for `{key}` must be a valid "
                f"Python identifier, got {value!r}"
            )
    return resolved


def _rebuild_composable(
    *,
    tree: ast.Module,
    origin: CompileOrigin,
    bound_externals: frozenset[str],
    arg_bindings: tuple[tuple[str, str], ...] = (),
    keep_names: frozenset[str] = frozenset(),
) -> BasicComposable:
    from astichi.hygiene import analyze_names

    markers = recognize_markers(tree)
    provisional = BasicComposable(
        tree=tree,
        origin=origin,
        markers=markers,
        bound_externals=bound_externals,
        arg_bindings=arg_bindings,
        keep_names=keep_names,
    )
    classification = analyze_names(
        provisional, mode="permissive", preserved_names=keep_names
    )
    return BasicComposable(
        tree=tree,
        origin=origin,
        markers=markers,
        classification=classification,
        demand_ports=extract_demand_ports(markers, classification),
        supply_ports=extract_supply_ports(markers),
        bound_externals=bound_externals,
        arg_bindings=arg_bindings,
        keep_names=keep_names,
    )
