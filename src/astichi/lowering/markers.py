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

    def is_hygiene_directive(self) -> bool:
        """True for markers that are name-level hygiene assertions (no port,
        no binding). Multiple occurrences of the same directive in the same
        scope are idempotent and do not create N-way conflicts."""
        return False

    def is_permitted_in_unroll_body(self) -> bool:
        """True if N copies of this marker inside an `astichi_for` body are
        safe — either because each copy is renamed per iteration, or because
        the marker is an idempotent hygiene directive. Defaults to the
        hygiene-directive answer; markers that are renamed per iteration
        (see `astichi_hole`) override independently."""
        return self.is_hygiene_directive()

    def accepts_call_context(self, node: ast.Call) -> bool:
        """Whether this marker accepts the given call node in call-expression context."""
        return not self.is_decorator_only()

    def accepts_decorator_context(self, node: ast.Call) -> bool:
        """Whether this marker accepts the given call node in decorator context."""
        return self.is_decorator_only()

    def call_context_shape(self) -> MarkerShape | None:
        """Fixed shape override for call context, or None to use _infer_shape."""
        return None

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
        hygiene_directive: bool = False,
        permitted_in_unroll_body: bool | None = None,
    ) -> None:
        self.source_name = source_name
        self._positional_args = positional_args
        self._name_bearing = name_bearing
        self._decorator_only = decorator_only
        self._hygiene_directive = hygiene_directive
        self._permitted_in_unroll_body = permitted_in_unroll_body

    def is_decorator_only(self) -> bool:
        return self._decorator_only

    def is_name_bearing(self) -> bool:
        return self._name_bearing

    def is_hygiene_directive(self) -> bool:
        return self._hygiene_directive

    def is_permitted_in_unroll_body(self) -> bool:
        if self._permitted_in_unroll_body is not None:
            return self._permitted_in_unroll_body
        return super().is_permitted_in_unroll_body()

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

    def is_hygiene_directive(self) -> bool:
        # Legacy suffix-form marker. Call-form is inert (stripped during
        # materialize). Treated as hygiene for unroll-body safety; issue 005
        # will replace this with __astichi_keep__ on the same footing.
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


class _InsertMarker(MarkerSpec):
    """Dual-context insert marker: decorator (1 arg) and expression (2 args)."""

    source_name = "astichi_insert"

    def is_name_bearing(self) -> bool:
        return True

    def accepts_call_context(self, node: ast.Call) -> bool:
        return len(node.args) == 2

    def accepts_decorator_context(self, node: ast.Call) -> bool:
        return len(node.args) == 1

    def call_context_shape(self) -> MarkerShape | None:
        return SCALAR_EXPR

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Call):
            raise TypeError("astichi_insert must be recognized from an ast.Call")
        if len(node.args) not in (1, 2):
            raise ValueError(
                "astichi_insert expects 1 positional argument (decorator) "
                "or 2 positional arguments (expression)"
            )
        first_arg = node.args[0]
        if not isinstance(first_arg, ast.Name):
            raise ValueError(
                "astichi_insert requires a bare identifier as the target argument"
            )


HOLE = _SimpleMarker(
    "astichi_hole",
    positional_args=1,
    name_bearing=True,
    # Unroll renames the target per iteration (UnrollRevision §4.1), so
    # N copies produce disambiguated targets rather than a conflict.
    permitted_in_unroll_body=True,
)
BIND_ONCE = _SimpleMarker("astichi_bind_once", positional_args=2, name_bearing=True)
BIND_SHARED = _SimpleMarker(
    "astichi_bind_shared", positional_args=2, name_bearing=True
)
BIND_EXTERNAL = _SimpleMarker(
    "astichi_bind_external", positional_args=1, name_bearing=True
)
KEEP = _SimpleMarker(
    "astichi_keep", positional_args=1, name_bearing=True, hygiene_directive=True
)
EXPORT = _SimpleMarker("astichi_export", positional_args=1, name_bearing=True)
FOR = _SimpleMarker("astichi_for", positional_args=1)
INSERT = _InsertMarker()
DEFINITIONAL_NAME = _DefinitionalNameMarker()

# Canonical registry of every marker Astichi knows about. Consumers that
# need to enumerate markers (e.g. the unroller) iterate this tuple and
# filter by marker self-description (`is_name_bearing`, `is_hygiene_directive`,
# ...), so new markers are picked up automatically.
ALL_MARKERS: tuple[MarkerSpec, ...] = (
    HOLE,
    BIND_ONCE,
    BIND_SHARED,
    BIND_EXTERNAL,
    KEEP,
    EXPORT,
    FOR,
    INSERT,
    DEFINITIONAL_NAME,
)

# Markers recognized from an `ast.Call` node by `accepts_call_context` /
# `accepts_decorator_context`. Excludes suffix-form markers like
# `DEFINITIONAL_NAME` which are matched from a class/def node.
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
        if marker is not None and marker.accepts_call_context(node):
            marker.validate_node(node)
            shape = marker.call_context_shape()
            if shape is None:
                shape = _infer_shape(node, self._parent())
            self.markers.append(
                RecognizedMarker(
                    spec=marker,
                    node=node,
                    context="call",
                    shape=shape,
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
            if not marker.accepts_decorator_context(decorator):
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
