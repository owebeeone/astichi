"""Internal lower-engine reference implementation."""

from astichi.lower_engine.catalog import (
    current_plus_future_surface_bundle_spec,
    current_surface_bundle_spec,
)
from astichi.lower_engine.engine import LowerEngine
from astichi.lower_engine.errors import LowerEngineError, StaleHandleError
from astichi.lower_engine.handles import (
    EdgeId,
    LocatorId,
    OccurrenceId,
    OverlayId,
    OperationId,
    PatternId,
    RecordId,
    SurfaceId,
    TemplateId,
    TemplateRecordId,
)
from astichi.lower_engine.materialization import (
    HygieneOperation,
    MaterializationOperation,
    MaterializationPlan,
)
from astichi.lower_engine.registry import (
    BundleSchemaMismatchError,
    CompatibilityDecision,
    CompatibilityRuleSpec,
    OperationSpec,
    PatternSpec,
    RegisteredSurfaceBundle,
    ResultPolicyDescriptor,
    ShapeFieldExpectation,
    ShapePredicateDescriptor,
    SurfaceBundleSpec,
    SurfaceRegistry,
    SurfaceSpec,
)
from astichi.lower_engine.templates import TemplateRecordSpec

__all__ = [
    "BundleSchemaMismatchError",
    "CompatibilityDecision",
    "CompatibilityRuleSpec",
    "EdgeId",
    "HygieneOperation",
    "LocatorId",
    "LowerEngine",
    "LowerEngineError",
    "MaterializationOperation",
    "MaterializationPlan",
    "OccurrenceId",
    "OperationId",
    "OperationSpec",
    "OverlayId",
    "PatternId",
    "PatternSpec",
    "RecordId",
    "RegisteredSurfaceBundle",
    "ResultPolicyDescriptor",
    "ShapeFieldExpectation",
    "ShapePredicateDescriptor",
    "StaleHandleError",
    "SurfaceBundleSpec",
    "SurfaceId",
    "SurfaceRegistry",
    "SurfaceSpec",
    "TemplateId",
    "TemplateRecordId",
    "TemplateRecordSpec",
    "current_plus_future_surface_bundle_spec",
    "current_surface_bundle_spec",
]
