"""Concrete immutable composable carrier for Astichi V1."""

from __future__ import annotations

import ast
import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from astichi.diagnostics import format_astichi_error
from astichi.lowering import RecognizedMarker, apply_external_bindings, recognize_markers
from astichi.lowering.markers import ARG_IDENTIFIER, strip_identifier_suffix
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

        tree = copy.deepcopy(self.tree)
        if self.arg_bindings:
            _apply_emitted_arg_bindings(tree, dict(self.arg_bindings))
        return emit_source(tree, provenance=provenance)

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
                    format_astichi_error(
                        "materialize",
                        f"cannot re-bind `{key}`: the external binding has already "
                        "been applied to this composable",
                        hint="each external key is applied once; use a fresh composable if needed",
                    )
                )
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    f"no astichi_bind_external({key}) site found; known bind-external "
                    f"demands on this composable: {known_demands!r}",
                    hint="add `astichi_bind_external({key})` to the snippet or bind only listed keys",
                )
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
                        format_astichi_error(
                            "materialize",
                            f"keep-name `{name}` is not a valid Python identifier",
                            hint="pass valid Python identifiers to `with_keep_names(...)`",
                        )
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
        """Resolve identifier-demand slots to target identifiers.

        Issue 005 §6 / 5d. Keys must be IDENTIFIER-shape demand-port
        names on this composable; values must be valid Python
        identifiers. All three surfaces — `__astichi_arg__` suffix
        slots, `astichi_import(...)` declarations, and
        `astichi_pass(...)` sites — are rewritten into the source tree
        eagerly so later merge-time validators (e.g. the call-argument
        payload duplicate-keyword check in
        `lowering/call_argument_payloads.py`) see the resolved names
        rather than the pre-resolution suffix text. Resolutions are
        also retained in `arg_bindings` metadata so the same name can
        be pinned through hygiene and so `emit()` -> `compile()` round
        trips preserve the binding.
        """
        resolved = _resolve_identifier_bindings(mapping, names)
        if not resolved:
            return self

        # Issue 006: accept IDENTIFIER demand ports sourced from
        # `__astichi_arg__` suffix slots, `astichi_import`
        # declarations, or value-form `astichi_pass(...)` sites — they
        # share the same identifier-binding surface.
        arg_demand_names = {
            port.name
            for port in self.demand_ports
            if "arg" in port.sources or "import" in port.sources or "pass" in port.sources
        }
        existing = dict(self.arg_bindings)
        for key, value in resolved.items():
            # Re-bind detection must precede the demand-port check:
            # eager `__astichi_arg__` rewrite removes the suffix slot
            # from the tree after the first bind, so a second bind of
            # the same name would otherwise surface as "unknown slot"
            # instead of the (more useful) "cannot re-bind" error.
            if key in existing:
                if existing[key] != value:
                    raise ValueError(
                        format_astichi_error(
                            "materialize",
                            f"cannot re-bind identifier arg `{key}`: already "
                            f"resolved to `{existing[key]}`",
                            hint="use one resolution per slot; remove conflicting `bind_identifier`",
                        )
                    )
                continue
            if key not in arg_demand_names:
                known = tuple(sorted(arg_demand_names))
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        f"no __astichi_arg__ / astichi_import / astichi_pass slot named "
                        f"`{key}`; known identifier demands on this "
                        f"composable: {known!r}",
                        hint="use `bind_identifier` only for declared slot names; "
                        "declare identifier demands with `__astichi_arg__`, "
                        "`astichi_import(...)`, or `astichi_pass(...)`",
                    )
                )
            existing[key] = value

        merged = tuple(sorted(existing.items()))
        rebound_tree = copy.deepcopy(self.tree)
        from astichi.materialize.api import (
            _resolve_arg_identifiers,
            _resolve_boundary_imports,
            _resolve_boundary_passes,
        )

        # Eagerly rewrite `__astichi_arg__` suffix slots into their
        # resolved identifiers. Previously these were left in the tree
        # and only substituted at materialize time via `arg_bindings`;
        # that lazy form broke merge-time validators that read the raw
        # kwarg text (e.g. repeatedly instantiating a parameterized
        # `astichi_funcargs(field__astichi_arg__=...)` payload for
        # distinct fields collided on `field__astichi_arg__` in the
        # duplicate-keyword check before resolution was consulted).
        _resolve_arg_identifiers(rebound_tree, resolved)
        _resolve_boundary_imports(rebound_tree, resolved)
        _resolve_boundary_passes(rebound_tree, resolved)
        return _rebuild_composable(
            tree=rebound_tree,
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
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        f"binding key `{key}` is not a valid Python identifier",
                        hint="use `bind(foo=...)` only with valid identifier keys",
                    )
                )
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
                    format_astichi_error(
                        "materialize",
                        f"identifier-arg slot name `{key}` is not a valid Python identifier",
                        hint="keys in `bind_identifier` must be valid Python identifiers",
                    )
                )
            resolved[key] = value
    resolved.update(values)
    for key, value in resolved.items():
        if not isinstance(value, str) or not value.isidentifier():
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    f"identifier-arg resolution for `{key}` must be a valid "
                    f"Python identifier, got {value!r}",
                    hint="resolve each slot to a plain identifier string",
                )
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


def _apply_emitted_arg_bindings(tree: ast.AST, bindings: dict[str, str]) -> None:
    """Rewrite resolved ``__astichi_arg__`` slots before source emission."""
    if not bindings:
        return

    class _Resolver(ast.NodeTransformer):
        def _resolve(self, name: str) -> str:
            base, marker = strip_identifier_suffix(name)
            if marker is not ARG_IDENTIFIER:
                return name
            return bindings.get(base, name)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            node.name = self._resolve(node.name)
            return self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
            node.name = self._resolve(node.name)
            return self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
            node.name = self._resolve(node.name)
            return self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> ast.AST:
            node.id = self._resolve(node.id)
            return node

        def visit_arg(self, node: ast.arg) -> ast.AST:
            node.arg = self._resolve(node.arg)
            return self.generic_visit(node)

        def visit_keyword(self, node: ast.keyword) -> ast.AST:
            # Issue 005 §1 extension: call-site keyword-argument names
            # are identifier positions too. `keyword.arg is None` is the
            # `**mapping` splat, which has no identifier to resolve.
            if node.arg is not None:
                node.arg = self._resolve(node.arg)
            return self.generic_visit(node)

    _Resolver().visit(tree)
