"""Lowering for `astichi_ref(...)` per `AstichiV3ExternalRefBind.m4`.

`astichi_ref` is a value-form marker that takes a Python reference path
expressed as a compile-time string and lowers it into the corresponding
`Name` / `Attribute` AST. The argument may be:

- a string literal (`astichi_ref("pkg.mod.attr")`),
- an f-string whose formatted parts reduce to compile-time literals
  (loop variables, externally bound values, or compile-time subscript
  lookups over those values),
- the `external=name` sugar — desugared at `compile()` time to
  `astichi_ref(astichi_bind_external(name))` so the bind site flows
  through the normal port machinery.

Two surface positions are supported:

1. value-form (§3): the call result fills any expression slot.
2. sentinel-attribute surface (§3a): wrapping the call as
   `astichi_ref(...).astichi_v` (or `.._`) makes it grammatically
   legal as an `Assign` / `AugAssign` / `Delete` target and is also a
   valid no-op in ordinary expression positions. The first immediate
   sentinel segment is stripped at materialize time and its `ctx`
   (`Load` / `Store` / `Del`) is propagated onto the lowered chain.

Lowering happens at materialize time, after `bind()` has substituted
`astichi_bind_external` calls and after `unroll_tree()` has substituted
loop-variable references. By then, every legal `astichi_ref(...)`
argument is reducible to a literal string with the restricted evaluator
defined here.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from astichi.lowering.sentinel_attrs import match_transparent_sentinel


@dataclass(frozen=True)
class _LowerError(ValueError):
    """Internal helper to attach a line number to lowering errors."""

    message: str
    lineno: int | None = None

    def __str__(self) -> str:  # pragma: no cover - dataclass repr fallback
        if self.lineno is None:
            return self.message
        return f"{self.message} (line {self.lineno})"


def desugar_external_ref_kwargs(tree: ast.AST) -> None:
    """Rewrite `astichi_ref(external=name)` -> `astichi_ref(astichi_bind_external(name))`.

    Runs at `compile()` time so the inner `astichi_bind_external` site
    is recognised by the normal marker pass and surfaces a demand port
    that `bind()` / the materialize gate can validate.

    Mutates `tree` in place.
    """
    _ExternalKwargRewriter().visit(tree)
    ast.fix_missing_locations(tree)


def apply_external_ref_lowering(tree: ast.Module) -> None:
    """Lower every `astichi_ref(...)` call (and §3a sentinel wrappers)
    into the corresponding `Name`/`Attribute` AST.

    Must run after external bindings and `astichi_for` unrolling have
    been applied so the `astichi_ref` argument is fully reducible. The
    caller owns deep-copying when immutable composable state must be
    preserved.
    """
    _RefLowerer().visit(tree)
    ast.fix_missing_locations(tree)


# ---------------------------------------------------------------------------
# §1 sugar: rewrite `external=name` to inner `astichi_bind_external(name)`
# ---------------------------------------------------------------------------


class _ExternalKwargRewriter(ast.NodeTransformer):
    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if not _is_astichi_ref_surface_call(node):
            return node
        external_kw: ast.keyword | None = None
        for keyword in node.keywords:
            if keyword.arg == "external":
                external_kw = keyword
                break
        if external_kw is None:
            return node
        # Markers.validate_node will already have rejected mixed forms,
        # extra kwargs, and non-Name external= values during marker
        # recognition. We keep a defensive check so direct callers that
        # bypass the marker visitor still get a clear diagnostic.
        if node.args:
            raise ValueError(
                "astichi_ref(...) accepts either a positional argument or "
                "`external=name`, not both"
            )
        for keyword in node.keywords:
            if keyword.arg != "external":
                raise ValueError(
                    f"astichi_ref(...) does not accept keyword `{keyword.arg}`"
                )
        if not isinstance(external_kw.value, ast.Name):
            raise ValueError(
                "astichi_ref(external=...) must reference a bare identifier "
                "(the name of an external bind slot)"
            )
        bind_call = ast.Call(
            func=ast.Name(id="astichi_bind_external", ctx=ast.Load()),
            args=[ast.Name(id=external_kw.value.id, ctx=ast.Load())],
            keywords=[],
        )
        ast.copy_location(bind_call, external_kw.value)
        ast.copy_location(bind_call.func, external_kw.value)
        ast.copy_location(bind_call.args[0], external_kw.value)
        node.args = [bind_call]
        node.keywords = []
        return node


# ---------------------------------------------------------------------------
# §3 / §3a: lower `astichi_ref(...)` and its sentinel-attribute wrapper
# ---------------------------------------------------------------------------


class _RefLowerer(ast.NodeTransformer):
    """Replace recognised `astichi_ref` shapes with lowered chains.

    Handled shapes:

    - sentinel wrapper (§3a): `Attribute(Call(astichi_ref...), SENTINEL)`
      — strip the wrapper once and propagate its `ctx` to the lowered
      chain.
    - value form (§3): `Call(astichi_ref...)` not wrapped by a sentinel
      attribute — lower as `Load`-context chain.

    Any non-sentinel attribute on a value-form ref (e.g.
    `astichi_ref("pkg.mod").other`) is left in place: the inner call
    is lowered to its chain, and the outer Attribute keeps its `attr`
    and `ctx` — so the final tree is a natural extension of the
    lowered path.
    """

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        sentinel = match_transparent_sentinel(
            node,
            is_marker_call=_is_astichi_ref_surface_call,
        )
        if sentinel is not None:
            chain = _lower_ref_surface_call_to_chain(sentinel.call, ctx=sentinel.ctx)
            return chain
        # Non-sentinel attribute access on a ref: lower the inner call
        # in Load context, then leave the outer Attribute alone.
        self.generic_visit(node)
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        # If this Call is the inner of a sentinel wrapper, the
        # `visit_Attribute` branch will already have rewritten the
        # whole subtree. So when the visitor reaches a bare
        # `astichi_ref(...)` Call here, lower it in Load context.
        # A `Call(Call(astichi_ref...), ...)` (calling the ref result)
        # is permitted — the inner ref call lowers normally.
        if _is_astichi_ref_surface_call(node):
            return _lower_ref_surface_call_to_chain(node, ctx=ast.Load())
        self.generic_visit(node)
        return node


def _is_base_astichi_ref_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "astichi_ref"
    )


def _contains_astichi_ref_surface(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        return _is_astichi_ref_surface_call(node)
    if isinstance(node, ast.Attribute):
        return _contains_astichi_ref_surface(node.value)
    return False


def _is_astichi_ref_surface_call(node: ast.AST) -> bool:
    if _is_base_astichi_ref_call(node):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "astichi_ref"
        and _contains_astichi_ref_surface(node.func.value)
    )


def _extract_ref_segments(call: ast.Call) -> tuple[str, ...]:
    if call.keywords or len(call.args) != 1:
        # `external=` should have been desugared at compile time. This
        # branch is reached for trees built outside the frontend (e.g.
        # programmatically) — surface the same diagnostic.
        raise ValueError(
            "astichi_ref(...) requires exactly one positional argument "
            "after `external=` desugar (call apply_external_ref_lowering "
            "after compile() has run)"
        )
    raw = _evaluate_path_expression(call.args[0])
    return _validate_path_string(raw, lineno=getattr(call, "lineno", None))


def _lower_ref_base_expr(node: ast.AST) -> ast.expr:
    if isinstance(node, ast.Call) and _is_astichi_ref_surface_call(node):
        return _lower_ref_surface_call_to_chain(node, ctx=ast.Load())
    if isinstance(node, ast.Attribute):
        lowered_value = _lower_ref_base_expr(node.value)
        lowered = ast.Attribute(
            value=lowered_value,
            attr=node.attr,
            ctx=ast.Load(),
        )
        return ast.copy_location(lowered, node)
    raise ValueError(
        "astichi_ref(...).astichi_ref(...) may only extend a lowered "
        "reference path"
    )


def _append_chain(
    base: ast.expr,
    segments: tuple[str, ...],
    *,
    ctx: ast.expr_context,
    lineno: int | None,
) -> ast.expr:
    node: ast.expr = base
    for idx, segment in enumerate(segments):
        is_last = idx == len(segments) - 1
        attr_ctx: ast.expr_context = ctx if is_last else ast.Load()
        attribute = ast.Attribute(value=node, attr=segment, ctx=attr_ctx)
        if lineno is not None:
            attribute.lineno = lineno
            attribute.col_offset = 0
        node = attribute
    return node


def _lower_ref_surface_call_to_chain(
    call: ast.Call, *, ctx: ast.expr_context
) -> ast.expr:
    segments = _extract_ref_segments(call)
    if _is_base_astichi_ref_call(call):
        return _build_chain(
            segments, ctx=ctx, lineno=getattr(call, "lineno", None)
        )
    assert isinstance(call.func, ast.Attribute)
    base = _lower_ref_base_expr(call.func.value)
    return _append_chain(
        base,
        segments,
        ctx=ctx,
        lineno=getattr(call, "lineno", None),
    )


# ---------------------------------------------------------------------------
# §2: restricted compile-time path evaluator
# ---------------------------------------------------------------------------


def _evaluate_path_expression(node: ast.expr) -> str:
    """Return the path string produced by a recognised compile-time expr.

    Accepts: string Constant, JoinedStr (f-string) whose FormattedValue
    parts reduce to literal scalars, or a compile-time subscript over a
    literal container that itself yields a string. Any other shape
    raises `ValueError`.
    """
    if isinstance(node, ast.JoinedStr):
        return "".join(_evaluate_joined_part(part) for part in node.values)
    # Constant / Subscript (and Tuple/List for nested containers) all
    # flow through the scalar evaluator; we then enforce that the
    # reduced top-level value is a string before lowering it as a path.
    if isinstance(node, (ast.Constant, ast.Subscript, ast.Tuple, ast.List)):
        value = _evaluate_scalar_expression(node)
        if not isinstance(value, str):
            raise ValueError(
                "astichi_ref(...) reduced value must be a string; got "
                f"{type(value).__name__}"
            )
        return value
    raise ValueError(
        "astichi_ref(...) value must be a string literal, an f-string "
        "whose formatted parts reduce to compile-time scalars, or a "
        "compile-time subscript over a literal container; got "
        f"{type(node).__name__}"
    )


def _evaluate_joined_part(part: ast.expr) -> str:
    if isinstance(part, ast.Constant):
        if not isinstance(part.value, str):
            raise ValueError(
                "astichi_ref(...) f-string literal segments must be strings"
            )
        return part.value
    if isinstance(part, ast.FormattedValue):
        if part.conversion != -1:
            raise ValueError(
                "astichi_ref(...) f-string segments may not use !r/!s/!a "
                "conversions"
            )
        if part.format_spec is not None:
            raise ValueError(
                "astichi_ref(...) f-string segments may not use a format spec"
            )
        value = _evaluate_scalar_expression(part.value)
        return str(value)
    raise ValueError(
        "astichi_ref(...) f-string contains an unsupported segment shape: "
        f"{type(part).__name__}"
    )


def _evaluate_scalar_expression(node: ast.expr) -> object:
    """Reduce a compile-time scalar expression.

    Allowed shapes:
    - `ast.Constant` (str/int/float/bool/None) — the value itself.
    - `ast.Tuple` / `ast.List` of literals — a Python tuple/list of
      the recursively-evaluated elements. Only useful as the container
      side of a Subscript (a bare tuple/list is not a legal final
      formatted value because `str(("a","b"))` would not parse as a
      ref path; the path-string validator rejects that downstream).
    - `ast.Subscript(value=container, slice=index)` — index into a
      literal container with a compile-time integer/string index.

    Any other shape — a bare `Name`, `Attribute`, `Call`, `BinOp`,
    `Compare`, etc. — is rejected.
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(_evaluate_scalar_expression(elt) for elt in node.elts)
    if isinstance(node, ast.List):
        return [_evaluate_scalar_expression(elt) for elt in node.elts]
    if isinstance(node, ast.Subscript):
        container = _evaluate_scalar_expression(node.value)
        index = _evaluate_subscript_index(node.slice)
        try:
            return container[index]
        except (TypeError, KeyError, IndexError) as exc:
            raise ValueError(
                f"astichi_ref(...) compile-time subscript failed: {exc}"
            ) from exc
    if isinstance(node, ast.Name):
        # A bare Name surviving past bind/unroll means the user
        # referenced something that was neither bound externally nor a
        # loop variable. Per spec §6 we never execute arbitrary Python
        # to compute the path text.
        raise ValueError(
            f"astichi_ref(...) f-string references unbound name `{node.id}`; "
            "only loop variables, externally bound values, and compile-time "
            "subscripts over those are allowed"
        )
    raise ValueError(
        "astichi_ref(...) f-string segment is not a compile-time scalar: "
        f"{type(node).__name__}"
    )


def _evaluate_subscript_index(node: ast.expr) -> object:
    # Python <3.9 wrapped index in `ast.Index`; modern AST stores the
    # expression directly as `slice`. A compile-time index must reduce
    # to a literal scalar.
    if hasattr(ast, "Index") and isinstance(node, ast.Index):  # pragma: no cover
        return _evaluate_subscript_index(node.value)
    if isinstance(node, ast.Slice):
        raise ValueError(
            "astichi_ref(...) compile-time subscript may not use slice "
            "notation; only single-key indexing is allowed"
        )
    return _evaluate_scalar_expression(node)


# ---------------------------------------------------------------------------
# §2 path validation + §3 chain construction
# ---------------------------------------------------------------------------


def _validate_path_string(value: str, *, lineno: int | None) -> tuple[str, ...]:
    if not isinstance(value, str):  # defence in depth
        raise ValueError(
            f"astichi_ref(...) reduced value must be a string; got "
            f"{type(value).__name__}"
        )
    if not value:
        raise ValueError("astichi_ref(...) path must not be empty")
    segments = value.split(".")
    for segment in segments:
        if not segment:
            raise ValueError(
                f"astichi_ref(...) path `{value}` has an empty segment "
                "(adjacent dots are not allowed)"
            )
        if not segment.isidentifier():
            raise ValueError(
                f"astichi_ref(...) path segment `{segment}` is not a valid "
                "Python identifier"
            )
    del lineno  # reserved for future enriched diagnostics
    return tuple(segments)


def _build_chain(
    segments: tuple[str, ...],
    *,
    ctx: ast.expr_context,
    lineno: int | None,
) -> ast.expr:
    if not segments:  # already rejected by _validate_path_string
        raise ValueError("astichi_ref(...) path is empty")
    head = ast.Name(id=segments[0], ctx=ast.Load() if len(segments) > 1 else ctx)
    if lineno is not None:
        head.lineno = lineno
        head.col_offset = 0
    node: ast.expr = head
    for idx, segment in enumerate(segments[1:], start=1):
        is_last = idx == len(segments) - 1
        attr_ctx: ast.expr_context = ctx if is_last else ast.Load()
        attribute = ast.Attribute(value=node, attr=segment, ctx=attr_ctx)
        if lineno is not None:
            attribute.lineno = lineno
            attribute.col_offset = 0
        node = attribute
    return node


def validate_external_ref_surface(tree: ast.AST) -> None:
    """Reject bare statement-form ``astichi_ref(...)`` surfaces."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        if _statement_form_ref(node.value) is None:
            continue
        lineno = getattr(node, "lineno", 0) or getattr(node.value, "lineno", 0) or 0
        raise ValueError(
            "astichi_ref(...) at line "
            f"{lineno} is value-form only and may not appear as a bare "
            "statement; use it in a real expression or wrap the immediate "
            "target position in `.astichi_v` / `._`"
        )


def _statement_form_ref(node: ast.AST) -> ast.Call | None:
    if _is_astichi_ref_surface_call(node):
        return node
    sentinel = match_transparent_sentinel(
        node,
        is_marker_call=_is_astichi_ref_surface_call,
    )
    if sentinel is None:
        return None
    return sentinel.call
