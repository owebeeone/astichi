"""Build merge and materialization for Astichi V1."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass

from astichi.builder.graph import BuilderGraph
from astichi.hygiene import analyze_names, assign_scope_identity, rename_scope_collisions
from astichi.lowering import recognize_markers
from astichi.model.basic import BasicComposable
from astichi.model.origin import CompileOrigin
from astichi.model.ports import DemandPort, SupplyPort, extract_demand_ports, extract_supply_ports, validate_port_pair


@dataclass(frozen=True)
class _ExpressionInsert:
    expr: ast.expr
    edge_order: int
    inline_order: int
    edge_index: int
    statement_index: int


def build_merge(graph: BuilderGraph) -> BasicComposable:
    """Merge a builder graph into a single composable."""
    if not graph.instances:
        raise ValueError("cannot build from empty graph")

    trees: dict[str, ast.Module] = {}
    instance_records: dict[str, object] = {}
    for record in graph.instances:
        if not isinstance(record.composable, BasicComposable):
            raise TypeError(
                f"instance {record.name} must be a BasicComposable"
            )
        instance_records[record.name] = record
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
        expr_replacements: dict[str, list[_ExpressionInsert]] = {}
        for (root, target_name), indexed_edges in edges_by_target.items():
            if root != inst_name:
                continue
            target_record = instance_records[inst_name]
            target_port = _lookup_demand_port(target_record.composable, target_name)
            bodies: list[list[ast.stmt]] = []
            inserts: list[_ExpressionInsert] = []
            for _idx, edge in indexed_edges:
                source_record = instance_records[edge.source_instance]
                source_port = _lookup_supply_port(source_record.composable, target_name)
                if target_port is not None and source_port is not None:
                    validate_port_pair(target_port, source_port)
                if target_port is not None and target_port.placement == "expr":
                    if source_port is None or source_port.placement != "expr":
                        raise ValueError(
                            f"source instance {edge.source_instance} cannot satisfy "
                            f"expression target {inst_name}.{target_name}"
                        )
                    inserts.extend(
                        _extract_expression_inserts(
                            trees[edge.source_instance],
                            target_name,
                            edge_order=edge.order,
                            edge_index=_idx,
                            source_instance=edge.source_instance,
                        )
                    )
                    continue
                bodies.append(copy.deepcopy(trees[edge.source_instance].body))
            if inserts:
                expr_replacements[target_name] = sorted(
                    inserts,
                    key=lambda item: (
                        item.edge_order,
                        item.inline_order,
                        item.edge_index,
                        item.statement_index,
                    ),
                )
            if bodies:
                hole_replacements[target_name] = bodies
        if hole_replacements or expr_replacements:
            trees[inst_name].body = _replace_targets_in_body(
                trees[inst_name].body,
                replacements=hole_replacements,
                expr_replacements=expr_replacements,
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


def _replace_targets_in_body(
    body: list[ast.stmt],
    *,
    replacements: dict[str, list[list[ast.stmt]]],
    expr_replacements: dict[str, list[_ExpressionInsert]],
) -> list[ast.stmt]:
    """Replace block and expression targets in a statement list."""
    transformer = _HoleReplacementTransformer(
        block_replacements=replacements,
        expr_replacements=expr_replacements,
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


def _extract_expression_inserts(
    tree: ast.Module,
    target_name: str,
    *,
    edge_order: int,
    edge_index: int,
    source_instance: str,
) -> list[_ExpressionInsert]:
    inserts: list[_ExpressionInsert] = []
    for stmt_index, stmt in enumerate(tree.body):
        if not isinstance(stmt, ast.Expr):
            if _contains_top_level_expression_insert(stmt):
                raise ValueError(
                    f"source instance {source_instance} has non-expression-statement "
                    "insert wrappers at top level"
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
                edge_order=edge_order,
                inline_order=_extract_insert_order(stmt.value),
                edge_index=edge_index,
                statement_index=stmt_index,
            )
        )
    if not inserts:
        raise ValueError(
            f"source instance {source_instance} cannot satisfy expression target "
            f"{target_name}: no matching astichi_insert(...) wrappers found"
        )
    return inserts


def _contains_top_level_expression_insert(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Expr):
        return False
    if not isinstance(stmt.value, ast.Call):
        return False
    return _is_expression_insert_call(stmt.value)


def _is_expression_insert_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Name):
        return False
    return node.func.id == "astichi_insert" and len(node.args) == 2


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
            raise ValueError("astichi_insert order must be an integer constant")
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


def _make_expression_insert_call(target_name: str, expr: ast.expr) -> ast.Call:
    return ast.Call(
        func=ast.Name(id="astichi_insert", ctx=ast.Load()),
        args=[
            ast.Name(id=target_name, ctx=ast.Load()),
            copy.deepcopy(expr),
        ],
        keywords=[],
    )


class _HoleReplacementTransformer(ast.NodeTransformer):
    def __init__(
        self,
        *,
        block_replacements: dict[str, list[list[ast.stmt]]],
        expr_replacements: dict[str, list[_ExpressionInsert]],
    ) -> None:
        self.block_replacements = block_replacements
        self.expr_replacements = expr_replacements

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
            return [
                copy.deepcopy(stmt)
                for source_body in self.block_replacements[hole_name]
                for stmt in source_body
            ]
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        hole_name = _extract_expr_hole_name(node)
        if hole_name is not None and hole_name in self.expr_replacements:
            inserts = self.expr_replacements[hole_name]
            if len(inserts) != 1:
                raise ValueError(
                    f"scalar expression target {hole_name} accepts at most one insert"
                )
            return _make_expression_insert_call(hole_name, inserts[0].expr)
        return self.generic_visit(node)

    def visit_Starred(self, node: ast.Starred) -> ast.AST | list[ast.expr]:
        hole_name = _extract_expr_hole_name(node.value)
        if hole_name is not None and hole_name in self.expr_replacements:
            return [
                ast.Starred(
                    value=_make_expression_insert_call(hole_name, insert.expr),
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
                        f"named variadic target {hole_name} requires dict-display expression inserts"
                    )
                expanded.append(
                    ast.keyword(
                        arg=None,
                        value=_make_expression_insert_call(hole_name, insert.expr),
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
                            f"named variadic target {hole_name} requires dict-display expression inserts"
                        )
                    new_keys.append(None)
                    new_values.append(
                        _make_expression_insert_call(hole_name, insert.expr)
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
            return self.visit(copy.deepcopy(node.args[1]))
        return self.generic_visit(node)

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
                    "named variadic expression inserts require dict-display payloads"
                )
            expanded: list[ast.keyword] = []
            for key, value in zip(expr.keys, expr.values, strict=True):
                if key is None or not isinstance(key, ast.Name):
                    raise ValueError(
                        "named variadic keyword expansion requires identifier keys"
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
                        "named variadic dict expansion requires dict-display payloads"
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


def materialize_composable(composable: BasicComposable) -> BasicComposable:
    """Materialize a composable: validate completeness and apply final hygiene."""
    mandatory_holes = [
        port for port in composable.demand_ports if "hole" in port.sources
    ]
    if mandatory_holes:
        names = ", ".join(port.name for port in mandatory_holes)
        raise ValueError(f"mandatory holes remain unresolved: {names}")

    tree = copy.deepcopy(composable.tree)
    markers = recognize_markers(tree)
    provisional = BasicComposable(
        tree=tree, origin=composable.origin, markers=markers
    )

    analysis = assign_scope_identity(provisional)
    rename_scope_collisions(analysis)
    _realize_expression_insert_wrappers(tree)

    markers = recognize_markers(tree)
    post_hygiene = BasicComposable(
        tree=tree, origin=composable.origin, markers=markers
    )
    classification = analyze_names(post_hygiene, mode="permissive")

    return BasicComposable(
        tree=tree,
        origin=composable.origin,
        markers=markers,
        classification=classification,
        demand_ports=extract_demand_ports(markers, classification),
        supply_ports=extract_supply_ports(markers),
    )
