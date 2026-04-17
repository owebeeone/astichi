"""Build merge and materialization for Astichi V1."""

from __future__ import annotations

import ast
import copy
import re
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


_IDENTIFIER_SANITIZER = re.compile(r"[^0-9A-Za-z_]")


def _sanitize_for_identifier(raw: str) -> str:
    cleaned = _IDENTIFIER_SANITIZER.sub("_", raw)
    if not cleaned:
        cleaned = "anon"
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


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
        block_replacements: dict[str, list[_BlockContribution]] = {}
        expr_replacements: dict[str, list[_ExpressionInsert]] = {}
        for (root, target_name), indexed_edges in edges_by_target.items():
            if root != inst_name:
                continue
            target_record = instance_records[inst_name]
            target_port = _lookup_demand_port(target_record.composable, target_name)
            contributions: list[_BlockContribution] = []
            inserts: list[_ExpressionInsert] = []
            for counter, (_idx, edge) in enumerate(indexed_edges):
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
                shell_name = (
                    f"__astichi_contrib__"
                    f"{_sanitize_for_identifier(inst_name)}"
                    f"__{_sanitize_for_identifier(target_name)}"
                    f"__{counter}"
                    f"__{_sanitize_for_identifier(edge.source_instance)}"
                )
                contributions.append(
                    _BlockContribution(
                        source_instance=edge.source_instance,
                        order=edge.order,
                        edge_index=_idx,
                        body=copy.deepcopy(trees[edge.source_instance].body),
                        shell_name=shell_name,
                    )
                )
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
            if contributions:
                block_replacements[target_name] = sorted(
                    contributions,
                    key=lambda item: (item.order, item.edge_index),
                )
        if block_replacements or expr_replacements:
            trees[inst_name].body = _replace_targets_in_body(
                trees[inst_name].body,
                block_replacements=block_replacements,
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
    raw_demands = extract_demand_ports(markers, classification)
    satisfied = _locally_satisfied_hole_names(merged_tree)
    demand_ports = tuple(
        port
        for port in raw_demands
        if not (port.sources == frozenset({"hole"}) and port.name in satisfied)
    )

    return BasicComposable(
        tree=merged_tree,
        origin=origin,
        markers=markers,
        classification=classification,
        demand_ports=demand_ports,
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
    block_replacements: dict[str, list[_BlockContribution]],
    expr_replacements: dict[str, list[_ExpressionInsert]],
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
    return ast.FunctionDef(
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
        block_replacements: dict[str, list[_BlockContribution]],
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
            contributions = self.block_replacements[hole_name]
            result: list[ast.stmt] = [node]
            for contrib in contributions:
                shell = _make_block_insert_shell(
                    target_name=hole_name,
                    order=contrib.order,
                    shell_name=contrib.shell_name,
                    body=contrib.body,
                )
                result.append(shell)
            return result
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
    """Materialize a composable: validate completeness and apply final hygiene.

    The pipeline (see
    `AstichiApiDesignV1-CompositionUnification.md §4`):

    1. reject unresolved mandatory demands (holes, bind-externals);
    2. deep-copy the tree and recognize markers;
    3. assign scope identity and rename scope collisions (hygiene);
    4. realize expression-insert wrappers;
    5. flatten block-level `astichi_hole`/`astichi_insert` shell pairs;
    6. re-recognize markers and re-extract ports.
    """
    satisfied_holes = _locally_satisfied_hole_names(composable.tree)
    mandatory_holes = [
        port
        for port in composable.demand_ports
        if "hole" in port.sources and port.name not in satisfied_holes
    ]
    if mandatory_holes:
        names = ", ".join(port.name for port in mandatory_holes)
        raise ValueError(f"mandatory holes remain unresolved: {names}")
    mandatory_binds = [
        port for port in composable.demand_ports if "bind_external" in port.sources
    ]
    if mandatory_binds:
        if len(mandatory_binds) == 1:
            name = mandatory_binds[0].name
            raise ValueError(
                f"external binding for `{name}` was not supplied; "
                f"call composable.bind({name}=...) before materializing."
            )
        names = ", ".join(port.name for port in mandatory_binds)
        raise ValueError(
            "external bindings were not supplied: "
            f"{names}; call composable.bind(...) before materializing."
        )

    tree = copy.deepcopy(composable.tree)
    markers = recognize_markers(tree)
    provisional = BasicComposable(
        tree=tree,
        origin=composable.origin,
        markers=markers,
        bound_externals=composable.bound_externals,
    )

    analysis = assign_scope_identity(provisional)
    rename_scope_collisions(analysis)
    _realize_expression_insert_wrappers(tree)
    _flatten_block_inserts(tree)

    markers = recognize_markers(tree)
    post_hygiene = BasicComposable(
        tree=tree,
        origin=composable.origin,
        markers=markers,
        bound_externals=composable.bound_externals,
    )
    classification = analyze_names(post_hygiene, mode="permissive")

    return BasicComposable(
        tree=tree,
        origin=composable.origin,
        markers=markers,
        classification=classification,
        demand_ports=extract_demand_ports(markers, classification),
        supply_ports=extract_supply_ports(markers),
        bound_externals=composable.bound_externals,
    )


def _extract_block_insert_shell(stmt: ast.stmt) -> tuple[str, int] | None:
    """Return (target_name, order) if stmt is an `astichi_insert`-decorated def.

    A block-form `astichi_insert` has a single positional argument (the
    target name, as a bare `ast.Name`) and may carry an optional
    integer `order=` keyword.
    """
    if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    for decorator in stmt.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not isinstance(decorator.func, ast.Name):
            continue
        if decorator.func.id != "astichi_insert":
            continue
        if len(decorator.args) != 1:
            continue
        first_arg = decorator.args[0]
        if not isinstance(first_arg, ast.Name):
            continue
        order = 0
        for keyword in decorator.keywords:
            if keyword.arg == "order":
                if not isinstance(keyword.value, ast.Constant) or not isinstance(
                    keyword.value.value, int
                ):
                    raise ValueError(
                        "astichi_insert order must be an integer constant"
                    )
                order = keyword.value.value
        return (first_arg.id, order)
    return None


def _locally_satisfied_hole_names(tree: ast.AST) -> frozenset[str]:
    """Hole names whose matching `astichi_insert` shell is a body sibling.

    A hole whose insert shell lives in the same statement list is
    "locally satisfied" — the flatten pass in
    `materialize_composable` will consume both. Demand gates therefore
    exclude these holes from the unresolved set.
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
                info = _extract_block_insert_shell(stmt)
                if info is not None:
                    shells.add(info[0])
            matched.update(holes & shells)
    return frozenset(matched)


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


def _flatten_body_splices(body: list[ast.stmt]) -> list[ast.stmt]:
    """Splice sibling `astichi_insert` shells into their matching hole positions."""
    shells_by_target: dict[str, list[tuple[int, int, ast.FunctionDef]]] = {}
    for index, stmt in enumerate(body):
        info = _extract_block_insert_shell(stmt)
        if info is None:
            continue
        target, order = info
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
