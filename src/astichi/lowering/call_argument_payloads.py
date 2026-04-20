"""Recognition and validation for ``astichi_funcargs(...)`` payload snippets."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
from typing import Callable, Literal

from astichi.ast_provenance import propagate_ast_source_locations
from astichi.lowering.markers import (
    BIND_EXTERNAL,
    EXPORT,
    FUNCARGS,
    IMPORT,
    MarkerSpec,
    PASS,
    call_name,
    is_call_to_marker,
)

_DIRECTIVE_SPECS: tuple[MarkerSpec, ...] = (IMPORT, EXPORT)


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


FuncArgRegion = Literal["plain", "starred", "dstar"]


def is_astichi_funcargs_call(node: ast.AST) -> bool:
    """Whether ``node`` is an ``astichi_funcargs(...)`` call."""
    return is_call_to_marker(node, FUNCARGS)


def direct_funcargs_directive_calls(call: ast.Call) -> tuple[ast.Call, ...]:
    """Return direct special ``_=astichi_import/export(...)`` carriers in order."""
    directives: list[ast.Call] = []
    for keyword in call.keywords:
        if keyword.arg != "_" or not isinstance(keyword.value, ast.Call):
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
    items: list[FuncArgPayloadItem] = []
    for arg in call.args:
        if isinstance(arg, ast.Starred):
            items.append(StarredFuncArgItem(expr=copy.deepcopy(arg.value)))
            continue
        items.append(PositionalFuncArgItem(expr=copy.deepcopy(arg)))
    for keyword in call.keywords:
        if keyword.arg == "_":
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
    if (
        len(calls) != 1
        or len(tree.body) != 1
        or not isinstance(tree.body[0], ast.Expr)
        or tree.body[0].value is not calls[0]
    ):
        raise ValueError(
            "astichi_funcargs(...) must appear as the only top-level expression "
            "statement in a call-argument payload snippet"
        )
    _validate_funcargs_call(calls[0])


def _validate_funcargs_call(call: ast.Call) -> None:
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
                "direct _= carriers inside astichi_funcargs(...)"
            )
    for keyword in call.keywords:
        value = keyword.value
        if keyword.arg == "_":
            if _is_direct_directive_call(value):
                continue
            if call_name(value) == PASS.source_name:
                raise ValueError(
                    "astichi_pass(...) is not valid in _= inside "
                    "astichi_funcargs(...); use it in a real argument "
                    "expression instead"
                )
            if _contains_non_value_directive(value):
                raise ValueError(
                    "astichi_import(...) / astichi_export(...) must be direct "
                    "_= carriers inside astichi_funcargs(...); wrapped forms "
                    "are not supported"
                )
            continue
        if _contains_non_value_directive(value):
            raise ValueError(
                "astichi_import(...) / astichi_export(...) are only valid as "
                "direct _= carriers inside astichi_funcargs(...)"
            )


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
        if region == "plain":
            continue
        if region == "starred" and isinstance(
            item, (PositionalFuncArgItem, StarredFuncArgItem)
        ):
            continue
        if region == "dstar" and isinstance(
            item, (KeywordFuncArgItem, DoubleStarFuncArgItem)
        ):
            continue
        if region == "starred":
            raise ValueError(
                f"starred target {hole_name} rejects keyword / **mapping payload items"
            )
        raise ValueError(
            f"double-starred target {hole_name} rejects positional / starred payload items"
        )

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
