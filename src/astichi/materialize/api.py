"""Build merge and materialization for Astichi V1."""

from __future__ import annotations

import ast
import copy
import re
from dataclasses import dataclass

from astichi.builder.graph import (
    AdditiveEdge,
    AssignBinding,
    BuilderGraph,
    InstanceRecord,
)
from astichi.hygiene import analyze_names, assign_scope_identity, rename_scope_collisions
from astichi.lowering import recognize_markers
from astichi.lowering.markers import (
    ARG_IDENTIFIER,
    KEEP_IDENTIFIER,
    strip_identifier_suffix,
)
from astichi.lowering.unroll import iter_target_name, unroll_tree
from astichi.model.basic import BasicComposable
from astichi.model.origin import CompileOrigin
from astichi.model.ports import DemandPort, SupplyPort, extract_demand_ports, extract_supply_ports, validate_port_pair
from astichi.shell_refs import (
    RefPath,
    extract_insert_ref,
    format_ref_path,
    normalize_ref_path,
    prefix_insert_ref,
    set_insert_ref,
)


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
    ref_path: RefPath


@dataclass(frozen=True)
class _BlockInsertShell:
    target_name: str
    order: int
    ref_path: RefPath | None = None


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
    original: BasicComposable, tree: ast.Module
) -> BasicComposable:
    """Re-extract markers/classification/ports against an unrolled tree."""
    markers = recognize_markers(tree)
    provisional = BasicComposable(
        tree=tree,
        origin=original.origin,
        markers=markers,
        bound_externals=original.bound_externals,
        arg_bindings=original.arg_bindings,
        keep_names=original.keep_names,
    )
    classification = analyze_names(
        provisional,
        mode="permissive",
        preserved_names=original.keep_names,
    )
    return BasicComposable(
        tree=tree,
        origin=original.origin,
        markers=markers,
        classification=classification,
        demand_ports=extract_demand_ports(markers, classification),
        supply_ports=extract_supply_ports(markers),
        bound_externals=original.bound_externals,
        arg_bindings=original.arg_bindings,
        keep_names=original.keep_names,
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
            f"indexed target {addr} has no matching astichi_hole "
            f"(expected synthetic name {root}.{effective_name}); "
            "index may be out of range or target was not unrolled"
        )


def _apply_assign_bindings(
    assigns: tuple[AssignBinding, ...],
    instance_records: dict[str, InstanceRecord],
    trees: dict[str, ast.Module],
) -> None:
    """Apply ``builder.assign`` wirings to local tree copies shell-locally."""
    published_target_aliases: set[tuple[str, RefPath, str]] = set()
    for binding in assigns:
        source_ref_path = normalize_ref_path(binding.source_ref_path)
        target_ref_path = normalize_ref_path(binding.target_ref_path)
        src = instance_records.get(binding.source_instance)
        if src is None:
            raise ValueError(
                f"builder.assign refers to unknown source instance "
                f"`{binding.source_instance}`"
            )
        dst = instance_records.get(binding.target_instance)
        if dst is None:
            raise ValueError(
                f"builder.assign refers to unknown target instance "
                f"`{binding.target_instance}` "
                f"(from {binding.source_instance}.{binding.inner_name})"
            )
        piece = src.composable
        if not isinstance(piece, BasicComposable):
            raise TypeError(
                f"builder.assign source instance `{binding.source_instance}` "
                f"must be a BasicComposable; got {type(piece).__name__}"
            )
        resolved_outer_name = binding.outer_name
        if target_ref_path:
            target_tree = trees[binding.target_instance]
            target_shell_body = _find_shell_body_by_ref(
                target_tree, target_ref_path
            )
            if target_shell_body is None:
                rendered = format_ref_path(target_ref_path)
                raise ValueError(
                    f"builder.assign target path `{binding.target_instance}."
                    f"{rendered}` has no matching descendant shell"
                )
            alias_key = (
                binding.target_instance,
                target_ref_path,
                binding.outer_name,
            )
            resolved_outer_name = _assign_target_alias_name(binding)
            if alias_key not in published_target_aliases:
                _publish_assign_target_alias(
                    target_shell_body,
                    source_name=binding.outer_name,
                    alias_name=resolved_outer_name,
                )
                published_target_aliases.add(alias_key)
                target_piece = _refresh_composable(dst.composable, target_tree)
                instance_records[binding.target_instance] = InstanceRecord(
                    name=binding.target_instance,
                    composable=target_piece,
                )
        source_tree = trees[binding.source_instance]
        shell_body = _find_shell_body_by_ref(source_tree, source_ref_path)
        if shell_body is None:
            rendered = format_ref_path(source_ref_path)
            raise ValueError(
                f"builder.assign source path `{binding.source_instance}."
                f"{rendered}` has no matching descendant shell"
            )
        local_demands = _collect_identifier_demands_in_body(shell_body)
        if binding.inner_name not in local_demands:
            raise ValueError(
                f"no __astichi_arg__ / astichi_import slot named "
                f"`{binding.inner_name}`"
            )
        _rewrite_identifier_demands_in_body(
            shell_body,
            {binding.inner_name: resolved_outer_name},
        )
        piece = _refresh_composable(piece, source_tree)
        instance_records[binding.source_instance] = InstanceRecord(
            name=binding.source_instance, composable=piece
        )


def _find_shell_body_by_ref(
    tree: ast.Module,
    ref_path: RefPath,
) -> list[ast.stmt] | None:
    ref_path = normalize_ref_path(ref_path)
    if not ref_path:
        return tree.body
    matches: list[list[ast.stmt]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        info = _extract_block_insert_shell(node)
        if info is None or info.ref_path != ref_path:
            continue
        matches.append(node.body)
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous descendant shell ref `{format_ref_path(ref_path)}`"
        )
    return matches[0] if matches else None


def _collect_identifier_demands_in_body(body: list[ast.stmt]) -> frozenset[str]:
    names: set[str] = set()
    for statement in body:
        info = _boundary_import_statement(statement)
        if info is None:
            break
        names.add(info[0])

    class _Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if _is_astichi_insert_shell(node):
                return
            self._check(node.name)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if _is_astichi_insert_shell(node):
                return
            self._check(node.name)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._check(node.name)
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            self._check(node.id)

        def visit_arg(self, node: ast.arg) -> None:
            self._check(node.arg)

        def _check(self, raw_name: str) -> None:
            base, marker = strip_identifier_suffix(raw_name)
            if marker is ARG_IDENTIFIER:
                names.add(base)

    collector = _Collector()
    for statement in body:
        collector.visit(statement)
    return frozenset(names)


def _rewrite_identifier_demands_in_body(
    body: list[ast.stmt],
    bindings: dict[str, str],
) -> None:
    arg_resolver = _ShellArgIdentifierResolver(bindings)
    import_resolver = _BoundaryImportRenamer(bindings)
    for index, statement in enumerate(body):
        info = _boundary_import_statement(statement)
        if info is not None and info[0] in bindings:
            _rewrite_boundary_import_name(statement, bindings[info[0]])
        rewritten = arg_resolver.visit(statement)
        if rewritten is None:
            continue
        assert isinstance(rewritten, ast.stmt)
        body[index] = import_resolver.visit(rewritten)


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
) -> None:
    body.extend(
        (
            ast.Expr(
                value=ast.Call(
                    func=ast.Name(id="astichi_pass", ctx=ast.Load()),
                    args=[ast.Name(id=alias_name, ctx=ast.Load())],
                    keywords=[],
                )
            ),
            ast.Assign(
                targets=[ast.Name(id=alias_name, ctx=ast.Store())],
                value=ast.Name(id=source_name, ctx=ast.Load()),
            ),
        )
    )


class _ShellArgIdentifierResolver(ast.NodeTransformer):
    def __init__(self, bindings: dict[str, str]) -> None:
        self._bindings = bindings

    def _resolve(self, raw_name: str) -> str:
        base, marker = strip_identifier_suffix(raw_name)
        if marker is not ARG_IDENTIFIER:
            return raw_name
        return self._bindings.get(base, raw_name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if _is_astichi_insert_shell(node):
            return node
        node.name = self._resolve(node.name)
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        if _is_astichi_insert_shell(node):
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
        raise ValueError("cannot build from empty graph")
    if unroll not in (True, False, "auto"):
        raise ValueError(
            f"unroll must be True, False, or 'auto'; got {unroll!r}"
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
            "unroll=False conflicts with indexed target edges: "
            + ", ".join(offenders)
        )
    do_unroll = (unroll is True) or (unroll == "auto" and has_indexed_edges)

    trees: dict[str, ast.Module] = {}
    instance_records: dict[str, InstanceRecord] = {}
    for record in graph.instances:
        if not isinstance(record.composable, BasicComposable):
            raise TypeError(
                f"instance {record.name} must be a BasicComposable"
            )
        tree = copy.deepcopy(record.composable.tree)
        if do_unroll:
            tree = unroll_tree(tree)
            composable = _refresh_composable(record.composable, tree)
        else:
            composable = record.composable
        trees[record.name] = tree
        instance_records[record.name] = InstanceRecord(
            name=record.name, composable=composable
        )

    # Issue 006 6c (assign surface):
    # ``builder.assign.<Src>.<inner>.to().<Dst>.<outer>`` declarations
    # are resolved against the local instance-record copies so each
    # ``build()`` invocation is idempotent. Unlike the in-graph
    # ``target.add.<Src>(arg_names=...)`` surface, the assign surface
    # never mutates the graph's instance records; the wiring is held as
    # ``AssignBinding`` records on the graph and applied fresh here.
    _apply_assign_bindings(graph.assigns, instance_records, trees)

    edges_by_target: dict[tuple[str, RefPath, str], list[tuple[int, AdditiveEdge]]] = {}
    for idx, edge in enumerate(graph.edges):
        effective_name = iter_target_name(
            edge.target.target_name, edge.target.path
        )
        key = (
            edge.target.root_instance,
            normalize_ref_path(edge.target.ref_path),
            effective_name,
        )
        edges_by_target.setdefault(key, []).append((idx, edge))
    for key in edges_by_target:
        edges_by_target[key].sort(key=lambda item: (item[1].order, item[0]))

    _validate_indexed_targets(edges_by_target, instance_records)

    resolution_order = _topo_sort_targets(graph)

    for inst_name in resolution_order:
        scoped_block_replacements: dict[tuple[RefPath, str], list[_BlockContribution]] = {}
        scoped_expr_replacements: dict[tuple[RefPath, str], list[_ExpressionInsert]] = {}
        for (
            root,
            target_ref_path,
            effective_target_name,
        ), indexed_edges in edges_by_target.items():
            if root != inst_name:
                continue
            target_record = instance_records[inst_name]
            target_port = _lookup_demand_port(
                target_record.composable, effective_target_name
            )
            contributions: list[_BlockContribution] = []
            inserts: list[_ExpressionInsert] = []
            for counter, (_idx, edge) in enumerate(indexed_edges):
                source_record = instance_records[edge.source_instance]
                # Source-side ports and insert wrappers use the raw (pre-
                # unroll) name — the author writes `astichi_insert(slot, ...)`
                # in the source; the suffixing happens on the target side.
                raw_target_name = edge.target.target_name
                source_port = _lookup_supply_port(
                    source_record.composable, raw_target_name
                )
                if target_port is not None and source_port is not None:
                    validate_port_pair(target_port, source_port)
                if target_port is not None and target_port.placement == "expr":
                    if source_port is None or source_port.placement != "expr":
                        raise ValueError(
                            f"source instance {edge.source_instance} cannot satisfy "
                            f"expression target {inst_name}.{effective_target_name}"
                        )
                    inserts.extend(
                        _extract_expression_inserts(
                            trees[edge.source_instance],
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
                contrib_body = copy.deepcopy(trees[edge.source_instance].body)
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
        if scoped_block_replacements or scoped_expr_replacements:
            _replace_targets_in_tree(
                trees[inst_name],
                block_replacements=scoped_block_replacements,
                expr_replacements=scoped_expr_replacements,
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
        merged_body.extend(_wrap_in_root_scope(trees[name].body, name))

    merged_tree = ast.Module(body=merged_body, type_ignores=[])
    ast.fix_missing_locations(merged_tree)

    # Issue 005 §6 / 5d: union per-instance `arg_bindings` and
    # `keep_names` into the merged composable so the materialize
    # resolver pass and hygiene see everything the builder accumulated.
    merged_arg_bindings: dict[str, str] = {}
    merged_keep_names: set[str] = set()
    for record in instance_records.values():
        for key, value in record.composable.arg_bindings:
            if key in merged_arg_bindings and merged_arg_bindings[key] != value:
                raise ValueError(
                    f"conflicting identifier-arg resolutions for `{key}`: "
                    f"`{merged_arg_bindings[key]}` vs `{value}` across "
                    "merged instances"
                )
            merged_arg_bindings[key] = value
        merged_keep_names.update(record.composable.keep_names)

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
        arg_bindings=tuple(sorted(merged_arg_bindings.items())),
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
    ref_path: RefPath | None = None,
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
        set_insert_ref(decorator, ref_path)
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
    return f"__astichi_root__{_sanitize_for_identifier(instance_name)}__"


def _wrap_in_root_scope(
    body: list[ast.stmt], instance_name: str
) -> list[ast.stmt]:
    """Wrap a root instance's body in a hole+shell pair (issue 006 6c).

    The wrapped body becomes a fresh Astichi scope for hygiene
    purposes. `_flatten_block_inserts` later consumes the hole and
    the shell (after rename-collisions has run), inlining the body
    back at module level — the wrapper exists purely to carry scope
    identity through the hygiene pass.
    """
    anchor = _root_scope_anchor(instance_name)
    hole = ast.Expr(
        value=ast.Call(
            func=ast.Name(id="astichi_hole", ctx=ast.Load()),
            args=[ast.Name(id=anchor, ctx=ast.Load())],
            keywords=[],
        )
    )
    shell = _make_block_insert_shell(
        target_name=anchor,
        order=0,
        shell_name=anchor,
        body=body,
    )
    return [hole, shell]


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
                    ref_path=contrib.ref_path,
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
            "unresolved identifier-arg slots (call .bind_identifier(...) "
            "or wire the arg before materialize): " + "; ".join(parts)
        )

    unmatched_block_shells = _find_unmatched_block_insert_shells(composable.tree)
    unmatched_expr_inserts = _find_unmatched_expression_inserts(composable.tree)
    if unmatched_block_shells or unmatched_expr_inserts:
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
        raise ValueError(
            "unmatched astichi_insert supplies; every insert must point "
            "at an extant hole before materialize runs hygiene: "
            + "; ".join(parts)
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
    markers = recognize_markers(tree)
    pinned_targets = frozenset(arg_bindings.values())
    effective_keep_names = composable.keep_names | pinned_targets
    provisional = BasicComposable(
        tree=tree,
        origin=composable.origin,
        markers=markers,
        bound_externals=composable.bound_externals,
        keep_names=effective_keep_names,
    )

    # Issue 006 6c (trust model): only user-declared keep_names (plus
    # keep/pass markers auto-unioned inside `assign_scope_identity`)
    # enter the trust set. `pinned_targets` reach preserved but not
    # trusted — they must still participate in cross-scope rename so
    # sibling-root contributions bound to the same `arg_names` value
    # do not clobber each other.
    analysis = assign_scope_identity(
        provisional,
        preserved_names=effective_keep_names,
        trust_names=composable.keep_names,
    )
    rename_scope_collisions(analysis)
    _realize_expression_insert_wrappers(tree)
    _flatten_block_inserts(tree)

    pre_strip_markers = recognize_markers(tree)
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


def _extract_block_insert_shell(stmt: ast.stmt) -> _BlockInsertShell | None:
    """Return block-insert metadata for an `astichi_insert`-decorated def.

    A block-form `astichi_insert` has a single positional argument (the
    target name, as a bare `ast.Name`) and may carry an optional
    integer `order=` keyword and structured `ref=` path.
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
        return _BlockInsertShell(
            target_name=first_arg.id,
            order=order,
            ref_path=extract_insert_ref(decorator),
        )
    return None


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
            info = _extract_block_insert_shell(node)
            if info is None or info.ref_path is None:
                return
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "astichi_insert"
                ):
                    prefix_insert_ref(decorator, prefix)
                    return

    prefixer = _ShellRefPrefixer()
    for index, stmt in enumerate(body):
        body[index] = prefixer.visit(stmt)  # type: ignore[assignment]


def _replace_targets_in_tree(
    tree: ast.Module,
    *,
    block_replacements: dict[tuple[RefPath, str], list[_BlockContribution]],
    expr_replacements: dict[tuple[RefPath, str], list[_ExpressionInsert]],
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
        if local_block or local_expr:
            body = _replace_targets_in_body(
                body,
                block_replacements=local_block,
                expr_replacements=local_expr,
            )
        for stmt in body:
            info = _extract_block_insert_shell(stmt)
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
                info = _extract_block_insert_shell(stmt)
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
                    shells.add(info.target_name)
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


_RESIDUAL_MARKER_NAMES: frozenset[str] = frozenset(
    {"astichi_keep", "astichi_export"}
)


# Issue 006 6c: `astichi_import(name)` / `astichi_pass(name)` are
# compile-time declarations that have already contributed port records
# and scope-identity classification by the time we run the residual
# stripper. They carry no runtime value and must not appear in the
# emitted source. Unlike `astichi_keep` / `astichi_export`, these
# markers are statement-only (no expression-form wrapping), so we
# strip the enclosing Expr and leave any embedded Call position
# untouched.
_BOUNDARY_STATEMENT_MARKER_NAMES: frozenset[str] = frozenset(
    {"astichi_import", "astichi_pass"}
)


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


def _is_boundary_statement_marker(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name):
        return False
    return node.func.id in _BOUNDARY_STATEMENT_MARKER_NAMES


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


class _ResidualMarkerStripper(ast.NodeTransformer):
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
        if _is_boundary_statement_marker(node.value):
            # Issue 006 6c: strip the declaration statement; port
            # records and hygiene-scope classification already consumed
            # this marker upstream.
            return None
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        inner = _residual_marker_inner(node)
        if inner is not None:
            return self.visit(copy.deepcopy(inner))
        return self.generic_visit(node)


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
    return [
        (name, tuple(sorted(set(lines))))
        for name, lines in sorted(by_name.items())
    ]


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

    Identity bindings (`"x" -> "x"`) are a no-op; names the user did
    not rebind are left alone and default to the enclosing Astichi
    scope's same-named binding (the 6c hygiene fix handles those
    without any AST rewrite).
    """
    if not bindings:
        return
    for shell_node in _find_astichi_shell_nodes(tree):
        declared_imports = _declared_imports_at_shell_top(shell_node)
        local_map = {
            name: bindings[name]
            for name in declared_imports
            if name in bindings and bindings[name] != name
        }
        if not local_map:
            continue
        for statement in shell_node.body:
            info = _boundary_import_statement(statement)
            if info is not None and info[0] in local_map:
                _rewrite_boundary_import_name(statement, local_map[info[0]])
                continue
            _BoundaryImportRenamer(local_map).visit(statement)


def _find_astichi_shell_nodes(
    tree: ast.AST,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]:
    shells: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "astichi_insert"
                ):
                    shells.append(node)
                    break
    return shells


def _declared_imports_at_shell_top(
    shell: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> frozenset[str]:
    names: set[str] = set()
    for statement in shell.body:
        info = _boundary_import_statement(statement)
        if info is None:
            break
        names.add(info[0])
    return frozenset(names)


def _boundary_import_statement(stmt: ast.stmt) -> tuple[str, ast.Call] | None:
    if not isinstance(stmt, ast.Expr):
        return None
    value = stmt.value
    if not isinstance(value, ast.Call):
        return None
    if not isinstance(value.func, ast.Name) or value.func.id != "astichi_import":
        return None
    if not value.args or not isinstance(value.args[0], ast.Name):
        return None
    return value.args[0].id, value


def _rewrite_boundary_import_name(stmt: ast.stmt, new_name: str) -> None:
    info = _boundary_import_statement(stmt)
    assert info is not None, "caller must pre-check the statement"
    _, call = info
    target = call.args[0]
    assert isinstance(target, ast.Name)
    target.id = new_name


class _BoundaryImportRenamer(ast.NodeTransformer):
    """Rewrite ``ast.Name`` / ``ast.arg`` occurrences under one shell body.

    Stops at nested ``@astichi_insert``-decorated shell boundaries: a
    nested shell that does NOT re-declare ``astichi_import(x)`` inherits
    the outer rewrite; a nested shell that DOES re-declare it is
    processed by its own outer-level pass call, so this walker
    short-circuits at nested shell roots to avoid double-rewriting.
    """

    def __init__(self, rename_map: dict[str, str]) -> None:
        self._rename_map = rename_map

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if _is_astichi_insert_shell(node):
            return node
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        if _is_astichi_insert_shell(node):
            return node
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        if _is_astichi_insert_shell(node):
            return node
        return self.generic_visit(node)

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


def _is_astichi_insert_shell(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> bool:
    for decorator in node.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "astichi_insert"
        ):
            return True
    return False


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
        info = _extract_block_insert_shell(stmt)
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
