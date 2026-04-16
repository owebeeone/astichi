"""Build merge for Astichi V1."""

from __future__ import annotations

import ast
import copy

from astichi.builder.graph import BuilderGraph
from astichi.hygiene import analyze_names
from astichi.lowering import recognize_markers
from astichi.model.basic import BasicComposable
from astichi.model.origin import CompileOrigin
from astichi.model.ports import extract_demand_ports, extract_supply_ports


def build_merge(graph: BuilderGraph) -> BasicComposable:
    """Merge a builder graph into a single composable."""
    if not graph.instances:
        raise ValueError("cannot build from empty graph")

    trees: dict[str, ast.Module] = {}
    for record in graph.instances:
        if not isinstance(record.composable, BasicComposable):
            raise TypeError(
                f"instance {record.name} must be a BasicComposable"
            )
        trees[record.name] = copy.deepcopy(record.composable.tree)

    edges_by_target: dict[tuple[str, str], list[tuple[int, object]]] = {}
    for idx, edge in enumerate(graph.edges):
        key = (edge.target.root_instance, edge.target.target_name)
        edges_by_target.setdefault(key, []).append((idx, edge))
    for key in edges_by_target:
        edges_by_target[key].sort(key=lambda item: (item[1].order, item[0]))

    resolution_order = _topo_sort_targets(graph)

    for inst_name in resolution_order:
        hole_replacements: dict[str, list[list[ast.stmt]]] = {}
        for (root, target_name), indexed_edges in edges_by_target.items():
            if root != inst_name:
                continue
            bodies: list[list[ast.stmt]] = []
            for _idx, edge in indexed_edges:
                bodies.append(copy.deepcopy(trees[edge.source_instance].body))
            hole_replacements[target_name] = bodies
        if hole_replacements:
            trees[inst_name].body = _replace_holes_in_body(
                trees[inst_name].body, hole_replacements
            )

    consumed = {edge.source_instance for edge in graph.edges}
    root_names = [r.name for r in graph.instances if r.name not in consumed]
    if not root_names:
        target_set = {edge.target.root_instance for edge in graph.edges}
        root_names = sorted(target_set) if target_set else sorted(trees)

    merged_body: list[ast.stmt] = []
    for name in root_names:
        merged_body.extend(trees[name].body)

    merged_tree = ast.Module(body=merged_body, type_ignores=[])
    ast.fix_missing_locations(merged_tree)

    markers = recognize_markers(merged_tree)
    origin = CompileOrigin(
        file_name="<astichi-build>", line_number=1, offset=0
    )
    provisional = BasicComposable(
        tree=merged_tree, origin=origin, markers=markers
    )
    classification = analyze_names(provisional, mode="permissive")

    return BasicComposable(
        tree=merged_tree,
        origin=origin,
        markers=markers,
        classification=classification,
        demand_ports=extract_demand_ports(markers, classification),
        supply_ports=extract_supply_ports(markers),
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


def _replace_holes_in_body(
    body: list[ast.stmt],
    replacements: dict[str, list[list[ast.stmt]]],
) -> list[ast.stmt]:
    """Replace block-position hole statements with source bodies."""
    result: list[ast.stmt] = []
    for stmt in body:
        hole_name = _extract_hole_name(stmt)
        if hole_name is not None and hole_name in replacements:
            for source_body in replacements[hole_name]:
                result.extend(source_body)
        else:
            _recurse_compound(stmt, replacements)
            result.append(stmt)
    return result


def _extract_hole_name(stmt: ast.stmt) -> str | None:
    """Extract the name from a block-position astichi_hole statement."""
    if not isinstance(stmt, ast.Expr):
        return None
    call = stmt.value
    if not isinstance(call, ast.Call):
        return None
    if not isinstance(call.func, ast.Name):
        return None
    if call.func.id != "astichi_hole":
        return None
    if not call.args:
        return None
    first_arg = call.args[0]
    if isinstance(first_arg, ast.Name):
        return first_arg.id
    return None


def _recurse_compound(
    stmt: ast.stmt,
    replacements: dict[str, list[list[ast.stmt]]],
) -> None:
    """Recurse into compound statements to replace nested holes."""
    if isinstance(
        stmt,
        (ast.If, ast.For, ast.While, ast.With, ast.AsyncFor, ast.AsyncWith),
    ):
        stmt.body = _replace_holes_in_body(stmt.body, replacements)
        if stmt.orelse:
            stmt.orelse = _replace_holes_in_body(stmt.orelse, replacements)
    elif isinstance(stmt, ast.Try):
        stmt.body = _replace_holes_in_body(stmt.body, replacements)
        for handler in stmt.handlers:
            handler.body = _replace_holes_in_body(handler.body, replacements)
        if stmt.orelse:
            stmt.orelse = _replace_holes_in_body(stmt.orelse, replacements)
        if stmt.finalbody:
            stmt.finalbody = _replace_holes_in_body(
                stmt.finalbody, replacements
            )
    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        stmt.body = _replace_holes_in_body(stmt.body, replacements)
