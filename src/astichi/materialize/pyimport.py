"""Materialize-time synthesis for managed ``astichi_pyimport(...)``."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from astichi.ast_provenance import propagate_ast_source_locations
from astichi.lowering import RecognizedMarker
from astichi.lowering.external_ref import extract_dotted_reference_chain
from astichi.lowering.markers import COMMENT, PYIMPORT


@dataclass(frozen=True)
class ManagedImportRecord:
    """One managed import binding after module path resolution."""

    marker: RecognizedMarker
    module_path: tuple[str, ...]
    local_node: ast.Name
    original_symbol: str | None = None

    @property
    def final_local_name(self) -> str:
        return self.local_node.id

    @property
    def is_from_import(self) -> bool:
        return self.original_symbol is not None


def collect_managed_imports(
    markers: tuple[RecognizedMarker, ...],
) -> tuple[ManagedImportRecord, ...]:
    """Collect pyimport records after external-ref lowering, before hygiene."""
    records: list[ManagedImportRecord] = []
    for marker in markers:
        if marker.spec is not PYIMPORT:
            continue
        node = marker.node
        if not isinstance(node, ast.Call):
            continue
        module_expr = _keyword_value(node, "module")
        if module_expr is None:
            continue
        module_path = extract_dotted_reference_chain(module_expr)
        names_expr = _keyword_value(node, "names")
        if isinstance(names_expr, ast.Tuple):
            for element in names_expr.elts:
                if isinstance(element, ast.Name):
                    records.append(
                        ManagedImportRecord(
                            marker=marker,
                            module_path=module_path,
                            local_node=element,
                            original_symbol=element.id,
                        )
                    )
            continue
        as_expr = _keyword_value(node, "as_")
        if isinstance(as_expr, ast.Name):
            records.append(
                ManagedImportRecord(
                    marker=marker,
                    module_path=module_path,
                    local_node=as_expr,
                )
            )
            continue
        if isinstance(module_expr, ast.Name):
            records.append(
                ManagedImportRecord(
                    marker=marker,
                    module_path=module_path,
                    local_node=module_expr,
                )
            )
    return tuple(records)


def insert_managed_imports(
    tree: ast.Module,
    records: tuple[ManagedImportRecord, ...],
) -> None:
    """Insert synthesized managed imports into ``tree.body``."""
    if not records:
        return
    imports = _synthesize_import_statements(records)
    if not imports:
        return
    index = _managed_import_insertion_index(tree.body)
    tree.body[index:index] = imports
    ast.fix_missing_locations(tree)


def has_pyimport_marker(markers: tuple[RecognizedMarker, ...]) -> bool:
    return any(marker.spec is PYIMPORT for marker in markers)


def _synthesize_import_statements(
    records: tuple[ManagedImportRecord, ...],
) -> list[ast.stmt]:
    plain_seen: set[tuple[tuple[str, ...], str]] = set()
    plain_records: list[ManagedImportRecord] = []
    from_seen: set[tuple[tuple[str, ...], str, str]] = set()
    from_records_by_module: dict[tuple[str, ...], list[ManagedImportRecord]] = {}
    for record in records:
        if record.is_from_import:
            assert record.original_symbol is not None
            key = (record.module_path, record.original_symbol, record.final_local_name)
            if key in from_seen:
                continue
            from_seen.add(key)
            from_records_by_module.setdefault(record.module_path, []).append(record)
            continue
        key = (record.module_path, record.final_local_name)
        if key in plain_seen:
            continue
        plain_seen.add(key)
        plain_records.append(record)

    statements: list[ast.stmt] = []
    for record in sorted(
        plain_records,
        key=lambda item: (".".join(item.module_path), item.final_local_name),
    ):
        module_name = ".".join(record.module_path)
        first_segment = record.module_path[0]
        asname = (
            None if record.final_local_name == first_segment else record.final_local_name
        )
        statement = ast.Import(
            names=[ast.alias(name=module_name, asname=asname)]
        )
        _copy_import_location(statement, record)
        statements.append(statement)

    for module_path in sorted(from_records_by_module):
        module_records = sorted(
            from_records_by_module[module_path],
            key=lambda item: (
                item.original_symbol or "",
                item.final_local_name,
            ),
        )
        aliases: list[ast.alias] = []
        for record in module_records:
            assert record.original_symbol is not None
            asname = (
                None
                if record.final_local_name == record.original_symbol
                else record.final_local_name
            )
            aliases.append(ast.alias(name=record.original_symbol, asname=asname))
        statement = ast.ImportFrom(
            module=".".join(module_path),
            names=aliases,
            level=0,
        )
        _copy_import_location(statement, module_records[0])
        statements.append(statement)
    return statements


def _copy_import_location(statement: ast.stmt, record: ManagedImportRecord) -> None:
    propagate_ast_source_locations(statement, record.marker.node)


def _managed_import_insertion_index(body: list[ast.stmt]) -> int:
    index = 0
    index = _skip_comment_markers(body, index)
    if index < len(body) and _is_module_docstring(body[index]):
        index += 1
    while True:
        index = _skip_comment_markers(body, index)
        if index >= len(body) or not _is_future_import(body[index]):
            break
        index += 1
    return index


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


def _skip_comment_markers(body: list[ast.stmt], index: int) -> int:
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


def _keyword_value(node: ast.Call, name: str) -> ast.expr | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None
