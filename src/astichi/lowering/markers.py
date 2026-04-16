"""Marker recognition for Astichi V1."""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass

from astichi.asttools import BLOCK, NAMED_VARIADIC, POSITIONAL_VARIADIC, SCALAR_EXPR, MarkerShape


class MarkerSpec(ABC):
    """Behavior-bearing marker capability object."""

    source_name: str

    def is_decorator_only(self) -> bool:
        return False

    def is_name_bearing(self) -> bool:
        return False

    def is_definitional_site(self) -> bool:
        return False

    @abstractmethod
    def validate_node(self, node: ast.AST) -> None:
        """Validate that the node shape is legal for this marker."""


class _SimpleMarker(MarkerSpec):
    def __init__(
        self,
        source_name: str,
        *,
        positional_args: int,
        name_bearing: bool = False,
        decorator_only: bool = False,
    ) -> None:
        self.source_name = source_name
        self._positional_args = positional_args
        self._name_bearing = name_bearing
        self._decorator_only = decorator_only

    def is_decorator_only(self) -> bool:
        return self._decorator_only

    def is_name_bearing(self) -> bool:
        return self._name_bearing

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Call):
            raise TypeError(f"{self.source_name} must be recognized from an ast.Call")
        if len(node.args) != self._positional_args:
            raise ValueError(
                f"{self.source_name} expects {self._positional_args} positional arguments"
            )
        if self._name_bearing:
            first_arg = node.args[0]
            if not isinstance(first_arg, ast.Name):
                raise ValueError(
                    f"{self.source_name} requires a bare identifier-like first argument"
                )


class _DefinitionalNameMarker(MarkerSpec):
    source_name = "astichi_definitional_name"
    suffix = "__astichi__"

    def is_name_bearing(self) -> bool:
        return True

    def is_definitional_site(self) -> bool:
        return True

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            raise TypeError(
                "astichi_definitional_name must be recognized from a class/def node"
            )
        if not node.name.endswith(self.suffix):
            raise ValueError(
                "astichi_definitional_name requires the reserved __astichi__ suffix"
            )
        base_name = node.name[: -len(self.suffix)]
        if not base_name.isidentifier():
            raise ValueError(
                "astichi_definitional_name requires an identifier prefix before __astichi__"
            )


HOLE = _SimpleMarker("astichi_hole", positional_args=1, name_bearing=True)
BIND_ONCE = _SimpleMarker("astichi_bind_once", positional_args=2, name_bearing=True)
BIND_SHARED = _SimpleMarker(
    "astichi_bind_shared", positional_args=2, name_bearing=True
)
BIND_EXTERNAL = _SimpleMarker(
    "astichi_bind_external", positional_args=1, name_bearing=True
)
KEEP = _SimpleMarker("astichi_keep", positional_args=1, name_bearing=True)
EXPORT = _SimpleMarker("astichi_export", positional_args=1, name_bearing=True)
FOR = _SimpleMarker("astichi_for", positional_args=1)
INSERT = _SimpleMarker(
    "astichi_insert", positional_args=1, decorator_only=True
)
DEFINITIONAL_NAME = _DefinitionalNameMarker()

MARKERS_BY_NAME: dict[str, MarkerSpec] = {
    marker.source_name: marker
    for marker in (
        HOLE,
        BIND_ONCE,
        BIND_SHARED,
        BIND_EXTERNAL,
        KEEP,
        EXPORT,
        FOR,
        INSERT,
    )
}


@dataclass(frozen=True)
class RecognizedMarker:
    """Recognized marker record."""

    spec: MarkerSpec
    node: ast.AST
    context: str
    shape: MarkerShape | None = None

    @property
    def source_name(self) -> str:
        return self.spec.source_name

    @property
    def name_id(self) -> str | None:
        if not self.spec.is_name_bearing():
            return None
        if isinstance(self.node, ast.Call):
            first_arg = self.node.args[0]
            if isinstance(first_arg, ast.Name):
                return first_arg.id
            return None
        if isinstance(self.node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            suffix = "__astichi__"
            if self.node.name.endswith(suffix):
                return self.node.name[: -len(suffix)]
        return None


def _marker_from_call(node: ast.Call) -> MarkerSpec | None:
    if not isinstance(node.func, ast.Name):
        return None
    return MARKERS_BY_NAME.get(node.func.id)


class _MarkerVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.markers: list[RecognizedMarker] = []
        self._stack: list[ast.AST] = []

    def visit(self, node: ast.AST) -> object:
        self._stack.append(node)
        try:
            return super().visit(node)
        finally:
            self._stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        marker = _marker_from_call(node)
        if marker is not None and not marker.is_decorator_only():
            marker.validate_node(node)
            self.markers.append(
                RecognizedMarker(
                    spec=marker,
                    node=node,
                    context="call",
                    shape=_infer_shape(node, self._parent()),
                )
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_definitional_name(node)
        self._visit_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_definitional_name(node)
        self._visit_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_definitional_name(node)
        self._visit_decorators(node.decorator_list)
        self.generic_visit(node)

    def _visit_decorators(self, decorators: list[ast.expr]) -> None:
        for decorator in decorators:
            if not isinstance(decorator, ast.Call):
                continue
            marker = _marker_from_call(decorator)
            if marker is None:
                continue
            if not marker.is_decorator_only():
                continue
            marker.validate_node(decorator)
            self.markers.append(
                RecognizedMarker(
                    spec=marker,
                    node=decorator,
                    context="decorator",
                    shape=None,
                )
            )

    def _visit_definitional_name(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        if not node.name.endswith(DEFINITIONAL_NAME.suffix):
            return
        DEFINITIONAL_NAME.validate_node(node)
        self.markers.append(
            RecognizedMarker(
                spec=DEFINITIONAL_NAME,
                node=node,
                context="definitional",
                shape=None,
            )
        )

    def _parent(self) -> ast.AST | None:
        if len(self._stack) < 2:
            return None
        return self._stack[-2]


def _infer_shape(node: ast.Call, parent: ast.AST | None) -> MarkerShape:
    if isinstance(parent, ast.Starred) and parent.value is node:
        return POSITIONAL_VARIADIC
    if isinstance(parent, ast.keyword) and parent.arg is None and parent.value is node:
        return NAMED_VARIADIC
    if isinstance(parent, ast.Dict):
        for i, v in enumerate(parent.values):
            if v is node:
                if parent.keys[i] is None:
                    return NAMED_VARIADIC
                break
    if isinstance(parent, ast.Expr) and parent.value is node:
        return BLOCK
    return SCALAR_EXPR


def recognize_markers(tree: ast.AST) -> tuple[RecognizedMarker, ...]:
    """Recognize V1 markers from a parsed AST."""
    visitor = _MarkerVisitor()
    visitor.visit(tree)
    return tuple(visitor.markers)
