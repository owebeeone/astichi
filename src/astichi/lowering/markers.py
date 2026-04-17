"""Marker recognition for Astichi V1."""

from __future__ import annotations

import ast
import re
import warnings
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
        the marker is an idempotent hygiene directive. Defaults to true when
        either condition holds."""
        return self.is_hygiene_directive() or self.is_renamed_per_iteration()

    def is_renamed_per_iteration(self) -> bool:
        """True for markers whose identifier argument is suffixed with
        `__iter_<i>` per loop iteration during unroll (UnrollRevision §4.1).
        The argument index is given by `iter_rename_arg_index()`."""
        return False

    def iter_rename_arg_index(self) -> int:
        """Positional index of the identifier argument that gets the per-
        iteration suffix when `is_renamed_per_iteration()` is True."""
        raise NotImplementedError(
            f"{type(self).__name__} is not renamed per iteration"
        )

    def accepts_call_context(self, node: ast.Call) -> bool:
        """Whether this marker accepts the given call node in call-expression context."""
        return not self.is_decorator_only()

    def accepts_decorator_context(self, node: ast.Call) -> bool:
        """Whether this marker accepts the given call node in decorator context."""
        return self.is_decorator_only()

    def call_context_shape(self) -> MarkerShape | None:
        """Fixed shape override for call context, or None to use _infer_shape."""
        return None

    def identifier_suffix(self) -> str | None:
        """Return the reserved name-suffix this marker claims (e.g.
        `__astichi_keep__`), or None if the marker is not a suffix-form
        identifier marker (issue 005 §1). Suffix-form markers are
        recognised by matching class/def names rather than call nodes."""
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
        renamed_per_iteration: bool = False,
        iter_rename_arg_index: int = 0,
    ) -> None:
        self.source_name = source_name
        self._positional_args = positional_args
        self._name_bearing = name_bearing
        self._decorator_only = decorator_only
        self._hygiene_directive = hygiene_directive
        self._renamed_per_iteration = renamed_per_iteration
        self._iter_rename_arg_index = iter_rename_arg_index

    def is_decorator_only(self) -> bool:
        return self._decorator_only

    def is_name_bearing(self) -> bool:
        return self._name_bearing

    def is_hygiene_directive(self) -> bool:
        return self._hygiene_directive

    def is_renamed_per_iteration(self) -> bool:
        return self._renamed_per_iteration

    def iter_rename_arg_index(self) -> int:
        if not self._renamed_per_iteration:
            return super().iter_rename_arg_index()
        return self._iter_rename_arg_index

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


class _SuffixIdentifierMarker(MarkerSpec):
    """Base for the identifier-shape suffix markers (issue 005 §1)."""

    suffix: str

    def is_name_bearing(self) -> bool:
        return True

    def is_definitional_site(self) -> bool:
        return True

    def identifier_suffix(self) -> str:
        return self.suffix

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            raise TypeError(
                f"{self.source_name} must be recognized from a class/def node"
            )
        if not node.name.endswith(self.suffix):
            raise ValueError(
                f"{self.source_name} requires the reserved {self.suffix} suffix"
            )
        base_name = node.name[: -len(self.suffix)]
        if not base_name.isidentifier():
            raise ValueError(
                f"{self.source_name} requires an identifier prefix before {self.suffix}"
            )


class _KeepIdentifierMarker(_SuffixIdentifierMarker):
    """`name__astichi_keep__` — pin an identifier through hygiene (issue 005 §1)."""

    source_name = "astichi_keep_identifier"
    suffix = "__astichi_keep__"

    def is_hygiene_directive(self) -> bool:
        # Hygiene directive: the stripped name is preserved, suffixed sites are
        # auto-unique. Allows N copies inside an `astichi_for` body without
        # rename conflicts; the strip pass runs once post-hygiene.
        return True


class _ArgIdentifierMarker(_SuffixIdentifierMarker):
    """`name__astichi_arg__` — unresolved identifier slot (issue 005 §1).

    Demand port of shape=IDENTIFIER; requires resolution (wiring, builder
    `arg_names=`, or `.bind_identifier(...)`) before materialize. 5a only
    lands the surface + gate; resolution is 5c/5d.
    """

    source_name = "astichi_arg_identifier"
    suffix = "__astichi_arg__"

    def is_hygiene_directive(self) -> bool:
        # An arg slot is not a rename directive: hygiene leaves the suffixed
        # name alone because the suffix is auto-unique, and the resolve pass
        # (5c) rewrites every occurrence to the supplied identifier.
        # Treated as permitted inside unroll bodies so existing unroll users
        # don't regress; per-iteration arg semantics are refined in 5b.
        return True


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
    renamed_per_iteration=True,
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
KEEP_IDENTIFIER = _KeepIdentifierMarker()
ARG_IDENTIFIER = _ArgIdentifierMarker()

# Canonical registry of every marker Astichi knows about. Consumers that
# need to enumerate markers (e.g. the unroller, the suffix-identifier
# visitor) iterate this tuple and filter by marker self-description
# (`is_name_bearing`, `is_hygiene_directive`, `identifier_suffix`, ...),
# so new markers are picked up automatically.
ALL_MARKERS: tuple[MarkerSpec, ...] = (
    HOLE,
    BIND_ONCE,
    BIND_SHARED,
    BIND_EXTERNAL,
    KEEP,
    EXPORT,
    FOR,
    INSERT,
    KEEP_IDENTIFIER,
    ARG_IDENTIFIER,
)

# Markers recognized from an `ast.Call` node by `accepts_call_context` /
# `accepts_decorator_context`. Derived from `ALL_MARKERS` by filtering
# out suffix-form markers (those that self-report an identifier suffix
# and are matched from a class/def node instead).
MARKERS_BY_NAME: dict[str, MarkerSpec] = {
    marker.source_name: marker
    for marker in ALL_MARKERS
    if marker.identifier_suffix() is None
}


def _build_identifier_suffix_map() -> dict[str, MarkerSpec]:
    """Static map from reserved identifier suffix to its marker.

    Built once at import by scanning `ALL_MARKERS` for entries that
    self-report an `identifier_suffix()` (issue 005 §1). Duplicate
    registrations are a programmer error and abort import.
    """
    mapping: dict[str, MarkerSpec] = {}
    for marker in ALL_MARKERS:
        suffix = marker.identifier_suffix()
        if suffix is None:
            continue
        existing = mapping.get(suffix)
        if existing is not None:
            raise RuntimeError(
                f"duplicate identifier suffix {suffix!r} registered on "
                f"{existing.source_name} and {marker.source_name}"
            )
        mapping[suffix] = marker
    return mapping


_IDENTIFIER_SUFFIX_MARKERS: dict[str, MarkerSpec] = _build_identifier_suffix_map()


# Whole-string pattern for `<identifier>__astichi_<tag>__`. The base
# must be a legal Python identifier prefix (at least one letter /
# underscore, then word characters), and the tail must match the
# reserved `__astichi_<tag>__` shape. The `(?P<suffix>...)` group is
# then looked up in `_IDENTIFIER_SUFFIX_MARKERS` in one O(1) hit.
_IDENTIFIER_SUFFIX_RE: re.Pattern[str] = re.compile(
    r"^(?P<base>[a-zA-Z_]\w*?)(?P<suffix>__astichi_\w+?__)$"
)


def strip_identifier_suffix(name: str) -> tuple[str, MarkerSpec | None]:
    """Return `(base_name, marker)` if `name` carries a registered
    identifier-shape suffix (issue 005 §1); otherwise `(name, None)`.

    Recognition is a single precompiled regex match plus a static-map
    lookup. Names matching the `<identifier>__astichi_<tag>__` shape
    whose `<tag>` is not registered emit a `UserWarning` (almost always
    a typo in one of the known suffixes) and return `(name, None)`.
    Names that do not match the shape return silently.
    """
    match = _IDENTIFIER_SUFFIX_RE.match(name)
    if match is None:
        return name, None
    suffix = match.group("suffix")
    marker = _IDENTIFIER_SUFFIX_MARKERS.get(suffix)
    if marker is None:
        warnings.warn(
            f"identifier {name!r} ends with an unrecognised Astichi suffix "
            f"{suffix!r}; this is almost certainly a typo. Known identifier "
            f"suffixes: {sorted(_IDENTIFIER_SUFFIX_MARKERS)}",
            category=UserWarning,
            stacklevel=3,
        )
        return name, None
    return match.group("base"), marker


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
            base, suffix_marker = strip_identifier_suffix(self.node.name)
            if suffix_marker is not None:
                return base
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
        self._visit_suffix_identifier(node)
        self._visit_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_suffix_identifier(node)
        self._visit_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_suffix_identifier(node)
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

    def _visit_suffix_identifier(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        _, suffix_marker = strip_identifier_suffix(node.name)
        if suffix_marker is None:
            # Fallback: catch bare-suffix pathology (e.g.
            # `class __astichi_keep__:`). `strip_identifier_suffix`
            # requires an identifier prefix, so the regex path above
            # returns None; delegate to the marker validator so the
            # user gets a specific diagnostic rather than silent ignore.
            for suffix, candidate in _IDENTIFIER_SUFFIX_MARKERS.items():
                if node.name.endswith(suffix):
                    candidate.validate_node(node)
                    return
            return
        suffix_marker.validate_node(node)
        self.markers.append(
            RecognizedMarker(
                spec=suffix_marker,
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
