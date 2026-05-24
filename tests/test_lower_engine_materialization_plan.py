from __future__ import annotations

from pathlib import Path
import sys

import astichi
from astichi.assembler import (
    AssemblyScope,
    as_composable,
    as_external_value,
    as_identifier,
    require_one,
)
from astichi.structural_snapshot import write_structural_snapshot
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STRUCTURAL_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="structural")
_ACTUAL_STRUCTURAL_DIR = (
    actual_results_dir(
        _PROJECT_ROOT,
        runtime_version=(sys.version_info.major, sys.version_info.minor),
    )
    / "goldens"
    / "structural"
)


def test_scope_lower_materialization_plan_matches_structural_golden() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
class class_name__astichi_arg__:
    default = astichi_bind_external(default_value)

    def run(self):
        astichi_hole(body)

result = astichi_hole(value)
""".strip()
        + "\n"
    )
    body = astichi.compile("item = 1\n")
    value = astichi.compile("40 + 2\n")
    scope.add("Root", root)

    scope.apply(
        require_one(
            scope.find_candidates(
                as_identifier("GeneratedClass"),
                name="class_name",
                build_match=("Root",),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_external_value(7),
                name="default_value",
                build_match=("Root",),
                owner_match=("GeneratedClass",),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(body, build_name="Body"),
                name="body",
                build_match=("Root",),
                owner_match=("GeneratedClass", "run"),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(value, build_name="Value"),
                name="value",
                build_match=("Root",),
            )
        )
    )

    plan = scope.lower_materialization_plan()
    assert {operation.operation_key for operation in plan.operation_stream} == {
        "astichi.operation.lower_external_ref",
        "astichi.operation.replace_expression",
        "astichi.operation.rewrite_identifier",
        "astichi.operation.splice_body_at_marker",
    }
    assert tuple(operation.operation_key for operation in plan.hygiene_stream) == (
        "astichi.operation.gate_no_unresolved",
    )

    actual_text = write_structural_snapshot(
        scope.lower_structural_snapshot(materialization_plan=plan)
    )

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "scope_materialization_plan.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "scope_materialization_plan.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text


def test_scope_lower_parameter_plan_matches_structural_golden() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("def run(value__astichi_param_hole__):\n    pass\n")
    params = astichi.compile("def astichi_params(item):\n    pass\n")
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(params, build_name="Params"),
                name="value",
                build_match=("Root",),
                owner_match=("run",),
            )
        )
    )

    plan = scope.lower_materialization_plan()
    assert tuple(operation.operation_key for operation in plan.operation_stream) == (
        "astichi.operation.splice_parameters",
    )
    assert tuple(operation.operation_key for operation in plan.hygiene_stream) == (
        "astichi.operation.gate_no_unresolved",
    )

    actual_text = write_structural_snapshot(
        scope.lower_structural_snapshot(materialization_plan=plan)
    )

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "scope_parameter_plan.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (_STRUCTURAL_GOLDENS_DIR / "scope_parameter_plan.json").read_text(
        encoding="utf-8"
    )
    assert actual_text == expected_text


def test_scope_lower_funcargs_plan_matches_structural_golden() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("result = func(*astichi_hole(args))\n")
    args = astichi.compile("astichi_funcargs(1)\n")
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(args, build_name="Args"),
                name="args",
                build_match=("Root",),
            )
        )
    )

    plan = scope.lower_materialization_plan()
    assert tuple(operation.operation_key for operation in plan.operation_stream) == (
        "astichi.operation.splice_call_arguments",
    )
    assert tuple(operation.operation_key for operation in plan.hygiene_stream) == (
        "astichi.operation.gate_no_unresolved",
    )

    actual_text = write_structural_snapshot(
        scope.lower_structural_snapshot(materialization_plan=plan)
    )

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "scope_funcargs_plan.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (_STRUCTURAL_GOLDENS_DIR / "scope_funcargs_plan.json").read_text(
        encoding="utf-8"
    )
    assert actual_text == expected_text


def test_scope_lower_defaulted_block_plan_matches_structural_golden() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
def run():
    with astichi_hole(body) as astichi_fallback:
        result = 1
""".strip()
        + "\n"
    )
    scope.add("Root", root)

    plan = scope.lower_materialization_plan()
    assert tuple(operation.operation_key for operation in plan.operation_stream) == (
        "astichi.operation.splice_body_at_marker",
    )
    assert plan.operation_stream[0].captures["fallback_selected"] is True
    assert tuple(operation.operation_key for operation in plan.hygiene_stream) == (
        "astichi.operation.gate_no_unresolved",
    )

    actual_text = write_structural_snapshot(
        scope.lower_structural_snapshot(materialization_plan=plan)
    )

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "scope_defaulted_block_plan.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "scope_defaulted_block_plan.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text


def test_scope_lower_pyimport_plan_matches_structural_golden() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        "astichi_pyimport(module=foo, names=(a, b))\nresult = a + b\n"
    )
    scope.add("Root", root)

    plan = scope.lower_materialization_plan()
    assert tuple(operation.operation_key for operation in plan.operation_stream) == ()
    assert tuple(operation.operation_key for operation in plan.hygiene_stream) == (
        "astichi.operation.managed_import_request",
        "astichi.operation.managed_import_request",
        "astichi.operation.gate_no_unresolved",
    )

    actual_text = write_structural_snapshot(
        scope.lower_structural_snapshot(materialization_plan=plan)
    )

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "scope_pyimport_plan.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (_STRUCTURAL_GOLDENS_DIR / "scope_pyimport_plan.json").read_text(
        encoding="utf-8"
    )
    assert actual_text == expected_text


def test_scope_lower_boundary_plan_matches_structural_golden() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
def run():
    items = []
    exported = []
    astichi_hole(body)
    return items, exported
""".strip()
        + "\n"
    )
    body = astichi.compile(
        """
astichi_import(items)
items.append(1)
astichi_pass(exported).append(2)
value = 3
astichi_export(value)
""".strip()
        + "\n"
    )
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(body, build_name="Body"),
                name="body",
                build_match=("Root",),
                owner_match=("run",),
            )
        )
    )

    plan = scope.lower_materialization_plan()
    assert tuple(operation.operation_key for operation in plan.operation_stream) == (
        "astichi.operation.splice_body_at_marker",
    )
    assert tuple(operation.operation_key for operation in plan.hygiene_stream) == (
        "astichi.operation.strip_marker",
        "astichi.operation.strip_marker",
        "astichi.operation.strip_marker",
        "astichi.operation.gate_no_unresolved",
    )

    actual_text = write_structural_snapshot(
        scope.lower_structural_snapshot(materialization_plan=plan)
    )

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "scope_boundary_plan.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (_STRUCTURAL_GOLDENS_DIR / "scope_boundary_plan.json").read_text(
        encoding="utf-8"
    )
    assert actual_text == expected_text


def test_scope_lower_keep_collision_plan_matches_structural_golden() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
def run():
    value = 1
    astichi_keep(value)
    astichi_hole(body)
    return value
""".strip()
        + "\n"
    )
    body = astichi.compile("value = 2\nseen = value\n")
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(body, build_name="Body"),
                name="body",
                build_match=("Root",),
                owner_match=("run",),
            )
        )
    )

    plan = scope.lower_materialization_plan()
    assert tuple(operation.operation_key for operation in plan.operation_stream) == (
        "astichi.operation.splice_body_at_marker",
    )
    assert tuple(operation.operation_key for operation in plan.hygiene_stream) == (
        "astichi.operation.rename_if_collides",
        "astichi.operation.keep_name",
        "astichi.operation.gate_no_unresolved",
    )

    actual_text = write_structural_snapshot(
        scope.lower_structural_snapshot(materialization_plan=plan)
    )

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "scope_keep_collision_plan.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "scope_keep_collision_plan.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text


def test_scope_lower_elif_plan_matches_structural_golden() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
def dispatch(kind):
    if kind == "base":
        return "base"
    elif astichi_elif(branches):
        pass
    else:
        return "fallback"
""".strip()
        + "\n"
    )
    branch = astichi.compile(
        """
def astichi_elif():
    if kind == "create":
        return "created"
""".strip()
        + "\n"
    )
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(branch, build_name="Create"),
                name="branches",
                build_match=("Root",),
                owner_match=("dispatch",),
            )
        )
    )

    plan = scope.lower_materialization_plan()
    assert tuple(operation.operation_key for operation in plan.operation_stream) == (
        "astichi.operation.append_clause",
    )
    assert tuple(operation.operation_key for operation in plan.hygiene_stream) == (
        "astichi.operation.gate_no_unresolved",
    )

    actual_text = write_structural_snapshot(
        scope.lower_structural_snapshot(materialization_plan=plan)
    )

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "scope_elif_plan.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (_STRUCTURAL_GOLDENS_DIR / "scope_elif_plan.json").read_text(
        encoding="utf-8"
    )
    assert actual_text == expected_text
