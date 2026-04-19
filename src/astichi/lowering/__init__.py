"""Marker recognition and lowering bridge for Astichi."""

from astichi.lowering.call_argument_payloads import (
    direct_funcargs_directive_calls,
    is_astichi_funcargs_call,
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
    "MarkerSpec",
    "PortTemplate",
    "RecognizedMarker",
    "apply_external_bindings",
    "direct_funcargs_directive_calls",
    "group_markers_by_astichi_scope",
    "is_astichi_funcargs_call",
    "recognize_markers",
    "validate_call_argument_payload_surface",
    "validate_boundary_interaction_matrix",
    "validate_boundary_marker_placement",
]
