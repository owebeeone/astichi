"""Recognition and validation for ``astichi_funcargs(...)`` payload snippets."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
from typing import Callable

from astichi.ast_provenance import propagate_ast_source_locations
from astichi.lowering.markers import (
    BIND_EXTERNAL,
    EXPORT,
    FUNCARGS,
    IMPORT,
    MarkerSpec,
    call_name,
    is_call_to_marker,
)
from astichi.lowering.payload_prefix import (
    single_payload_expression_after_boundary_prefix,
)
from astichi.model.semantics import SemanticSingleton

_DIRECTIVE_SPECS: tuple[MarkerSpec, ...] = (IMPORT, EXPORT)
_DIRECTIVE_PLACEHOLDER_PREFIX = "__astichi_ph_"
_DIRECTIVE_PLACEHOLDER_SUFFIX = "__"


@dataclass(frozen=True)
class FuncArgPayloadItem:
    """Base payload item for one authored ``astichi_funcargs(...)`` entry."""


@dataclass(frozen=True)
class PositionalFuncArgItem(FuncArgPayloadItem):
    expr: ast.expr


@dataclass(frozen=True)
class StarredFuncArgItem(FuncArgPayloadItem):
    expr: ast.expr


@dataclass(frozen=True)
class KeywordFuncArgItem(FuncArgPayloadItem):
    name: str
    expr: ast.expr


@dataclass(frozen=True)
class DoubleStarFuncArgItem(FuncArgPayloadItem):
    expr: ast.expr


@dataclass(frozen=True)
class DirectiveFuncArgItem(FuncArgPayloadItem):
    directive_name: str
    name: str
    call: ast.Call


@dataclass(frozen=True)
class FuncArgPayload:
    items: tuple[FuncArgPayloadItem, ...]


@dataclass(frozen=True)
class PayloadLocalDirective:
    spec: MarkerSpec
    name: str


class FuncArgRegion(SemanticSingleton):
    """Target region for authored call-argument payloads."""

    def accepts_payload_item(self, item: FuncArgPayloadItem) -> bool:
        return False

    def rejects_message(self, hole_name: str) -> str:
        return f"call-argument target {hole_name} rejects payload item"


@dataclass(frozen=True, eq=False)
class _PlainFuncArgRegion(FuncArgRegion):
    name: str = "plain"

    def accepts_payload_item(self, item: FuncArgPayloadItem) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _StarredFuncArgRegion(FuncArgRegion):
    name: str = "starred"

    def accepts_payload_item(self, item: FuncArgPayloadItem) -> bool:
        return isinstance(item, (PositionalFuncArgItem, StarredFuncArgItem))

    def rejects_message(self, hole_name: str) -> str:
        return f"starred target {hole_name} rejects keyword / **mapping payload items"


@dataclass(frozen=True, eq=False)
class _DoubleStarFuncArgRegion(FuncArgRegion):
    name: str = "dstar"

    def accepts_payload_item(self, item: FuncArgPayloadItem) -> bool:
        return isinstance(item, (KeywordFuncArgItem, DoubleStarFuncArgItem))

    def rejects_message(self, hole_name: str) -> str:
        return (
            f"double-starred target {hole_name} rejects positional / "
            "starred payload items"
        )


PLAIN_FUNC_ARG_REGION = _PlainFuncArgRegion()
STARRED_FUNC_ARG_REGION = _StarredFuncArgRegion()
DOUBLE_STAR_FUNC_ARG_REGION = _DoubleStarFuncArgRegion()


def is_astichi_funcargs_call(node: ast.AST) -> bool:
    """Whether ``node`` is an ``astichi_funcargs(...)`` call."""
    return is_call_to_marker(node, FUNCARGS)


def direct_funcargs_directive_calls(call: ast.Call) -> tuple[ast.Call, ...]:
    """Return direct special placeholder import/export carriers in order."""
    directives: list[ast.Call] = []
    for keyword in call.keywords:
        if (
            keyword.arg is None
            or _directive_placeholder_index(keyword.arg) is None
            or not isinstance(keyword.value, ast.Call)
        ):
            continue
        spec = _directive_spec(keyword.value)
        if spec is not None:
            directives.append(keyword.value)
    return tuple(directives)


def collect_payload_local_directives(
    tree: ast.Module,
) -> tuple[PayloadLocalDirective, ...]:
    directives: list[PayloadLocalDirective] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not is_astichi_funcargs_call(node):
            continue
        for directive in direct_funcargs_directive_calls(node):
            spec = _require_directive_spec(directive)
            directives.append(
                PayloadLocalDirective(
                    spec=spec,
                    name=_validated_name_arg(directive, spec),
                )
            )
    return tuple(directives)


def extract_funcargs_payload(call: ast.Call) -> FuncArgPayload:
    """Extract one authored ``astichi_funcargs(...)`` call into a payload model."""
    if not is_astichi_funcargs_call(call):
        raise TypeError("extract_funcargs_payload expects an astichi_funcargs(...) call")
    _validate_funcargs_call(call)
    items: list[FuncArgPayloadItem] = []
    for arg in call.args:
        if isinstance(arg, ast.Starred):
            items.append(StarredFuncArgItem(expr=copy.deepcopy(arg.value)))
            continue
        items.append(PositionalFuncArgItem(expr=copy.deepcopy(arg)))
    for keyword in call.keywords:
        if keyword.arg is not None and _directive_placeholder_index(keyword.arg) is not None:
            directive_spec = _directive_spec(keyword.value)
        else:
            directive_spec = None
        if directive_spec is not None:
            assert isinstance(keyword.value, ast.Call)
            items.append(
                DirectiveFuncArgItem(
                    directive_name=directive_spec.source_name,
                    name=_validated_name_arg(keyword.value, directive_spec),
                    call=copy.deepcopy(keyword.value),
                )
            )
            continue
        if keyword.arg is None:
            items.append(DoubleStarFuncArgItem(expr=copy.deepcopy(keyword.value)))
            continue
        items.append(
            KeywordFuncArgItem(
                name=keyword.arg,
                expr=copy.deepcopy(keyword.value),
            )
        )
    return FuncArgPayload(items=tuple(items))


def validate_call_argument_payload_surface(tree: ast.Module) -> None:
    """Reject malformed or misplaced ``astichi_funcargs(...)`` payload snippets."""
    calls = [node for node in ast.walk(tree) if is_astichi_funcargs_call(node)]
    if not calls:
        return
    payload_statement = single_payload_expression_after_boundary_prefix(tree.body)
    if len(calls) != 1 or payload_statement is None or payload_statement.value is not calls[0]:
        raise ValueError(
            "astichi_funcargs(...) must appear as the only non-prefix top-level "
            "expression statement in a call-argument payload snippet"
        )
    _validate_funcargs_call(calls[0])


def _validate_funcargs_call(call: ast.Call) -> None:
    _validate_directive_placeholders(call)
    directive_names = {
        _validated_name_arg(directive, _require_directive_spec(directive))
        for directive in direct_funcargs_directive_calls(call)
    }
    bind_external_names = {
        _validated_name_arg(child, BIND_EXTERNAL)
        for child in ast.walk(call)
        if isinstance(child, ast.Call) and is_call_to_marker(child, BIND_EXTERNAL)
    }
    for name in sorted(directive_names & bind_external_names):
        raise ValueError(
            "payload-local astichi_import/export and astichi_bind_external may "
            f"not share the same name `{name}` inside astichi_funcargs(...)"
        )
    for arg in call.args:
        if _contains_non_value_directive(arg):
            raise ValueError(
                "astichi_import(...) / astichi_export(...) are only valid as "
                "direct __astichi_ph_{N}__= carriers inside astichi_funcargs(...)"
            )
    for keyword in call.keywords:
        value = keyword.value
        if keyword.arg is not None and _directive_placeholder_index(keyword.arg) is not None:
            continue
        if _contains_non_value_directive(value):
            raise ValueError(
                "astichi_import(...) / astichi_export(...) are only valid as "
                "direct __astichi_ph_{N}__= carriers inside astichi_funcargs(...)"
            )


def _validate_directive_placeholders(call: ast.Call) -> None:
    indexes: list[int] = []
    for keyword in call.keywords:
        if keyword.arg is None:
            continue
        if keyword.arg == "_":
            raise ValueError(
                "keyword `_` is reserved inside astichi_funcargs(...); use "
                "__astichi_ph_{N}__=astichi_import/export(...) for payload-local "
                "directives"
            )
        if keyword.arg.startswith(_DIRECTIVE_PLACEHOLDER_PREFIX):
            index = _directive_placeholder_index(keyword.arg)
            if index is None:
                raise ValueError(
                    "astichi_funcargs directive placeholder names must match "
                    "__astichi_ph_{N}__"
                )
            if not _is_direct_directive_call(keyword.value):
                raise ValueError(
                    "astichi_funcargs directive placeholders may only carry direct "
                    "astichi_import(...) or astichi_export(...) calls"
                )
            indexes.append(index)
    expected = list(range(len(indexes)))
    if indexes != expected:
        raise ValueError(
            "astichi_funcargs directive placeholders must be contiguous and ordered "
            "from __astichi_ph_0__"
        )


def _directive_placeholder_index(name: str) -> int | None:
    if not (
        name.startswith(_DIRECTIVE_PLACEHOLDER_PREFIX)
        and name.endswith(_DIRECTIVE_PLACEHOLDER_SUFFIX)
    ):
        return None
    raw_index = name[
        len(_DIRECTIVE_PLACEHOLDER_PREFIX) : -len(_DIRECTIVE_PLACEHOLDER_SUFFIX)
    ]
    if not raw_index or not raw_index.isdecimal():
        return None
    if len(raw_index) > 1 and raw_index.startswith("0"):
        return None
    return int(raw_index)


def _contains_non_value_directive(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _directive_spec(child) is not None:
            return True
    return False


def _is_direct_directive_call(node: ast.AST) -> bool:
    return _directive_spec(node) is not None


def _directive_spec(node: ast.AST) -> MarkerSpec | None:
    marker_name = call_name(node)
    if marker_name is None:
        return None
    for spec in _DIRECTIVE_SPECS:
        if marker_name == spec.source_name:
            return spec
    return None


def _require_directive_spec(node: ast.AST) -> MarkerSpec:
    spec = _directive_spec(node)
    if spec is None:
        raise TypeError("expected a direct astichi_import/export directive call")
    return spec


def _validated_name_arg(call: ast.Call, spec: MarkerSpec) -> str:
    spec.validate_node(call)
    first_arg = call.args[0]
    if not isinstance(first_arg, ast.Name):
        raise TypeError(
            f"{spec.source_name} requires a bare identifier-like first argument"
        )
    return first_arg.id


def payload_explicit_keyword_names(payload: FuncArgPayload) -> tuple[str, ...]:
    return tuple(
        item.name for item in payload.items if isinstance(item, KeywordFuncArgItem)
    )


def register_explicit_keyword(name: str, seen: set[str]) -> None:
    if name in seen:
        raise ValueError(
            f"duplicate explicit keyword `{name}` in call-argument payloads"
        )
    seen.add(name)


def validate_payload_for_region(
    payload: FuncArgPayload,
    *,
    region: FuncArgRegion,
    hole_name: str,
    seen_explicit_keywords: set[str] | None = None,
) -> None:
    for item in payload.items:
        if isinstance(item, DirectiveFuncArgItem):
            continue
        if region.accepts_payload_item(item):
            continue
        raise ValueError(region.rejects_message(hole_name))

    if seen_explicit_keywords is None:
        return
    for name in payload_explicit_keyword_names(payload):
        register_explicit_keyword(name, seen_explicit_keywords)


def lower_payload_for_region(
    payload: FuncArgPayload,
    *,
    region: FuncArgRegion,
    hole_name: str,
    transform_expr: Callable[[ast.expr], ast.expr],
) -> tuple[list[ast.expr], list[ast.keyword]]:
    validate_payload_for_region(payload, region=region, hole_name=hole_name)

    positional: list[ast.expr] = []
    keywords: list[ast.keyword] = []
    for item in payload.items:
        if isinstance(item, DirectiveFuncArgItem):
            continue
        if isinstance(item, PositionalFuncArgItem):
            positional.append(transform_expr(item.expr))
            continue
        if isinstance(item, StarredFuncArgItem):
            inner = transform_expr(item.expr)
            starred = ast.Starred(value=inner, ctx=ast.Load())
            propagate_ast_source_locations(starred, item.expr)
            positional.append(starred)
            continue
        if isinstance(item, KeywordFuncArgItem):
            value = transform_expr(item.expr)
            kw = ast.keyword(arg=item.name, value=value)
            propagate_ast_source_locations(kw, item.expr)
            keywords.append(kw)
            continue
        if isinstance(item, DoubleStarFuncArgItem):
            value = transform_expr(item.expr)
            kw = ast.keyword(arg=None, value=value)
            propagate_ast_source_locations(kw, item.expr)
            keywords.append(kw)
            continue
        raise TypeError(f"unhandled funcarg payload item: {type(item).__name__}")
    return positional, keywords
