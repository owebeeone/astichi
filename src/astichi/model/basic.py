"""Concrete immutable composable carrier for Astichi V1."""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from astichi.asttools import clone_ast
from astichi.diagnostics import format_astichi_error
from astichi.lowering import RecognizedMarker, apply_external_bindings, recognize_markers
from astichi.lowering.markers import ARG_IDENTIFIER, strip_identifier_suffix
from astichi.model.composable import Composable
from astichi.model.external_values import validate_external_value, value_to_ast
from astichi.model.inventory import (
    Inventory,
    build_inventory,
    empty_inventory,
)
from astichi.model.inventory_describe import describe_inventory
from astichi.model.origin import CompileOrigin
from astichi.model.ports import (
    DemandPort,
    SupplyPort,
    extract_demand_ports,
    extract_supply_ports,
)
from astichi.perf_counters import counted_perf_call
from astichi.perf_counters import active_perf_counters

if TYPE_CHECKING:
    from astichi.hygiene import NameClassification
    from astichi.lower_engine.facade import LowerTemplateBinding
    from astichi.model.descriptors import ComposableDescription


@dataclass(frozen=True)
class BasicComposable(Composable):
    """First concrete immutable composable implementation."""

    tree: ast.Module
    origin: CompileOrigin
    markers: tuple[RecognizedMarker, ...] = field(default_factory=tuple)
    classification: NameClassification | None = None
    demand_ports: tuple[DemandPort, ...] = field(default_factory=tuple)
    supply_ports: tuple[SupplyPort, ...] = field(default_factory=tuple)
    inventory: Inventory = field(default_factory=empty_inventory)
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
    _lower_template: LowerTemplateBinding | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _already_materialized: bool = field(
        default=False,
        repr=False,
        compare=False,
    )

    def arg_bindings_map(self) -> dict[str, str]:
        """Return the identifier-arg resolutions as a plain dict."""
        return dict(self.arg_bindings)

    def emit(self, *, provenance: bool = True) -> str:
        from astichi.emit import emit_source
        from astichi.materialize.api import _reify_scope_keep_metadata_for_emit

        tree = clone_ast(self.tree)
        _reify_scope_keep_metadata_for_emit(tree)
        if self.arg_bindings:
            _apply_emitted_arg_bindings(tree, dict(self.arg_bindings))
        return emit_source(tree, provenance=provenance)

    def emit_commented(self) -> str:
        from astichi.materialize.api import emit_commented_composable

        return emit_commented_composable(self)

    def to_executable_ast(self) -> ast.Module:
        if self._already_materialized:
            counters = active_perf_counters()
            if counters is None:
                return clone_ast(self.tree)
            with counters.measure("copy_python_ast"):
                return clone_ast(self.tree)

        from astichi.materialize import to_executable_ast

        return to_executable_ast(self)

    def materialize(self) -> "BasicComposable":
        from astichi.materialize import materialize_composable

        return materialize_composable(self)

    def describe(self) -> "ComposableDescription":
        return describe_inventory(self.inventory)

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
                tree=clone_ast(self.tree),
                origin=self.origin,
                bound_externals=self.bound_externals,
            )

        bind_external_demands = {
            port.name
            for port in self.demand_ports
            if port.is_external_bind_demand()
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

        native = _try_native_bind(self, resolved)
        if native is not None:
            return native

        rebound_tree = clone_ast(self.tree)
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
        native = _try_native_keep_names(self, new_keep_names)
        if native is not None:
            return native
        return _rebuild_composable(
            tree=clone_ast(self.tree),
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
            if port.is_identifier_demand()
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
        native = _try_native_bind_identifier(self, resolved, merged)
        if native is not None:
            return native

        rebound_tree = clone_ast(self.tree)
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


def apply_source_overlay(
    piece: BasicComposable,
    *,
    bind_values: Mapping[str, object] | None = None,
    arg_names: Mapping[str, str] | None = None,
    keep_names: Iterable[str] | None = None,
) -> BasicComposable:
    """Apply edge-local source specialization without mutating the base piece."""
    specialized = piece
    if bind_values is not None:
        specialized = specialized.bind(bind_values)
    if keep_names is not None:
        specialized = specialized.with_keep_names(keep_names)
    if arg_names is not None:
        specialized = specialized.bind_identifier(arg_names)
    return specialized


def _try_native_bind(
    piece: BasicComposable,
    resolved: Mapping[str, object],
) -> BasicComposable | None:
    if not resolved:
        return None
    session = _native_specialization_session(piece)
    if session is None:
        return None
    module, engine, template, workspace = session
    try:
        state, root = _native_overlay_state(module, engine, template)
        for name, value in resolved.items():
            record_index = _native_record_index(piece, "external.bind", name)
            if record_index is None:
                return None
            target = module.assembly_state_record_handle(
                engine,
                state,
                root,
                record_index,
            )
            overlay = module.assembly_state_append_overlay(
                engine,
                state,
                target,
                "external",
                name,
            )
            module.materialization_workspace_apply_external_overlay_literal(
                engine,
                workspace,
                state,
                overlay,
                ast.unparse(value_to_ast(value)),
            )
        _increment_counter("native_specialize_bind")
        return _native_reproject_specialized(
            piece,
            module=module,
            engine=engine,
            workspace=workspace,
            bound_externals=frozenset(set(piece.bound_externals) | set(resolved)),
            arg_bindings=piece.arg_bindings,
            keep_names=piece.keep_names,
        )
    finally:
        module.engine_close(engine)


def _try_native_bind_identifier(
    piece: BasicComposable,
    resolved: Mapping[str, str],
    merged: tuple[tuple[str, str], ...],
) -> BasicComposable | None:
    if not resolved:
        return None
    session = _native_specialization_session(piece)
    if session is None:
        return None
    module, engine, template, workspace = session
    try:
        state, root = _native_overlay_state(module, engine, template)
        for name, target_name in resolved.items():
            record_index = _native_record_index(piece, "identifier.demand", name)
            if record_index is None:
                return None
            target = module.assembly_state_record_handle(
                engine,
                state,
                root,
                record_index,
            )
            overlay = module.assembly_state_append_overlay(
                engine,
                state,
                target,
                _native_identifier_overlay_kind(piece, name),
                target_name,
            )
            module.materialization_workspace_apply_identifier_overlay(
                engine,
                workspace,
                state,
                overlay,
            )
        _increment_counter("native_specialize_identifier")
        return _native_reproject_specialized(
            piece,
            module=module,
            engine=engine,
            workspace=workspace,
            bound_externals=piece.bound_externals,
            arg_bindings=merged,
            keep_names=piece.keep_names,
        )
    finally:
        module.engine_close(engine)


def _try_native_keep_names(
    piece: BasicComposable,
    keep_names: frozenset[str],
) -> BasicComposable | None:
    if not _can_native_specialize(piece):
        return None
    _increment_counter("native_specialize_keep")
    return BasicComposable(
        tree=piece.tree,
        origin=piece.origin,
        markers=piece.markers,
        classification=piece.classification,
        demand_ports=piece.demand_ports,
        supply_ports=piece.supply_ports,
        inventory=piece.inventory,
        bound_externals=piece.bound_externals,
        arg_bindings=piece.arg_bindings,
        keep_names=keep_names,
        _lower_template=piece._lower_template,
        _already_materialized=piece._already_materialized,
    )


def _native_specialization_session(
    piece: BasicComposable,
) -> tuple[object, object, object, object] | None:
    binding = piece._lower_template
    if not _can_native_specialize(piece):
        return None
    assert binding is not None
    assert binding.native_source is not None
    assert binding.native_origin is not None
    from astichi.lower_engine import ensure_current_native_surface_bundle
    from astichi.lower_engine.native import load_native_extension

    module = load_native_extension(required=False)
    if module is None:
        return None
    engine = module.engine_create()
    try:
        ensure_current_native_surface_bundle(
            module=module,
            engine_handle=engine,
        )
        template = module.register_template_package_v2_source(
            engine,
            binding.native_source,
            binding.native_origin.file_name,
            binding.native_origin.line_number,
        )
        workspace = module.materialization_workspace_create(engine, template)
    except Exception:
        module.engine_close(engine)
        raise
    return module, engine, template, workspace


def _can_native_specialize(piece: BasicComposable) -> bool:
    binding = piece._lower_template
    if binding is None:
        return False
    if not getattr(binding, "backend", "").startswith("native-"):
        return False
    if binding.native_source is None or binding.native_origin is None:
        return False
    from astichi.lower_engine.native import select_lower_engine

    return select_lower_engine().selected_engine in {"native-rust", "native-cpp"}


def _native_overlay_state(
    module: object,
    engine: object,
    template: object,
) -> tuple[object, object]:
    state = module.assembly_state_create(engine)
    root = module.assembly_state_append_occurrence(
        engine,
        state,
        template,
        ("Root",),
    )
    return state, root


def _native_record_index(
    piece: BasicComposable,
    inventory_kind: str,
    name: str,
) -> int | None:
    binding = piece._lower_template
    if binding is None:
        return None
    for index, record in enumerate(binding.record_specs):
        if record.inventory_kind == inventory_kind and record.resource_name == name:
            return index
    return None


def _native_identifier_overlay_kind(piece: BasicComposable, name: str) -> str:
    for port in piece.demand_ports:
        if port.name == name and port.is_identifier_demand():
            if port.sources == frozenset({"arg"}):
                return "identifier_suffix"
            return "identifier"
    return "identifier"


def _native_reproject_specialized(
    piece: BasicComposable,
    *,
    module: object,
    engine: object,
    workspace: object,
    bound_externals: frozenset[str],
    arg_bindings: tuple[tuple[str, str], ...],
    keep_names: frozenset[str],
) -> BasicComposable:
    from astichi.hygiene import analyze_names
    from astichi.lower_engine import register_native_template_source_direct

    tree = module.materialization_workspace_copy_to_python_ast(engine, workspace)
    source = f"{module.materialization_workspace_to_source(engine, workspace)}\n"
    lower_template, inventory = register_native_template_source_direct(
        source=source,
        origin=piece.origin,
        tree=tree,
    )
    markers = recognize_markers(tree)
    provisional = BasicComposable(
        tree=tree,
        origin=piece.origin,
        markers=markers,
        bound_externals=bound_externals,
        arg_bindings=arg_bindings,
        keep_names=keep_names,
    )
    classification = analyze_names(
        provisional,
        mode="permissive",
        preserved_names=keep_names,
    )
    from astichi.model.ports import merge_reprojected_demand_ports

    demand_ports = merge_reprojected_demand_ports(
        piece.demand_ports,
        extract_demand_ports(markers, classification),
        bound_externals=bound_externals,
    )
    supply_ports = extract_supply_ports(markers)
    return BasicComposable(
        tree=tree,
        origin=piece.origin,
        markers=markers,
        classification=classification,
        demand_ports=demand_ports,
        supply_ports=supply_ports,
        inventory=inventory,
        bound_externals=bound_externals,
        arg_bindings=arg_bindings,
        keep_names=keep_names,
        _lower_template=lower_template,
    )


def _increment_counter(key: str) -> None:
    counters = active_perf_counters()
    if counters is not None:
        counters.increment(key)


@counted_perf_call("rebuild_composable")
def _rebuild_composable(
    *,
    tree: ast.Module,
    origin: CompileOrigin,
    bound_externals: frozenset[str],
    arg_bindings: tuple[tuple[str, str], ...] = (),
    keep_names: frozenset[str] = frozenset(),
    already_materialized: bool = False,
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
    demand_ports = extract_demand_ports(markers, classification)
    supply_ports = extract_supply_ports(markers)
    inventory = build_inventory(tree, markers, demand_ports, supply_ports)
    lower_template = _register_lower_template(
        tree=tree,
        origin=origin,
        inventory=inventory,
    )
    return BasicComposable(
        tree=tree,
        origin=origin,
        markers=markers,
        classification=classification,
        demand_ports=demand_ports,
        supply_ports=supply_ports,
        inventory=inventory,
        bound_externals=bound_externals,
        arg_bindings=arg_bindings,
        keep_names=keep_names,
        _lower_template=lower_template,
        _already_materialized=already_materialized,
    )


def _register_lower_template(
    *,
    tree: ast.Module,
    origin: CompileOrigin,
    inventory: Inventory,
) -> "LowerTemplateBinding":
    from astichi.lower_engine import (
        register_inventory_template,
        register_native_template_source,
        select_lower_engine,
    )

    lower_template = register_inventory_template(
        tree=tree,
        origin=origin,
        inventory=inventory,
    )
    selected = select_lower_engine().selected_engine
    if selected == "python":
        return lower_template
    if selected not in {"native-rust", "native-cpp"}:
        return lower_template
    return register_native_template_source(
        source=f"{ast.unparse(tree)}\n",
        origin=origin,
        fallback_binding=lower_template,
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
