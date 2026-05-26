from __future__ import annotations

import ast

import pytest

import astichi
from astichi.lower_engine.native import load_native_extension
from astichi.perf_counters import collect_perf_counters


def test_native_bind_specializes_without_rebuild_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_native(monkeypatch)
    piece = astichi.compile("astichi_bind_external(value)\nresult = value\n")

    with collect_perf_counters() as counters:
        bound = piece.bind(value=7)

    assert ast.unparse(bound.tree) == "result = 7"
    counts = counters.snapshot()["counts"]
    assert counts["native_specialize_bind"] == 1
    assert counts.get("rebuild_composable", 0) == 0


def test_native_bind_identifier_specializes_suffix_without_rebuild_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_native(monkeypatch)
    piece = astichi.compile("result = field__astichi_arg__\n")

    with collect_perf_counters() as counters:
        bound = piece.bind_identifier(field="actual")

    assert ast.unparse(bound.tree) == "result = actual"
    counts = counters.snapshot()["counts"]
    assert counts["native_specialize_identifier"] == 1
    assert counts.get("rebuild_composable", 0) == 0


def test_native_bind_identifier_specializes_keyword_names_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_native(monkeypatch)
    piece = astichi.compile("func(field__astichi_arg__=1)\n")

    bound = piece.bind_identifier(field="actual")

    assert ast.unparse(bound.tree) == "func(actual=1)"


def test_native_bind_identifier_marks_boundary_pass_as_explicit_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_native(monkeypatch)
    piece = astichi.compile("result = astichi_pass(dep)\n")

    bound = piece.bind_identifier(dep="outer_dep")

    assert ast.unparse(bound.tree) == "result = astichi_pass(outer_dep, bound=True)"


def test_native_keep_name_specializes_without_rebuild_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_native(monkeypatch)
    piece = astichi.compile("value = 1\n")

    with collect_perf_counters() as counters:
        kept = piece.with_keep_names(["value"])

    assert kept.keep_names == frozenset({"value"})
    assert kept.tree is piece.tree
    counts = counters.snapshot()["counts"]
    assert counts["native_specialize_keep"] == 1
    assert counts.get("rebuild_composable", 0) == 0


def _require_native(monkeypatch: pytest.MonkeyPatch) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
