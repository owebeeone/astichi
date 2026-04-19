"""Marker recognition and lowering bridge for Astichi."""

from astichi.lowering.call_argument_payloads import (
    PayloadLocalDirective,
    DirectiveFuncArgItem,
    DoubleStarFuncArgItem,
    FuncArgPayload,
    FuncArgPayloadItem,
    KeywordFuncArgItem,
    PositionalFuncArgItem,
    StarredFuncArgItem,
    collect_payload_local_directives,
    direct_funcargs_directive_calls,
    extract_funcargs_payload,
    is_astichi_funcargs_call,
    lower_payload_for_region,
    register_explicit_keyword,
    validate_payload_for_region,
    validate_call_argument_payload_surface,
)
from astichi.lowering.boundaries import (
    group_markers_by_astichi_scope,
    validate_boundary_interaction_matrix,
    validate_boundary_marker_placement,
)
from astichi.lowering.external_bind import apply_external_bindings
from astichi.lowering.markers import (
    MARKERS_BY_NAME,
    MarkerSpec,
    PortTemplate,
    RecognizedMarker,
    recognize_markers,
)

__all__ = [
    "MARKERS_BY_NAME",
    "DirectiveFuncArgItem",
    "DoubleStarFuncArgItem",
    "FuncArgPayload",
    "FuncArgPayloadItem",
    "KeywordFuncArgItem",
    "MarkerSpec",
    "PayloadLocalDirective",
    "PortTemplate",
    "PositionalFuncArgItem",
    "RecognizedMarker",
    "StarredFuncArgItem",
    "apply_external_bindings",
    "collect_payload_local_directives",
    "direct_funcargs_directive_calls",
    "extract_funcargs_payload",
    "group_markers_by_astichi_scope",
    "is_astichi_funcargs_call",
    "lower_payload_for_region",
    "recognize_markers",
    "register_explicit_keyword",
    "validate_call_argument_payload_surface",
    "validate_boundary_interaction_matrix",
    "validate_boundary_marker_placement",
    "validate_payload_for_region",
]
