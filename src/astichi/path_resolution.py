"""Semantic resolution of descendant/build refs against insert shells."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from astichi.diagnostics import default_build_path_hint, format_astichi_error
from astichi.lowering.markers import ARG_IDENTIFIER, strip_identifier_suffix
from astichi.shell_refs import (
    RefPath,
    RefSegment,
    extract_insert_ref,
    format_ref_path,
    normalize_ref_path,
)


@dataclass(frozen=True)
class BlockInsertShell:
    """Metadata carried by a decorator-form ``astichi_insert`` shell."""

    target_name: str
    order: int
    ref_path: RefPath | None = None


def format_instance_ref(instance_name: str, ref_path: RefPath) -> str:
    """Render ``instance`` + descendant path for diagnostics."""
    ref_path = normalize_ref_path(ref_path)
    if not ref_path:
        return instance_name
    return f"{instance_name}.{format_ref_path(ref_path)}"


def format_instance_leaf(
    instance_name: str,
    ref_path: RefPath,
    leaf_name: str,
) -> str:
    """Render ``instance`` + descendant path + leaf for diagnostics."""
    prefix = format_instance_ref(instance_name, ref_path)
    return f"{prefix}.{leaf_name}"


def is_astichi_insert_shell(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> bool:
    """Whether ``node`` is decorated by ``astichi_insert(...)``."""
    for decorator in node.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "astichi_insert"
        ):
            return True
    return False


def extract_block_insert_shell(
    stmt: ast.stmt, *, phase: str = "build"
) -> BlockInsertShell | None:
    """Return block-insert metadata for an ``astichi_insert``-decorated def.

    ``phase`` selects the diagnostic prefix for validation failures (e.g.
    ``\"compile\"`` during snippet compile, ``\"build\"`` when indexing shells
    for the builder graph, ``\"materialize\"`` when validating merged trees).
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
            if keyword.arg != "order":
                continue
            if not isinstance(keyword.value, ast.Constant) or not isinstance(
                keyword.value.value, int
            ):
                raise ValueError(
                    format_astichi_error(
                        phase,
                        "astichi_insert order must be an integer constant",
                        hint="use `order=0` with a literal int in the decorator",
                    )
                )
            order = keyword.value.value
        return BlockInsertShell(
            target_name=first_arg.id,
            order=order,
            ref_path=extract_insert_ref(decorator, phase=phase),
        )
    return None


@dataclass(frozen=True)
class AddressableShell:
    """One addressable shell scope in a composable tree."""

    ref_path: RefPath
    body: list[ast.stmt]


class ShellPathResolution:
    """Behavior-bearing result for descendant path lookup."""

    def is_resolved(self) -> bool:
        return False

    def require(self, *, instance_name: str, role: str) -> AddressableShell:
        raise NotImplementedError


@dataclass(frozen=True)
class ResolvedShellPath(ShellPathResolution):
    shell: AddressableShell

    def is_resolved(self) -> bool:
        return True

    def require(self, *, instance_name: str, role: str) -> AddressableShell:
        return self.shell


@dataclass(frozen=True)
class UnknownShellPath(ShellPathResolution):
    ref_path: RefPath

    def require(self, *, instance_name: str, role: str) -> AddressableShell:
        addr = format_instance_ref(instance_name, self.ref_path)
        raise ValueError(
            format_astichi_error(
                "build",
                f"unknown {role} `{addr}`",
                context=f"instance {instance_name!r}",
                hint=default_build_path_hint(),
            )
        )


@dataclass(frozen=True)
class AmbiguousShellPath(ShellPathResolution):
    ref_path: RefPath
    match_count: int

    def require(self, *, instance_name: str, role: str) -> AddressableShell:
        addr = format_instance_ref(instance_name, self.ref_path)
        raise ValueError(
            format_astichi_error(
                "build",
                f"ambiguous {role} `{addr}` ({self.match_count} matches)",
                context=f"instance {instance_name!r}",
                hint="make each `ref=` path on insert shells uniquely addressable",
            )
        )


@dataclass(frozen=True)
class ShellIndex:
    """Addressable-shell index for one AST tree."""

    _matches_by_ref: dict[RefPath, tuple[AddressableShell, ...]]

    @classmethod
    def from_tree(cls, tree: ast.Module) -> "ShellIndex":
        matches: dict[RefPath, list[AddressableShell]] = {
            (): [AddressableShell(ref_path=(), body=tree.body)]
        }
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            info = extract_block_insert_shell(node, phase="build")
            if info is None or info.ref_path is None:
                continue
            ref_path = normalize_ref_path(info.ref_path)
            matches.setdefault(ref_path, []).append(
                AddressableShell(ref_path=ref_path, body=node.body)
            )
        return cls(
            _matches_by_ref={
                ref_path: tuple(shells)
                for ref_path, shells in matches.items()
            }
        )

    def resolve(self, ref_path: RefPath) -> ShellPathResolution:
        ref_path = normalize_ref_path(ref_path)
        matches = self._matches_by_ref.get(ref_path, ())
        if not matches:
            return UnknownShellPath(ref_path=ref_path)
        if len(matches) > 1:
            return AmbiguousShellPath(
                ref_path=ref_path,
                match_count=len(matches),
            )
        return ResolvedShellPath(shell=matches[0])

    def direct_child_segments(self, prefix: RefPath) -> frozenset[RefSegment]:
        prefix = normalize_ref_path(prefix)
        prefix_len = len(prefix)
        next_segments: set[RefSegment] = set()
        for ref_path in self._matches_by_ref:
            if len(ref_path) <= prefix_len:
                continue
            if ref_path[:prefix_len] != prefix:
                continue
            next_segments.add(ref_path[prefix_len])
        return frozenset(next_segments)

    def require_unique_non_root_paths(self, *, instance_name: str) -> None:
        for ref_path, matches in sorted(
            self._matches_by_ref.items(),
            key=lambda item: format_ref_path(item[0]),
        ):
            if not ref_path or len(matches) == 1:
                continue
            raise ValueError(
                format_astichi_error(
                    "build",
                    "instance "
                    f"`{instance_name}` exposes ambiguous descendant ref "
                    f"`{format_instance_ref(instance_name, ref_path)}` "
                    f"({len(matches)} matches); reused build refs must be unique",
                    hint="give each `@astichi_insert(..., ref=...)` shell a distinct fluent path",
                )
            )


def boundary_import_statement(stmt: ast.stmt) -> tuple[str, ast.Call] | None:
    """Return ``(name, call)`` if ``stmt`` is ``astichi_import(name)``."""
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


def collect_hole_names_in_body(body: list[ast.stmt]) -> frozenset[str]:
    """Collect hole names reachable in ``body``, excluding nested shells."""
    names: set[str] = set()

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
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "astichi_hole"
                and node.args
                and isinstance(node.args[0], ast.Name)
            ):
                names.add(node.args[0].id)
            self.generic_visit(node)

    collector = _Collector()
    for statement in body:
        collector.visit(statement)
    return frozenset(names)


def collect_identifier_demands_in_body(body: list[ast.stmt]) -> frozenset[str]:
    """Collect local identifier-demand names in ``body``."""
    names: set[str] = set()
    for statement in body:
        info = boundary_import_statement(statement)
        if info is None:
            break
        names.add(info[0])

    # Any ``astichi_import(name)`` / ``astichi_pass(name)`` call in the body
    # (including expression positions) exposes ``name`` for ``builder.assign``.
    for statement in body:
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            fid = node.func.id
            if fid == "astichi_import" and (
                len(node.args) == 1
                and isinstance(node.args[0], ast.Name)
                and not node.keywords
            ):
                names.add(node.args[0].id)
            elif fid == "astichi_pass" and (
                len(node.args) == 1
                and isinstance(node.args[0], ast.Name)
                and not node.keywords
            ):
                names.add(node.args[0].id)

    class _Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if is_astichi_insert_shell(node):
                return
            self._check(node.name)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if is_astichi_insert_shell(node):
                return
            self._check(node.name)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if is_astichi_insert_shell(node):
                return
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


def collect_identifier_suppliers_in_body(body: list[ast.stmt]) -> frozenset[str]:
    """Collect names visibly readable inside ``body`` for deep assign targets."""
    names: set[str] = set()
    for statement in body:
        info = boundary_import_statement(statement)
        if info is None:
            break
        names.add(info[0])

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

        def visit_arg(self, node: ast.arg) -> None:
            names.add(node.arg)

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            for alias in node.names:
                names.add(alias.asname or alias.name)

    collector = _Collector()
    for statement in body:
        collector.visit(statement)
    return frozenset(names)
