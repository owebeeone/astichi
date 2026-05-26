from __future__ import annotations

from tests.lower_engine_matrix import (
    available_matrix_engines,
    matrix_exempt_module,
    matrix_variant_suffix,
    node_uses_matrix_variant,
)


def test_matrix_exempt_module_names() -> None:
    assert matrix_exempt_module("test_native_engine_parser_ir")
    assert matrix_exempt_module("test_validation_perf_helper")
    assert not matrix_exempt_module("test_assembler_scope")


def test_matrix_variant_nodeid_suffix() -> None:
    assert node_uses_matrix_variant(
        "tests/test_emit.py::test_round_trip[lower_engine=python]"
    )
    assert not node_uses_matrix_variant("tests/test_emit.py::test_round_trip")
    assert matrix_variant_suffix("native") == "[lower_engine=native]"


def test_available_matrix_engines_includes_python() -> None:
    assert "python" in available_matrix_engines()
