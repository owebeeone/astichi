from __future__ import annotations

from io import StringIO
from pathlib import Path

from tests.versioned_test_harness import (
    actual_results_dir,
    build_run_tests_invocation,
    data_golden_dir,
    data_gold_src_dir,
    discover_golden_cases,
    load_install_requirements,
    load_supported_runtime_specs,
    report_run_tests_all_results,
    resolve_requested_runtime_specs,
    runtime_tag,
    should_passthrough_run_tests_all_output,
)


def test_discover_golden_cases_reads_source_scripts(tmp_path: Path) -> None:
    source_dir = tmp_path / "tests" / "data" / "gold_src"
    source_dir.mkdir(parents=True)
    (source_dir / "b_case.py").write_text("", encoding="utf-8")
    (source_dir / "a_case.py").write_text("", encoding="utf-8")
    (source_dir / "notes.txt").write_text("", encoding="utf-8")

    assert discover_golden_cases(tmp_path) == ("a_case.py", "b_case.py")


def test_load_install_requirements_reads_project_and_test_dependencies(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[build-system]
requires = ["hatchling>=1.24"]

[project]
dependencies = ["typing-extensions>=4"]

[project.optional-dependencies]
test = ["pytest>=8"]
dev = ["ruff>=0.6"]
""".strip(),
        encoding="utf-8",
    )

    assert load_install_requirements(pyproject) == [
        "hatchling>=1.24",
        "typing-extensions>=4",
        "pytest>=8",
    ]


def test_load_install_requirements_falls_back_to_dev_group(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[build-system]
requires = ["hatchling>=1.24"]

[project.optional-dependencies]
dev = ["pytest>=7"]
""".strip(),
        encoding="utf-8",
    )

    assert load_install_requirements(pyproject) == ["hatchling>=1.24", "pytest>=7"]


def test_load_supported_runtime_specs_reads_pyproject_matrix(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.astichi.test-matrix]
python = ["3.12", "3.13", "3.14", "3.15"]
""".strip(),
        encoding="utf-8",
    )

    assert load_supported_runtime_specs(pyproject) == ("3.12", "3.13", "3.14", "3.15")


def test_resolve_requested_runtime_specs_defaults_to_supported_matrix(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.astichi.test-matrix]
python = ["3.12", "3.13", "3.14", "3.15"]
""".strip(),
        encoding="utf-8",
    )

    assert resolve_requested_runtime_specs(pyproject, requested=None) == (
        "3.12",
        "3.13",
        "3.14",
        "3.15",
    )
    assert resolve_requested_runtime_specs(pyproject, requested=["3.13", "3.13", "3.14"]) == (
        "3.13",
        "3.14",
    )


def test_build_run_tests_invocation_preserves_pytest_args() -> None:
    script_path = Path("tests/versioned_test_harness.py")

    assert build_run_tests_invocation(
        script_path=script_path,
        python_executable=".venv/bin/python",
        python_spec="3.14",
        venv_root="tests/.uv-venvs",
        recreate=True,
        pytest_args=["tests/test_ast_goldens.py", "-q"],
    ) == [
        ".venv/bin/python",
        "tests/versioned_test_harness.py",
        "run-tests",
        "--python",
        "3.14",
        "--venv-root",
        "tests/.uv-venvs",
        "--recreate",
        "--pytest-args",
        "tests/test_ast_goldens.py",
        "-q",
    ]


def test_report_run_tests_all_results_can_show_passing_output_serially() -> None:
    stdout = StringIO()
    stderr = StringIO()

    report_run_tests_all_results(
        [
            ("3.12", 0, "alpha out\n", ""),
            ("3.13", 0, "beta out\n", "beta err\n"),
        ],
        show_output=True,
        stdout=stdout,
        stderr=stderr,
    )

    assert stdout.getvalue() == (
        "3.12: PASS\n"
        "--- 3.12 stdout ---\n"
        "alpha out\n"
        "3.13: PASS\n"
        "--- 3.13 stdout ---\n"
        "beta out\n"
    )
    assert stderr.getvalue() == "--- 3.13 stderr ---\nbeta err\n"


def test_should_passthrough_run_tests_all_output_only_for_single_selected_version() -> None:
    assert should_passthrough_run_tests_all_output(show_output=False, runtime_specs=("3.12",)) is False
    assert should_passthrough_run_tests_all_output(show_output=True, runtime_specs=("3.12",)) is True
    assert should_passthrough_run_tests_all_output(show_output=True, runtime_specs=("3.12", "3.13")) is False


def test_runtime_and_golden_paths_are_versioned_by_runtime() -> None:
    project_root = Path("project")

    assert runtime_tag((3, 14)) == "py3_14"
    assert data_gold_src_dir(project_root) == project_root / "tests" / "data" / "gold_src"
    assert data_golden_dir(project_root, phase="pre_materialized") == (
        project_root / "tests" / "data" / "goldens" / "pre_materialized"
    )
    assert data_golden_dir(project_root, phase="materialized") == (
        project_root / "tests" / "data" / "goldens" / "materialized"
    )
    assert actual_results_dir(project_root, runtime_version=(3, 14)) == (
        project_root / "tests" / "actual_test_results" / "py3_14"
    )
