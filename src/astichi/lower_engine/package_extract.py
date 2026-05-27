"""Python extraction helpers for lower template package rows."""

from __future__ import annotations

import ast
from collections.abc import Iterable

from astichi.asttools import import_statement_binding_names
from astichi.lowering.external_ref import evaluate_restricted_path_expression
from astichi.lowering import RecognizedMarker, recognize_markers
from astichi.lowering.markers import (
    boundary_explicit_bind_enabled,
    boundary_outer_bind_enabled,
)
from astichi.lowering.pyimport import validate_pyimport_declarations
from astichi.lowering.sentinel_attrs import match_transparent_sentinel
from astichi.lower_engine.templates import (
    TemplateCommentMarkerSpec,
    TemplateMarkerSpec,
    TemplatePyImportMarkerSpec,
    TemplateRefMarkerSpec,
    TemplateScopeSpec,
    TemplateUnrollMarkerSpec,
)


def extract_scope_specs(
    tree: ast.Module,
    *,
    module_start_line: int | None = None,
) -> tuple[TemplateScopeSpec, ...]:
    """Extract deterministic lexical scope specs from a Python module AST."""
    scopes: list[TemplateScopeSpec] = []

    def append_scope(
        *,
        node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        scope_kind: str,
        ast_path: str,
        owner_path: tuple[str, ...],
        parent_scope_id: int | None,
    ) -> int:
        arguments = _argument_names(node)
        scope_id = len(scopes)
        if isinstance(node, ast.Module) and module_start_line is not None:
            start_line = module_start_line
        else:
            start_line = getattr(node, "lineno", None)
        scopes.append(
            TemplateScopeSpec(
                scope_kind=scope_kind,
                ast_path=ast_path,
                owner_path=owner_path,
                local_bindings=tuple(sorted(_scope_binding_names(node))),
                arguments=tuple(sorted(arguments)),
                parent_scope_id=parent_scope_id,
                start_line=start_line if isinstance(start_line, int) else None,
            )
        )
        return scope_id

    def visit(
        node: ast.AST,
        *,
        ast_path: str,
        owner_path: tuple[str, ...],
        parent_scope_id: int | None,
    ) -> None:
        scope_id = parent_scope_id
        child_owner_path = owner_path
        if isinstance(node, ast.Module):
            scope_id = append_scope(
                node=node,
                scope_kind="module",
                ast_path=ast_path,
                owner_path=owner_path,
                parent_scope_id=None,
            )
        elif isinstance(node, ast.AsyncFunctionDef):
            child_owner_path = (*owner_path, node.name)
            scope_id = append_scope(
                node=node,
                scope_kind="async_function",
                ast_path=ast_path,
                owner_path=child_owner_path,
                parent_scope_id=parent_scope_id,
            )
        elif isinstance(node, ast.FunctionDef):
            child_owner_path = (*owner_path, node.name)
            scope_id = append_scope(
                node=node,
                scope_kind="function",
                ast_path=ast_path,
                owner_path=child_owner_path,
                parent_scope_id=parent_scope_id,
            )
        elif isinstance(node, ast.ClassDef):
            child_owner_path = (*owner_path, node.name)
            scope_id = append_scope(
                node=node,
                scope_kind="class",
                ast_path=ast_path,
                owner_path=child_owner_path,
                parent_scope_id=parent_scope_id,
            )

        for field_name, value in ast.iter_fields(node):
            for child_path, child in _iter_ast_children(
                field_name=field_name,
                value=value,
                parent_path=ast_path,
            ):
                visit(
                    child,
                    ast_path=child_path,
                    owner_path=child_owner_path,
                    parent_scope_id=scope_id,
                )

    visit(
        tree,
        ast_path="",
        owner_path=(),
        parent_scope_id=None,
    )
    return tuple(scopes)


def extract_marker_specs(
    tree: ast.Module,
    scope_specs: tuple[TemplateScopeSpec, ...],
) -> tuple[TemplateMarkerSpec, ...]:
    """Extract source-ordered generic marker specs from a Python module AST."""
    ast_paths, statement_paths = _build_ast_path_maps(tree)
    marker_specs: list[TemplateMarkerSpec] = []
    for source_order, marker in enumerate(recognize_markers(tree)):
        ast_path = ast_paths.get(id(marker.node), "")
        statement_path = statement_paths.get(id(marker.node))
        scope_id = _scope_id_for_ast_path(scope_specs, ast_path)
        scope = scope_specs[scope_id]
        marker_specs.append(
            TemplateMarkerSpec(
                marker_kind=_marker_kind(marker),
                source_name=marker.source_name,
                ast_path=ast_path,
                statement_path=statement_path,
                owner_path=scope.owner_path,
                scope_id=scope_id,
                source_order=source_order,
                resource_name=marker.name_id or "",
                operation_key=marker.source_name,
                flags=_marker_flags(marker, ast_path, statement_path),
            )
        )
    return tuple(marker_specs)


def extract_pyimport_marker_specs(
    tree: ast.Module,
) -> tuple[TemplatePyImportMarkerSpec, ...]:
    """Extract typed source facts for ``astichi_pyimport`` markers."""
    markers = recognize_markers(tree)
    marker_ids_by_node_id = {
        id(marker.node): marker_id for marker_id, marker in enumerate(markers)
    }
    specs: list[TemplatePyImportMarkerSpec] = []
    for declaration in validate_pyimport_declarations(tree, markers):
        marker_id = marker_ids_by_node_id[id(declaration.marker.node)]
        flags: list[str] = []
        if declaration.is_from_import:
            flags.append("from_import")
        if declaration.is_plain_import:
            flags.append("plain_import")
        if declaration.module_path is None:
            flags.append("dynamic_module")
        specs.append(
            TemplatePyImportMarkerSpec(
                marker_id=marker_id,
                module_path=declaration.module_path,
                names=tuple(name.id for name in declaration.names),
                as_name=(
                    "" if declaration.as_name is None else declaration.as_name.id
                ),
                flags=tuple(flags),
            )
        )
    return tuple(specs)


def extract_comment_marker_specs(
    tree: ast.Module,
) -> tuple[TemplateCommentMarkerSpec, ...]:
    """Extract typed source facts for ``astichi_comment`` markers."""
    specs: list[TemplateCommentMarkerSpec] = []
    for marker_id, marker in enumerate(recognize_markers(tree)):
        if marker.source_name != "astichi_comment":
            continue
        node = marker.node
        if not isinstance(node, ast.Call):
            continue
        payload = node.args[0]
        if not isinstance(payload, ast.Constant) or not isinstance(payload.value, str):
            continue
        specs.append(
            TemplateCommentMarkerSpec(
                marker_id=marker_id,
                payload=payload.value,
                flags=(
                    "strip_for_executable",
                    "preserve_for_commented_source",
                ),
            )
        )
    return tuple(specs)


def extract_ref_marker_specs(
    tree: ast.Module,
) -> tuple[TemplateRefMarkerSpec, ...]:
    """Extract typed source facts for ``astichi_ref`` markers."""
    sentinel_contexts = _ref_sentinel_contexts(tree)
    bare_statement_call_ids = _bare_ref_statement_call_ids(tree)
    specs: list[TemplateRefMarkerSpec] = []
    for marker_id, marker in enumerate(recognize_markers(tree)):
        if marker.source_name != "astichi_ref":
            continue
        if id(marker.node) in bare_statement_call_ids:
            raise ValueError("unsupported astichi_ref statement context")
        sentinel_context = sentinel_contexts.get(id(marker.node))
        if sentinel_context is None:
            specs.append(
                TemplateRefMarkerSpec(
                    marker_id=marker_id,
                    ref_kind="value",
                    context="load",
                    literal_path=_literal_ref_path(marker),
                    flags=("value_form",),
                )
            )
            continue
        sentinel_attr, context = sentinel_context
        specs.append(
            TemplateRefMarkerSpec(
                marker_id=marker_id,
                ref_kind="sentinel_attribute",
                context=context,
                sentinel_attr=sentinel_attr,
                literal_path=_literal_ref_path(marker),
                flags=("sentinel_attribute",),
            )
        )
    return tuple(specs)


def extract_unroll_marker_specs(
    tree: ast.Module,
) -> tuple[TemplateUnrollMarkerSpec, ...]:
    """Extract typed source facts for statement-context ``astichi_for`` markers."""
    ast_paths, _statement_paths = _build_ast_path_maps(tree)
    parent_map = _build_parent_map(tree)
    specs: list[TemplateUnrollMarkerSpec] = []
    for marker_id, marker in enumerate(recognize_markers(tree)):
        if marker.source_name != "astichi_for" or not isinstance(marker.node, ast.Call):
            continue
        node = _parent_for_iter(parent_map, marker.node)
        if node is None:
            continue
        statement_path = ast_paths.get(id(node), "")
        domain = node.iter.args[0] if len(node.iter.args) == 1 else None
        flags = _unroll_marker_flags(node, domain)
        specs.append(
            TemplateUnrollMarkerSpec(
                marker_id=marker_id,
                statement_path=statement_path,
                target_ast_path=ast_paths.get(id(node.target), ""),
                iter_ast_path=ast_paths.get(id(node.iter), ""),
                domain_ast_path=(
                    "" if domain is None else ast_paths.get(id(domain), "")
                ),
                body_path=_join_ast_path(statement_path, "body"),
                orelse_path=(
                    None
                    if not node.orelse
                    else _join_ast_path(statement_path, "orelse")
                ),
                target_bindings=tuple(sorted(_target_binding_names(node.target))),
                domain_shape="" if domain is None else _domain_shape(domain),
                flags=flags,
            )
        )
    return tuple(specs)


def _iter_ast_children(
    *,
    field_name: str,
    value: object,
    parent_path: str,
) -> Iterable[tuple[str, ast.AST]]:
    if isinstance(value, ast.AST):
        yield _join_ast_path(parent_path, field_name), value
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, ast.AST):
                yield _join_ast_path(parent_path, f"{field_name}[{index}]"), child


def _join_ast_path(parent_path: str, part: str) -> str:
    if parent_path == "":
        return part
    return f"{parent_path}/{part}"


def _ref_sentinel_contexts(tree: ast.AST) -> dict[int, tuple[str, str]]:
    contexts: dict[int, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        sentinel = match_transparent_sentinel(
            node,
            is_marker_call=_is_ref_marker_call,
        )
        if sentinel is None:
            continue
        contexts[id(sentinel.call)] = (node.attr, _ctx_name(sentinel.ctx))
    return contexts


def _bare_ref_statement_call_ids(tree: ast.AST) -> frozenset[int]:
    call_ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        call = _statement_ref_call(node.value)
        if call is not None:
            call_ids.add(id(call))
    return frozenset(call_ids)


def _statement_ref_call(node: ast.AST) -> ast.Call | None:
    if _is_ref_marker_call(node):
        assert isinstance(node, ast.Call)
        return node
    if isinstance(node, ast.Attribute):
        sentinel = match_transparent_sentinel(
            node,
            is_marker_call=_is_ref_marker_call,
        )
        if sentinel is not None:
            return sentinel.call
    return None


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _parent_for_iter(
    parent_map: dict[int, ast.AST],
    node: ast.Call,
) -> ast.For | None:
    parent = parent_map.get(id(node))
    if isinstance(parent, ast.For) and parent.iter is node:
        return parent
    return None


def _unroll_marker_flags(
    node: ast.For,
    domain: ast.expr | None,
) -> tuple[str, ...]:
    flags = ["statement_context", "for_statement"]
    if node.orelse:
        flags.append("has_else")
    if domain is None or node.iter.keywords:
        flags.append("invalid_signature")
    if _target_binding_names(node.target):
        flags.append("simple_target")
    else:
        flags.append("unsupported_target")
    if isinstance(domain, (ast.Tuple, ast.List)) or _is_range_domain(domain):
        flags.append("literal_domain")
    elif isinstance(domain, ast.Name):
        flags.append("external_domain_candidate")
    return tuple(flags)


def _target_binding_names(target: ast.expr) -> frozenset[str]:
    names: set[str] = set()

    def collect(node: ast.expr) -> None:
        if isinstance(node, ast.Name):
            names.add(node.id)
            return
        if isinstance(node, (ast.Tuple, ast.List)):
            for child in node.elts:
                collect(child)
            return
        if isinstance(node, ast.Starred):
            collect(node.value)

    collect(target)
    return frozenset(names)


def _domain_shape(domain: ast.expr) -> str:
    if isinstance(domain, ast.Tuple):
        return "tuple"
    if isinstance(domain, ast.List):
        return "list"
    if _is_range_domain(domain):
        return "range"
    if isinstance(domain, ast.Name):
        return "name"
    if isinstance(domain, ast.Call):
        return "call"
    return type(domain).__name__


def _is_range_domain(domain: ast.expr | None) -> bool:
    return (
        isinstance(domain, ast.Call)
        and isinstance(domain.func, ast.Name)
        and domain.func.id == "range"
    )


def _is_ref_marker_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and (
            (
                isinstance(node.func, ast.Name)
                and node.func.id == "astichi_ref"
            )
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "astichi_ref"
            )
        )
    )


def _literal_ref_path(marker: RecognizedMarker) -> tuple[str, ...] | None:
    node = marker.node
    if not isinstance(node, ast.Call) or len(node.args) != 1 or node.keywords:
        return None
    try:
        return evaluate_restricted_path_expression(node.args[0])
    except ValueError:
        return None


def _ctx_name(ctx: ast.expr_context) -> str:
    if isinstance(ctx, ast.Store):
        return "store"
    if isinstance(ctx, ast.Del):
        return "delete"
    return "load"


def _build_ast_path_maps(
    tree: ast.AST,
) -> tuple[dict[int, str], dict[int, str | None]]:
    ast_paths: dict[int, str] = {}
    statement_paths: dict[int, str | None] = {}

    def visit(
        node: ast.AST,
        *,
        ast_path: str,
        statement_path: str | None,
    ) -> None:
        resolved_statement_path = ast_path if isinstance(node, ast.stmt) else statement_path
        ast_paths[id(node)] = ast_path
        statement_paths[id(node)] = resolved_statement_path
        for field_name, value in ast.iter_fields(node):
            for child_path, child in _iter_ast_children(
                field_name=field_name,
                value=value,
                parent_path=ast_path,
            ):
                visit(
                    child,
                    ast_path=child_path,
                    statement_path=resolved_statement_path,
                )

    visit(tree, ast_path="", statement_path=None)
    return ast_paths, statement_paths


def _scope_id_for_ast_path(
    scope_specs: tuple[TemplateScopeSpec, ...],
    ast_path: str,
) -> int:
    best_scope_id = 0
    best_depth = -1
    for scope_id, scope in enumerate(scope_specs):
        if not _ast_path_is_prefix(scope.ast_path, ast_path):
            continue
        depth = _ast_path_depth(scope.ast_path)
        if depth > best_depth:
            best_scope_id = scope_id
            best_depth = depth
    return best_scope_id


def _marker_kind(marker: RecognizedMarker) -> str:
    if marker.source_name == "astichi_pyimport":
        return "pyimport"
    if marker.source_name == "astichi_comment":
        return "comment"
    if marker.source_name == "astichi_ref":
        return "ref"
    if marker.source_name == "astichi_for":
        return "unroll"
    if marker.source_name.startswith("astichi_"):
        return marker.source_name.removeprefix("astichi_")
    return marker.source_name


def _marker_flags(
    marker: RecognizedMarker,
    ast_path: str,
    statement_path: str | None,
) -> tuple[str, ...]:
    flags: list[str] = []
    if marker.context.is_call_context():
        flags.append("call_context")
    if marker.context.is_decorator_context():
        flags.append("decorator_context")
    if marker.context.is_definitional_context():
        flags.append("definitional_context")
    if marker.context.is_identifier_context():
        flags.append("identifier_context")
    if statement_path is not None and ast_path == statement_path:
        flags.append("is_statement_marker")
    if marker.spec.is_hygiene_directive():
        flags.append("is_metadata_marker")
    if isinstance(marker.node, ast.Call) and marker.source_name in {
        "astichi_import",
        "astichi_pass",
    }:
        if boundary_explicit_bind_enabled(marker.node):
            flags.append("explicit_bind_enabled")
        if boundary_outer_bind_enabled(marker.node):
            flags.append("outer_bind_enabled")
    return tuple(flags)


def _scope_binding_names(
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> frozenset[str]:
    names: set[str] = set(_argument_names(scope))

    class Collector(ast.NodeVisitor):
        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                names.add(node.id)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            names.add(node.name)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            names.add(node.name)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            names.add(node.name)

        def visit_Import(self, node: ast.Import) -> None:
            names.update(import_statement_binding_names(node, include_star=True))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            names.update(import_statement_binding_names(node, include_star=True))

    collector = Collector()
    for statement in scope.body:
        collector.visit(statement)
    return frozenset(names)


def _argument_names(
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> frozenset[str]:
    if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return frozenset()
    names = {
        argument.arg
        for argument in (
            list(scope.args.posonlyargs)
            + list(scope.args.args)
            + list(scope.args.kwonlyargs)
        )
    }
    if scope.args.vararg is not None:
        names.add(scope.args.vararg.arg)
    if scope.args.kwarg is not None:
        names.add(scope.args.kwarg.arg)
    return frozenset(names)


def _ast_path_is_prefix(scope_path: str, ast_path: str) -> bool:
    if scope_path == "":
        return True
    return ast_path == scope_path or ast_path.startswith(f"{scope_path}/")


def _ast_path_depth(ast_path: str) -> int:
    if ast_path == "":
        return 0
    return len(tuple(part for part in ast_path.split("/") if part))
