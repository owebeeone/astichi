"""F4e: scope materialize handoff uses copy_python_ast only."""

from __future__ import annotations

import pytest

import astichi
from astichi.assembler import AssemblyScope, as_composable, require_one
from astichi.lower_engine.native import load_native_extension
from astichi.perf_counters import collect_perf_counters


def test_scope_build_to_executable_ast_uses_copy_python_ast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    root = astichi.compile(
        """
def run():
    astichi_hole(body)
"""
    )
    body = astichi.compile("result = 1\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)
    check = scope.find_candidates(
        as_composable(body, build_name="Body"),
        name="body",
        build_match=("Root",),
        owner_match=("run",),
    )
    scope.apply(require_one(check))

    with collect_perf_counters() as counters:
        built = scope.build()
        built.to_executable_ast()

    counts = counters.snapshot()["counts"]
    assert counts.get("copy_python_ast", 0) >= 1
    assert counts.get("materialize_composable", 0) == 0
