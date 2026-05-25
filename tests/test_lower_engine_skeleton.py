from __future__ import annotations

from pathlib import Path
import sys

import pytest

from astichi.lower_engine import (
    LowerEngine,
    MaterializationOperation,
    MaterializationPlan,
    StaleHandleError,
    TemplateRecordSpec,
    write_package_snapshot,
)
from astichi.structural_snapshot import write_structural_snapshot
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STRUCTURAL_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="structural")
_PACKAGE_GOLDENS_DIR = data_golden_dir(
    _PROJECT_ROOT,
    phase="lower_template_package_v2",
)
_ACTUAL_STRUCTURAL_DIR = actual_results_dir(
    _PROJECT_ROOT,
    runtime_version=(sys.version_info.major, sys.version_info.minor),
) / "goldens" / "structural"
_ACTUAL_PACKAGE_DIR = actual_results_dir(
    _PROJECT_ROOT,
    runtime_version=(sys.version_info.major, sys.version_info.minor),
) / "goldens" / "lower_template_package_v2"


def test_lower_engine_skeleton_state_matches_structural_golden() -> None:
    engine = LowerEngine()
    root_template = engine.register_template(
        template_key="lower_engine_root",
        source_summary="result = astichi_hole(value)",
        records=(
            TemplateRecordSpec(
                surface_key="expression.hole",
                semantic_summary="expression hole value",
                ast_path="body[0].value",
                role_key="expression.hole",
                materialization_anchor="replace-expression",
                authored_summary="astichi_hole(value)",
            ),
        ),
    )
    source_template = engine.register_template(
        template_key="lower_engine_value",
        source_summary="value",
        records=(
            TemplateRecordSpec(
                surface_key="expression.production",
                semantic_summary="expression production value",
                ast_path="body[0].value",
                role_key="expression.production",
                materialization_anchor="copy-expression",
                authored_summary="value",
            ),
        ),
    )
    state = engine.new_state()
    root = engine.append_occurrence(state, root_template, build_path=("Root",))
    source = engine.append_occurrence(state, source_template, build_path=("Value",))
    target_record = engine.record_id(state, root, 0)
    engine.append_edge(
        state,
        target_record_id=target_record,
        source_occurrence_id=source,
        operation_key="insert.expression",
    )
    engine.mark_satisfied(state, target_record)
    plan = MaterializationPlan(
        root_occurrence_id=root,
        operation_stream=(
            MaterializationOperation(
                operation_key="insert.expression",
                target_record_id=target_record,
                source_occurrence_id=source,
                captures={"surface_key": "expression.hole"},
            ),
        ),
        debug_views={"final_source": "result = value"},
        artifact_requests=("python_ast",),
    )

    actual_text = write_structural_snapshot(
        engine.structural_snapshot(state, materialization_plan=plan)
    )

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "lower_engine_tiny_state.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "lower_engine_tiny_state.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text


def test_lower_engine_template_package_matches_golden() -> None:
    engine = LowerEngine()
    template_id = engine.register_template(
        template_key="lower_engine_root",
        source_summary="result = astichi_hole(value)",
        records=(
            TemplateRecordSpec(
                surface_key="expression.hole",
                semantic_summary="expression hole value",
                ast_path="body[0].value",
                role_key="expression.hole",
                materialization_anchor="replace-expression",
                authored_summary="astichi_hole(value)",
            ),
        ),
    )

    actual_text = write_package_snapshot(
        engine.template_package(template_id).snapshot()
    )

    _ACTUAL_PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_PACKAGE_DIR / "lower_engine_root_package.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _PACKAGE_GOLDENS_DIR / "lower_engine_root_package.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text


def test_lower_engine_rejects_foreign_template_handle() -> None:
    engine = LowerEngine()
    foreign_engine = LowerEngine()
    foreign_template = foreign_engine.register_template(
        template_key="foreign",
        source_summary="value",
        records=(),
    )

    with pytest.raises(StaleHandleError, match="another lower engine"):
        engine.append_occurrence(
            engine.new_state(),
            foreign_template,
            build_path=("Foreign",),
        )


def test_lower_engine_rejects_foreign_state() -> None:
    engine = LowerEngine()
    foreign_state = LowerEngine().new_state()
    template = engine.register_template(
        template_key="root",
        source_summary="value",
        records=(),
    )

    with pytest.raises(StaleHandleError, match="another lower engine"):
        engine.append_occurrence(
            foreign_state,
            template,
            build_path=("Root",),
        )
