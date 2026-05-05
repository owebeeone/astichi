"""Marker recognition for Astichi V1."""

from __future__ import annotations

import ast
import re
import warnings
from abc import ABC, abstractmethod
from collections.abc import Container, Iterable, Sequence
from dataclasses import dataclass

from astichi.asttools import (
    BLOCK,
    IDENTIFIER,
    NAMED_VARIADIC,
    PARAMETER,
    POSITIONAL_VARIADIC,
    SCALAR_EXPR,
    MarkerShape,
)
from astichi.model.semantics import (
    ARG_IDENTIFIER_ORIGIN,
    BIND_EXTERNAL_ORIGIN,
    CONST_MUTABILITY,
    EXPORT_ORIGIN,
    HOLE_ORIGIN,
    IMPORT_ORIGIN,
    INSERT_ORIGIN,
    PARAMETER_HOLE_ORIGIN,
    PARAMETER_PAYLOAD_ORIGIN,
    PASS_ORIGIN,
    PortMutability,
    PortOrigin,
)
from astichi.lowering.marker_contexts import (
    CALL_CONTEXT,
    DECORATOR_CONTEXT,
    DEFINITIONAL_CONTEXT,
    IDENTIFIER_CONTEXT,
    MarkerContext,
)
from astichi.shell_refs import parse_ref_path_literal


BOUNDARY_OUTER_BIND_KEYWORD = "outer_bind"
BOUNDARY_EXPLICIT_BIND_KEYWORD = "bound"
BOUNDARY_STATE_KEYWORDS: frozenset[str] = frozenset(
    {
        BOUNDARY_OUTER_BIND_KEYWORD,
        BOUNDARY_EXPLICIT_BIND_KEYWORD,
    }
)


def _boundary_keyword_bool(keyword: ast.keyword) -> bool:
    value = keyword.value
    if not isinstance(value, ast.Constant) or not isinstance(value.value, bool):
        raise ValueError(
            f"boundary keyword `{keyword.arg}` must be a literal True/False"
        )
    return value.value


def boundary_outer_bind_enabled(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg == BOUNDARY_OUTER_BIND_KEYWORD:
            return _boundary_keyword_bool(keyword)
    return False


def boundary_explicit_bind_enabled(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg == BOUNDARY_EXPLICIT_BIND_KEYWORD:
            return _boundary_keyword_bool(keyword)
    return False


def set_boundary_explicit_bind_state(call: ast.Call) -> None:
    """Mark ``call`` as explicitly wired in source-visible syntax."""
    kept_keywords: list[ast.keyword] = []
    saw_bound = False
    for keyword in call.keywords:
        if keyword.arg == BOUNDARY_OUTER_BIND_KEYWORD:
            continue
        if keyword.arg == BOUNDARY_EXPLICIT_BIND_KEYWORD:
            keyword.value = ast.Constant(value=True)
            kept_keywords.append(keyword)
            saw_bound = True
            continue
        kept_keywords.append(keyword)
    if not saw_bound:
        kept_keywords.append(
            ast.keyword(
                arg=BOUNDARY_EXPLICIT_BIND_KEYWORD,
                value=ast.Constant(value=True),
            )
        )
    call.keywords = kept_keywords


@dataclass(frozen=True)
class PortTemplate:
    """Port parameters contributed by a marker at a single occurrence.

    Each `MarkerSpec` that contributes to demand/supply ports returns
    one of these (or `None`) from `demand_template` / `supply_template`.
    The model's `extract_demand_ports` / `extract_supply_ports` then
    builds the actual `DemandPort` / `SupplyPort` by pairing the
    template with the marker's `name_id` (and derives `placement` from
    `shape`). This keeps the per-marker knowledge on the marker spec
    rather than in a giant `if/elif` chain.
    """

    shape: MarkerShape
    mutability: PortMutability
    origin: PortOrigin


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

    def is_boundary_declaration_directive(self) -> bool:
        """True for non-emitting import/export-style boundary directives."""
        return False

    def is_expression_prefix_directive(self) -> bool:
        """True for statement-prefix directives allowed before an authored
        expression payload."""
        return False

    def is_payload_carrier(self) -> bool:
        """True for authored payload carriers such as `astichi_funcargs(...)`."""
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

    def demand_template(self, marker: "RecognizedMarker") -> PortTemplate | None:
        """Return the demand-port contribution for a recognised occurrence.

        Markers that don't contribute a demand port (hygiene directives,
        binding-only markers, supply-only markers) return `None`.
        """
        return None

    def supply_template(self, marker: "RecognizedMarker") -> PortTemplate | None:
        """Return the supply-port contribution for a recognised occurrence."""
        return None

    def metadata_name_nodes(self, marker: "RecognizedMarker") -> tuple[ast.Name, ...]:
        """Return marker-owned name nodes that are not runtime loads."""
        node = marker.node
        if not isinstance(node, ast.Call):
            return ()
        if not self.is_name_bearing() or not node.args:
            return ()
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Name):
            return (first_arg,)
        return ()

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
        boundary_declaration_directive: bool = False,
        expression_prefix_directive: bool = False,
        renamed_per_iteration: bool = False,
        iter_rename_arg_index: int = 0,
        demand_template: PortTemplate | None = None,
        supply_template: PortTemplate | None = None,
    ) -> None:
        self.source_name = source_name
        self._positional_args = positional_args
        self._name_bearing = name_bearing
        self._decorator_only = decorator_only
        self._hygiene_directive = hygiene_directive
        self._boundary_declaration_directive = boundary_declaration_directive
        self._expression_prefix_directive = expression_prefix_directive
        self._renamed_per_iteration = renamed_per_iteration
        self._iter_rename_arg_index = iter_rename_arg_index
        self._demand_template = demand_template
        self._supply_template = supply_template

    def is_decorator_only(self) -> bool:
        return self._decorator_only

    def is_name_bearing(self) -> bool:
        return self._name_bearing

    def is_hygiene_directive(self) -> bool:
        return self._hygiene_directive

    def is_boundary_declaration_directive(self) -> bool:
        return self._boundary_declaration_directive

    def is_expression_prefix_directive(self) -> bool:
        return self._expression_prefix_directive

    def is_renamed_per_iteration(self) -> bool:
        return self._renamed_per_iteration

    def iter_rename_arg_index(self) -> int:
        if not self._renamed_per_iteration:
            return super().iter_rename_arg_index()
        return self._iter_rename_arg_index

    def demand_template(self, marker: "RecognizedMarker") -> PortTemplate | None:
        return self._demand_template

    def supply_template(self, marker: "RecognizedMarker") -> PortTemplate | None:
        return self._supply_template

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


class _ReservedMarker(MarkerSpec):
    """Known marker name with no supported user-facing semantics."""

    def __init__(self, source_name: str, *, hint: str) -> None:
        self.source_name = source_name
        self._hint = hint

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Call):
            raise TypeError(f"{self.source_name} must be recognized from an ast.Call")
        raise ValueError(
            f"{self.source_name}(...) is reserved and obsolete; {self._hint}"
        )


class _BoundaryIdentifierMarker(_SimpleMarker):
    """Boundary identifier marker with explicit state keywords."""

    def validate_node(self, node: ast.AST) -> None:
        super().validate_node(node)
        assert isinstance(node, ast.Call)
        seen: set[str] = set()
        for keyword in node.keywords:
            if keyword.arg not in BOUNDARY_STATE_KEYWORDS:
                raise ValueError(
                    f"{self.source_name}(...) does not accept keyword `{keyword.arg}`; "
                    f"only `{BOUNDARY_OUTER_BIND_KEYWORD}=True|False` and "
                    f"`{BOUNDARY_EXPLICIT_BIND_KEYWORD}=True|False` are allowed"
                )
            if keyword.arg in seen:
                raise ValueError(
                    f"{self.source_name}(...) received duplicate keyword `{keyword.arg}`"
                )
            seen.add(keyword.arg)
            _boundary_keyword_bool(keyword)
        if (
            boundary_outer_bind_enabled(node)
            and boundary_explicit_bind_enabled(node)
        ):
            raise ValueError(
                f"{self.source_name}(...) may not combine "
                f"`{BOUNDARY_OUTER_BIND_KEYWORD}=True` with "
                f"`{BOUNDARY_EXPLICIT_BIND_KEYWORD}=True`"
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

    def validate_node(self, node: ast.AST) -> None:
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                raise ValueError(
                    f"{self.source_name} is not valid on relative import levels"
                )
            for segment in node.module.split("."):
                base_name, suffix_marker = strip_identifier_suffix(segment)
                if suffix_marker is self and base_name.isidentifier():
                    return
            raise ValueError(
                f"{self.source_name} requires an identifier prefix before {self.suffix}"
            )
        if isinstance(node, ast.alias):
            candidates = [node.name]
            if node.asname is not None:
                candidates.append(node.asname)
            for candidate in candidates:
                base_name, suffix_marker = strip_identifier_suffix(candidate)
                if suffix_marker is self and base_name.isidentifier():
                    return
            raise ValueError(
                f"{self.source_name} requires an identifier prefix before {self.suffix}"
            )
        super().validate_node(node)

    def demand_template(self, marker: "RecognizedMarker") -> PortTemplate | None:
        return PortTemplate(
            shape=IDENTIFIER, mutability=CONST_MUTABILITY, origin=ARG_IDENTIFIER_ORIGIN
        )


class _ParamHoleIdentifierMarker(_SuffixIdentifierMarker):
    """`name__astichi_param_hole__` — function parameter-list insertion target."""

    source_name = "astichi_param_hole_identifier"
    suffix = "__astichi_param_hole__"

    def is_definitional_site(self) -> bool:
        return False

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, ast.arg):
            raise TypeError(
                f"{self.source_name} must be recognized from a function parameter"
            )
        if not node.arg.endswith(self.suffix):
            raise ValueError(
                f"{self.source_name} requires the reserved {self.suffix} suffix"
            )
        base_name = node.arg[: -len(self.suffix)]
        if not base_name.isidentifier():
            raise ValueError(
                f"{self.source_name} requires an identifier prefix before {self.suffix}"
            )

    def demand_template(self, marker: "RecognizedMarker") -> PortTemplate | None:
        return PortTemplate(
            shape=PARAMETER, mutability=CONST_MUTABILITY, origin=PARAMETER_HOLE_ORIGIN
        )


class _HoleMarker(_SimpleMarker):
    """`astichi_hole(name)` — demand-port with shape inferred at recognition."""

    def __init__(self) -> None:
        super().__init__(
            "astichi_hole",
            positional_args=1,
            name_bearing=True,
            # Unroll renames the target per iteration (UnrollRevision §4.1),
            # so N copies produce disambiguated targets rather than a
            # conflict.
            renamed_per_iteration=True,
        )

    def demand_template(self, marker: "RecognizedMarker") -> PortTemplate | None:
        assert marker.shape is not None, (
            "astichi_hole occurrences must carry a shape by recognition time"
        )
        return PortTemplate(
            shape=marker.shape, mutability=CONST_MUTABILITY, origin=HOLE_ORIGIN
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

    def supply_template(self, marker: "RecognizedMarker") -> PortTemplate | None:
        # Only the expression-form (call context) contributes a supply
        # port. Decorator-form inserts are block shells that are matched
        # by the flatten pass, not by port wiring.
        if not marker.context.is_call_context():
            return None
        return PortTemplate(
            shape=SCALAR_EXPR, mutability=CONST_MUTABILITY, origin=INSERT_ORIGIN
        )

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
        for keyword in node.keywords:
            if keyword.arg == "ref":
                if len(node.args) != 1:
                    raise ValueError(
                        "astichi_insert ref= is only valid on decorator-form shells"
                    )
                parse_ref_path_literal(keyword.value)
                continue
            if keyword.arg == "kind":
                if len(node.args) != 1:
                    raise ValueError(
                        "astichi_insert kind= is only valid on decorator-form shells"
                    )
                if not isinstance(keyword.value, ast.Constant) or keyword.value.value not in {
                    "block",
                    "params",
                }:
                    raise ValueError(
                        "astichi_insert kind= must be the literal string 'block' or 'params'"
                    )
                continue
            if keyword.arg == "order":
                if not isinstance(keyword.value, ast.Constant) or not isinstance(
                    keyword.value.value, int
                ):
                    raise ValueError("astichi_insert order must be an integer constant")
                continue
            if keyword.arg == "pyimport":
                if len(node.args) != 2:
                    raise ValueError(
                        "astichi_insert pyimport= is only valid on expression-form inserts"
                    )
                if not isinstance(keyword.value, ast.Tuple):
                    raise ValueError("astichi_insert pyimport= must be a tuple")
                for element in keyword.value.elts:
                    if not (
                        isinstance(element, ast.Call)
                        and isinstance(element.func, ast.Name)
                        and element.func.id == PYIMPORT.source_name
                    ):
                        raise ValueError(
                            "astichi_insert pyimport= entries must be astichi_pyimport(...) calls"
                        )
                continue
            raise ValueError(
                f"astichi_insert does not accept keyword `{keyword.arg}`"
            )


class _FuncArgsMarker(MarkerSpec):
    """Authored call-argument payload surface."""

    source_name = "astichi_funcargs"

    def is_payload_carrier(self) -> bool:
        return True

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Call):
            raise TypeError("astichi_funcargs must be recognized from an ast.Call")


class _ParamsMarker(MarkerSpec):
    """Authored function-parameter payload surface."""

    source_name = "astichi_params"

    def accepts_call_context(self, node: ast.Call) -> bool:
        return False

    def accepts_decorator_context(self, node: ast.Call) -> bool:
        return False

    def is_name_bearing(self) -> bool:
        return True

    def is_payload_carrier(self) -> bool:
        return True

    def supply_template(self, marker: "RecognizedMarker") -> PortTemplate | None:
        return PortTemplate(
            shape=PARAMETER, mutability=CONST_MUTABILITY, origin=PARAMETER_PAYLOAD_ORIGIN
        )

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise TypeError("astichi_params must be recognized from a function definition")
        if node.name != self.source_name:
            raise ValueError("astichi_params payload function must be named astichi_params")


class _RefMarker(MarkerSpec):
    """`astichi_ref(value)` — value-form reference path lowering.

    See `AstichiV3ExternalRefBind.m4` and `apply_external_ref_lowering`
    in `lowering.external_ref` for the lowering pass.
    """

    source_name = "astichi_ref"

    def is_payload_carrier(self) -> bool:
        return True

    def is_permitted_in_unroll_body(self) -> bool:
        return True

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Call):
            raise TypeError("astichi_ref must be recognized from an ast.Call")
        positional = len(node.args)
        keywords = list(node.keywords)
        if positional == 0 and not keywords:
            raise ValueError("astichi_ref(...) requires either a positional value or external=name")
        if positional > 1:
            raise ValueError("astichi_ref(...) accepts at most one positional argument")
        # Only `external=` is recognised as a keyword; reject other kwargs.
        for keyword in keywords:
            if keyword.arg != "external":
                raise ValueError(
                    f"astichi_ref(...) does not accept keyword `{keyword.arg}`; "
                    "only `external=name` is allowed"
                )
        if any(kw.arg is None for kw in keywords):
            raise ValueError("astichi_ref(...) does not accept **kwargs")
        if positional == 1 and any(kw.arg == "external" for kw in keywords):
            raise ValueError(
                "astichi_ref(...) accepts either a positional argument or "
                "`external=name`, not both"
            )
        # `external=` must point at a bare identifier.
        for keyword in keywords:
            if keyword.arg == "external":
                if not isinstance(keyword.value, ast.Name):
                    raise ValueError(
                        "astichi_ref(external=...) must reference a bare "
                        "identifier (the name of an external bind slot); "
                        f"got {type(keyword.value).__name__}"
                    )


class _PyImportMarker(MarkerSpec):
    """`astichi_pyimport(...)` — managed Python import declaration."""

    source_name = "astichi_pyimport"

    def is_expression_prefix_directive(self) -> bool:
        return True

    def is_permitted_in_unroll_body(self) -> bool:
        return False

    def metadata_name_nodes(self, marker: "RecognizedMarker") -> tuple[ast.Name, ...]:
        node = marker.node
        if not isinstance(node, ast.Call):
            return ()
        nodes: list[ast.Name] = []
        for keyword in node.keywords:
            if keyword.arg == "module":
                for child in ast.walk(keyword.value):
                    if isinstance(child, ast.Name):
                        nodes.append(child)
                continue
            if keyword.arg == "names":
                value = keyword.value
                if isinstance(value, ast.Tuple):
                    nodes.extend(
                        elt for elt in value.elts if isinstance(elt, ast.Name)
                    )
                continue
            if keyword.arg == "as_" and isinstance(keyword.value, ast.Name):
                nodes.append(keyword.value)
        return tuple(nodes)

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Call):
            raise TypeError("astichi_pyimport must be recognized from an ast.Call")
        if node.args:
            raise ValueError(
                "astichi_pyimport(...) accepts keyword arguments only"
            )
        seen: set[str] = set()
        for keyword in node.keywords:
            if keyword.arg is None:
                raise ValueError("astichi_pyimport(...) does not accept **kwargs")
            if keyword.arg not in {"module", "names", "as_"}:
                raise ValueError(
                    f"astichi_pyimport(...) does not accept keyword `{keyword.arg}`"
                )
            if keyword.arg in seen:
                raise ValueError(
                    f"astichi_pyimport(...) received duplicate keyword `{keyword.arg}`"
                )
            seen.add(keyword.arg)
        if "module" not in seen:
            raise ValueError("astichi_pyimport(...) requires module=...")
        if "names" in seen and "as_" in seen:
            raise ValueError(
                "astichi_pyimport(...) may not combine names= with as_="
            )


class _CommentMarker(MarkerSpec):
    """`astichi_comment("...")` — statement-only final-output comment."""

    source_name = "astichi_comment"

    def is_permitted_in_unroll_body(self) -> bool:
        return True

    def validate_node(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Call):
            raise TypeError("astichi_comment must be recognized from an ast.Call")
        if node.keywords:
            raise ValueError("astichi_comment(...) does not accept keyword arguments")
        if len(node.args) != 1:
            raise ValueError(
                "astichi_comment(...) expects exactly one positional string argument"
            )
        payload = node.args[0]
        if not isinstance(payload, ast.Constant) or not isinstance(payload.value, str):
            raise ValueError(
                "astichi_comment(...) requires a literal string argument"
            )


HOLE = _HoleMarker()
BIND_ONCE = _ReservedMarker(
    "astichi_bind_once",
    hint="use ordinary Python assignment for single-evaluation reuse",
)
BIND_SHARED = _ReservedMarker(
    "astichi_bind_shared",
    hint=(
        "use enclosing Python state plus astichi_import/astichi_pass/"
        "astichi_export or builder.assign for shared state"
    ),
)
BIND_EXTERNAL = _SimpleMarker(
    "astichi_bind_external",
    positional_args=1,
    name_bearing=True,
    demand_template=PortTemplate(
        shape=SCALAR_EXPR, mutability=CONST_MUTABILITY, origin=BIND_EXTERNAL_ORIGIN
    ),
)
KEEP = _SimpleMarker(
    "astichi_keep",
    positional_args=1,
    name_bearing=True,
    hygiene_directive=True,
    expression_prefix_directive=True,
)
EXPORT = _SimpleMarker(
    "astichi_export",
    positional_args=1,
    name_bearing=True,
    boundary_declaration_directive=True,
    expression_prefix_directive=True,
    supply_template=PortTemplate(
        shape=SCALAR_EXPR, mutability=CONST_MUTABILITY, origin=EXPORT_ORIGIN
    ),
)
FOR = _SimpleMarker("astichi_for", positional_args=1)
FUNCARGS = _FuncArgsMarker()
PARAMS = _ParamsMarker()
INSERT = _InsertMarker()
REF = _RefMarker()
PYIMPORT = _PyImportMarker()
COMMENT = _CommentMarker()
KEEP_IDENTIFIER = _KeepIdentifierMarker()
ARG_IDENTIFIER = _ArgIdentifierMarker()
PARAM_HOLE_IDENTIFIER = _ParamHoleIdentifierMarker()
# Issue 006: `astichi_import(name)` is the declaration-form
# identifier-threading surface; `astichi_pass(name)` is the value-form
# surface. Import participates in the top-prefix boundary-declaration
# rule; pass contributes an IDENTIFIER demand and is resolved later as a
# value expression.
IMPORT = _BoundaryIdentifierMarker(
    "astichi_import",
    positional_args=1,
    name_bearing=True,
    boundary_declaration_directive=True,
    expression_prefix_directive=True,
    demand_template=PortTemplate(
        shape=IDENTIFIER, mutability=CONST_MUTABILITY, origin=IMPORT_ORIGIN
    ),
)
PASS = _BoundaryIdentifierMarker(
    "astichi_pass",
    positional_args=1,
    name_bearing=True,
    demand_template=PortTemplate(
        shape=IDENTIFIER, mutability=CONST_MUTABILITY, origin=PASS_ORIGIN
    ),
)

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
    FUNCARGS,
    PARAMS,
    INSERT,
    REF,
    PYIMPORT,
    COMMENT,
    KEEP_IDENTIFIER,
    ARG_IDENTIFIER,
    PARAM_HOLE_IDENTIFIER,
    IMPORT,
    PASS,
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
    context: MarkerContext
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
            if self.spec is PARAMS and isinstance(self.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return self.node.name
            base, suffix_marker = strip_identifier_suffix(self.node.name)
            if suffix_marker is not None:
                return base
        if isinstance(self.node, ast.Name):
            # Issue 005 §2: identifier-shape demands collect occurrences
            # from every binding position, including `ast.Name` in
            # Load/Store/Del context.
            base, suffix_marker = strip_identifier_suffix(self.node.id)
            if suffix_marker is not None:
                return base
        if isinstance(self.node, ast.arg):
            base, suffix_marker = strip_identifier_suffix(self.node.arg)
            if suffix_marker is not None:
                return base
        if isinstance(self.node, ast.keyword) and self.node.arg is not None:
            # Issue 005 §1 extension: call-site keyword-argument names
            # are identifier positions too. `keyword.arg is None` is the
            # `**mapping` splat form, which carries no identifier slot.
            base, suffix_marker = strip_identifier_suffix(self.node.arg)
            if suffix_marker is not None:
                return base
        if isinstance(self.node, ast.ImportFrom) and self.node.module is not None:
            for segment in self.node.module.split("."):
                base, suffix_marker = strip_identifier_suffix(segment)
                if suffix_marker is not None:
                    return base
        if isinstance(self.node, ast.alias):
            base, suffix_marker = strip_identifier_suffix(self.node.name)
            if suffix_marker is not None:
                return base
            if self.node.asname is not None:
                base, suffix_marker = strip_identifier_suffix(self.node.asname)
                if suffix_marker is not None:
                    return base
        return None


@dataclass(frozen=True)
class StatementPrefixScan:
    """Direct statement-form marker prefix scan result."""

    body: tuple[ast.stmt, ...]
    prefix_statements: tuple[ast.Expr, ...]
    first_non_prefix_index: int


def marker_metadata_name_nodes(
    markers: Iterable[RecognizedMarker],
) -> tuple[ast.Name, ...]:
    """Return marker-owned name nodes that should not count as runtime loads."""
    nodes: list[ast.Name] = []
    for marker in markers:
        if isinstance(marker.node, ast.Call):
            if isinstance(marker.node.func, ast.Name):
                nodes.append(marker.node.func)
            nodes.extend(marker.spec.metadata_name_nodes(marker))
            if marker.source_name == "astichi_insert":
                for keyword in marker.node.keywords:
                    if keyword.arg != "ref":
                        continue
                    for child in ast.walk(keyword.value):
                        if isinstance(child, ast.Name):
                            nodes.append(child)
    return tuple(nodes)


def marker_metadata_name_node_ids(
    markers: Iterable[RecognizedMarker],
) -> set[int]:
    """Return id-set form for callers that compare AST nodes by identity."""
    return {id(node) for node in marker_metadata_name_nodes(markers)}


def scan_statement_prefix(
    body: Sequence[ast.stmt],
    *,
    allowed_specs: Container[MarkerSpec],
) -> StatementPrefixScan:
    """Scan direct statement-form marker calls at the start of a body.

    This is a classifier, not marker recognition: it matches direct calls by
    registered marker singleton identity and does not re-validate call shape.
    """
    prefix: list[ast.Expr] = []
    allowed_ids = {id(spec) for spec in allowed_specs}
    index = 0
    while index < len(body):
        statement = body[index]
        if not isinstance(statement, ast.Expr):
            break
        value = statement.value
        if not isinstance(value, ast.Call):
            break
        marker = _marker_from_call(value)
        if marker is None or id(marker) not in allowed_ids:
            break
        prefix.append(statement)
        index += 1
    return StatementPrefixScan(
        body=tuple(body),
        prefix_statements=tuple(prefix),
        first_non_prefix_index=index,
    )


def _marker_from_call(node: ast.Call) -> MarkerSpec | None:
    marker_name = call_name(node)
    if marker_name is None:
        return None
    return MARKERS_BY_NAME.get(marker_name)


def call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Name):
        return None
    return node.func.id


def is_call_to_marker(node: ast.AST, marker: MarkerSpec) -> bool:
    return call_name(node) == marker.source_name


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
                    context=CALL_CONTEXT,
                    shape=shape,
                )
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_params_payload(node)
        self._visit_suffix_identifier(node)
        self._visit_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_params_payload(node)
        self._visit_suffix_identifier(node)
        self._visit_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_suffix_identifier(node)
        self._visit_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        # Issue 005 §1: identifier-shape slots collect every occurrence
        # of the suffixed name, including Load/Store/Del references, so
        # the arg gate and the resolver pass see the full set.
        self._visit_identifier_occurrence(node, node.id)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        # Issue 005 §1: parameter-position suffixed names are slot
        # occurrences too.
        self._visit_identifier_occurrence(node, node.arg)
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        # Issue 005 §1 extension: call-site keyword-argument names are
        # identifier positions. `keyword.arg is None` is the `**mapping`
        # splat form and carries no identifier; skip it.
        if node.arg is not None:
            self._visit_identifier_occurrence(node, node.arg)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._visit_import_alias_occurrences(alias)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is not None:
            for segment in node.module.split("."):
                if self._identifier_suffix_marker(segment) is not None:
                    self._visit_identifier_occurrence(node, segment)
                    break
        for alias in node.names:
            self._visit_import_alias_occurrences(alias)
        self.generic_visit(node)

    def _visit_import_alias_occurrences(self, node: ast.alias) -> None:
        self._visit_identifier_occurrence(node, node.name)
        if node.asname is not None:
            self._visit_identifier_occurrence(node, node.asname)

    def _visit_identifier_occurrence(
        self, node: ast.AST, name: str
    ) -> None:
        _, suffix_marker = strip_identifier_suffix(name)
        if suffix_marker is None:
            return
        if suffix_marker is PARAM_HOLE_IDENTIFIER:
            suffix_marker.validate_node(node)
        self.markers.append(
            RecognizedMarker(
                spec=suffix_marker,
                node=node,
                context=IDENTIFIER_CONTEXT,
                shape=None,
            )
        )

    def _identifier_suffix_marker(self, name: str) -> MarkerSpec | None:
        _, suffix_marker = strip_identifier_suffix(name)
        return suffix_marker

    def _visit_params_payload(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.name != PARAMS.source_name:
            return
        PARAMS.validate_node(node)
        self.markers.append(
            RecognizedMarker(
                spec=PARAMS,
                node=node,
                context=DEFINITIONAL_CONTEXT,
                shape=None,
            )
        )

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
                    context=DECORATOR_CONTEXT,
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
                context=DEFINITIONAL_CONTEXT,
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
