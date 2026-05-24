from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

import astichi
from astichi.assembler import (
    AssemblyScope,
    as_composable,
    as_external_value,
    as_identifier,
    find_candidates,
    require_one,
)
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STRUCTURAL_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="structural")
_DIFFERENTIAL_GOLDENS_DIR = _STRUCTURAL_GOLDENS_DIR / "differential"
_ACTUAL_STRUCTURAL_DIR = (
    actual_results_dir(
        _PROJECT_ROOT,
        runtime_version=(sys.version_info.major, sys.version_info.minor),
    )
    / "goldens"
    / "structural"
    / "differential"
)
_GOLDEN_NAME = "lower_differential_harness.json"


@dataclass(frozen=True)
class _Fixture:
    name: str
    run: Callable[[], dict[str, Any]]


def test_transient_lower_differential_harness_matches_golden() -> None:
    """Transient Slice 7.5a harness; delete after lower materialization owns output."""
    actual = _harness_snapshot()
    actual_text = _json_text(actual)

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    (_ACTUAL_STRUCTURAL_DIR / _GOLDEN_NAME).write_text(
        actual_text,
        encoding="utf-8",
    )

    expected_text = (_DIFFERENTIAL_GOLDENS_DIR / _GOLDEN_NAME).read_text(
        encoding="utf-8",
    )
    expected = json.loads(expected_text)

    assert actual["schema"] == expected["schema"]
    assert actual["transient"] is True
    assert expected["transient"] is True
    assert _fixture_names(actual) == _fixture_names(expected)

    expected_by_name = {fixture["name"]: fixture for fixture in expected["fixtures"]}
    for fixture in actual["fixtures"]:
        name = fixture["name"]
        assert fixture == expected_by_name[name], (
            f"lower differential fixture `{name}` mismatch; compared "
            "candidate_checks, lower_source, projected_inventory, and final_source"
        )


def _harness_snapshot() -> dict[str, object]:
    fixtures = (
        _Fixture("block_insert", _block_insert),
        _Fixture("expression_insert", _expression_insert),
        _Fixture("external_overlay", _external_overlay),
        _Fixture("identifier_overlay", _identifier_overlay),
        _Fixture("single_add_satisfaction", _single_add_satisfaction),
    )
    return {
        "schema": "astichi.lower-differential-harness.v1",
        "transient": True,
        "fixtures": [fixture.run() for fixture in fixtures],
    }


def _block_insert() -> dict[str, Any]:
    root = _piece(
        """
        def run():
            astichi_hole(body)
        """
    )
    body = _piece(
        """
        result = 1
        """
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    check = _candidate_check(
        "body",
        scope,
        as_composable(body, build_name="Body"),
        name="body",
        build_match=("Root",),
        owner_match=("run",),
    )
    scope.apply(require_one(check["lower_candidates"]))
    return _fixture_result("block_insert", scope, (check,))


def _expression_insert() -> dict[str, Any]:
    root = _piece("result = astichi_hole(value)")
    value = _piece("40 + 2")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    check = _candidate_check(
        "value",
        scope,
        as_composable(value, build_name="Value"),
        name="value",
        build_match=("Root",),
    )
    scope.apply(require_one(check["lower_candidates"]))
    return _fixture_result("expression_insert", scope, (check,), lower_supported=True)


def _external_overlay() -> dict[str, Any]:
    root = _piece("value = astichi_bind_external(value)")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    check = _candidate_check(
        "value",
        scope,
        as_external_value(7),
        name="value",
        build_match=("Root",),
    )
    scope.apply(require_one(check["lower_candidates"]))
    return _fixture_result("external_overlay", scope, (check,), lower_supported=True)


def _identifier_overlay() -> dict[str, Any]:
    root = _piece(
        """
        class class_name__astichi_arg__:
            pass
        """
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    check = _candidate_check(
        "class_name",
        scope,
        as_identifier("GeneratedClass"),
        name="class_name",
        build_match=("Root",),
    )
    scope.apply(require_one(check["lower_candidates"]))
    return _fixture_result("identifier_overlay", scope, (check,), lower_supported=True)


def _single_add_satisfaction() -> dict[str, Any]:
    root = _piece("result = astichi_hole(value)")
    first = _piece("1")
    second = _piece("2")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    fill_check = _candidate_check(
        "fill_value",
        scope,
        as_composable(first, build_name="First"),
        name="value",
        build_match=("Root",),
    )
    scope.apply(require_one(fill_check["lower_candidates"]))
    satisfied_check = _candidate_check(
        "after_single_add_satisfied",
        scope,
        as_composable(second, build_name="Second"),
        name="value",
        build_match=("Root",),
    )
    return _fixture_result(
        "single_add_satisfaction",
        scope,
        (fill_check, satisfied_check),
        lower_supported=True,
    )


def _candidate_check(
    step: str,
    scope: AssemblyScope,
    resource: object,
    *,
    name: str,
    build_match: tuple[str, ...],
    owner_match: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    lower_candidates = scope.find_candidates(
        resource,
        name=name,
        build_match=build_match,
        owner_match=owner_match,
    )
    projected_candidates = find_candidates(
        scope.inventory,
        resource,
        name=name,
        build_match=build_match,
        owner_match=owner_match,
    )
    assert lower_candidates == projected_candidates, (
        f"lower/projected candidate mismatch in fixture step `{step}`"
    )
    return {
        "step": step,
        "selector": {
            "name": name,
            "build_match": list(build_match),
            "owner_match": None if owner_match is None else list(owner_match),
        },
        "lower_count": len(lower_candidates),
        "projection_count": len(projected_candidates),
        "candidate_lines": [
            list(candidate.diagnostic_lines()) for candidate in lower_candidates
        ],
        "lower_candidates": lower_candidates,
    }


def _fixture_result(
    name: str,
    scope: AssemblyScope,
    checks: tuple[dict[str, Any], ...],
    *,
    lower_supported: bool = False,
) -> dict[str, Any]:
    lower_source = (
        scope.lower_materialize().emit(provenance=False) if lower_supported else None
    )
    return {
        "name": name,
        "candidate_checks": [
            {key: value for key, value in check.items() if key != "lower_candidates"}
            for check in checks
        ],
        "lower_source": lower_source,
        "projected_inventory": str(scope.inventory),
        "final_source": scope.build().materialize().emit(provenance=False),
    }


def _fixture_names(snapshot: dict[str, Any]) -> tuple[str, ...]:
    return tuple(fixture["name"] for fixture in snapshot["fixtures"])


def _piece(source: str) -> astichi.Composable:
    return astichi.compile(source.strip() + "\n")


def _json_text(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"
