"""Public frontend entrypoints for Astichi."""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping

from astichi.frontend.compiled import FrontendComposable
from astichi.hygiene import analyze_names
from astichi.lowering import (
    recognize_markers,
    validate_boundary_interaction_matrix,
    validate_boundary_marker_placement,
)
from astichi.model import (
    BasicComposable,
    Composable,
    CompileOrigin,
    extract_demand_ports,
    extract_supply_ports,
)


def _single_line_source(source: str) -> bool:
    """Return whether source is logically one line."""
    return "\n" not in source.rstrip("\n")


def _padded_source(
    source: str,
    *,
    line_number: int,
    offset: int,
    apply_offset: bool,
) -> str:
    """Construct parse input with source-origin padding applied."""
    prefix = "\n" * max(line_number - 1, 0)
    if apply_offset and offset > 0:
        prefix += " " * offset
    return prefix + source


def compile(
    source: str,
    file_name: str | None = None,
    line_number: int = 1,
    offset: int = 0,
    *,
    arg_names: Mapping[str, str] | None = None,
    keep_names: Iterable[str] | None = None,
) -> Composable:
    """Compile marker-bearing source into a composable.

    `arg_names`: initial resolutions for `__astichi_arg__` slots
    (stripped name -> target identifier). Equivalent to the composable
    returned from compile having `.bind_identifier(**arg_names)` already
    applied, but validated eagerly at compile time against the demand
    ports recognised in `source`.

    `keep_names`: names the user pins as hygiene-preserved without
    rewriting source. Additive to any `__astichi_keep__` suffix sites
    found in `source`.
    """
    origin = CompileOrigin(
        file_name=file_name or "<astichi>",
        line_number=line_number,
        offset=offset,
    )
    apply_offset = _single_line_source(source)
    try:
        tree = ast.parse(
            _padded_source(
                source,
                line_number=line_number,
                offset=offset,
                apply_offset=apply_offset,
            ),
            filename=origin.file_name,
        )
    except IndentationError:
        if not apply_offset or offset <= 0:
            raise
        tree = ast.parse(
            _padded_source(
                source,
                line_number=line_number,
                offset=offset,
                apply_offset=False,
            ),
            filename=origin.file_name,
        )
    # Issue 006 6a: reject misplaced astichi_import / astichi_pass
    # declarations before any downstream pipeline step observes them.
    validate_boundary_marker_placement(tree)
    markers = recognize_markers(tree)
    # Issue 006 6b: reject forbidden per-scope marker combinations
    # (e.g. `import + pass` on the same name) before continuing.
    validate_boundary_interaction_matrix(tree, markers)
    validated_keep_names = _validate_keep_names(keep_names)
    provisional = BasicComposable(
        tree=tree,
        origin=origin,
        markers=markers,
        keep_names=validated_keep_names,
    )
    classification = analyze_names(
        provisional, mode="permissive", preserved_names=validated_keep_names
    )
    demand_ports = extract_demand_ports(markers, classification)
    supply_ports = extract_supply_ports(markers)
    validated_arg_bindings = _validate_arg_names(arg_names, demand_ports)
    return FrontendComposable(
        tree=tree,
        origin=origin,
        markers=markers,
        classification=classification,
        demand_ports=demand_ports,
        supply_ports=supply_ports,
        arg_bindings=validated_arg_bindings,
        keep_names=validated_keep_names,
    )


def _validate_keep_names(names: Iterable[str] | None) -> frozenset[str]:
    if names is None:
        return frozenset()
    result: set[str] = set()
    for name in names:
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError(
                f"keep_names entry `{name}` is not a valid Python identifier"
            )
        result.add(name)
    return frozenset(result)


def _validate_arg_names(
    arg_names: Mapping[str, str] | None,
    demand_ports: tuple,
) -> tuple[tuple[str, str], ...]:
    if arg_names is None or not arg_names:
        return ()
    if not isinstance(arg_names, Mapping):
        raise TypeError("arg_names must implement Mapping")
    arg_slot_names = {
        port.name for port in demand_ports if "arg" in port.sources
    }
    resolved: dict[str, str] = {}
    for key, value in arg_names.items():
        if not isinstance(key, str) or not key.isidentifier():
            raise ValueError(
                f"arg_names key `{key}` is not a valid Python identifier"
            )
        if not isinstance(value, str) or not value.isidentifier():
            raise ValueError(
                f"arg_names resolution for `{key}` must be a valid "
                f"Python identifier, got {value!r}"
            )
        if key not in arg_slot_names:
            known = tuple(sorted(arg_slot_names))
            raise ValueError(
                f"no __astichi_arg__ slot named `{key}` in source; known "
                f"identifier-arg demands: {known!r}"
            )
        resolved[key] = value
    return tuple(sorted(resolved.items()))
