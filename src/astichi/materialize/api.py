"""Build merge and materialization for Astichi V1."""

from __future__ import annotations

import ast
import copy
import re
from dataclasses import dataclass

from astichi.ast_provenance import propagate_ast_source_locations
from astichi.asttools import (
    import_statement_binding_names,
    is_astichi_insert_call,
    is_astichi_insert_shell,
    is_expression_insert_call as _is_expression_insert_call,
)
from astichi.diagnostics import default_build_path_hint, format_astichi_error
from astichi.builder.graph import (
    AdditiveEdge,
    AssignBinding,
    BuilderGraph,
    EdgeSourceOverlay,
    IdentifierBinding,
    InstanceRecord,
)
from astichi.hygiene import (
    SyntheticBindingOccurrence,
    analyze_names,
    assign_scope_identity,
    rename_scope_collisions,
)
from astichi.lowering import (
    PayloadLocalDirective,
    DOUBLE_STAR_FUNC_ARG_REGION,
    PLAIN_FUNC_ARG_REGION,
    RecognizedMarker,
    STARRED_FUNC_ARG_REGION,
    collect_payload_local_directives,
    direct_funcargs_directive_calls,
    extract_funcargs_payload,
    extract_params_payload_from_body,
    has_params_payload,
    is_astichi_funcargs_call,
    lower_payload_for_region,
    param_hole_name,
    register_explicit_keyword,
    recognize_markers,
    validate_payload_for_region,
)
from astichi.lowering.marker_contexts import CALL_CONTEXT
from astichi.lowering.markers import (
    ALL_MARKERS,
    ARG_IDENTIFIER,
    IMPORT,
    KEEP,
    PASS,
    PYIMPORT,
    boundary_explicit_bind_enabled,
    boundary_outer_bind_enabled,
    call_name,
    is_call_to_marker,
    KEEP_IDENTIFIER,
    scan_statement_prefix,
    set_boundary_explicit_bind_state,
    strip_identifier_suffix,
)
from astichi.lowering.external_ref import apply_external_ref_lowering
from astichi.lowering.sentinel_attrs import match_transparent_sentinel
from astichi.lowering.unroll import iter_target_name, unroll_tree
from astichi.materialize.pyimport import (
    collect_managed_imports,
    has_pyimport_marker,
    insert_managed_imports,
)
from astichi.model.basic import BasicComposable, apply_source_overlay
from astichi.model.origin import CompileOrigin
from astichi.model.ports import (
    DemandPort,
    SupplyPort,
    extract_demand_ports,
    extract_supply_ports,
    validate_port_pair,
)
from astichi.path_resolution import (
    ROOT_SCOPE_HOLE_PREFIX as _ROOT_SCOPE_HOLE_PREFIX,
    ShellIndex,
    boundary_import_statement,
    collect_hole_names_in_body,
    collect_identifier_demands_in_body,
    collect_identifier_suppliers_in_body,
    collect_param_hole_names_in_body,
    effective_root_body as _effective_root_body,
    extract_block_insert_shell,
    extract_hole_name as _extract_hole_name,
    extract_param_insert_shell,
    format_instance_leaf,
    promote_wrapped_root_ref_path,
    synthetic_root_scope_shell as _synthetic_root_scope_shell,
)
from astichi.shell_refs import (
    RefPath,
    format_ref_path,
    normalize_ref_path,
    prefix_insert_ref,
    set_insert_ref,
)


@dataclass(frozen=True)
class _ExpressionInsert:
    expr: ast.expr
    payload: object | None
    pyimports: tuple[ast.Call, ...]
    edge_order: int
    inline_order: int
    edge_index: int
    statement_index: int


@dataclass(frozen=True)
class _BlockContribution:
    """A block-target contribution wired via the builder.

    Per `AstichiApiDesignV1-CompositionUnification.md §3`, every `.add()`
    wiring produces an `astichi_insert`-decorated shell in the
    pre-materialize tree; this record carries the source body and the
    shell metadata for that synthesis.
    """

    source_instance: str
    order: int
    edge_index: int
    body: list[ast.stmt]
    shell_name: str
    ref_path: RefPath


@dataclass(frozen=True)
class _ParamContribution:
    source_instance: str
    order: int
    edge_index: int
    args: ast.arguments
    shell_name: str
    ref_path: RefPath


class _SkipInsertShellTransformerMixin:
    def _visit_non_shell_node(self, node: ast.AST) -> ast.AST:
        if is_astichi_insert_shell(node):
            return node
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._visit_non_shell_node(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._visit_non_shell_node(node)


class _SkipInsertShellTransformerWithClassMixin(_SkipInsertShellTransformerMixin):
    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        return self._visit_non_shell_node(node)


class _SkipInsertShellVisitorWithClassMixin:
    def _visit_non_shell_node(self, node: ast.AST) -> None:
        if is_astichi_insert_shell(node):
            return
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_non_shell_node(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_non_shell_node(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_non_shell_node(node)


_IDENTIFIER_SANITIZER = re.compile(r"[^0-9A-Za-z_]")


def _sanitize_for_identifier(raw: str) -> str:
    cleaned = _IDENTIFIER_SANITIZER.sub("_", raw)
    if not cleaned:
        cleaned = "anon"
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


def _format_target_address(edge: AdditiveEdge) -> str:
    """Human-readable `root.slot[i][j]` form for diagnostics."""
    ref_prefix = ""
    target_ref_path = normalize_ref_path(edge.target.ref_path)
    if target_ref_path:
        ref_prefix = f".{format_ref_path(target_ref_path)}"
    suffix = "".join(f"[{i}]" for i in edge.target.path)
    return (
        f"{edge.target.root_instance}{ref_prefix}."
        f"{edge.target.target_name}{suffix}"
    )


def _refresh_composable(
    original: BasicComposable,
    tree: ast.Module,
    *,
    arg_bindings: tuple[tuple[str, str], ...] | None = None,
    keep_names: frozenset[str] | None = None,
) -> BasicComposable:
    """Re-extract markers/classification/ports against an unrolled tree."""
    markers = recognize_markers(tree)
    provisional = BasicComposable(
        tree=tree,
        origin=original.origin,
        markers=markers,
        bound_externals=original.bound_externals,
        arg_bindings=original.arg_bindings if arg_bindings is None else arg_bindings,
        keep_names=original.keep_names if keep_names is None else keep_names,
    )
    classification = analyze_names(
        provisional,
        mode="permissive",
        preserved_names=original.keep_names if keep_names is None else keep_names,
    )
    return BasicComposable(
        tree=tree,
        origin=original.origin,
        markers=markers,
        classification=classification,
        demand_ports=extract_demand_ports(markers, classification),
        supply_ports=extract_supply_ports(markers),
        bound_externals=original.bound_externals,
        arg_bindings=original.arg_bindings if arg_bindings is None else arg_bindings,
        keep_names=original.keep_names if keep_names is None else keep_names,
    )


def _edge_scoped_composable(
    record: InstanceRecord, edge: AdditiveEdge
) -> BasicComposable:
    piece = record.composable
    if not isinstance(piece, BasicComposable):
        raise TypeError(
            f"source instance {record.name} must be a BasicComposable; "
            f"got {type(piece).__name__}"
        )
    overlay = edge.overlay
    if overlay == EdgeSourceOverlay():
        return piece
    return apply_source_overlay(
        piece,
        bind_values=overlay.bind_values_map() if overlay.bind_values else None,
        arg_names=overlay.arg_names_map() if overlay.arg_names else None,
        keep_names=overlay.keep_names if overlay.keep_names else None,
    )


def _validate_indexed_targets(
    edges_by_target: dict[tuple[str, RefPath, str], list[tuple[int, AdditiveEdge]]],
    instance_records: dict[str, InstanceRecord],
) -> None:
    """Reject indexed edges whose post-unroll hole does not exist."""
    for (root, _ref_path, effective_name), indexed_edges in edges_by_target.items():
        origin_edge = indexed_edges[0][1]
        if not origin_edge.target.path:
            continue
        composable = instance_records[root].composable
        if _lookup_demand_port(composable, effective_name) is not None:
            continue
        addr = _format_target_address(origin_edge)
        raise ValueError(
            format_astichi_error(
                "materialize",
                f"indexed target {addr} has no matching astichi_hole "
                f"(expected synthetic name {root}.{effective_name}); "
                "index may be out of range or target was not unrolled",
                hint="enable unroll for indexed edges or fix the hole name / index",
            )
        )


def _apply_assign_bindings(
    assigns: tuple[AssignBinding, ...],
    instance_records: dict[str, InstanceRecord],
    trees: dict[str, ast.Module],
    shell_indexes: dict[str, ShellIndex],
) -> None:
    """Apply ``builder.assign`` wirings to local tree copies shell-locally."""
    target_keys_by_source_scope_name: dict[
        tuple[str, RefPath, str], set[tuple[str, RefPath, str]]
    ] = {}
    for binding in assigns:
        source_ref_path = normalize_ref_path(binding.source_ref_path)
        target_ref_path = normalize_ref_path(binding.target_ref_path)
        target_keys_by_source_scope_name.setdefault(
            (binding.source_instance, source_ref_path, binding.outer_name), set()
        ).add(
            (binding.target_instance, target_ref_path, binding.outer_name)
        )
    ambiguous_source_scope_names = frozenset(
        source_scope_key
        for source_scope_key, keys in target_keys_by_source_scope_name.items()
        if len(keys) > 1
    )
    published_target_aliases: set[tuple[str, RefPath, str]] = set()
    for binding in assigns:
        source_ref_path = normalize_ref_path(binding.source_ref_path)
        target_ref_path = normalize_ref_path(binding.target_ref_path)
        src = instance_records.get(binding.source_instance)
        if src is None:
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    f"builder.assign refers to unknown source instance "
                    f"`{binding.source_instance}`",
                    hint="register the source instance with `builder.add` before `assign`",
                )
            )
        dst = instance_records.get(binding.target_instance)
        if dst is None:
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    f"builder.assign refers to unknown target instance "
                    f"`{binding.target_instance}` "
                    f"(from {binding.source_instance}.{binding.inner_name})",
                    hint="register the target instance with `builder.add` before resolving assign",
                )
            )
        piece = src.composable
        if not isinstance(piece, BasicComposable):
            raise TypeError(
                f"builder.assign source instance `{binding.source_instance}` "
                f"must be a BasicComposable; got {type(piece).__name__}"
            )
        resolved_outer_name = binding.outer_name
        target_tree = trees[binding.target_instance]
        target_shell = shell_indexes[binding.target_instance].resolve(
            target_ref_path
        ).require(
            instance_name=binding.target_instance,
            role="assign target path",
        )
        target_body = (
            _effective_root_body(target_shell.body)
            if not target_ref_path
            else target_shell.body
        )
        if (
            binding.outer_name not in collect_identifier_suppliers_in_body(target_body)
        ):
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    "no readable supplier named "
                    f"`{binding.outer_name}` at "
                    f"`{format_instance_leaf(binding.target_instance, target_ref_path, binding.outer_name)}`",
                    hint="publish the name with `astichi_export` or an assignable value at that path",
                )
            )
        if target_ref_path or (
            binding.source_instance,
            source_ref_path,
            binding.outer_name,
        ) in ambiguous_source_scope_names:
            alias_key = (
                binding.target_instance,
                target_ref_path,
                binding.outer_name,
            )
            resolved_outer_name = _assign_target_alias_name(binding)
            if alias_key not in published_target_aliases:
                _publish_assign_target_alias(
                    target_body,
                    source_name=binding.outer_name,
                    alias_name=resolved_outer_name,
                    location_donor=target_body[0] if target_body else None,
                )
                published_target_aliases.add(alias_key)
                target_piece = _refresh_composable(dst.composable, target_tree)
                instance_records[binding.target_instance] = InstanceRecord(
                    name=binding.target_instance,
                    composable=target_piece,
                )
                shell_indexes[binding.target_instance] = ShellIndex.from_tree(
                    target_tree
                )
        source_tree = trees[binding.source_instance]
        source_shell = shell_indexes[binding.source_instance].resolve(
            source_ref_path
        ).require(
            instance_name=binding.source_instance,
            role="assign source path",
        )
        source_body = (
            _effective_root_body(source_shell.body)
            if not source_ref_path
            else source_shell.body
        )
        local_demands = collect_identifier_demands_in_body(source_body)
        if binding.inner_name not in local_demands:
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    f"no __astichi_arg__ / astichi_import / astichi_pass slot named "
                    f"`{binding.inner_name}` at "
                    f"`{format_instance_leaf(binding.source_instance, source_ref_path, binding.inner_name)}`",
                    hint="declare the slot in the source snippet or fix the path on `assign`",
                )
            )
        _rewrite_identifier_demands_in_body(
            source_body,
            {binding.inner_name: resolved_outer_name},
        )
        piece = _refresh_composable(piece, source_tree)
        instance_records[binding.source_instance] = InstanceRecord(
            name=binding.source_instance, composable=piece
        )
        shell_indexes[binding.source_instance] = ShellIndex.from_tree(source_tree)


def _validate_explicit_identifier_wiring_conflicts(
    assigns: tuple[AssignBinding, ...],
    identifier_bindings: tuple[IdentifierBinding, ...],
) -> None:
    seen: dict[tuple[str, RefPath, str], str] = {}
    for binding in assigns:
        key = (
            binding.source_instance,
            normalize_ref_path(binding.source_ref_path),
            binding.inner_name,
        )
        seen[key] = "builder.assign"
    for binding in identifier_bindings:
        key = (
            binding.source_instance,
            normalize_ref_path(binding.source_ref_path),
            binding.inner_name,
        )
        existing = seen.get(key)
        if existing is None:
            seen[key] = "builder.bind_identifier"
            continue
        raise ValueError(
            format_astichi_error(
                "materialize",
                f"conflicting identifier wiring for "
                f"`{format_instance_leaf(binding.source_instance, key[1], binding.inner_name)}`: "
                f"already wired by {existing}, cannot also use builder.bind_identifier",
                hint="use exactly one explicit identifier wiring surface for each source demand",
            )
        )


def _apply_identifier_bindings(
    bindings: tuple[IdentifierBinding, ...],
    instance_records: dict[str, InstanceRecord],
    trees: dict[str, ast.Module],
    shell_indexes: dict[str, ShellIndex],
) -> None:
    """Apply direct scope-aware identifier bindings to local tree copies."""
    resolved_names = _identifier_binding_direct_names(bindings)
    for binding in bindings:
        source_ref_path = normalize_ref_path(binding.source_ref_path)
        target_ref_path = normalize_ref_path(binding.target_ref_path)
        resolved_outer_name = resolved_names[binding]
        src = instance_records.get(binding.source_instance)
        if src is None:
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    "builder.bind_identifier refers to unknown source instance "
                    f"`{binding.source_instance}`",
                    hint="register the source instance with `builder.add` before `bind_identifier`",
                )
            )
        if not isinstance(src.composable, BasicComposable):
            raise TypeError(
                f"builder.bind_identifier source instance `{binding.source_instance}` "
                f"must be a BasicComposable; got {type(src.composable).__name__}"
            )
        dst = instance_records.get(binding.target_instance)
        if dst is None:
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    "builder.bind_identifier refers to unknown target instance "
                    f"`{binding.target_instance}` "
                    f"(from {binding.source_instance}.{binding.inner_name})",
                    hint="register the target instance with `builder.add` before resolving identifier bindings",
                )
            )
        target_shell = shell_indexes[binding.target_instance].resolve(
            target_ref_path
        ).require(
            instance_name=binding.target_instance,
            role="bind_identifier target path",
        )
        target_body = (
            _effective_root_body(target_shell.body)
            if not target_ref_path
            else target_shell.body
        )
        if binding.outer_name not in collect_identifier_suppliers_in_body(target_body):
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    "no readable supplier named "
                    f"`{binding.outer_name}` at "
                    f"`{format_instance_leaf(binding.target_instance, target_ref_path, binding.outer_name)}`",
                    hint="publish the name with `astichi_export` or an assignable value at that path",
                )
            )
        if resolved_outer_name != binding.outer_name:
            _rewrite_identifiers_in_body(
                target_body,
                {binding.outer_name: resolved_outer_name},
            )
        _ensure_keep_marker(target_body, resolved_outer_name)
        if not isinstance(dst.composable, BasicComposable):
            raise TypeError(
                f"builder.bind_identifier target instance `{binding.target_instance}` "
                f"must be a BasicComposable; got {type(dst.composable).__name__}"
            )
        target_piece = _refresh_composable(
            dst.composable,
            trees[binding.target_instance],
            keep_names=dst.composable.keep_names | frozenset({resolved_outer_name}),
        )
        instance_records[binding.target_instance] = InstanceRecord(
            name=binding.target_instance,
            composable=target_piece,
        )
        source_tree = trees[binding.source_instance]
        source_shell = shell_indexes[binding.source_instance].resolve(
            source_ref_path
        ).require(
            instance_name=binding.source_instance,
            role="bind_identifier source path",
        )
        source_body = (
            _effective_root_body(source_shell.body)
            if not source_ref_path
            else source_shell.body
        )
        local_demands = collect_identifier_demands_in_body(source_body)
        if binding.inner_name not in local_demands:
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    f"no __astichi_arg__ / astichi_import / astichi_pass slot named "
                    f"`{binding.inner_name}` at "
                    f"`{format_instance_leaf(binding.source_instance, source_ref_path, binding.inner_name)}`",
                    hint="declare the slot in the source snippet or fix the path on `bind_identifier`",
                )
            )
        _rewrite_identifier_demands_in_body(
            source_body,
            {binding.inner_name: resolved_outer_name},
            remove_imports=True,
        )
        arg_bindings = dict(src.composable.arg_bindings)
        existing = arg_bindings.get(binding.inner_name)
        if existing is not None and existing != resolved_outer_name:
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    f"cannot re-bind identifier `{binding.inner_name}`: already "
                    f"resolved to `{existing}`",
                    hint="use one identifier binding per source demand",
                )
            )
        arg_bindings[binding.inner_name] = resolved_outer_name
        piece = _refresh_composable(
            src.composable,
            source_tree,
            arg_bindings=tuple(sorted(arg_bindings.items())),
            keep_names=src.composable.keep_names | frozenset({resolved_outer_name}),
        )
        instance_records[binding.source_instance] = InstanceRecord(
            name=binding.source_instance, composable=piece
        )
        shell_indexes[binding.source_instance] = ShellIndex.from_tree(source_tree)


def _identifier_binding_direct_names(
    bindings: tuple[IdentifierBinding, ...],
) -> dict[IdentifierBinding, str]:
    by_name: dict[str, list[IdentifierBinding]] = {}
    for binding in bindings:
        by_name.setdefault(binding.outer_name, []).append(binding)
    resolved: dict[IdentifierBinding, str] = {}
    for outer_name, named_bindings in by_name.items():
        target_keys: set[tuple[str, RefPath, str]] = set()
        for binding in named_bindings:
            key = (
                binding.target_instance,
                normalize_ref_path(binding.target_ref_path),
                binding.outer_name,
            )
            if key in target_keys:
                resolved[binding] = outer_name
                continue
            index = len(target_keys)
            target_keys.add(key)
            resolved[binding] = (
                outer_name
                if index == 0
                else f"{outer_name}__astichi_scoped_{index}"
            )
    return resolved


def _ensure_keep_marker(body: list[ast.stmt], name: str) -> None:
    for stmt in body:
        if not isinstance(stmt, ast.Expr):
            continue
        call = stmt.value
        if (
            is_call_to_marker(call, KEEP)
            and len(call.args) == 1
            and not call.keywords
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == name
        ):
            return
    insert_at = _keep_marker_insert_index(body)
    donor = body[insert_at] if insert_at < len(body) else (body[0] if body else None)
    body.insert(insert_at, _make_keep_statement(name, location_donor=donor))


def _keep_marker_insert_index(body: list[ast.stmt]) -> int:
    index = 0
    while index < len(body) and boundary_import_statement(body[index]) is not None:
        index += 1
    while index < len(body) and _is_keep_statement(body[index]):
        index += 1
    return index


def _is_keep_statement(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and is_call_to_marker(stmt.value, KEEP)
    )


def _rewrite_identifiers_in_body(
    body: list[ast.stmt],
    bindings: dict[str, str],
) -> None:
    renamer = _BoundaryImportRenamer(bindings)
    for index, statement in enumerate(body):
        rewritten = renamer.visit(statement)
        if rewritten is None:
            continue
        assert isinstance(rewritten, ast.stmt)
        body[index] = rewritten


def _rewrite_identifier_demands_in_body(
    body: list[ast.stmt],
    bindings: dict[str, str],
    *,
    remove_imports: bool = False,
) -> None:
    import_bindings = {
        name: bindings[name]
        for name in _declared_import_like_names_in_body(body)
        if name in bindings
    }
    arg_resolver = _ShellArgIdentifierResolver(bindings)
    import_resolver = _BoundaryImportRenamer(import_bindings)
    pass_resolver = _BoundaryPassRenamer(bindings)
    rewritten_body: list[ast.stmt] = []
    for statement in body:
        info = boundary_import_statement(statement)
        if info is not None and info[0] in import_bindings:
            if remove_imports:
                continue
            _rewrite_boundary_import_name(statement, import_bindings[info[0]])
        rewritten = arg_resolver.visit(statement)
        if rewritten is None:
            continue
        assert isinstance(rewritten, ast.stmt)
        rewritten_body.append(pass_resolver.visit(import_resolver.visit(rewritten)))
    body[:] = rewritten_body


def _declared_import_like_names_in_body(body: list[ast.stmt]) -> frozenset[str]:
    names: set[str] = set()
    for statement in body:
        info = boundary_import_statement(statement)
        if info is not None:
            names.add(info[0])
    for statement in body:
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call) or not is_astichi_funcargs_call(node):
                continue
            for directive in direct_funcargs_directive_calls(node):
                if (
                    call_name(directive) == IMPORT.source_name
                    and directive.args
                    and isinstance(directive.args[0], ast.Name)
                ):
                    names.add(directive.args[0].id)
    return frozenset(names)


def _assign_target_alias_name(binding: AssignBinding) -> str:
    target_ref_path = normalize_ref_path(binding.target_ref_path)
    parts = [
        "__astichi_assign",
        "inst",
        _sanitize_for_identifier(binding.target_instance),
    ]
    for segment in target_ref_path:
        if isinstance(segment, int):
            parts.extend(("idx", str(segment)))
        else:
            parts.extend(("ref", _sanitize_for_identifier(segment)))
    parts.extend(("name", _sanitize_for_identifier(binding.outer_name)))
    return "__".join(parts)


def _publish_assign_target_alias(
    body: list[ast.stmt],
    *,
    source_name: str,
    alias_name: str,
    location_donor: ast.AST | None = None,
) -> None:
    donor = location_donor or (body[0] if body else None)
    keep_stmt = _make_keep_statement(alias_name, location_donor=donor)
    export_stmt = ast.Expr(
        value=ast.Call(
            func=ast.Name(id="astichi_export", ctx=ast.Load()),
            args=[ast.Name(id=alias_name, ctx=ast.Load())],
            keywords=[],
        )
    )
    assign_stmt = ast.Assign(
        targets=[ast.Name(id=alias_name, ctx=ast.Store())],
        value=ast.Name(id=source_name, ctx=ast.Load()),
    )
    propagate_ast_source_locations(export_stmt, donor)
    propagate_ast_source_locations(assign_stmt, donor)

    implicit_expr = _implicit_expression_supply_after_boundary_prefix(body)
    if implicit_expr is not None:
        expr, stmt_index = implicit_expr
        final_stmt = body[stmt_index]
        assert isinstance(final_stmt, ast.Expr)
        rewritten_expr, captured_inline = _inline_expression_alias_capture(
            expr,
            source_name=source_name,
            alias_name=alias_name,
        )
        if not captured_inline:
            rewritten_expr = _wrap_expression_with_alias_capture(
                expr,
                source_name=source_name,
                alias_name=alias_name,
                location_donor=expr,
            )
        final_stmt.value = rewritten_expr
        body[stmt_index:stmt_index] = (keep_stmt, export_stmt)
        return

    body.extend((keep_stmt, export_stmt, assign_stmt))


def _wrap_expression_with_alias_capture(
    expr: ast.expr,
    *,
    source_name: str,
    alias_name: str,
    location_donor: ast.AST | None = None,
) -> ast.expr:
    wrapped = ast.Subscript(
        value=ast.Tuple(
            elts=[
                expr,
                ast.NamedExpr(
                    target=ast.Name(id=alias_name, ctx=ast.Store()),
                    value=ast.Name(id=source_name, ctx=ast.Load()),
                ),
            ],
            ctx=ast.Load(),
        ),
        slice=ast.Constant(value=0),
        ctx=ast.Load(),
    )
    propagate_ast_source_locations(wrapped, location_donor)
    return wrapped


def _inline_expression_alias_capture(
    expr: ast.expr,
    *,
    source_name: str,
    alias_name: str,
) -> tuple[ast.expr, bool]:
    class _Transformer(ast.NodeTransformer):
        def __init__(self) -> None:
            self.captured = False

        def visit_NamedExpr(self, node: ast.NamedExpr) -> ast.AST:
            node = self.generic_visit(node)
            assert isinstance(node, ast.NamedExpr)
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == source_name
            ):
                self.captured = True
                return _wrap_expression_with_alias_capture(
                    node,
                    source_name=source_name,
                    alias_name=alias_name,
                    location_donor=node,
                )
            return node

    transformer = _Transformer()
    rewritten = transformer.visit(expr)
    assert isinstance(rewritten, ast.expr)
    return rewritten, transformer.captured


class _ShellArgIdentifierResolver(ast.NodeTransformer):
    def __init__(self, bindings: dict[str, str]) -> None:
        self._bindings = bindings

    def _resolve(self, raw_name: str) -> str:
        base, marker = strip_identifier_suffix(raw_name)
        if marker is not ARG_IDENTIFIER:
            return raw_name
        return self._bindings.get(base, raw_name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if is_astichi_insert_shell(node):
            return node
        node.name = self._resolve(node.name)
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        if is_astichi_insert_shell(node):
            return node
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


def build_merge(
    graph: BuilderGraph, *, unroll: bool | str = "auto"
) -> BasicComposable:
    """Merge a builder graph into a single composable.

    `unroll` controls `astichi_for` expansion before edge resolution
    (UnrollRevision §3):

    - ``"auto"`` (default): unroll iff any edge targets an indexed path.
    - ``True``: unroll every instance regardless of edges.
    - ``False``: do not unroll; reject if any edge has a non-empty path.
    """
    if not graph.instances:
        raise ValueError(
            format_astichi_error(
                "build",
                "cannot build from empty graph",
                hint="register at least one instance with `builder.add.<Name>(...)`",
            )
        )
    if unroll not in (True, False, "auto"):
        raise ValueError(
            format_astichi_error(
                "build",
                f"unroll must be True, False, or 'auto'; got {unroll!r}",
                hint="pass `unroll=True`, `unroll=False`, or use the default `unroll='auto'`",
            )
        )

    has_indexed_edges = any(e.target.path for e in graph.edges)
    if unroll is False and has_indexed_edges:
        offenders = sorted(
            {
                _format_target_address(e)
                for e in graph.edges
                if e.target.path
            }
        )
        raise ValueError(
            format_astichi_error(
                "build",
                "unroll=False conflicts with indexed target edges: "
                + ", ".join(offenders),
                hint="use `unroll=True` or `'auto'` when wiring indexed `slot[i]` targets",
            )
        )
    do_unroll = (unroll is True) or (unroll == "auto" and has_indexed_edges)

    trees: dict[str, ast.Module] = {}
    instance_records: dict[str, InstanceRecord] = {}
    shell_indexes: dict[str, ShellIndex] = {}
    for record in graph.instances:
        if not isinstance(record.composable, BasicComposable):
            raise TypeError(
                f"instance {record.name} must be a BasicComposable"
            )
        tree = copy.deepcopy(record.composable.tree)
        if do_unroll:
            tree = unroll_tree(tree)
        # Re-derive ports from the current tree so anchor-preserved
        # holes a prior build() marked satisfied remain addressable.
        composable = _refresh_composable(record.composable, tree)
        trees[record.name] = tree
        instance_records[record.name] = InstanceRecord(
                name=record.name, composable=composable
        )
        shell_indexes[record.name] = ShellIndex.from_tree(tree)

    # Issue 006 6c (assign surface):
    # ``builder.assign.<Src>.<inner>.to().<Dst>.<outer>`` declarations
    # are resolved against the local instance-record copies so each
    # ``build()`` invocation is idempotent. Unlike the in-graph
    # ``target.add.<Src>(arg_names=...)`` surface, the assign surface
    # never mutates the graph's instance records; the wiring is held as
    # ``AssignBinding`` records on the graph and applied fresh here.
    _validate_explicit_identifier_wiring_conflicts(
        graph.assigns,
        graph.identifier_bindings,
    )
    _apply_assign_bindings(graph.assigns, instance_records, trees, shell_indexes)
    _apply_identifier_bindings(
        graph.identifier_bindings,
        instance_records,
        trees,
        shell_indexes,
    )

    edges_by_target: dict[tuple[str, RefPath, str], list[tuple[int, AdditiveEdge]]] = {}
    for idx, edge in enumerate(graph.edges):
        effective_name = iter_target_name(
            edge.target.target_name, edge.target.path
        )
        ref_path = promote_wrapped_root_ref_path(
            trees[edge.target.root_instance],
            normalize_ref_path(edge.target.ref_path),
        )
        key = (
            edge.target.root_instance,
            ref_path,
            effective_name,
        )
        edges_by_target.setdefault(key, []).append((idx, edge))
    for key in edges_by_target:
        edges_by_target[key].sort(key=lambda item: (item[1].order, item[0]))

    _validate_indexed_targets(edges_by_target, instance_records)

    resolution_order = _topo_sort_targets(graph)
    merged_arg_binding_pairs: set[tuple[str, str]] = set()
    merged_keep_names: set[str] = set()

    for inst_name in resolution_order:
        scoped_block_replacements: dict[tuple[RefPath, str], list[_BlockContribution]] = {}
        scoped_expr_replacements: dict[tuple[RefPath, str], list[_ExpressionInsert]] = {}
        scoped_param_replacements: dict[tuple[RefPath, str], list[_ParamContribution]] = {}
        for (
            root,
            target_ref_path,
            effective_target_name,
        ), indexed_edges in edges_by_target.items():
            if root != inst_name:
                continue
            target_shell = shell_indexes[inst_name].resolve(target_ref_path).require(
                instance_name=inst_name,
                role="target path",
            )
            target_body = (
                _effective_root_body(target_shell.body)
                if not target_ref_path
                else target_shell.body
            )
            if (
                target_ref_path
                and effective_target_name
                not in (
                    collect_hole_names_in_body(target_shell.body)
                    | collect_param_hole_names_in_body(target_shell.body)
                )
            ):
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        f"unknown target site "
                        f"`{format_instance_leaf(inst_name, target_ref_path, effective_target_name)}`",
                        context=f"instance {inst_name!r}",
                        hint=default_build_path_hint(),
                    )
                )
            target_record = instance_records[inst_name]
            target_port = _lookup_demand_port(
                target_record.composable, effective_target_name
            )
            contributions: list[_BlockContribution] = []
            inserts: list[_ExpressionInsert] = []
            param_contributions: list[_ParamContribution] = []
            for counter, (_idx, edge) in enumerate(indexed_edges):
                source_record = instance_records[edge.source_instance]
                source_piece = _edge_scoped_composable(source_record, edge)
                merged_arg_binding_pairs.update(source_piece.arg_bindings)
                merged_keep_names.update(source_piece.keep_names)
                # Source-side ports and generated insert wrappers use the raw
                # (pre-unroll) name; the suffixing happens on the target side.
                raw_target_name = edge.target.target_name
                source_port = _lookup_supply_port(source_piece, raw_target_name)
                source_tree = source_piece.tree
                source_effective_body = _effective_root_body(source_tree.body)
                source_is_param_payload = has_params_payload(source_effective_body)
                implicit_expr_supply = (
                    _implicit_expression_supply_after_boundary_prefix(
                        source_effective_body
                    )
                    is not None
                )
                if target_port is not None and source_port is not None:
                    validate_port_pair(target_port, source_port)
                if (
                    source_is_param_payload
                    and (
                        target_port is None
                        or not target_port.is_signature_parameter_demand()
                    )
                ):
                    raise ValueError(
                        format_astichi_error(
                            "materialize",
                            f"parameter payload source {edge.source_instance} cannot be wired "
                            f"into non-parameter target {inst_name}.{effective_target_name}",
                            hint="wire `def astichi_params(...): pass` only into `__astichi_param_hole__` targets",
                        )
                    )
                if (
                    target_port is not None
                    and target_port.is_signature_parameter_demand()
                ):
                    param_supply = _lookup_parameter_supply_port(source_piece)
                    if param_supply is None:
                        raise ValueError(
                            format_astichi_error(
                                "materialize",
                                f"source instance {edge.source_instance} cannot satisfy "
                                f"parameter target {inst_name}.{effective_target_name}",
                                hint="supply a `def astichi_params(...): pass` parameter payload",
                            )
                        )
                    validate_port_pair(target_port, param_supply)
                    payload_args = extract_params_payload_from_body(
                        source_effective_body
                    )
                    if payload_args is None:
                        raise ValueError(
                            format_astichi_error(
                                "materialize",
                                f"source instance {edge.source_instance} has no parameter payload",
                                hint="parameter sources must contain only `def astichi_params(...): pass`",
                            )
                        )
                    shell_name = (
                        f"__astichi_param_contrib__"
                        f"{_sanitize_for_identifier(inst_name)}"
                        f"__{_sanitize_for_identifier(effective_target_name)}"
                        f"__{counter}"
                        f"__{_sanitize_for_identifier(edge.source_instance)}"
                    )
                    inserted_ref_path = normalize_ref_path(
                        edge.target.ref_path
                        + (edge.source_instance,)
                        + edge.target.path
                    )
                    param_contributions.append(
                        _ParamContribution(
                            source_instance=edge.source_instance,
                            order=edge.order,
                            edge_index=_idx,
                            args=payload_args,
                            shell_name=shell_name,
                            ref_path=inserted_ref_path,
                        )
                    )
                    continue
                if (
                    target_port is not None
                    and target_port.is_expression_family_demand()
                ):
                    if (
                        _is_call_argument_target_body(target_body, effective_target_name)
                        and _has_authored_expression_insert_source(source_tree, raw_target_name)
                    ):
                        raise ValueError(
                            format_astichi_error(
                                "materialize",
                                "legacy user-authored astichi_insert(target, expr) "
                                "is not supported for call-argument targets; use "
                                "astichi_funcargs(...)",
                                hint="wrap payload items with `astichi_funcargs(...)` for call-argument holes",
                            )
                        )
                    expr_source_ok = (
                        source_port is not None
                        and source_port.is_expression_family_supply()
                    ) or (source_port is None and implicit_expr_supply)
                    if not expr_source_ok:
                        raise ValueError(
                            format_astichi_error(
                                "materialize",
                                f"source instance {edge.source_instance} cannot satisfy "
                                f"expression target {inst_name}.{effective_target_name}",
                                hint="supply an expression-shaped source or an implicit expression after boundary markers",
                            )
                        )
                    inserts.extend(
                        _extract_expression_inserts(
                            source_tree,
                            raw_target_name,
                            edge_order=edge.order,
                            edge_index=_idx,
                            source_instance=edge.source_instance,
                        )
                    )
                    continue
                shell_name = (
                    f"__astichi_contrib__"
                    f"{_sanitize_for_identifier(inst_name)}"
                    f"__{_sanitize_for_identifier(effective_target_name)}"
                    f"__{counter}"
                    f"__{_sanitize_for_identifier(edge.source_instance)}"
                )
                inserted_ref_path = normalize_ref_path(
                    edge.target.ref_path
                    + (edge.source_instance,)
                    + edge.target.path
                )
                contrib_body = copy.deepcopy(source_tree.body)
                _inject_scoped_keep_markers(
                    contrib_body, source_piece.keep_names
                )
                _prefix_shell_refs_in_body(contrib_body, inserted_ref_path)
                contributions.append(
                    _BlockContribution(
                        source_instance=edge.source_instance,
                        order=edge.order,
                        edge_index=_idx,
                        body=contrib_body,
                        shell_name=shell_name,
                        ref_path=inserted_ref_path,
                    )
                )
            if inserts:
                scoped_expr_replacements[(target_ref_path, effective_target_name)] = sorted(
                    inserts,
                    key=lambda item: (
                        item.edge_order,
                        item.inline_order,
                        item.edge_index,
                        item.statement_index,
                    ),
                )
            if contributions:
                scoped_block_replacements[(target_ref_path, effective_target_name)] = sorted(
                    contributions,
                    key=lambda item: (item.order, item.edge_index),
                )
            if param_contributions:
                scoped_param_replacements[(target_ref_path, effective_target_name)] = sorted(
                    param_contributions,
                    key=lambda item: (item.order, item.edge_index),
                )
        if scoped_block_replacements or scoped_expr_replacements or scoped_param_replacements:
            _replace_targets_in_tree(
                trees[inst_name],
                block_replacements=scoped_block_replacements,
                expr_replacements=scoped_expr_replacements,
                param_replacements=scoped_param_replacements,
            )

    consumed = {edge.source_instance for edge in graph.edges}
    root_names = [r.name for r in graph.instances if r.name not in consumed]
    if not root_names:
        target_set = {edge.target.root_instance for edge in graph.edges}
        root_names = sorted(target_set) if target_set else sorted(trees)

    # Issue 006 6c (root-scope wrap): give every root instance its
    # own `astichi_hole(__astichi_root__X__)` + `@astichi_insert(...)`
    # pair before concatenation. The pair is a fresh Astichi scope
    # that hygiene renames against sibling roots, so two Roots that
    # both bind `total` at module level emit as distinct variables
    # instead of clobbering each other. `_flatten_block_inserts`
    # consumes the pair back into flat module body after hygiene.
    merged_body: list[ast.stmt] = []
    for name in root_names:
        merged_arg_binding_pairs.update(instance_records[name].composable.arg_bindings)
        merged_keep_names.update(instance_records[name].composable.keep_names)
        _inject_scoped_keep_markers(
            trees[name].body, instance_records[name].composable.keep_names
        )
        merged_body.extend(_wrap_in_root_scope(trees[name].body, name))

    merged_tree = ast.Module(body=merged_body, type_ignores=[])
    ast.fix_missing_locations(merged_tree)

    markers = recognize_markers(merged_tree)
    origin = CompileOrigin(
        file_name="<astichi-build>", line_number=1, offset=0
    )
    provisional = BasicComposable(
        tree=merged_tree, origin=origin, markers=markers
    )
    classification = analyze_names(
        provisional, mode="permissive", preserved_names=frozenset(merged_keep_names)
    )
    raw_demands = extract_demand_ports(markers, classification)
    satisfied = _locally_satisfied_hole_names(merged_tree)
    satisfied_params = _locally_satisfied_param_hole_names(merged_tree)
    demand_ports = tuple(
        port
        for port in raw_demands
        if not (
            (port.is_additive_hole_demand() and port.name in satisfied)
            or (
                port.is_parameter_hole_demand()
                and port.name in satisfied_params
            )
        )
    )

    return BasicComposable(
        tree=merged_tree,
        origin=origin,
        markers=markers,
        classification=classification,
        demand_ports=demand_ports,
        supply_ports=extract_supply_ports(markers),
        arg_bindings=tuple(sorted(merged_arg_binding_pairs)),
        keep_names=frozenset(merged_keep_names),
    )


def _topo_sort_targets(graph: BuilderGraph) -> list[str]:
    """Topological sort of target instances for resolution order."""
    target_set = {edge.target.root_instance for edge in graph.edges}
    if not target_set:
        return []

    deps: dict[str, set[str]] = {}
    for inst in target_set:
        sources = {
            e.source_instance
            for e in graph.edges
            if e.target.root_instance == inst
        }
        deps[inst] = sources & target_set

    resolved: set[str] = set()
    order: list[str] = []
    while len(resolved) < len(target_set):
        ready = [
            inst
            for inst in sorted(target_set - resolved)
            if deps.get(inst, set()).issubset(resolved)
        ]
        if not ready:
            order.extend(sorted(target_set - resolved))
            break
        order.extend(ready)
        resolved.update(ready)
    return order


def _replace_targets_in_body(
    body: list[ast.stmt],
    *,
    block_replacements: dict[str, list[_BlockContribution]],
    expr_replacements: dict[str, list[_ExpressionInsert]],
    param_replacements: dict[str, list[_ParamContribution]],
) -> list[ast.stmt]:
    """Replace block and expression targets in a statement list.

    Block-target holes are preserved (anchor) and each `.add()`
    contribution is appended as an `astichi_insert`-decorated shell
    (see `AstichiApiDesignV1-CompositionUnification.md §3`). The
    actual splice happens later during `materialize()`.
    """
    transformer = _HoleReplacementTransformer(
        block_replacements=block_replacements,
        expr_replacements=expr_replacements,
        param_replacements=param_replacements,
    )
    result: list[ast.stmt] = []
    for stmt in body:
        transformed = transformer.visit(stmt)
        if transformed is None:
            continue
        if isinstance(transformed, list):
            result.extend(transformed)
            continue
        assert isinstance(transformed, ast.stmt)
        result.append(transformed)
    return result


def _make_block_insert_shell(
    *,
    target_name: str,
    order: int,
    shell_name: str,
    body: list[ast.stmt],
    ref_path: RefPath | None = None,
    location_donor: ast.AST | None = None,
) -> ast.FunctionDef:
    """Build an `astichi_insert`-decorated shell for a block contribution.

    Per `AstichiApiDesignV1-CompositionUnification.md §3`, each `.add()`
    wiring of a block target produces one such shell.
    """
    shell_body: list[ast.stmt] = (
        [copy.deepcopy(stmt) for stmt in body] if body else [ast.Pass()]
    )
    keywords: list[ast.keyword] = []
    if order != 0:
        keywords.append(
            ast.keyword(arg="order", value=ast.Constant(value=order))
        )
    decorator = ast.Call(
        func=ast.Name(id="astichi_insert", ctx=ast.Load()),
        args=[ast.Name(id=target_name, ctx=ast.Load())],
        keywords=keywords,
    )
    if ref_path is not None:
        set_insert_ref(decorator, ref_path, phase="materialize")
    shell = ast.FunctionDef(
        name=shell_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=shell_body,
        decorator_list=[decorator],
        returns=None,
        type_comment=None,
        type_params=[],
    )
    donor = location_donor or (shell_body[0] if shell_body else None)
    propagate_ast_source_locations(shell, donor)
    return shell


def _make_param_insert_shell(
    *,
    target_name: str,
    order: int,
    shell_name: str,
    args: ast.arguments,
    ref_path: RefPath | None = None,
    location_donor: ast.AST | None = None,
) -> ast.FunctionDef:
    keywords: list[ast.keyword] = [
        ast.keyword(arg="kind", value=ast.Constant(value="params"))
    ]
    if order != 0:
        keywords.append(
            ast.keyword(arg="order", value=ast.Constant(value=order))
        )
    decorator = ast.Call(
        func=ast.Name(id="astichi_insert", ctx=ast.Load()),
        args=[ast.Name(id=target_name, ctx=ast.Load())],
        keywords=keywords,
    )
    if ref_path is not None:
        set_insert_ref(decorator, ref_path, phase="materialize")
    shell = ast.FunctionDef(
        name=shell_name,
        args=copy.deepcopy(args),
        body=[ast.Pass()],
        decorator_list=[decorator],
        returns=None,
        type_comment=None,
        type_params=[],
    )
    propagate_ast_source_locations(shell, location_donor)
    return shell


def _root_scope_anchor(instance_name: str) -> str:
    """Anchor name for the per-root-instance scope-isolation shell.

    Issue 006 6c (root-scope wrap): every top-level root instance in
    a build is given a distinct `astichi_hole(anchor)` +
    `@astichi_insert(anchor) def anchor(): ...` pair at module scope
    so hygiene sees each root's bindings as a separate Astichi scope.
    Using `_sanitize_for_identifier` on the instance name keeps the
    anchor both unique across sibling roots and persistable through
    an `emit()` + re-compile round trip.
    """
    return f"{_ROOT_SCOPE_HOLE_PREFIX}{_sanitize_for_identifier(instance_name)}__"


def _wrap_in_root_scope(
    body: list[ast.stmt], instance_name: str
) -> list[ast.stmt]:
    """Wrap a root instance's body in a hole+shell pair (issue 006 6c).

    The wrapped body becomes a fresh Astichi scope for hygiene
    purposes. `_flatten_block_inserts` later consumes the hole and
    the shell (after rename-collisions has run), inlining the body
    back at module level — the wrapper exists purely to carry scope
    identity through the hygiene pass. If ``body`` already carries a
    synthetic root wrapper (previously-built composable), it is
    stripped first to avoid double-nesting.
    """
    outer_shell = _synthetic_root_scope_shell(body)
    if outer_shell is not None:
        body = list(outer_shell.body)
    anchor = _root_scope_anchor(instance_name)
    root_ref = normalize_ref_path((instance_name,))
    _prefix_shell_refs_in_body(body, root_ref)
    hole = ast.Expr(
        value=ast.Call(
            func=ast.Name(id="astichi_hole", ctx=ast.Load()),
            args=[ast.Name(id=anchor, ctx=ast.Load())],
            keywords=[],
        )
    )
    donor = body[0] if body else None
    propagate_ast_source_locations(hole, donor)
    shell = _make_block_insert_shell(
        target_name=anchor,
        order=0,
        shell_name=anchor,
        body=body,
        ref_path=root_ref,
        location_donor=donor,
    )
    return [hole, shell]


def _lookup_demand_port(
    composable: BasicComposable,
    name: str,
) -> DemandPort | None:
    for port in composable.demand_ports:
        if port.name == name:
            return port
    return None


def _lookup_supply_port(
    composable: BasicComposable,
    name: str,
) -> SupplyPort | None:
    for port in composable.supply_ports:
        if port.name == name:
            return port
    return None


def _lookup_parameter_supply_port(
    composable: BasicComposable,
) -> SupplyPort | None:
    matches = [
        port for port in composable.supply_ports
        if port.is_signature_parameter_supply()
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(
            format_astichi_error(
                "materialize",
                "parameter payload source exposes multiple parameter supplies",
                hint="use one `def astichi_params(...): pass` payload per source snippet",
            )
        )
    return matches[0]


_BOUNDARY_EXPR_PREFIX_SPECS = tuple(
    marker
    for marker in ALL_MARKERS
    if marker.is_expression_prefix_directive()
)


def _implicit_expression_supply_after_boundary_prefix(
    body: list[ast.stmt],
) -> tuple[ast.expr, int] | None:
    """If ``body`` is ``<boundary Expr(Call) prefix>* <one Expr (non-insert)``,
    return the trailing expression and its statement index.

    This lets contributors write plain user expressions (e.g. ``(x := y)``)
    for expression targets without spelling ``astichi_insert(...)`` in source;
    merge synthesizes the insert wrapper from the edge target name.
    """
    prefix = scan_statement_prefix(
        body,
        allowed_specs=_BOUNDARY_EXPR_PREFIX_SPECS,
    )
    index = prefix.first_non_prefix_index
    rest = body[index:]
    if len(rest) != 1:
        return None
    final = rest[0]
    if not isinstance(final, ast.Expr):
        return None
    if isinstance(final.value, ast.Call) and _is_expression_insert_call(
        final.value
    ):
        return None
    return final.value, index


def _pyimport_prefix_calls(
    body: list[ast.stmt], *, before_index: int
) -> tuple[ast.Call, ...]:
    calls: list[ast.Call] = []
    for statement in body[:before_index]:
        if not isinstance(statement, ast.Expr):
            continue
        call = statement.value
        if isinstance(call, ast.Call) and is_call_to_marker(call, PYIMPORT):
            calls.append(copy.deepcopy(call))
    return tuple(calls)


def _make_keep_statement(
    name: str, *, location_donor: ast.AST | None = None
) -> ast.Expr:
    expr = ast.Expr(
        value=ast.Call(
            func=ast.Name(id=KEEP.source_name, ctx=ast.Load()),
            args=[ast.Name(id=name, ctx=ast.Load())],
            keywords=[],
        )
    )
    propagate_ast_source_locations(expr, location_donor)
    return expr


def _inject_scoped_keep_markers(
    body: list[ast.stmt],
    keep_names: frozenset[str],
) -> None:
    if not keep_names:
        return
    target_body = _effective_root_body(body)
    existing: set[str] = set()
    for stmt in target_body:
        if not isinstance(stmt, ast.Expr):
            continue
        call = stmt.value
        if is_call_to_marker(call, KEEP) and len(call.args) == 1 and not call.keywords and isinstance(call.args[0], ast.Name):
            existing.add(call.args[0].id)
    insert_at = _keep_marker_insert_index(target_body)
    donor = (
        target_body[insert_at]
        if insert_at < len(target_body)
        else (target_body[0] if target_body else None)
    )
    additions = [
        _make_keep_statement(name, location_donor=donor)
        for name in sorted(keep_names)
        if name not in existing
    ]
    if additions:
        target_body[insert_at:insert_at] = additions


def _extract_expression_inserts(
    tree: ast.Module,
    target_name: str,
    *,
    edge_order: int,
    edge_index: int,
    source_instance: str,
) -> list[_ExpressionInsert]:
    effective_body = _effective_root_body(tree.body)
    implicit = _implicit_expression_supply_after_boundary_prefix(effective_body)
    if implicit is not None:
        expr, stmt_index = implicit
        pyimports = _pyimport_prefix_calls(effective_body, before_index=stmt_index)
        if isinstance(expr, ast.Call) and is_astichi_funcargs_call(expr):
            return [
                _ExpressionInsert(
                    expr=copy.deepcopy(expr),
                    payload=extract_funcargs_payload(expr),
                    pyimports=pyimports,
                    edge_order=edge_order,
                    inline_order=0,
                    edge_index=edge_index,
                    statement_index=stmt_index,
                )
            ]
    if (
        len(effective_body) == 1
        and isinstance(effective_body[0], ast.Expr)
        and isinstance(effective_body[0].value, ast.Call)
        and is_astichi_funcargs_call(effective_body[0].value)
    ):
        call = effective_body[0].value
        return [
            _ExpressionInsert(
                expr=copy.deepcopy(call),
                payload=extract_funcargs_payload(call),
                pyimports=(),
                edge_order=edge_order,
                inline_order=0,
                edge_index=edge_index,
                statement_index=0,
            )
        ]
    inserts: list[_ExpressionInsert] = []
    for stmt_index, stmt in enumerate(effective_body):
        if not isinstance(stmt, ast.Expr):
            if _contains_top_level_expression_insert(stmt):
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        f"source instance {source_instance} has non-expression-statement "
                        "insert wrappers at top level",
                        hint="use only expression-level `astichi_insert` for expression targets",
                    )
                )
            continue
        if not isinstance(stmt.value, ast.Call):
            continue
        if not _is_expression_insert_call(stmt.value):
            continue
        insert_name = _insert_target_name(stmt.value)
        if insert_name != target_name:
            continue
        inserts.append(
            _ExpressionInsert(
                expr=copy.deepcopy(stmt.value.args[1]),
                payload=None,
                pyimports=(),
                edge_order=edge_order,
                inline_order=_extract_insert_order(stmt.value),
                edge_index=edge_index,
                statement_index=stmt_index,
            )
        )
    if inserts:
        return inserts
    if implicit is not None:
        expr, stmt_index = implicit
        return [
            _ExpressionInsert(
                expr=copy.deepcopy(expr),
                payload=None,
                pyimports=_pyimport_prefix_calls(
                    effective_body, before_index=stmt_index
                ),
                edge_order=edge_order,
                inline_order=0,
                edge_index=edge_index,
                statement_index=stmt_index,
            )
        ]

    raise ValueError(
        format_astichi_error(
            "materialize",
            f"source instance {source_instance} cannot satisfy expression target "
            f"{target_name}: no matching astichi_insert(...) wrappers found",
            hint="add `astichi_insert({target_name}, expr)` (or implicit expression) in the source body",
        )
    )


def _has_authored_expression_insert_source(
    tree: ast.Module, target_name: str
) -> bool:
    for stmt in _effective_root_body(tree.body):
        if not isinstance(stmt, ast.Expr):
            continue
        if not isinstance(stmt.value, ast.Call):
            continue
        if not _is_expression_insert_call(stmt.value):
            continue
        if _insert_target_name(stmt.value) == target_name:
            return True
    return False


def _is_call_argument_target_body(body: list[ast.stmt], hole_name: str) -> bool:
    class _Visitor(_SkipInsertShellVisitorWithClassMixin, ast.NodeVisitor):
        def __init__(self) -> None:
            self.found = False

        def visit_Call(self, node: ast.Call) -> None:
            for arg in node.args:
                target = arg.value if isinstance(arg, ast.Starred) else arg
                if _extract_expr_hole_name(target) == hole_name:
                    self.found = True
                    return
            for keyword in node.keywords:
                if keyword.arg is None and _extract_expr_hole_name(keyword.value) == hole_name:
                    self.found = True
                    return
            self.generic_visit(node)

    visitor = _Visitor()
    for statement in body:
        visitor.visit(statement)
        if visitor.found:
            return True
    return False


def _contains_top_level_expression_insert(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Expr):
        return False
    if not isinstance(stmt.value, ast.Call):
        return False
    return _is_expression_insert_call(stmt.value)


def _insert_target_name(node: ast.Call) -> str | None:
    first_arg = node.args[0]
    if isinstance(first_arg, ast.Name):
        return first_arg.id
    return None


def _extract_insert_order(node: ast.Call) -> int:
    for keyword in node.keywords:
        if keyword.arg != "order":
            continue
        if not isinstance(keyword.value, ast.Constant) or not isinstance(
            keyword.value.value, int
        ):
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    "astichi_insert order must be an integer constant",
                    hint="use `order=0` with a literal int",
                )
            )
        return keyword.value.value
    return 0


def _extract_expr_hole_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Name):
        return None
    if node.func.id != "astichi_hole":
        return None
    if not node.args:
        return None
    first_arg = node.args[0]
    if isinstance(first_arg, ast.Name):
        return first_arg.id
    return None


def _required_hole_names(tree: ast.AST) -> frozenset[str]:
    optional_annotation_hole_ids = _direct_annotation_hole_ids(tree)
    names: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in optional_annotation_hole_ids:
            continue
        name = _extract_expr_hole_name(node)
        if name is not None:
            names.add(name)
    return frozenset(names)


def _direct_annotation_hole_ids(tree: ast.AST) -> frozenset[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.arg) or node.annotation is None:
            continue
        if _extract_expr_hole_name(node.annotation) is not None:
            ids.add(id(node.annotation))
    return frozenset(ids)


def _remove_optional_annotation_holes(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.arg) or node.annotation is None:
            continue
        if _extract_expr_hole_name(node.annotation) is not None:
            node.annotation = None


def _make_expression_insert_call(
    target_name: str,
    expr: ast.expr,
    *,
    pyimports: tuple[ast.Call, ...] = (),
    location_donor: ast.AST | None = None,
) -> ast.Call:
    donor = location_donor if location_donor is not None else expr
    keywords: list[ast.keyword] = []
    if pyimports:
        keywords.append(
            ast.keyword(
                arg="pyimport",
                value=ast.Tuple(
                    elts=[copy.deepcopy(call) for call in pyimports],
                    ctx=ast.Load(),
                ),
            )
        )
    call = ast.Call(
        func=ast.Name(id="astichi_insert", ctx=ast.Load()),
        args=[
            ast.Name(id=target_name, ctx=ast.Load()),
            copy.deepcopy(expr),
        ],
        keywords=keywords,
    )
    propagate_ast_source_locations(call, donor)
    return call


def _validate_star_region_inserts(
    hole_name: str, inserts: list[_ExpressionInsert]
) -> None:
    for insert in inserts:
        if insert.payload is None:
            continue
        validate_payload_for_region(
            insert.payload,
            region=STARRED_FUNC_ARG_REGION,
            hole_name=hole_name,
        )


def _validate_dstar_region_inserts(
    hole_name: str,
    inserts: list[_ExpressionInsert],
    *,
    seen_explicit_keywords: set[str],
) -> None:
    for insert in inserts:
        if insert.payload is None:
            if not isinstance(insert.expr, ast.Dict):
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        f"named variadic target {hole_name} requires dict-display expression inserts",
                        hint="use `astichi_insert(hole, {{...}})` with a dict literal payload",
                    )
                )
            continue
        validate_payload_for_region(
            insert.payload,
            region=DOUBLE_STAR_FUNC_ARG_REGION,
            hole_name=hole_name,
            seen_explicit_keywords=seen_explicit_keywords,
        )


def _validate_plain_call_region_inserts(
    inserts: list[_ExpressionInsert],
    *,
    seen_explicit_keywords: set[str],
) -> None:
    for insert in inserts:
        if insert.payload is None:
            continue
        validate_payload_for_region(
            insert.payload,
            region=PLAIN_FUNC_ARG_REGION,
            hole_name="call-argument hole",
            seen_explicit_keywords=seen_explicit_keywords,
        )


def _realize_param_insert_wrappers(tree: ast.Module) -> None:
    realizer = _ParamInsertRealizer()
    realizer.visit(tree)


class _ParamInsertRealizer(ast.NodeTransformer):
    def generic_visit(self, node: ast.AST) -> ast.AST:
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                if all(isinstance(item, ast.stmt) for item in value):
                    value[:] = self._realize_body([item for item in value if isinstance(item, ast.stmt)])
                    continue
                new_items: list[object] = []
                for item in value:
                    if isinstance(item, ast.AST):
                        new_items.append(self.visit(item))
                    else:
                        new_items.append(item)
                value[:] = new_items
                continue
            if isinstance(value, ast.AST):
                setattr(node, field, self.visit(value))
        return node

    def _realize_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
        visited_body: list[ast.stmt] = []
        for stmt in body:
            if extract_param_insert_shell(stmt, phase="materialize") is not None:
                visited_body.append(stmt)
                continue
            visited = self.visit(stmt)
            assert isinstance(visited, ast.stmt)
            visited_body.append(visited)

        wrappers_by_target: dict[str, list[tuple[int, int, ast.FunctionDef]]] = {}
        for index, stmt in enumerate(visited_body):
            info = extract_param_insert_shell(stmt, phase="materialize")
            if info is None:
                continue
            assert isinstance(stmt, ast.FunctionDef)
            wrappers_by_target.setdefault(info.target_name, []).append(
                (info.order, index, stmt)
            )
        if not wrappers_by_target:
            return visited_body

        target_counts: dict[str, int] = {}
        for stmt in visited_body:
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if is_astichi_insert_shell(stmt):
                continue
            for argument in stmt.args.args:
                name = param_hole_name(argument)
                if name is not None:
                    target_counts[name] = target_counts.get(name, 0) + 1
        for name, count_value in sorted(target_counts.items()):
            if count_value > 1 and name in wrappers_by_target:
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        f"ambiguous parameter target `{name}` in one statement body",
                        hint="use distinct parameter-hole names or a more specific build path",
                    )
                )

        consumed_shell_ids: set[int] = set()
        result: list[ast.stmt] = []
        for stmt in visited_body:
            if id(stmt) in consumed_shell_ids:
                continue
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and not is_astichi_insert_shell(stmt):
                consumed = _apply_param_contributions_to_function(
                    stmt, wrappers_by_target
                )
                consumed_shell_ids.update(consumed)
                result.append(stmt)
                continue
            result.append(stmt)
        return result


def _apply_param_contributions_to_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    wrappers_by_target: dict[str, list[tuple[int, int, ast.FunctionDef]]],
) -> set[int]:
    consumed: set[int] = set()
    payloads_by_target: dict[str, list[ast.arguments]] = {}
    for argument in node.args.args:
        name = param_hole_name(argument)
        if name is None or name not in wrappers_by_target:
            continue
        ordered = sorted(wrappers_by_target[name], key=lambda item: (item[0], item[1]))
        payloads_by_target[name] = [copy.deepcopy(shell.args) for _order, _index, shell in ordered]
        consumed.update(id(shell) for _order, _index, shell in ordered)
    if not payloads_by_target:
        return consumed
    node.args = _merge_params_into_arguments(node.args, payloads_by_target)
    return consumed


def _merge_params_into_arguments(
    target: ast.arguments,
    payloads_by_target: dict[str, list[ast.arguments]],
) -> ast.arguments:
    positional = list(target.posonlyargs) + list(target.args)
    target_defaults = _defaults_by_arg(positional, list(target.defaults))
    new_posonlyargs: list[ast.arg] = []
    new_args: list[ast.arg] = []
    new_default_by_id: dict[int, ast.expr | None] = {}
    ordered_payloads: list[ast.arguments] = []

    for argument in target.posonlyargs:
        copied = copy.deepcopy(argument)
        new_posonlyargs.append(copied)
        new_default_by_id[id(copied)] = copy.deepcopy(target_defaults.get(id(argument)))

    for argument in target.args:
        name = param_hole_name(argument)
        if name is None:
            copied = copy.deepcopy(argument)
            new_args.append(copied)
            new_default_by_id[id(copied)] = copy.deepcopy(target_defaults.get(id(argument)))
            continue
        for payload in payloads_by_target.get(name, []):
            ordered_payloads.append(payload)
            payload_positionals = list(payload.posonlyargs) + list(payload.args)
            payload_defaults = _defaults_by_arg(payload_positionals, list(payload.defaults))
            for payload_arg in payload.args:
                copied = copy.deepcopy(payload_arg)
                new_args.append(copied)
                new_default_by_id[id(copied)] = copy.deepcopy(
                    payload_defaults.get(id(payload_arg))
                )

    merged = copy.deepcopy(target)
    merged.posonlyargs = new_posonlyargs
    merged.args = new_args
    merged.defaults = _rebuild_defaults(
        list(merged.posonlyargs) + list(merged.args), new_default_by_id
    )

    for payload in ordered_payloads:
        if payload.vararg is not None:
            if merged.vararg is not None:
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        "parameter insertion would create multiple *args parameters",
                        hint="only one authored or inserted vararg is allowed per function",
                    )
                )
            merged.vararg = copy.deepcopy(payload.vararg)
        if payload.kwarg is not None:
            if merged.kwarg is not None:
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        "parameter insertion would create multiple **kwargs parameters",
                        hint="only one authored or inserted kwarg is allowed per function",
                    )
                )
            merged.kwarg = copy.deepcopy(payload.kwarg)
        merged.kwonlyargs.extend(copy.deepcopy(payload.kwonlyargs))
        merged.kw_defaults.extend(copy.deepcopy(payload.kw_defaults))

    _validate_unique_parameter_names(merged)
    return merged


def _defaults_by_arg(
    positional: list[ast.arg], defaults: list[ast.expr]
) -> dict[int, ast.expr | None]:
    result: dict[int, ast.expr | None] = {id(arg): None for arg in positional}
    if not defaults:
        return result
    for argument, default in zip(positional[-len(defaults):], defaults, strict=True):
        result[id(argument)] = default
    return result


def _rebuild_defaults(
    positional: list[ast.arg],
    defaults_by_id: dict[int, ast.expr | None],
) -> list[ast.expr]:
    defaults: list[ast.expr] = []
    seen_default = False
    for argument in positional:
        default = defaults_by_id.get(id(argument))
        if default is None:
            if seen_default:
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        "parameter insertion would place a non-default parameter after a default",
                        hint="ensure inserted ordinary parameters with no default appear before defaulted parameters",
                    )
                )
            continue
        seen_default = True
        defaults.append(default)
    return defaults


def _validate_unique_parameter_names(args: ast.arguments) -> None:
    names: list[str] = []
    names.extend(argument.arg for argument in args.posonlyargs)
    names.extend(argument.arg for argument in args.args)
    names.extend(argument.arg for argument in args.kwonlyargs)
    if args.vararg is not None:
        names.append(args.vararg.arg)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        rendered = ", ".join(sorted(duplicates))
        raise ValueError(
            format_astichi_error(
                "materialize",
                f"duplicate final parameter names: {rendered}",
                hint="parameter names are API bindings and are not renamed by hygiene",
            )
        )


class _HoleReplacementTransformer(
    _SkipInsertShellTransformerMixin, ast.NodeTransformer
):
    def __init__(
        self,
        *,
        block_replacements: dict[str, list[_BlockContribution]],
        expr_replacements: dict[str, list[_ExpressionInsert]],
        param_replacements: dict[str, list[_ParamContribution]],
    ) -> None:
        self.block_replacements = block_replacements
        self.expr_replacements = expr_replacements
        self.param_replacements = param_replacements

    def generic_visit(self, node: ast.AST) -> ast.AST:
        for field, old_value in ast.iter_fields(node):
            if isinstance(old_value, list):
                new_values: list[object] = []
                for value in old_value:
                    if isinstance(value, ast.AST):
                        value = self.visit(value)
                        if value is None:
                            continue
                        if isinstance(value, list):
                            new_values.extend(value)
                            continue
                    new_values.append(value)
                old_value[:] = new_values
                continue
            if isinstance(old_value, ast.AST):
                new_node = self.visit(old_value)
                setattr(node, field, new_node)
        return node

    def visit_Expr(self, node: ast.Expr) -> ast.AST | list[ast.stmt]:
        hole_name = _extract_hole_name(node)
        if hole_name is not None and hole_name in self.block_replacements:
            contributions = self.block_replacements[hole_name]
            result: list[ast.stmt] = [node]
            for contrib in contributions:
                shell = _make_block_insert_shell(
                    target_name=hole_name,
                    order=contrib.order,
                    shell_name=contrib.shell_name,
                    body=contrib.body,
                    ref_path=contrib.ref_path,
                    location_donor=node,
                )
                result.append(shell)
            return result
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST | list[ast.stmt]:
        if is_astichi_insert_shell(node):
            return node
        result: list[ast.stmt] = []
        wrapped_targets: set[str] = set()
        for argument in node.args.args:
            target_name = param_hole_name(argument)
            if target_name is None or target_name not in self.param_replacements:
                continue
            wrapped_targets.add(target_name)
        visited = self.generic_visit(node)
        assert isinstance(visited, ast.FunctionDef)
        result.append(visited)
        for target_name in sorted(wrapped_targets):
            for contrib in self.param_replacements[target_name]:
                result.append(
                    _make_param_insert_shell(
                        target_name=target_name,
                        order=contrib.order,
                        shell_name=contrib.shell_name,
                        args=contrib.args,
                        ref_path=contrib.ref_path,
                        location_donor=node,
                    )
                )
        return result

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST | list[ast.stmt]:
        if is_astichi_insert_shell(node):
            return node
        result: list[ast.stmt] = []
        wrapped_targets: set[str] = set()
        for argument in node.args.args:
            target_name = param_hole_name(argument)
            if target_name is None or target_name not in self.param_replacements:
                continue
            wrapped_targets.add(target_name)
        visited = self.generic_visit(node)
        assert isinstance(visited, ast.AsyncFunctionDef)
        result.append(visited)
        for target_name in sorted(wrapped_targets):
            for contrib in self.param_replacements[target_name]:
                shell = _make_param_insert_shell(
                    target_name=target_name,
                    order=contrib.order,
                    shell_name=contrib.shell_name,
                    args=contrib.args,
                    ref_path=contrib.ref_path,
                    location_donor=node,
                )
                result.append(shell)
        return result

    def visit_Call(self, node: ast.Call) -> ast.AST:
        hole_name = _extract_expr_hole_name(node)
        if hole_name is not None and hole_name in self.expr_replacements:
            inserts = self.expr_replacements[hole_name]
            if len(inserts) != 1:
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        f"scalar expression target {hole_name} accepts at most one insert",
                        hint="wire only one edge into a scalar expression hole",
                    )
                )
            return _make_expression_insert_call(
                hole_name,
                inserts[0].expr,
                pyimports=inserts[0].pyimports,
                location_donor=node,
            )

        node.func = self.visit(node.func)

        authored_explicit_keywords = [
            keyword.arg for keyword in node.keywords if keyword.arg is not None
        ]
        seen_explicit_keywords: set[str] = set()
        for name in authored_explicit_keywords:
            register_explicit_keyword(name, seen_explicit_keywords)

        # `astichi_hole(name)` is an anchor through build/emit and is
        # only removed by `materialize()` (§2.2). Keep the authored
        # hole arg/keyword and append sibling `astichi_insert(name,
        # expr)` entries, mirroring the block-hole anchor pattern.
        new_args: list[ast.expr] = []
        for arg in node.args:
            hole_name = _extract_expr_hole_name(arg)
            if hole_name is not None and hole_name in self.expr_replacements:
                inserts = self.expr_replacements[hole_name]
                _validate_plain_call_region_inserts(
                    inserts, seen_explicit_keywords=seen_explicit_keywords
                )
                new_args.append(arg)
                new_args.extend(
                    _make_expression_insert_call(
                        hole_name,
                        insert.expr,
                        pyimports=insert.pyimports,
                        location_donor=arg,
                    )
                    for insert in inserts
                )
                continue
            if (
                isinstance(arg, ast.Starred)
                and (hole_name := _extract_expr_hole_name(arg.value)) is not None
                and hole_name in self.expr_replacements
            ):
                inserts = self.expr_replacements[hole_name]
                _validate_star_region_inserts(hole_name, inserts)
                new_args.append(arg)
                new_args.extend(
                    ast.Starred(
                        value=_make_expression_insert_call(
                            hole_name,
                            insert.expr,
                            pyimports=insert.pyimports,
                            location_donor=arg,
                        ),
                        ctx=arg.ctx,
                    )
                    for insert in inserts
                )
                continue
            visited = self.visit(arg)
            if isinstance(visited, list):
                new_args.extend(visited)
            else:
                new_args.append(visited)

        new_keywords: list[ast.keyword] = []
        for keyword in node.keywords:
            hole_name = _extract_expr_hole_name(keyword.value)
            if keyword.arg is None and hole_name is not None and hole_name in self.expr_replacements:
                inserts = self.expr_replacements[hole_name]
                _validate_dstar_region_inserts(
                    hole_name,
                    inserts,
                    seen_explicit_keywords=seen_explicit_keywords,
                )
                new_keywords.append(keyword)
                new_keywords.extend(
                    ast.keyword(
                        arg=None,
                        value=_make_expression_insert_call(
                            hole_name,
                            insert.expr,
                            pyimports=insert.pyimports,
                            location_donor=keyword,
                        ),
                    )
                    for insert in inserts
                )
                continue
            visited = self.visit(keyword)
            if isinstance(visited, list):
                new_keywords.extend(visited)
            else:
                new_keywords.append(visited)

        node.args = new_args
        node.keywords = new_keywords
        return node

    def visit_Starred(self, node: ast.Starred) -> ast.AST | list[ast.expr]:
        hole_name = _extract_expr_hole_name(node.value)
        if hole_name is not None and hole_name in self.expr_replacements:
            return [
                ast.Starred(
                    value=_make_expression_insert_call(
                        hole_name,
                        insert.expr,
                        pyimports=insert.pyimports,
                        location_donor=node,
                    ),
                    ctx=node.ctx,
                )
                for insert in self.expr_replacements[hole_name]
            ]
        return self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> ast.AST | list[ast.keyword]:
        hole_name = _extract_expr_hole_name(node.value)
        if node.arg is None and hole_name is not None and hole_name in self.expr_replacements:
            expanded: list[ast.keyword] = []
            for insert in self.expr_replacements[hole_name]:
                if not isinstance(insert.expr, ast.Dict):
                    raise ValueError(
                        format_astichi_error(
                            "materialize",
                            f"named variadic target {hole_name} requires dict-display expression inserts",
                            hint="use `astichi_insert(hole, {{...}})` with a dict literal payload",
                        )
                    )
                expanded.append(
                    ast.keyword(
                        arg=None,
                        value=_make_expression_insert_call(
                            hole_name,
                            insert.expr,
                            pyimports=insert.pyimports,
                            location_donor=node,
                        ),
                    )
                )
            return expanded
        return self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> ast.AST:
        new_keys: list[ast.expr | None] = []
        new_values: list[ast.expr] = []
        for key, value in zip(node.keys, node.values, strict=True):
            hole_name = _extract_expr_hole_name(value)
            if key is None and hole_name is not None and hole_name in self.expr_replacements:
                for insert in self.expr_replacements[hole_name]:
                    if not isinstance(insert.expr, ast.Dict):
                        raise ValueError(
                            format_astichi_error(
                                "materialize",
                                f"named variadic target {hole_name} requires dict-display expression inserts",
                                hint="use `astichi_insert(hole, {{...}})` with a dict literal payload",
                            )
                        )
                    new_keys.append(None)
                    new_values.append(
                        _make_expression_insert_call(
                            hole_name,
                            insert.expr,
                            pyimports=insert.pyimports,
                            location_donor=value,
                        )
                    )
                continue
            new_keys.append(self.visit(key) if key is not None else None)
            new_values.append(self.visit(value))
        node.keys = new_keys
        node.values = new_values
        return node


def _realize_expression_insert_wrappers(tree: ast.Module) -> None:
    transformer = _ExpressionInsertRealizer()
    transformed = transformer.visit(tree)
    assert isinstance(transformed, ast.Module)
    tree.body = transformed.body


class _ExpressionInsertRealizer(ast.NodeTransformer):
    def generic_visit(self, node: ast.AST) -> ast.AST:
        for field, old_value in ast.iter_fields(node):
            if isinstance(old_value, list):
                new_values: list[object] = []
                for value in old_value:
                    if isinstance(value, ast.AST):
                        value = self.visit(value)
                        if value is None:
                            continue
                        if isinstance(value, list):
                            new_values.extend(value)
                            continue
                    new_values.append(value)
                old_value[:] = new_values
                continue
            if isinstance(old_value, ast.AST):
                setattr(node, field, self.visit(old_value))
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        if _is_expression_insert_call(node):
            payload_expr = node.args[1]
            if is_astichi_funcargs_call(payload_expr):
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        "astichi_funcargs payload wrapper must be realized in a call "
                        "argument position",
                        hint="keep `astichi_funcargs` inside a call's arg list, not a bare statement",
                    )
                )
            return self.visit(copy.deepcopy(payload_expr))

        node.func = self.visit(node.func)

        # Materialize strips the `astichi_hole(name)` anchor and keeps
        # only the sibling `astichi_insert(...)` entries wired to it.
        new_args: list[ast.expr] = []
        suffix_keywords: list[ast.keyword] = []
        for arg in node.args:
            if _extract_expr_hole_name(arg) is not None:
                continue
            if (
                isinstance(arg, ast.Starred)
                and _extract_expr_hole_name(arg.value) is not None
            ):
                continue
            if (
                isinstance(arg, ast.Call)
                and _is_expression_insert_call(arg)
                and is_astichi_funcargs_call(arg.args[1])
            ):
                payload = extract_funcargs_payload(arg.args[1])
                lowered_args, lowered_keywords = lower_payload_for_region(
                    payload,
                    region=PLAIN_FUNC_ARG_REGION,
                    hole_name=_insert_target_name(arg) or "<payload>",
                    transform_expr=lambda expr: self.visit(copy.deepcopy(expr)),
                )
                new_args.extend(lowered_args)
                suffix_keywords.extend(lowered_keywords)
                continue
            if (
                isinstance(arg, ast.Starred)
                and isinstance(arg.value, ast.Call)
                and _is_expression_insert_call(arg.value)
                and is_astichi_funcargs_call(arg.value.args[1])
            ):
                payload = extract_funcargs_payload(arg.value.args[1])
                lowered_args, _ = lower_payload_for_region(
                    payload,
                    region=STARRED_FUNC_ARG_REGION,
                    hole_name=_insert_target_name(arg.value) or "<payload>",
                    transform_expr=lambda expr: self.visit(copy.deepcopy(expr)),
                )
                new_args.extend(lowered_args)
                continue
            visited = self.visit(arg)
            if isinstance(visited, list):
                new_args.extend(visited)
            else:
                new_args.append(visited)

        new_keywords: list[ast.keyword] = []
        for keyword in node.keywords:
            if (
                keyword.arg is None
                and _extract_expr_hole_name(keyword.value) is not None
            ):
                continue
            if (
                keyword.arg is None
                and isinstance(keyword.value, ast.Call)
                and _is_expression_insert_call(keyword.value)
                and is_astichi_funcargs_call(keyword.value.args[1])
            ):
                payload = extract_funcargs_payload(keyword.value.args[1])
                _, lowered_keywords = lower_payload_for_region(
                    payload,
                    region=DOUBLE_STAR_FUNC_ARG_REGION,
                    hole_name=_insert_target_name(keyword.value) or "<payload>",
                    transform_expr=lambda expr: self.visit(copy.deepcopy(expr)),
                )
                new_keywords.extend(lowered_keywords)
                continue
            visited = self.visit(keyword)
            if isinstance(visited, list):
                new_keywords.extend(visited)
            else:
                new_keywords.append(visited)

        node.args = new_args
        # Addendum §4.1: for a plain call-position hole, keyword / `**`
        # payload items land after the authored keyword region.
        node.keywords = new_keywords + suffix_keywords
        return node

    def visit_Starred(self, node: ast.Starred) -> ast.AST | list[ast.expr]:
        if isinstance(node.value, ast.Call) and _is_expression_insert_call(node.value):
            return [self.visit(copy.deepcopy(node.value.args[1]))]
        return self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> ast.AST | list[ast.keyword]:
        if (
            node.arg is None
            and isinstance(node.value, ast.Call)
            and _is_expression_insert_call(node.value)
        ):
            expr = copy.deepcopy(node.value.args[1])
            if not isinstance(expr, ast.Dict):
                raise ValueError(
                    format_astichi_error(
                        "materialize",
                        "named variadic expression inserts require dict-display payloads",
                        hint="use a dict display `{k: v, ...}` as the insert payload",
                    )
                )
            expanded: list[ast.keyword] = []
            for key, value in zip(expr.keys, expr.values, strict=True):
                if key is None or not isinstance(key, ast.Name):
                    raise ValueError(
                        format_astichi_error(
                            "materialize",
                            "named variadic keyword expansion requires identifier keys",
                            hint="use `{{name: expr}}` with bare identifier keys",
                        )
                    )
                expanded.append(
                    ast.keyword(
                        arg=key.id,
                        value=self.visit(copy.deepcopy(value)),
                    )
                )
            return expanded
        return self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> ast.AST:
        new_keys: list[ast.expr | None] = []
        new_values: list[ast.expr] = []
        for key, value in zip(node.keys, node.values, strict=True):
            if (
                key is None
                and isinstance(value, ast.Call)
                and _is_expression_insert_call(value)
            ):
                expr = copy.deepcopy(value.args[1])
                if not isinstance(expr, ast.Dict):
                    raise ValueError(
                        format_astichi_error(
                            "materialize",
                            "named variadic dict expansion requires dict-display payloads",
                            hint="use a dict literal inside the insert for `**` expansion",
                        )
                    )
                for insert_key, insert_value in zip(expr.keys, expr.values, strict=True):
                    new_keys.append(
                        self.visit(copy.deepcopy(insert_key))
                        if insert_key is not None
                        else None
                    )
                    new_values.append(self.visit(copy.deepcopy(insert_value)))
                continue
            new_keys.append(self.visit(key) if key is not None else None)
            new_values.append(self.visit(value))
        node.keys = new_keys
        node.values = new_values
        return node


def _payload_local_directive_markers(
    directives: tuple[PayloadLocalDirective, ...],
) -> tuple[RecognizedMarker, ...]:
    markers: list[RecognizedMarker] = []
    for directive in directives:
        call = ast.Call(
            func=ast.Name(id=directive.spec.source_name, ctx=ast.Load()),
            args=[ast.Name(id=directive.name, ctx=ast.Load())],
            keywords=[],
        )
        propagate_ast_source_locations(call, None)
        markers.append(
            RecognizedMarker(spec=directive.spec, node=call, context=CALL_CONTEXT)
        )
    return tuple(markers)


def materialize_composable(composable: BasicComposable) -> BasicComposable:
    """Materialize a composable: validate completeness and apply final hygiene.

    The pipeline (see
    `AstichiApiDesignV1-CompositionUnification.md §4`):

    1. **Gate** (runs before hygiene): reject any composable that is not
       fully well-formed — unresolved mandatory holes, unsupplied
       bind-externals, unmatched `@astichi_insert` block shells, or
       unmatched expression-form `astichi_insert` calls. Per §2.5,
       hygiene must never run on an out-of-place tree.
    2. deep-copy the tree and recognize markers;
    3. assign scope identity and rename scope collisions (hygiene);
    4. realize expression-insert wrappers;
    5. flatten block-level `astichi_hole`/`astichi_insert` shell pairs;
    6. strip residual metadata markers;
    7. re-recognize markers and re-extract ports.
    """
    satisfied_holes = _locally_satisfied_hole_names(composable.tree)
    satisfied_param_holes = _locally_satisfied_param_hole_names(composable.tree)
    required_holes = _required_hole_names(composable.tree)
    mandatory_holes = [
        port
        for port in composable.demand_ports
        if (
            (
                port.is_additive_hole_demand()
                and port.name in required_holes
                and port.name not in satisfied_holes
            )
            or (
                port.is_parameter_hole_demand()
                and port.name not in satisfied_param_holes
            )
        )
    ]
    if mandatory_holes:
        names = ", ".join(port.name for port in mandatory_holes)
        raise ValueError(
            format_astichi_error(
                "materialize",
                f"mandatory holes remain unresolved: {names}",
                hint="wire each hole with `builder` edges or fill `astichi_hole` targets before materialize",
            )
        )
    mandatory_binds = [
        port for port in composable.demand_ports if port.is_external_bind_demand()
    ]
    if mandatory_binds:
        if len(mandatory_binds) == 1:
            name = mandatory_binds[0].name
            raise ValueError(
                format_astichi_error(
                    "materialize",
                    f"external binding for `{name}` was not supplied; "
                    f"call composable.bind({name}=...) before materializing.",
                    hint="use `composable.bind(...)` to supply `astichi_bind_external` values",
                )
            )
        names = ", ".join(port.name for port in mandatory_binds)
        raise ValueError(
            format_astichi_error(
                "materialize",
                "external bindings were not supplied: "
                f"{names}; call composable.bind(...) before materializing.",
                hint="pass every required `astichi_bind_external` name to `bind(...)`",
            )
        )

    arg_bindings = dict(composable.arg_bindings)
    unresolved_args = _find_unresolved_arg_identifiers(
        composable.tree, resolved_names=frozenset(arg_bindings)
    )
    if unresolved_args:
        # Issue 005 §5 step 1 / §7: unresolved `__astichi_arg__` sites are a
        # hard gate error. Each entry carries every textual occurrence of the
        # parameter so the user sees the full reach of the unresolved slot.
        # 5a covers only class/def names; 5b extends coverage to ast.Name /
        # ast.arg; 5c consults `composable.arg_bindings` so resolved slots
        # are not rejected.
        parts: list[str] = []
        for name, lines in unresolved_args:
            rendered_lines = ", ".join(str(lineno) for lineno in lines)
            parts.append(
                f"{name}__astichi_arg__ at line(s) {rendered_lines}"
            )
        raise ValueError(
            format_astichi_error(
                "materialize",
                "unresolved identifier-arg slots (call .bind_identifier(...) "
                "or wire the arg before materialize): " + "; ".join(parts),
                hint="use `bind_identifier` or compile-time `arg_names=` for each `__astichi_arg__` slot",
            )
        )

    unmatched_block_shells = _find_unmatched_block_insert_shells(composable.tree)
    unmatched_param_shells = _find_unmatched_param_insert_shells(composable.tree)
    unmatched_expr_inserts = _find_unmatched_expression_inserts(composable.tree)
    if unmatched_block_shells or unmatched_param_shells or unmatched_expr_inserts:
        parts: list[str] = []
        for name, lineno in unmatched_block_shells:
            parts.append(
                f"@astichi_insert({name}) at line {lineno} has no matching "
                f"astichi_hole({name}) in the same body"
            )
        for name, lineno in unmatched_expr_inserts:
            parts.append(
                f"astichi_insert({name}, ...) at line {lineno} has no "
                f"matching astichi_hole({name}) expression in the tree"
            )
        for name, lineno in unmatched_param_shells:
            parts.append(
                f"@astichi_insert({name}, kind='params') at line {lineno} has no "
                f"matching {name}__astichi_param_hole__ parameter in the same body"
            )
        raise ValueError(
            format_astichi_error(
                "materialize",
                "unmatched astichi_insert supplies; every insert must point "
                "at an extant hole before materialize runs hygiene: "
                + "; ".join(parts),
                hint="add a matching `astichi_hole(name)` for each `astichi_insert(name, ...)`",
            )
        )

    tree = copy.deepcopy(composable.tree)
    # Issue 005 §5 step 2 / 5c: resolve identifier-arg slots before
    # hygiene. Every `__astichi_arg__` occurrence whose stripped name is
    # in the bindings map is substituted atomically with the target
    # identifier; post-pass no `__astichi_arg__` suffix survives (the
    # gate already rejected unresolved ones). Resolved targets are then
    # pinned through hygiene so later passes do not rename them.
    if arg_bindings:
        _resolve_arg_identifiers(tree, arg_bindings)
        # Issue 006 6c: the same `arg_bindings` map is consulted to
        # rename `astichi_import(x)` declarations and their body
        # references from inner `x` to outer `arg_bindings[x]`. Entries
        # that do not match an import site are a no-op here (they may
        # still have matched `__astichi_arg__` above, or they may
        # surface as a validation error at compile-time).
        _resolve_boundary_imports(tree, arg_bindings)
        _resolve_boundary_passes(tree, arg_bindings)
    _realize_param_insert_wrappers(tree)
    _remove_optional_annotation_holes(tree)
    unresolved_boundaries = _find_unresolved_boundary_demands(tree)
    if unresolved_boundaries:
        parts = [
            f"{kind}({name}) at line {lineno}"
            for kind, name, lineno in unresolved_boundaries
        ]
        raise ValueError(
            format_astichi_error(
                "materialize",
                "unresolved boundary identifier demands: " + "; ".join(parts),
                hint="wire each `astichi_import(...)` / `astichi_pass(...)` explicitly "
                "before materialize, or author `outer_bind=True` for immediate same-name outer binding",
            )
        )
    apply_external_ref_lowering(tree)
    markers = recognize_markers(tree)
    managed_imports = collect_managed_imports(markers)
    pyimport_synthetic_bindings = tuple(
        SyntheticBindingOccurrence(
            raw_name=record.local_node.id,
            declaration_node=record.marker.node,
            node=record.local_node,
            collision_domain=0,
            identity_key=(
                "astichi_pyimport",
                record.module_path,
                record.original_symbol,
            ),
        )
        for record in managed_imports
    )
    # Hygiene pinning is only meaningful for names that actually sit
    # at a hygiene-relevant position in the tree — `ast.Name`,
    # `ast.arg`, or a def/class name. Callsite `ast.keyword.arg`
    # labels are not lexical bindings in any scope; "pinning" such a
    # name is vacuous for itself and could incorrectly shield an
    # unrelated same-named scope binding elsewhere in the merged tree
    # from being renamed on collision. The candidate pin set (every
    # `arg_bindings` value plus explicitly-bound boundary targets) is
    # therefore intersected with the set of names that appear at a
    # scope-relevant position. This also handles the merge case where
    # multiple same-key `arg_bindings` pairs contribute distinct
    # target names (e.g. two payloads bound `slot` to `x` and `y`
    # respectively before merge) — both are pinned if both land as
    # real identifier occurrences.
    hygiene_relevant_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            hygiene_relevant_names.add(node.id)
        elif isinstance(node, ast.arg):
            hygiene_relevant_names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            hygiene_relevant_names.add(node.name)

    pin_candidates = {value for _, value in composable.arg_bindings} | (
        _collect_explicitly_bound_boundary_targets(tree)
    )
    pinned_targets = frozenset(pin_candidates & hygiene_relevant_names)
    marker_keep_names = frozenset(
        marker.name_id
        for marker in markers
        if marker.spec is KEEP and marker.name_id is not None
    )
    explicit_keep_names = composable.keep_names - marker_keep_names
    effective_keep_names = explicit_keep_names | pinned_targets
    provisional = BasicComposable(
        tree=tree,
        origin=composable.origin,
        markers=markers,
        bound_externals=composable.bound_externals,
        keep_names=effective_keep_names,
    )

    # Issue 006 6c (trust model): only user-declared keep_names (plus
    # keep markers auto-unioned inside `assign_scope_identity`)
    # enter the trust set. `pinned_targets` reach preserved but not
    # trusted — they must still participate in cross-scope rename so
    # sibling-root contributions bound to the same `arg_names` value
    # do not clobber each other.
    analysis = assign_scope_identity(
        provisional,
        preserved_names=effective_keep_names,
        trust_names=explicit_keep_names,
        synthetic_bindings=pyimport_synthetic_bindings,
    )
    rename_scope_collisions(analysis)
    payload_local_directives = collect_payload_local_directives(tree)
    _realize_expression_insert_wrappers(tree)
    _flatten_block_inserts(tree)
    insert_managed_imports(tree, managed_imports)

    pre_strip_markers = (
        recognize_markers(tree)
        + _payload_local_directive_markers(payload_local_directives)
    )
    pre_strip_composable = BasicComposable(
        tree=tree,
        origin=composable.origin,
        markers=pre_strip_markers,
        bound_externals=composable.bound_externals,
    )
    pre_strip_classification = analyze_names(
        pre_strip_composable, mode="permissive", preserved_names=effective_keep_names
    )
    demand_ports = extract_demand_ports(pre_strip_markers, pre_strip_classification)
    supply_ports = extract_supply_ports(pre_strip_markers)

    _strip_residual_markers(tree)
    _strip_keep_identifier_suffix(tree)
    _assert_no_arg_suffix_remains(tree)

    markers = recognize_markers(tree)
    if has_pyimport_marker(markers):
        raise AssertionError("astichi_pyimport marker survived materialize")
    post_strip = BasicComposable(
        tree=tree,
        origin=composable.origin,
        markers=markers,
        bound_externals=composable.bound_externals,
        keep_names=effective_keep_names,
    )
    classification = analyze_names(
        post_strip, mode="permissive", preserved_names=effective_keep_names
    )

    return BasicComposable(
        tree=tree,
        origin=composable.origin,
        markers=markers,
        classification=classification,
        demand_ports=demand_ports,
        supply_ports=supply_ports,
        bound_externals=composable.bound_externals,
        keep_names=effective_keep_names,
    )
def _prefix_shell_refs_in_body(body: list[ast.stmt], prefix: RefPath) -> None:
    """Prefix every builder-carried shell ref inside ``body`` in-place."""

    class _ShellRefPrefixer(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            self._prefix_node(node)
            return self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
            self._prefix_node(node)
            return self.generic_visit(node)

        def _prefix_node(
            self, node: ast.FunctionDef | ast.AsyncFunctionDef
        ) -> None:
            info = extract_block_insert_shell(node, phase="materialize")
            if info is None or info.ref_path is None:
                return
            for decorator in node.decorator_list:
                if is_astichi_insert_call(decorator):
                    prefix_insert_ref(decorator, prefix, phase="materialize")
                    return

    prefixer = _ShellRefPrefixer()
    for index, stmt in enumerate(body):
        body[index] = prefixer.visit(stmt)  # type: ignore[assignment]


def _replace_targets_in_tree(
    tree: ast.Module,
    *,
    block_replacements: dict[tuple[RefPath, str], list[_BlockContribution]],
    expr_replacements: dict[tuple[RefPath, str], list[_ExpressionInsert]],
    param_replacements: dict[tuple[RefPath, str], list[_ParamContribution]],
) -> None:
    """Apply target replacements keyed by ``(shell_ref_path, hole_name)``."""

    def _apply_to_body(body: list[ast.stmt], current_ref: RefPath) -> list[ast.stmt]:
        local_block = {
            target_name: contributions
            for (ref_path, target_name), contributions in block_replacements.items()
            if ref_path == current_ref
        }
        local_expr = {
            target_name: inserts
            for (ref_path, target_name), inserts in expr_replacements.items()
            if ref_path == current_ref
        }
        local_param = {
            target_name: contributions
            for (ref_path, target_name), contributions in param_replacements.items()
            if ref_path == current_ref
        }
        if local_block or local_expr or local_param:
            body = _replace_targets_in_body(
                body,
                block_replacements=local_block,
                expr_replacements=local_expr,
                param_replacements=local_param,
            )
        for stmt in body:
            info = extract_block_insert_shell(stmt, phase="materialize")
            if info is None or not isinstance(
                stmt, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            next_ref = info.ref_path if info.ref_path is not None else current_ref
            stmt.body = _apply_to_body(stmt.body, next_ref)
        return body

    tree.body = _apply_to_body(tree.body, ())


def _find_unmatched_block_insert_shells(tree: ast.AST) -> list[tuple[str, int]]:
    """Return `(target_name, lineno)` for every `@astichi_insert` block
    shell whose target hole is not a sibling in the same body.

    Per `AstichiApiDesignV1-CompositionUnification.md §2.5 (c)` and §4,
    a block-form insert must be matched by a sibling `astichi_hole` in
    the same statement list. Unmatched shells are rejected at the
    materialize gate before hygiene runs.
    """
    unmatched: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            if not hasattr(node, field):
                continue
            value = getattr(node, field)
            if not isinstance(value, list):
                continue
            if not value or not all(isinstance(item, ast.stmt) for item in value):
                continue
            holes: set[str] = set()
            shells: list[tuple[str, int]] = []
            for stmt in value:
                hole_name = _extract_hole_name(stmt)
                if hole_name is not None:
                    holes.add(hole_name)
                info = extract_block_insert_shell(stmt, phase="materialize")
                if info is not None:
                    lineno = getattr(stmt, "lineno", 0) or 0
                    shells.append((info.target_name, lineno))
            for name, lineno in shells:
                if name not in holes:
                    unmatched.append((name, lineno))
    return unmatched


def _find_unmatched_expression_inserts(tree: ast.AST) -> list[tuple[str, int]]:
    """Return `(target_name, lineno)` for every *orphan* expression-form
    `astichi_insert(name, expr)` — i.e. a bare `ast.Expr` statement
    whose value is an expression-insert call.

    Per `AstichiApiDesignV1-CompositionUnification.md §2.5 (c)`, an
    expression-form insert is **matched** when it sits at an expression
    position that was formerly an `astichi_hole(name)` — that is, when
    it appears as a wrapper embedded in an expression context. `build()`
    produces exactly that shape by substituting each expression hole
    with an `astichi_insert(name, expr)` call at the hole's expression
    position, so at materialize time the legitimate wrapper form is
    always embedded (inside an `ast.Assign`, `ast.Call` argument list,
    inside an `ast.Starred`, etc.), never a bare statement.

    A surviving *bare statement* form is therefore an unwired supply
    that no `build()` step consumed. It would not be unwrapped by
    `_realize_expression_insert_wrappers` (that pass replaces call
    nodes in expression context), so it would leak through hygiene and
    into the emitted output. The gate refuses it.
    """
    unmatched: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            if not hasattr(node, field):
                continue
            value = getattr(node, field)
            if not isinstance(value, list):
                continue
            for stmt in value:
                if not isinstance(stmt, ast.Expr):
                    continue
                if not isinstance(stmt.value, ast.Call):
                    continue
                if not _is_expression_insert_call(stmt.value):
                    continue
                target = _insert_target_name(stmt.value)
                if target is None:
                    continue
                lineno = getattr(stmt, "lineno", 0) or 0
                unmatched.append((target, lineno))
    return unmatched


def _find_unmatched_param_insert_shells(tree: ast.AST) -> list[tuple[str, int]]:
    unmatched: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            if not hasattr(node, field):
                continue
            value = getattr(node, field)
            if not isinstance(value, list):
                continue
            if not value or not all(isinstance(item, ast.stmt) for item in value):
                continue
            holes = _param_holes_in_statement_list(value)
            for stmt in value:
                info = extract_param_insert_shell(stmt, phase="materialize")
                if info is None:
                    continue
                if info.target_name not in holes:
                    unmatched.append((info.target_name, getattr(stmt, "lineno", 0) or 0))
    return unmatched


def _locally_satisfied_hole_names(tree: ast.AST) -> frozenset[str]:
    """Hole names whose matching `astichi_insert` shell is a body sibling.

    A hole whose insert shell lives in the same statement list — or,
    for call-argument anchors, in the same call's ``args`` /
    ``keywords`` list — is "locally satisfied": the materialize pass
    will consume both. Demand gates therefore exclude these holes from
    the unresolved set.
    """
    matched: set[str] = set()
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            if not hasattr(node, field):
                continue
            value = getattr(node, field)
            if not isinstance(value, list):
                continue
            if not value or not all(isinstance(item, ast.stmt) for item in value):
                continue
            holes: set[str] = set()
            shells: set[str] = set()
            for stmt in value:
                hole_name = _extract_hole_name(stmt)
                if hole_name is not None:
                    holes.add(hole_name)
                info = extract_block_insert_shell(stmt, phase="materialize")
                if info is not None:
                    shells.add(info.target_name)
            matched.update(holes & shells)
        if isinstance(node, ast.Call):
            matched.update(_call_region_locally_satisfied(node))
    return frozenset(matched)


def _call_region_locally_satisfied(call: ast.Call) -> frozenset[str]:
    """Hole anchor + sibling insert pairs in call arg/kwarg lists."""
    holes: set[str] = set()
    inserts: set[str] = set()
    for arg in call.args:
        name = _extract_expr_hole_name(arg)
        if name is not None:
            holes.add(name)
            continue
        if isinstance(arg, ast.Starred):
            name = _extract_expr_hole_name(arg.value)
            if name is not None:
                holes.add(name)
                continue
            if isinstance(arg.value, ast.Call) and _is_expression_insert_call(arg.value):
                target = _insert_target_name(arg.value)
                if target is not None:
                    inserts.add(target)
            continue
        if isinstance(arg, ast.Call) and _is_expression_insert_call(arg):
            target = _insert_target_name(arg)
            if target is not None:
                inserts.add(target)
    for keyword in call.keywords:
        if keyword.arg is None:
            name = _extract_expr_hole_name(keyword.value)
            if name is not None:
                holes.add(name)
                continue
            if (
                isinstance(keyword.value, ast.Call)
                and _is_expression_insert_call(keyword.value)
            ):
                target = _insert_target_name(keyword.value)
                if target is not None:
                    inserts.add(target)
    return frozenset(holes & inserts)


def _locally_satisfied_param_hole_names(tree: ast.AST) -> frozenset[str]:
    matched: set[str] = set()
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            if not hasattr(node, field):
                continue
            value = getattr(node, field)
            if not isinstance(value, list):
                continue
            if not value or not all(isinstance(item, ast.stmt) for item in value):
                continue
            holes = _param_holes_in_statement_list(value)
            shells = {
                info.target_name
                for stmt in value
                if (info := extract_param_insert_shell(stmt, phase="materialize")) is not None
            }
            matched.update(holes & shells)
    return frozenset(matched)


def _param_holes_in_statement_list(body: list[ast.stmt]) -> set[str]:
    names: set[str] = set()

    class _Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if is_astichi_insert_shell(node):
                return
            for argument in node.args.args:
                name = param_hole_name(argument)
                if name is not None:
                    names.add(name)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if is_astichi_insert_shell(node):
                return
            for argument in node.args.args:
                name = param_hole_name(argument)
                if name is not None:
                    names.add(name)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

    collector = _Collector()
    for statement in body:
        collector.visit(statement)
    return names


def _flatten_block_inserts(tree: ast.AST) -> None:
    """Recursively flatten `astichi_hole`/`astichi_insert` pairs in bodies.

    For each body-bearing node, scan its statement list for
    `astichi_hole(name)` anchors and their sibling `astichi_insert`-
    decorated shells, then splice the shell bodies at the hole
    position (in `order=` ascending, stable on ties) and remove both
    the hole and the consumed shells. Unmatched shells are left in
    place; an unmatched hole cannot occur here because the mandatory-
    demand gate rejects them before this pass runs.

    See `AstichiApiDesignV1-CompositionUnification.md §4`.
    """
    _BlockInsertFlattener().visit(tree)


class _BlockInsertFlattener(ast.NodeTransformer):
    def generic_visit(self, node: ast.AST) -> ast.AST:
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                new_items: list[object] = []
                for item in value:
                    if isinstance(item, ast.AST):
                        visited = self.visit(item)
                        if visited is None:
                            continue
                        if isinstance(visited, list):
                            new_items.extend(visited)
                            continue
                        new_items.append(visited)
                    else:
                        new_items.append(item)
                if new_items and all(isinstance(item, ast.stmt) for item in new_items):
                    stmt_list: list[ast.stmt] = [item for item in new_items if isinstance(item, ast.stmt)]
                    flattened = _flatten_body_splices(stmt_list)
                    value[:] = flattened
                else:
                    value[:] = new_items
            elif isinstance(value, ast.AST):
                setattr(node, field, self.visit(value))
        return node


_RESIDUAL_MARKER_NAMES: frozenset[str] = frozenset(
    {"astichi_keep", "astichi_export"}
)


# Issue 006: `astichi_import(name)` is the declaration-form boundary
# marker. It carries no runtime value and is stripped when it survives as
# a bare statement. `astichi_pass(name)` is the value-form surface and is
# lowered to the wrapped identifier only in expression positions.
_BOUNDARY_DECLARATION_MARKER_NAMES: frozenset[str] = frozenset({"astichi_import"})
_PYIMPORT_DECLARATION_MARKER_NAMES: frozenset[str] = frozenset({"astichi_pyimport"})


def _residual_marker_inner(node: ast.AST) -> ast.expr | None:
    """Return the wrapped identifier expression if node is a residual-marker call."""
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Name):
        return None
    if node.func.id not in _RESIDUAL_MARKER_NAMES:
        return None
    if len(node.args) != 1 or node.keywords:
        return None
    return node.args[0]


def _is_boundary_declaration_marker(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name):
        return False
    return node.func.id in _BOUNDARY_DECLARATION_MARKER_NAMES


def _is_pyimport_declaration_marker(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name):
        return False
    return node.func.id in _PYIMPORT_DECLARATION_MARKER_NAMES


def _is_pass_call(node: ast.Call) -> bool:
    return is_call_to_marker(node, PASS)


def _boundary_value_replacement(node: ast.AST) -> ast.expr | None:
    if (
        isinstance(node, ast.Call)
        and (
            _is_boundary_declaration_marker(node)
            or _is_pass_call(node)
        )
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
    ):
        return copy.deepcopy(node.args[0])
    sentinel = match_transparent_sentinel(
        node,
        is_marker_call=_is_pass_call,
    )
    if sentinel is None:
        return None
    call = sentinel.call
    if len(call.args) != 1:
        return None
    if not isinstance(call.args[0], ast.Name):
        return None
    inner = copy.deepcopy(call.args[0])
    inner.ctx = sentinel.ctx
    ast.copy_location(inner, node)
    return inner


def _strip_residual_markers(tree: ast.AST) -> None:
    """Strip `astichi_keep` / `astichi_export` call-form markers.

    Per `AstichiApiDesignV1-CompositionUnification.md §6`:
    - statement form (e.g. `astichi_export(x)`) is removed;
    - expression form (e.g. `result = astichi_keep(x)`) is replaced
      with the wrapped identifier expression (`result = x`).

    Port records for these markers are extracted before this pass
    runs, so stripping the call sites does not lose supply-port
    metadata on the returned composable.

    Identifier-shape suffix markers (`__astichi_keep__` /
    `__astichi_arg__`, issue 005) are handled by separate passes:
    `_strip_keep_identifier_suffix` runs after this one, and the
    arg-unresolved gate rejects any residual `__astichi_arg__`.
    """
    _ResidualMarkerStripper().visit(tree)
    ast.fix_missing_locations(tree)


class _ResidualMarkerStripper(ast.NodeTransformer):
    def visit_NamedExpr(self, node: ast.NamedExpr) -> ast.AST:
        replacement = _boundary_value_replacement(node.value)
        if replacement is not None:
            return ast.NamedExpr(
                target=node.target,
                value=replacement,
            )
        return self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> ast.AST:
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                original_items = tuple(value)
                new_items: list[object] = []
                for item in value:
                    if isinstance(item, ast.AST):
                        visited = self.visit(item)
                        if visited is None:
                            continue
                        if isinstance(visited, list):
                            new_items.extend(visited)
                            continue
                        new_items.append(visited)
                    else:
                        new_items.append(item)
                if (
                    not new_items
                    and _is_suite_statement_list(node, field)
                    and any(isinstance(item, ast.stmt) for item in original_items)
                ):
                    new_items.append(_empty_suite_pass(node, original_items))
                value[:] = new_items
            elif isinstance(value, ast.AST):
                replaced = self.visit(value)
                if replaced is None:
                    setattr(node, field, None)
                else:
                    setattr(node, field, replaced)
        return node

    def visit_Expr(self, node: ast.Expr) -> ast.AST | None:
        if _residual_marker_inner(node.value) is not None:
            return None
        if _is_boundary_declaration_marker(node.value):
            # Import declarations are compile-time-only; port records
            # and hygiene-scope classification already consumed them
            # upstream.
            return None
        if _is_pyimport_declaration_marker(node.value):
            return None
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        inner = _residual_marker_inner(node)
        if inner is not None:
            return self.visit(copy.deepcopy(inner))
        replacement = _boundary_value_replacement(node)
        if replacement is not None:
            return self.visit(replacement)
        return self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        replacement = _boundary_value_replacement(node)
        if replacement is not None:
            return self.visit(replacement)
        return self.generic_visit(node)


def _is_suite_statement_list(node: ast.AST, field: str) -> bool:
    if isinstance(node, ast.Module):
        return False
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return field == "body"
    if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While)):
        return field in {"body", "orelse"}
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return field == "body"
    try_star = getattr(ast, "TryStar", None)
    try_nodes = (ast.Try,) if try_star is None else (ast.Try, try_star)
    if isinstance(node, try_nodes):
        return field in {"body", "orelse", "finalbody"}
    if isinstance(node, ast.ExceptHandler):
        return field == "body"
    match_case = getattr(ast, "match_case", None)
    if match_case is not None and isinstance(node, match_case):
        return field == "body"
    return False


def _empty_suite_pass(
    owner: ast.AST,
    original_items: tuple[object, ...],
) -> ast.Pass:
    donor = next(
        (item for item in original_items if isinstance(item, ast.AST)),
        owner,
    )
    return ast.copy_location(ast.Pass(), donor)


def _find_unresolved_arg_identifiers(
    tree: ast.AST,
    *,
    resolved_names: frozenset[str] = frozenset(),
) -> list[tuple[str, tuple[int, ...]]]:
    """Return unresolved `__astichi_arg__` slots grouped by stripped name.

    Issue 005 §5 step 1 / §7: every occurrence of a suffixed arg name
    that reaches the materialize gate without being resolved (wiring,
    builder `arg_names=`, or `.bind_identifier(...)`) is a hard error.
    Per §1 the scan covers every binding position that can carry the
    suffix: `ast.ClassDef` / `ast.FunctionDef` / `ast.AsyncFunctionDef`
    names (5a) plus `ast.Name` Load/Store/Del and `ast.arg` parameter
    positions (5b). `ast.Attribute` is intentionally omitted until a
    concrete consumer appears. 5c: slots whose stripped name is in
    `resolved_names` (supplied via `arg_bindings`) are skipped.
    """
    by_name: dict[str, list[int]] = {}

    def _check(name: str, lineno: int) -> None:
        base, marker = strip_identifier_suffix(name)
        if marker is not ARG_IDENTIFIER:
            return
        if base in resolved_names:
            return
        by_name.setdefault(base, []).append(lineno)

    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _check(node.name, lineno)
        elif isinstance(node, ast.Name):
            _check(node.id, lineno)
        elif isinstance(node, ast.arg):
            _check(node.arg, lineno)
        elif isinstance(node, ast.keyword) and node.arg is not None:
            # Issue 005 §1 extension: call-site keyword-argument names
            # are identifier positions. `keyword.arg is None` is the
            # `**mapping` splat and carries no identifier.
            _check(node.arg, lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                for segment in node.module.split("."):
                    _check(segment, lineno)
            for alias in node.names:
                _check(alias.name, lineno)
                if alias.asname is not None:
                    _check(alias.asname, lineno)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                _check(alias.name, lineno)
                if alias.asname is not None:
                    _check(alias.asname, lineno)
    return [
        (name, tuple(sorted(set(lines))))
        for name, lines in sorted(by_name.items())
    ]


def _is_identifier_boundary_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name):
        return False
    return node.func.id in {IMPORT.source_name, PASS.source_name}


def _collect_explicitly_bound_boundary_targets(
    tree: ast.AST,
) -> frozenset[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not _is_identifier_boundary_call(node):
            continue
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
            continue
        if boundary_explicit_bind_enabled(node):
            names.add(node.args[0].id)
    return frozenset(names)


def _iter_astichi_scopes(
    tree: ast.Module,
) -> list[ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]:
    scopes: list[ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = [tree]

    def _walk_body(body: list[ast.stmt]) -> None:
        for statement in body:
            if not isinstance(
                statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            if not is_astichi_insert_shell(statement):
                continue
            scopes.append(statement)
            _walk_body(statement.body)

    _walk_body(tree.body)
    return scopes


def _is_root_equivalent_scope(
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> bool:
    if isinstance(scope, ast.Module):
        return True
    info = extract_block_insert_shell(scope, phase="materialize")
    if info is None:
        return False
    return info.target_name.startswith(_ROOT_SCOPE_HOLE_PREFIX)


def _scope_runtime_suppliers(
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> frozenset[str]:
    names: set[str] = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for argument in (
            list(scope.args.posonlyargs)
            + list(scope.args.args)
            + list(scope.args.kwonlyargs)
        ):
            names.add(argument.arg)
        if scope.args.vararg is not None:
            names.add(scope.args.vararg.arg)
        if scope.args.kwarg is not None:
            names.add(scope.args.kwarg.arg)

    class _Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if is_astichi_insert_shell(node):
                return
            names.add(node.name)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if is_astichi_insert_shell(node):
                return
            names.add(node.name)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if is_astichi_insert_shell(node):
                return
            names.add(node.name)
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                names.add(node.id)

        def visit_Import(self, node: ast.Import) -> None:
            names.update(import_statement_binding_names(node, include_star=True))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            names.update(import_statement_binding_names(node, include_star=True))

    collector = _Collector()
    for statement in scope.body:
        collector.visit(statement)
    return frozenset(names)


def _scope_boundary_calls(
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> tuple[ast.Call, ...]:
    calls: list[ast.Call] = []

    class _Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if is_astichi_insert_shell(node):
                return
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if is_astichi_insert_shell(node):
                return
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if is_astichi_insert_shell(node):
                return
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            if _is_identifier_boundary_call(node):
                calls.append(node)
            self.generic_visit(node)

    collector = _Collector()
    for statement in scope.body:
        collector.visit(statement)
    return tuple(calls)


def _find_unresolved_boundary_demands(
    tree: ast.Module,
) -> list[tuple[str, str, int]]:
    unresolved: list[tuple[str, str, int]] = []
    for scope in _iter_astichi_scopes(tree):
        if _is_root_equivalent_scope(scope):
            continue
        local_suppliers = _scope_runtime_suppliers(scope)
        for node in _scope_boundary_calls(scope):
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
                continue
            if boundary_outer_bind_enabled(node) or boundary_explicit_bind_enabled(node):
                continue
            if node.args[0].id in local_suppliers:
                continue
            unresolved.append(
                (
                    node.func.id,
                    node.args[0].id,
                    getattr(node, "lineno", 0) or 0,
                )
            )
    unresolved.sort()
    return unresolved


def _strip_keep_identifier_suffix(tree: ast.AST) -> None:
    """Strip `__astichi_keep__` from every identifier carrying it.

    Issue 005 §4 / §5 step 4: after hygiene + residual-marker stripping,
    every class/def name and matching `ast.Name` Load/Store/Del
    reference plus `ast.arg` parameter position bearing the keep suffix
    is rewritten to the stripped base. The stripped name was added to
    `preserved_names` before hygiene (see `analyze_names`), so any
    competing `foo` has already been renamed and the rewrite cannot
    introduce a collision.
    """
    _KeepIdentifierSuffixStripper().visit(tree)


def _resolve_arg_identifiers(
    tree: ast.AST, bindings: dict[str, str]
) -> None:
    """Substitute `__astichi_arg__` occurrences with their resolved names.

    Issue 005 §5 step 2 / 5c: for every class/def name, `ast.Name`, and
    `ast.arg` whose stripped name appears in `bindings`, rewrite the
    node identifier to the target. Substitution is atomic across all
    occurrences of a given stripped name because the map is consulted
    per-node during a single walk. The gate has already rejected any
    unresolved arg slot, so this pass only runs for names the user
    explicitly supplied.
    """
    _ArgIdentifierResolver(bindings).visit(tree)


class _ArgIdentifierResolver(ast.NodeTransformer):
    def __init__(self, bindings: dict[str, str]) -> None:
        self._bindings = bindings

    def _resolve(self, name: str) -> str:
        base, marker = strip_identifier_suffix(name)
        if marker is not ARG_IDENTIFIER:
            return name
        return self._bindings.get(base, name)

    def _resolve_dotted(self, name: str) -> str:
        return ".".join(self._resolve(segment) for segment in name.split("."))

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

    def visit_Import(self, node: ast.Import) -> ast.AST:
        for alias in node.names:
            alias.name = self._resolve_dotted(alias.name)
            if alias.asname is not None:
                alias.asname = self._resolve(alias.asname)
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        if node.module is not None:
            node.module = self._resolve_dotted(node.module)
        for alias in node.names:
            alias.name = self._resolve(alias.name)
            if alias.asname is not None:
                alias.asname = self._resolve(alias.asname)
        return node

    def visit_keyword(self, node: ast.keyword) -> ast.AST:
        # Issue 005 §1 extension: rewrite suffixed call-keyword names.
        # `keyword.arg is None` is the `**mapping` splat and has no
        # identifier to resolve.
        if node.arg is not None:
            node.arg = self._resolve(node.arg)
        return self.generic_visit(node)


def _resolve_boundary_imports(
    tree: ast.AST, bindings: dict[str, str]
) -> None:
    """Rename ``astichi_import``-declared names per explicit user bindings.

    Issue 006 6c: when the user supplies ``arg_names={"x": "y"}`` for a
    piece that declares ``astichi_import(x)`` inside a fresh Astichi
    scope (``@astichi_insert``-decorated shell body), the inner scope's
    references to `x` must thread to outer `y` instead of outer `x`.
    This pass rewrites, within each shell body:

    - every ``astichi_import(x)`` declaration's name argument from `x`
      to `y` (so the post-rewrite hygiene-scope collector sees `y`);
    - every ``ast.Name`` (any context) and ``ast.arg`` whose identifier
      is `x` — up to nested fresh-scope boundaries, where inner shells
      that re-declare ``astichi_import(x)`` take over.

    Identity bindings (`"x" -> "x"`) still stamp the boundary site as
    explicitly wired so the state survives `emit()` -> `compile()`.
    """
    if not bindings:
        return
    scope_bodies: list[list[ast.stmt]] = [tree.body] if isinstance(tree, ast.Module) else []
    scope_bodies.extend(shell_node.body for shell_node in _find_astichi_shell_nodes(tree))
    for scope_body in scope_bodies:
        declared_imports = _declared_imports_at_scope_top(scope_body)
        local_map = {
            name: bindings[name]
            for name in declared_imports
            if name in bindings
        }
        if not local_map:
            continue
        for statement in scope_body:
            info = boundary_import_statement(statement)
            if info is not None and info[0] in local_map:
                _rewrite_boundary_import_name(statement, local_map[info[0]])
                continue
            _BoundaryImportRenamer(local_map).visit(statement)
    for expr_insert in _find_expression_insert_payload_nodes(tree):
        payload_call = expr_insert.args[1]
        assert isinstance(payload_call, ast.Call)
        declared_imports = {
            directive.args[0].id
            for directive in direct_funcargs_directive_calls(payload_call)
            if call_name(directive) == IMPORT.source_name
            and directive.args
            and isinstance(directive.args[0], ast.Name)
        }
        local_map = {
            name: bindings[name]
            for name in declared_imports
            if name in bindings
        }
        if not local_map:
            continue
        _BoundaryImportRenamer(local_map).visit(payload_call)


def _resolve_boundary_passes(
    tree: ast.AST, bindings: dict[str, str]
) -> None:
    """Rename ``astichi_pass(name)`` arguments per explicit user bindings.

    ``astichi_pass`` is the value-form cross-scope surface. When the user
    binds ``name -> outer_name`` through ``arg_names=`` / ``bind_identifier`` /
    ``builder.assign``, the marker argument must be rewritten before
    residual stripping so ``astichi_pass(name)`` later lowers to the bound
    outer identifier.
    """
    if not bindings:
        return
    _BoundaryPassRenamer(bindings).visit(tree)


def _find_astichi_shell_nodes(
    tree: ast.AST,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]:
    shells: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = []
    for node in ast.walk(tree):
        if is_astichi_insert_shell(node):
            assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            shells.append(node)
    return shells


def _find_expression_insert_payload_nodes(tree: ast.AST) -> list[ast.Call]:
    nodes: list[ast.Call] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and _is_expression_insert_call(node)
            and is_astichi_funcargs_call(node.args[1])
        ):
            nodes.append(node)
    return nodes


def _declared_imports_at_scope_top(body: list[ast.stmt]) -> frozenset[str]:
    names: set[str] = set()
    for statement in body:
        info = boundary_import_statement(statement)
        if info is None:
            break
        names.add(info[0])
    return frozenset(names)
def _rewrite_boundary_import_name(stmt: ast.stmt, new_name: str) -> None:
    info = boundary_import_statement(stmt)
    assert info is not None, "caller must pre-check the statement"
    _, call = info
    target = call.args[0]
    assert isinstance(target, ast.Name)
    target.id = new_name
    set_boundary_explicit_bind_state(call)


class _BoundaryImportRenamer(
    _SkipInsertShellTransformerWithClassMixin, ast.NodeTransformer
):
    """Rewrite ``ast.Name`` / ``ast.arg`` occurrences under one shell body.

    Stops at nested ``@astichi_insert``-decorated shell boundaries: a
    nested shell that does NOT re-declare ``astichi_import(x)`` inherits
    the outer rewrite; a nested shell that DOES re-declare it is
    processed by its own outer-level pass call, so this walker
    short-circuits at nested shell roots to avoid double-rewriting.
    """

    def __init__(self, rename_map: dict[str, str]) -> None:
        self._rename_map = rename_map

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if not is_call_to_marker(node, IMPORT):
            return node
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
            return node
        replacement = self._rename_map.get(node.args[0].id)
        if replacement is None:
            return node
        node.args[0].id = replacement
        set_boundary_explicit_bind_state(node)
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        replacement = self._rename_map.get(node.id)
        if replacement is not None:
            node.id = replacement
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        replacement = self._rename_map.get(node.arg)
        if replacement is not None:
            node.arg = replacement
        return self.generic_visit(node)


class _BoundaryPassRenamer(ast.NodeTransformer):
    def __init__(self, rename_map: dict[str, str]) -> None:
        self._rename_map = rename_map

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if not is_call_to_marker(node, PASS):
            return node
        if len(node.args) != 1:
            return node
        target = node.args[0]
        if not isinstance(target, ast.Name):
            return node
        replacement = self._rename_map.get(target.id)
        if replacement is None:
            return node
        target.id = replacement
        set_boundary_explicit_bind_state(node)
        return node
def _assert_no_arg_suffix_remains(tree: ast.AST) -> None:
    """Sanity check that the arg-resolver + gate cover every occurrence.

    Issue 005 §5 step 2: after the gate has rejected unresolved slots
    and the resolver has substituted bound ones, no `__astichi_arg__`
    suffix can survive to the final emit. A residual suffix indicates
    a gap between gate and resolver coverage (a bug).
    """
    for node in ast.walk(tree):
        name: str | None = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.arg):
            name = node.arg
        elif isinstance(node, ast.keyword):
            # Issue 005 §1 extension: `keyword.arg is None` is the
            # `**mapping` splat and carries no identifier.
            name = node.arg
        if name is None:
            continue
        _, marker = strip_identifier_suffix(name)
        if marker is ARG_IDENTIFIER:
            raise AssertionError(
                f"internal error: __astichi_arg__ suffix survived materialize "
                f"(name={name!r}, node={type(node).__name__}); arg gate and "
                f"resolver coverage are out of sync"
            )


class _KeepIdentifierSuffixStripper(ast.NodeTransformer):
    def _strip(self, name: str) -> str:
        base, marker = strip_identifier_suffix(name)
        return base if marker is KEEP_IDENTIFIER else name

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        node.name = self._strip(node.name)
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        node.name = self._strip(node.name)
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        node.name = self._strip(node.name)
        return self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        node.id = self._strip(node.id)
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.arg = self._strip(node.arg)
        return self.generic_visit(node)


def _flatten_body_splices(body: list[ast.stmt]) -> list[ast.stmt]:
    """Splice sibling `astichi_insert` shells into their matching hole positions."""
    shells_by_target: dict[str, list[tuple[int, int, ast.FunctionDef]]] = {}
    for index, stmt in enumerate(body):
        info = extract_block_insert_shell(stmt, phase="materialize")
        if info is None:
            continue
        target = info.target_name
        order = info.order
        assert isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        if isinstance(stmt, ast.FunctionDef):
            shells_by_target.setdefault(target, []).append((order, index, stmt))

    if not shells_by_target:
        return body

    consumed_shell_ids: set[int] = set()
    result: list[ast.stmt] = []
    for stmt in body:
        hole_name = _extract_hole_name(stmt)
        if hole_name is not None and hole_name in shells_by_target:
            ordered = sorted(
                shells_by_target[hole_name],
                key=lambda item: (item[0], item[1]),
            )
            for _order, _index, shell in ordered:
                result.extend(shell.body)
                consumed_shell_ids.add(id(shell))
            continue
        if id(stmt) in consumed_shell_ids:
            continue
        result.append(stmt)
    return result
