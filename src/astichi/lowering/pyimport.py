"""Validation helpers for managed ``astichi_pyimport(...)`` declarations."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass

from astichi.asttools import AstichiScope, AstichiScopeMap
from astichi.diagnostics import format_astichi_error
from astichi.lowering.external_ref import (
    evaluate_restricted_path_expression,
    extract_dotted_reference_chain,
)
from astichi.lowering.markers import (
    BIND_EXTERNAL,
    COMMENT,
    EXPORT,
    IMPORT,
    KEEP,
    PYIMPORT,
    RecognizedMarker,
    scan_statement_prefix,
)


@dataclass(frozen=True)
class PyImportDeclaration:
    """Parsed managed import declaration.

    Phase 1 uses this as a validation model only. Later phases can extend or
    replace it with post-hygiene binding records without changing marker
    recognition.
    """

    marker: RecognizedMarker
    module_path: tuple[str, ...] | None
    names: tuple[ast.Name, ...]
    as_name: ast.Name | None

    @property
    def is_from_import(self) -> bool:
        return bool(self.names)

    @property
    def is_plain_import(self) -> bool:
        return not self.names


@dataclass(frozen=True)
class PyImportLocalBinding:
    """Marker-owned local binding node declared by pyimport."""

    marker: RecognizedMarker
    node: ast.Name


_PYIMPORT_PREFIX_SPECS = frozenset(
    {
        BIND_EXTERNAL,
        IMPORT,
        KEEP,
        EXPORT,
        PYIMPORT,
        COMMENT,
    }
)


def validate_pyimport_declarations(
    tree: ast.Module,
    markers: tuple[RecognizedMarker, ...],
) -> tuple[PyImportDeclaration, ...]:
    """Validate all ``astichi_pyimport(...)`` markers in ``tree``."""
    declarations: list[PyImportDeclaration] = []
    errors: list[str] = []
    scope_map = AstichiScopeMap.from_tree(tree)
    pyimport_markers = [
        marker for marker in markers if marker.spec is PYIMPORT
    ]
    if not pyimport_markers:
        return ()
    carrier_call_ids = _expression_insert_carrier_pyimport_call_ids(tree)
    for marker in pyimport_markers:
        declaration = _parse_declaration(marker, errors)
        _validate_marker_placement(
            tree,
            scope_map,
            marker,
            errors,
            carrier_call_ids=carrier_call_ids,
        )
        if declaration is not None:
            declarations.append(declaration)
    if errors:
        raise ValueError(
            format_astichi_error(
                "compile",
                "invalid astichi_pyimport declarations",
                context="; ".join(errors),
            )
        )
    return tuple(declarations)


def pyimport_local_bindings(
    markers: tuple[object, ...],
) -> tuple[PyImportLocalBinding, ...]:
    """Return marker-owned local binding nodes from validated pyimports."""
    bindings: list[PyImportLocalBinding] = []
    for marker in markers:
        if not isinstance(marker, RecognizedMarker):
            continue
        if marker.spec is not PYIMPORT:
            continue
        node = marker.node
        if not isinstance(node, ast.Call):
            continue
        names_expr = _keyword_value(node, "names")
        if isinstance(names_expr, ast.Tuple):
            bindings.extend(
                PyImportLocalBinding(marker=marker, node=element)
                for element in names_expr.elts
                if isinstance(element, ast.Name)
            )
            continue
        as_expr = _keyword_value(node, "as_")
        if isinstance(as_expr, ast.Name):
            bindings.append(PyImportLocalBinding(marker=marker, node=as_expr))
            continue
        module_expr = _keyword_value(node, "module")
        if isinstance(module_expr, ast.Name):
            bindings.append(PyImportLocalBinding(marker=marker, node=module_expr))
    return tuple(bindings)


def _parse_declaration(
    marker: RecognizedMarker,
    errors: list[str],
) -> PyImportDeclaration | None:
    node = marker.node
    if not isinstance(node, ast.Call):
        return None
    module_expr = _keyword_value(node, "module")
    assert module_expr is not None, "marker validation requires module="
    names_expr = _keyword_value(node, "names")
    as_expr = _keyword_value(node, "as_")
    module_path = _known_module_path(module_expr, errors)
    names = _parse_names(names_expr, errors) if names_expr is not None else ()
    as_name = _parse_as_name(as_expr, errors) if as_expr is not None else None
    if names:
        if module_path == ("__future__",):
            errors.append("managed `from __future__ import ...` is not supported")
    else:
        if as_name is None and module_path is not None and len(module_path) > 1:
            errors.append("dotted plain imports require as_= in v1")
        if module_path == ("__future__",):
            errors.append("managed `import __future__` is not supported")
    if names_expr is None and as_expr is None and module_path is None:
        errors.append(
            "plain imports with dynamic module paths require as_= in v1"
        )
    return PyImportDeclaration(
        marker=marker,
        module_path=module_path,
        names=names,
        as_name=as_name,
    )


def _keyword_value(node: ast.Call, name: str) -> ast.expr | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _known_module_path(
    node: ast.expr,
    errors: list[str],
) -> tuple[str, ...] | None:
    if _is_astichi_ref_call(node):
        if len(node.args) != 1 or node.keywords:
            return None
        if _is_dynamic_ref_argument(node.args[0]):
            return None
        try:
            return evaluate_restricted_path_expression(node.args[0])
        except ValueError as exc:
            errors.append(
                "module= astichi_ref(...) did not reduce to a valid path: "
                f"{exc}"
            )
            return None
    try:
        return extract_dotted_reference_chain(node)
    except ValueError:
        errors.append(
            "module= must be an absolute dotted reference or astichi_ref(...)"
        )
        return None


def _is_astichi_ref_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "astichi_ref"
    )


def _is_dynamic_ref_argument(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "astichi_bind_external"
    )


def _parse_names(
    node: ast.expr,
    errors: list[str],
) -> tuple[ast.Name, ...]:
    if isinstance(node, ast.Dict):
        errors.append("alias dict names= forms are deferred in v1")
        return ()
    if not isinstance(node, ast.Tuple):
        errors.append("names= must be a non-empty tuple of bare identifiers")
        return ()
    if not node.elts:
        errors.append("names= must not be empty")
        return ()
    names: list[ast.Name] = []
    seen: set[str] = set()
    for element in node.elts:
        if not isinstance(element, ast.Name):
            errors.append(
                "names= elements must be bare identifiers; "
                f"got {type(element).__name__}"
            )
            continue
        if element.id in seen:
            errors.append(f"duplicate pyimport name `{element.id}`")
            continue
        seen.add(element.id)
        names.append(element)
    return tuple(names)


def _parse_as_name(
    node: ast.expr,
    errors: list[str],
) -> ast.Name | None:
    if not isinstance(node, ast.Name):
        errors.append("as_= must be a bare identifier")
        return None
    return node


def _validate_marker_placement(
    tree: ast.Module,
    scope_map: AstichiScopeMap,
    marker: RecognizedMarker,
    errors: list[str],
    *,
    carrier_call_ids: frozenset[int],
) -> None:
    if not isinstance(marker.node, ast.Call):
        return
    if id(marker.node) in carrier_call_ids:
        return
    lineno = getattr(marker.node, "lineno", 0) or 0
    nested_root = scope_map.nested_python_root_for(marker.node)
    if nested_root is not None:
        errors.append(
            f"astichi_pyimport(...) at line {lineno} is nested inside a real "
            "user-authored function/class body"
        )
        return
    scope = scope_map.scope_for(marker.node)
    body = _scope_prefix_body(tree, scope)
    if body is None:
        errors.append(
            f"astichi_pyimport(...) at line {lineno} is not valid in expression "
            "insert payloads in v1"
        )
        return
    prefix = scan_statement_prefix(body, allowed_specs=_PYIMPORT_PREFIX_SPECS)
    prefix_call_ids = {id(statement.value) for statement in prefix.prefix_statements}
    if id(marker.node) not in prefix_call_ids:
        errors.append(
            f"astichi_pyimport(...) at line {lineno} must appear in the "
            "contiguous top-of-Astichi-scope prefix"
        )


def _expression_insert_carrier_pyimport_call_ids(tree: ast.AST) -> frozenset[int]:
    call_ids: set[int] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "astichi_insert"
            and len(node.args) == 2
        ):
            continue
        for keyword in node.keywords:
            if keyword.arg != "pyimport":
                continue
            value = keyword.value
            if not isinstance(value, ast.Tuple):
                continue
            for element in value.elts:
                if (
                    isinstance(element, ast.Call)
                    and isinstance(element.func, ast.Name)
                    and element.func.id == PYIMPORT.source_name
                ):
                    call_ids.add(id(element))
    return frozenset(call_ids)


def _scope_prefix_body(
    tree: ast.Module, scope: AstichiScope
) -> Sequence[ast.stmt] | None:
    if scope.root is tree:
        index = 0
        index = _skip_comment_markers(tree.body, index)
        if index < len(tree.body) and _is_module_docstring(tree.body[index]):
            index += 1
        while True:
            index = _skip_comment_markers(tree.body, index)
            if index >= len(tree.body) or not _is_future_import(tree.body[index]):
                break
            index += 1
        return tree.body[index:]
    root = scope.root
    if isinstance(root, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return root.body
    return None


def _is_module_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _is_future_import(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.ImportFrom)
        and statement.module == "__future__"
        and statement.level == 0
    )


def _skip_comment_markers(body: Sequence[ast.stmt], index: int) -> int:
    while index < len(body) and _is_comment_marker_statement(body[index]):
        index += 1
    return index


def _is_comment_marker_statement(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == COMMENT.source_name
    )
