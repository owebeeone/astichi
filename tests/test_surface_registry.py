from __future__ import annotations

from pathlib import Path
import sys

import pytest

from astichi.lower_engine import (
    BundleSchemaMismatchError,
    CompatibilityRuleSpec,
    LowerEngine,
    LowerEngineError,
    OperationSpec,
    PatternSpec,
    ResultPolicyDescriptor,
    ShapeFieldExpectation,
    ShapePredicateDescriptor,
    StaleHandleError,
    SurfaceBundleSpec,
    SurfaceSpec,
)
from astichi.structural_snapshot import write_structural_snapshot
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STRUCTURAL_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="structural")
_ACTUAL_STRUCTURAL_DIR = actual_results_dir(
    _PROJECT_ROOT,
    runtime_version=(sys.version_info.major, sys.version_info.minor),
) / "goldens" / "structural"


def test_surface_registry_minimal_bundle_matches_structural_golden() -> None:
    registry = LowerEngine().surface_registry

    registered = registry.register_bundle(_minimal_bundle_spec())

    assert registered.surfaces[0].handle is registry.surface_handle("expression.hole")
    assert registered.operations[0].handle is registry.operation_handle(
        "insert.expression"
    )
    assert registered.patterns[0].handle is registry.pattern_handle(
        "expression-hole-call"
    )

    actual_text = write_structural_snapshot(registry.structural_snapshot())
    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "registry_minimal_bundle.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "registry_minimal_bundle.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text


def test_surface_registry_compatibility_uses_shape_descriptors() -> None:
    registry = LowerEngine().surface_registry
    registry.register_bundle(_minimal_bundle_spec())

    decision = registry.compatibility_decision(
        target_surface_id=registry.surface_handle("expression.hole"),
        production_surface_id=registry.surface_handle("expression.production"),
        target_shape={"placement": "expression"},
        production_shape={"shape": "scalar"},
    )

    assert decision.accepted
    assert decision.result_policy is not None
    assert decision.result_policy.policy_key == "single-expression-insert"

    rejected = registry.compatibility_decision(
        target_surface_id=registry.surface_handle("expression.hole"),
        production_surface_id=registry.surface_handle("expression.production"),
        target_shape={"placement": "block"},
        production_shape={"shape": "scalar"},
    )
    assert not rejected.accepted
    assert rejected.result_policy is None


def test_surface_registry_rejects_foreign_surface_handle() -> None:
    registry = LowerEngine().surface_registry
    foreign_registry = LowerEngine().surface_registry
    registry.register_bundle(_minimal_bundle_spec())
    foreign_registry.register_bundle(_minimal_bundle_spec())

    with pytest.raises(StaleHandleError, match="another lower engine"):
        registry.compatibility_decision(
            target_surface_id=foreign_registry.surface_handle("expression.hole"),
            production_surface_id=registry.surface_handle("expression.production"),
            target_shape={"placement": "expression"},
            production_shape={"shape": "scalar"},
        )


def test_surface_registry_rejects_duplicate_keys() -> None:
    registry = LowerEngine().surface_registry
    spec = SurfaceBundleSpec(
        bundle_key="bad",
        schema_version=1,
        surfaces=(
            SurfaceSpec("expression.hole", 1, "first"),
            SurfaceSpec("expression.hole", 1, "second"),
        ),
        operations=(),
        patterns=(),
    )

    with pytest.raises(LowerEngineError, match="duplicate surface keys"):
        registry.register_bundle(spec)


def test_surface_registry_rejects_unknown_schema_version() -> None:
    registry = LowerEngine().surface_registry
    spec = SurfaceBundleSpec(
        bundle_key="bad",
        schema_version=2,
        surfaces=(),
        operations=(),
        patterns=(),
    )

    with pytest.raises(BundleSchemaMismatchError, match="unsupported surface bundle"):
        registry.register_bundle(spec)


def _minimal_bundle_spec() -> SurfaceBundleSpec:
    return SurfaceBundleSpec(
        bundle_key="astichi.core.minimal",
        schema_version=1,
        surfaces=(
            SurfaceSpec(
                surface_key="expression.hole",
                version=1,
                summary="Target expression replacement point.",
            ),
            SurfaceSpec(
                surface_key="expression.production",
                version=1,
                summary="Scalar expression production.",
            ),
        ),
        operations=(
            OperationSpec(
                operation_key="insert.expression",
                version=1,
                summary="Replace one expression target with one expression source.",
            ),
        ),
        patterns=(
            PatternSpec(
                pattern_key="expression-hole-call",
                template_key="direct-call",
                version=1,
                surface_key="expression.hole",
                operation_key="insert.expression",
                summary="Recognize astichi_hole(name) in expression position.",
            ),
            PatternSpec(
                pattern_key="expression-production",
                template_key="expression-payload",
                version=1,
                surface_key="expression.production",
                operation_key="insert.expression",
                summary="Recognize a scalar expression payload.",
            ),
        ),
        compatibility_rules=(
            CompatibilityRuleSpec(
                target_surface_key="expression.hole",
                production_surface_key="expression.production",
                shape_predicate=ShapePredicateDescriptor(
                    target_expectations=(
                        ShapeFieldExpectation("placement", "expression"),
                    ),
                    production_expectations=(
                        ShapeFieldExpectation("shape", "scalar"),
                    ),
                ),
                result_policy=ResultPolicyDescriptor(
                    policy_key="single-expression-insert",
                    summary="Use one source expression for one expression hole.",
                ),
            ),
        ),
    )
