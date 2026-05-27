"""Public frontend entrypoints for Astichi."""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping

from astichi.ast_provenance import attach_astichi_source_file
from astichi.asttools import is_astichi_insert_call
from astichi.frontend.source_kind import (
    AUTHORED_SOURCE,
    SourceKind,
    normalize_source_kind,
)
from astichi.frontend.compiled import FrontendComposable
from astichi.hygiene import analyze_names
from astichi.lowering import (
    COMMENT,
    desugar_external_ref_kwargs,
    validate_call_argument_payload_surface,
    validate_external_ref_surface,
    validate_parameter_hole_surface,
    validate_parameter_payload_surface,
    recognize_markers,
    validate_boundary_interaction_matrix,
    validate_boundary_marker_placement,
    validate_pyimport_declarations,
)
from astichi.model import (
    BasicComposable,
    Composable,
    CompileOrigin,
    build_inventory,
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
    source_kind: SourceKind | str = AUTHORED_SOURCE,
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

    `source_kind`: defaults to `"authored"` for user-authored snippets.
    The `"astichi-emitted"` mode is reserved for re-ingesting source emitted
    by Astichi itself; it enables internal marker metadata such as
    `astichi_insert(...)`.
    """
    normalized_source_kind = normalize_source_kind(source_kind)
    origin = CompileOrigin(
        file_name=file_name or "<astichi>",
        line_number=line_number,
        offset=offset,
    )
    apply_offset = _single_line_source(source)
    parse_source = _padded_source(
        source,
        line_number=line_number,
        offset=offset,
        apply_offset=apply_offset,
    )
    selected_native = _selected_native_lower_engine()
    validated_keep_names = _validate_keep_names(keep_names)
    use_native_hot_path = _native_hot_path_compile_selected(
        selected_native,
        parse_source=parse_source,
    )
    if use_native_hot_path:
        from astichi.lower_engine import register_native_template_source_hot_path
        from astichi.lower_engine.facade import _ports_from_native_projection_inventory
        from astichi.lower_engine.native_hot_path_compile import (
            o3_production_hot_path_compile_active,
        )

        o3_compile = o3_production_hot_path_compile_active()
        tree = _hot_path_compile_placeholder_tree()
        if not o3_compile:
            tree, parse_source = _parse_compile_tree(
                source=source,
                parse_source=parse_source,
                origin=origin,
                line_number=line_number,
                offset=offset,
                apply_offset=apply_offset,
                selected_native=selected_native,
            )
            attach_astichi_source_file(tree, origin.file_name)
            if not normalized_source_kind.allows_internal_insert_metadata():
                _maybe_native_compile_validate(source, origin.file_name)
            markers, classification, demand_ports, supply_ports = (
                _recognize_compile_markers(
                    tree=tree,
                    origin=origin,
                    source_kind=normalized_source_kind,
                    validated_keep_names=validated_keep_names,
                )
            )
        elif not normalized_source_kind.allows_internal_insert_metadata():
            _maybe_native_compile_validate(source, origin.file_name)

        lower_template, inventory = register_native_template_source_hot_path(
            source=parse_source,
            origin=origin,
        )
        _assert_selected_native_backend(selected_native, lower_template)

        if o3_compile:
            demand_ports, supply_ports = _ports_from_native_projection_inventory(
                inventory
            )
            markers = ()
            classification = analyze_names(
                BasicComposable(
                    tree=tree,
                    origin=origin,
                    markers=markers,
                    keep_names=validated_keep_names,
                ),
                mode="permissive",
                preserved_names=validated_keep_names,
            )
        else:
            from dataclasses import replace

            from astichi.lower_engine.facade import (
                _native_specs_from_package,
                _projection_inventory_from_package,
            )

            inventory, projection_records = _projection_inventory_from_package(
                tree=tree,
                origin=origin,
                package=lower_template.package_v2,
            )
            native_specs = _native_specs_from_package(
                engine=lower_template.engine,
                package=lower_template.package_v2,
                fallback_binding=lower_template,
                projection_records=projection_records,
            )
            lower_template = replace(
                lower_template,
                record_specs=native_specs.record_specs,
                scope_specs=native_specs.scope_specs,
                marker_specs=native_specs.marker_specs,
                pyimport_marker_specs=native_specs.pyimport_marker_specs,
                comment_marker_specs=native_specs.comment_marker_specs,
                ref_marker_specs=native_specs.ref_marker_specs,
                unroll_marker_specs=native_specs.unroll_marker_specs,
            )
    else:
        tree, parse_source = _parse_compile_tree(
            source=source,
            parse_source=parse_source,
            origin=origin,
            line_number=line_number,
            offset=offset,
            apply_offset=apply_offset,
            selected_native=selected_native,
        )
        attach_astichi_source_file(tree, origin.file_name)
        if (
            selected_native is not None
            and not normalized_source_kind.allows_internal_insert_metadata()
        ):
            _maybe_native_compile_validate(source, origin.file_name)
        markers, classification, demand_ports, supply_ports = (
            _recognize_compile_markers(
                tree=tree,
                origin=origin,
                source_kind=normalized_source_kind,
                validated_keep_names=validated_keep_names,
            )
        )
        if selected_native is None:
            inventory = build_inventory(tree, markers, demand_ports, supply_ports)
            from astichi.lower_engine import register_inventory_template

            lower_template = register_inventory_template(
                tree=tree,
                origin=origin,
                inventory=inventory,
            )
        else:
            from astichi.lower_engine import register_native_template_source_direct

            lower_template, inventory = register_native_template_source_direct(
                source=parse_source,
                origin=origin,
                tree=tree,
            )
            _assert_selected_native_backend(selected_native, lower_template)
    validated_arg_bindings = _validate_arg_names(arg_names, demand_ports)
    compiled = FrontendComposable(
        tree=tree,
        origin=origin,
        markers=markers,
        classification=classification,
        demand_ports=demand_ports,
        supply_ports=supply_ports,
        inventory=inventory,
        arg_bindings=validated_arg_bindings,
        keep_names=validated_keep_names,
        _lower_template=lower_template,
    )
    if validated_arg_bindings:
        return compiled.bind_identifier(dict(validated_arg_bindings))
    return compiled


def _maybe_native_compile_validate(source: str, file_name: str) -> None:
    from astichi.lower_engine.native_compile_validate import (
        native_compile_validate_source,
        native_compile_validation_enabled,
    )

    if not native_compile_validation_enabled():
        return
    native_compile_validate_source(source, file_name=file_name)


def _recognize_compile_markers(
    *,
    tree: ast.Module,
    origin: CompileOrigin,
    source_kind: SourceKind,
    validated_keep_names: frozenset[str],
) -> tuple[tuple[object, ...], object, tuple[object, ...], tuple[object, ...]]:
    """Validate authored surfaces and derive marker/port projections from ``tree``."""
    _validate_authored_marker_surface(tree, source_kind=source_kind)
    validate_boundary_marker_placement(tree)
    if source_kind.validates_authored_payload_surfaces():
        validate_call_argument_payload_surface(tree)
        validate_parameter_payload_surface(tree)
    desugar_external_ref_kwargs(tree)
    validate_external_ref_surface(tree)
    markers = recognize_markers(tree)
    _validate_comment_markers(markers)
    validate_pyimport_declarations(tree, markers)
    validate_parameter_hole_surface(tree, markers)
    validate_boundary_interaction_matrix(tree, markers)
    provisional = BasicComposable(
        tree=tree,
        origin=origin,
        markers=markers,
        keep_names=validated_keep_names,
    )
    classification = analyze_names(
        provisional,
        mode="permissive",
        preserved_names=validated_keep_names,
    )
    demand_ports = extract_demand_ports(markers, classification)
    supply_ports = extract_supply_ports(markers)
    return markers, classification, demand_ports, supply_ports


def _native_hot_path_compile_selected(
    selected_native: str | None,
    *,
    parse_source: str,
) -> bool:
    if selected_native is None:
        return False
    from astichi.lower_engine.native_hot_path_compile import (
        native_hot_path_compile_enabled,
    )

    return native_hot_path_compile_enabled()


def _hot_path_compile_placeholder_tree() -> ast.Module:
    from astichi.lower_engine.native_hot_path_compile import (
        hot_path_compile_placeholder_tree,
    )

    return hot_path_compile_placeholder_tree()


def _parse_compile_tree(
    *,
    source: str,
    parse_source: str,
    origin: CompileOrigin,
    line_number: int,
    offset: int,
    apply_offset: bool,
    selected_native: str | None,
) -> tuple[ast.Module, str]:
    """Parse compile input with native or CPython parser."""
    from astichi.lower_engine.native_compile_parse import (
        native_compile_tree_from_parse_source,
        native_no_python_parse_compile_enabled,
    )
    from astichi.perf_counters import active_perf_counters

    use_native_parse = (
        selected_native is not None and native_no_python_parse_compile_enabled()
    )

    def _parse_with_python(text: str) -> ast.Module:
        counters = active_perf_counters()
        if counters is None:
            return ast.parse(text, filename=origin.file_name)
        with counters.measure("python_compile_ast_parse"):
            return ast.parse(text, filename=origin.file_name)

    if use_native_parse:
        try:
            return (
                native_compile_tree_from_parse_source(
                    parse_source,
                    file_name=origin.file_name,
                ),
                parse_source,
            )
        except SyntaxError as native_error:
            # Fall back to CPython parse so padded compile input reports lineno/offset.
            if native_error.filename is not None:
                raise

    try:
        return _parse_with_python(parse_source), parse_source
    except IndentationError:
        if not apply_offset or offset <= 0:
            raise
        parse_source = _padded_source(
            source,
            line_number=line_number,
            offset=offset,
            apply_offset=False,
        )
        return _parse_with_python(parse_source), parse_source


def _selected_native_lower_engine() -> str | None:
    from astichi.lower_engine.native import select_effective_lower_engine

    selected = select_effective_lower_engine().selected_engine
    if selected == "python":
        return None
    if selected in {"native-rust", "native-cpp"}:
        return selected
    return None


def _assert_selected_native_backend(selected: str, lower_template: object) -> None:
    backend = getattr(lower_template, "backend", "")
    if selected == "native-cpp" and backend != "native-cpp":
        raise RuntimeError(
            "selected native-cpp lower engine, but native backend is not C++"
        )
    if selected == "native-rust" and backend != "native-rust":
        raise RuntimeError(
            "selected native-rust lower engine, but native backend is not Rust"
        )


def _maybe_attach_native_lower_template(
    *,
    source: str,
    origin: CompileOrigin,
    lower_template: object,
) -> object:
    from astichi.lower_engine.native import select_lower_engine

    selected = select_lower_engine().selected_engine
    if selected == "python":
        return lower_template
    if selected not in {"native-rust", "native-cpp"}:
        return lower_template

    from astichi.lower_engine import register_native_template_source

    native_binding = register_native_template_source(
        source=source,
        origin=origin,
        fallback_binding=lower_template,
    )
    if selected == "native-cpp" and native_binding.backend != "native-cpp":
        raise RuntimeError("selected native-cpp lower engine, but native backend is not C++")
    if selected == "native-rust" and native_binding.backend != "native-rust":
        raise RuntimeError("selected native-rust lower engine, but native backend is not Rust")
    return native_binding


def _validate_authored_marker_surface(
    tree: ast.AST,
    *,
    source_kind: SourceKind,
) -> None:
    if source_kind.allows_internal_insert_metadata():
        return
    for node in ast.walk(tree):
        if not is_astichi_insert_call(node):
            continue
        lineno = getattr(node, "lineno", "?")
        raise ValueError(
            "astichi_insert(...) is internal emitted-source metadata and "
            f"cannot be authored directly at line {lineno}; use astichi.build() "
            "to add snippets into astichi_hole(...) and only compile emitted "
            "Astichi source with source_kind='astichi-emitted'"
        )


def _validate_comment_markers(markers: tuple[object, ...]) -> None:
    for marker in markers:
        spec = getattr(marker, "spec", None)
        if spec is not COMMENT:
            continue
        shape = getattr(marker, "shape", None)
        if shape is not None and shape.is_block():
            continue
        node = getattr(marker, "node", None)
        lineno = getattr(node, "lineno", "?")
        raise ValueError(
            "astichi_comment(...) is statement-only and cannot be used as a "
            f"value at line {lineno}"
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
    # Issue 006: an IDENTIFIER-demand port can come from a
    # ``name__astichi_arg__`` suffix slot (005), an ``astichi_import``
    # declaration, or a value-form ``astichi_pass(...)`` occurrence.
    # All three are wired through the same ``arg_names`` mapping.
    arg_slot_names = {
        port.name
        for port in demand_ports
        if port.is_identifier_demand()
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
                f"no __astichi_arg__ / astichi_import / astichi_pass slot named `{key}` "
                f"in source; known identifier demands: {known!r}"
            )
        resolved[key] = value
    return tuple(sorted(resolved.items()))
