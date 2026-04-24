"""Helpers for structured build-path refs on Astichi insert shells."""

from __future__ import annotations

import ast
from typing import TypeAlias

from astichi.ast_provenance import propagate_ast_source_locations
from astichi.diagnostics import format_astichi_error

RefSegment: TypeAlias = str | int
RefPath: TypeAlias = tuple[RefSegment, ...]


def format_ref_path(path: RefPath) -> str:
    """Render a mixed ref path in a compact diagnostic form."""
    path = normalize_ref_path(path, phase="build")
    if not path:
        return "<root>"
    parts: list[str] = []
    for segment in path:
        if isinstance(segment, int):
            parts.append(f"[{segment}]")
        else:
            if not parts:
                parts.append(segment)
            elif parts[-1].startswith("["):
                parts.append(f".{segment}")
            else:
                parts.append(f".{segment}")
    return "".join(parts)


def normalize_ref_path(path: RefPath, *, phase: str = "build") -> RefPath:
    """Canonicalize a ref path to name-first fluent order.

    The V3 emitted-source form is fluent (`Foo.Parse[1, 2]`), so the
    canonical internal layout is also name-first:

    - name segments stay in-order
    - index segments follow the name they qualify

    Older intermediate tuples may still carry an initial index run
    (`(0, 'Foo')`); normalize those to the fluent shape (`('Foo', 0)`).
    """
    if not path:
        return path
    if isinstance(path[0], str):
        return path
    split = 0
    while split < len(path) and isinstance(path[split], int):
        split += 1
    if split == len(path):
        raise ValueError(
            format_astichi_error(
                phase,
                "astichi_insert ref paths may not contain only index segments",
                hint="start the path with a name segment such as `Foo[0].Bar`",
            )
        )
    first_name = path[split]
    assert isinstance(first_name, str)
    return (first_name,) + path[:split] + path[split + 1 :]


def ref_path_to_ast(
    path: RefPath,
    *,
    location_donor: ast.AST | None = None,
    phase: str = "build",
) -> ast.expr:
    """Encode a canonical ref path as fluent Python AST.

    When ``location_donor`` is provided (typically the existing ``ref=`` value
    or the enclosing ``astichi_insert`` call), line/column metadata is copied
    onto the synthesized fluent expression. If any name segment is not a valid
    Python identifier, fall back to the tuple-literal `ref=(...)` form so the
    path remains round-trippable.
    """
    path = normalize_ref_path(path, phase=phase)
    if not path:
        raise ValueError(
            format_astichi_error(
                phase,
                "astichi_insert ref path may not be empty",
                hint="use a non-empty fluent path like `Foo.Bar` in `ref=`",
            )
        )
    if any(
        isinstance(segment, str) and not segment.isidentifier() for segment in path
    ):
        expr = ast.Tuple(
            elts=[ast.Constant(value=segment) for segment in path],
            ctx=ast.Load(),
        )
        propagate_ast_source_locations(expr, location_donor)
        return expr
    expr: ast.expr | None = None
    index_run: list[int] = []
    for segment in path:
        if isinstance(segment, int):
            index_run.append(segment)
            continue
        if expr is None:
            expr = ast.Name(id=segment, ctx=ast.Load())
        else:
            if index_run:
                expr = _apply_index_run(expr, tuple(index_run), location_donor=expr)
                index_run.clear()
            expr = ast.Attribute(value=expr, attr=segment, ctx=ast.Load())
    if expr is None:
        raise ValueError(
            format_astichi_error(
                phase,
                "astichi_insert ref path must contain a name segment",
                hint="include at least one identifier segment in `ref=`",
            )
        )
    if index_run:
        expr = _apply_index_run(expr, tuple(index_run), location_donor=expr)
    propagate_ast_source_locations(expr, location_donor)
    return expr


def parse_ref_path_literal(
    node: ast.AST, *, phase: str = "compile"
) -> RefPath:
    """Decode a ref path from fluent syntax or a legacy tuple literal."""
    if isinstance(node, ast.Tuple):
        return normalize_ref_path(
            tuple(_parse_ref_segment(elt, phase=phase) for elt in node.elts),
            phase=phase,
        )
    components = _parse_ref_components(node, phase=phase)
    path: list[RefSegment] = []
    for name, indices in components:
        path.append(name)
        path.extend(indices)
    return tuple(path)


def extract_insert_ref(call: ast.Call, *, phase: str = "compile") -> RefPath | None:
    """Return the structured ``ref=...`` path from an insert call, if present."""
    seen: RefPath | None = None
    for keyword in call.keywords:
        if keyword.arg != "ref":
            continue
        if seen is not None:
            raise ValueError(
                format_astichi_error(
                    phase,
                    "astichi_insert may not repeat the `ref=` keyword",
                    hint="use a single `ref=` keyword on each insert decorator",
                )
            )
        seen = parse_ref_path_literal(keyword.value, phase=phase)
    return seen


def set_insert_ref(
    call: ast.Call, path: RefPath, *, phase: str = "materialize"
) -> None:
    """Set or replace the structured ``ref=...`` keyword on an insert call."""
    ref_donor: ast.AST = call
    for keyword in call.keywords:
        if keyword.arg == "ref":
            ref_donor = keyword.value
            break
    new_keyword = ast.keyword(
        arg="ref",
        value=ref_path_to_ast(path, location_donor=ref_donor, phase=phase),
    )
    for index, keyword in enumerate(call.keywords):
        if keyword.arg == "ref":
            call.keywords[index] = new_keyword
            return
    call.keywords.append(new_keyword)


def prefix_insert_ref(
    call: ast.Call, prefix: RefPath, *, phase: str = "materialize"
) -> None:
    """Prefix an existing insert ``ref=...`` path in-place if present."""
    existing = extract_insert_ref(call, phase=phase)
    if existing is None:
        return
    set_insert_ref(
        call,
        normalize_ref_path(prefix + existing, phase=phase),
        phase=phase,
    )


def iter_insert_shell_ref_paths(tree: ast.AST) -> tuple[RefPath, ...]:
    """Return every structured shell ref carried by insert-decorated shells."""
    refs: list[RefPath] = []
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Name):
                continue
            if decorator.func.id != "astichi_insert":
                continue
            ref = extract_insert_ref(decorator, phase="build")
            if ref is not None:
                refs.append(ref)
            break
    return tuple(refs)


def next_insert_ref_segments(tree: ast.AST, prefix: RefPath) -> frozenset[RefSegment]:
    """Return the direct child segments under ``prefix`` in the shell ref tree."""
    prefix = normalize_ref_path(prefix, phase="build")
    next_segments: set[RefSegment] = set()
    prefix_len = len(prefix)
    for ref in iter_insert_shell_ref_paths(tree):
        if len(ref) <= prefix_len:
            continue
        if ref[:prefix_len] != prefix:
            continue
        next_segments.add(ref[prefix_len])
    return frozenset(next_segments)


def _parse_ref_segment(node: ast.AST, *, phase: str = "compile") -> RefSegment:
    if not isinstance(node, ast.Constant):
        raise ValueError(
            format_astichi_error(
                phase,
                "astichi_insert ref must be a fluent path expression "
                "or a tuple literal of str/int segments",
                hint="use fluent syntax like `Foo.Bar[1,2]` or `ref=(\"Foo\", \"Bar\")`",
            )
        )
    value = node.value
    if isinstance(value, bool):
        raise ValueError(
            format_astichi_error(
                phase,
                "astichi_insert ref segments must be str/int literals, got bool",
                hint="use string or int literals inside tuple `ref=` forms",
            )
        )
    if isinstance(value, (str, int)):
        return value
    raise ValueError(
        format_astichi_error(
            phase,
            "astichi_insert ref segments must be str/int literals",
            hint="tuple `ref=` segments must be str or int constants",
        )
    )


def _apply_index_run(
    expr: ast.expr,
    indices: tuple[int, ...],
    *,
    location_donor: ast.AST | None,
) -> ast.expr:
    if len(indices) == 1:
        slice_node: ast.expr = ast.Constant(value=indices[0])
    else:
        slice_node = ast.Tuple(
            elts=[ast.Constant(value=index) for index in indices],
            ctx=ast.Load(),
        )
    sub = ast.Subscript(value=expr, slice=slice_node, ctx=ast.Load())
    propagate_ast_source_locations(sub, location_donor or expr)
    return sub


def _parse_ref_components(
    node: ast.AST, *, phase: str = "compile"
) -> list[tuple[str, tuple[int, ...]]]:
    if isinstance(node, ast.Name):
        return [(node.id, ())]
    if isinstance(node, ast.Attribute):
        components = _parse_ref_components(node.value, phase=phase)
        components.append((node.attr, ()))
        return components
    if isinstance(node, ast.Subscript):
        components = _parse_ref_components(node.value, phase=phase)
        if not components:
            raise ValueError(
                format_astichi_error(
                    phase,
                    "astichi_insert ref subscript must follow a named path segment",
                    hint="write `Foo[0]` not a leading subscript without a name",
                )
            )
        name, existing = components[-1]
        components[-1] = (
            name,
            existing + _parse_subscript_indices(node.slice, phase=phase),
        )
        return components
    raise ValueError(
        format_astichi_error(
            phase,
            "astichi_insert ref must be a fluent path expression "
            "or a tuple literal of str/int segments",
            hint="use fluent syntax like `Foo.Bar[1,2]` or `ref=(\"Foo\", \"Bar\")`",
        )
    )


def _parse_subscript_indices(
    node: ast.AST, *, phase: str = "compile"
) -> tuple[int, ...]:
    if isinstance(node, ast.Tuple):
        indices = tuple(
            _parse_index_segment(elt, phase=phase) for elt in node.elts
        )
    else:
        indices = (_parse_index_segment(node, phase=phase),)
    if not indices:
        raise ValueError(
            format_astichi_error(
                phase,
                "astichi_insert ref index groups may not be empty",
                hint="use `[i]` or `[i,j]` with at least one index",
            )
        )
    return indices


def _parse_index_segment(node: ast.AST, *, phase: str = "compile") -> int:
    segment = _parse_ref_segment(node, phase=phase)
    if not isinstance(segment, int):
        raise ValueError(
            format_astichi_error(
                phase,
                "astichi_insert ref indexes must be integer literals",
                hint="subscripts in `ref=` must use int literals only",
            )
        )
    return segment
