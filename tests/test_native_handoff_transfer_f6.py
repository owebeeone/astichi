"""F6: transfer native materialize handoff without a second clone_ast copy."""

from __future__ import annotations

import ast

import pytest

import astichi
from astichi.assembler import AssemblyScope, as_composable, require_one
from astichi.asttools import clone_ast
from astichi.lower_engine.native import load_native_extension, native_capabilities
from astichi.lower_engine.self_native import SELF_NATIVE_HANDOFF_TRANSFER_FEATURE
from astichi.lower_engine.self_native_gates import native_handoff_transfer_enabled
from astichi.perf_counters import collect_perf_counters


def test_handoff_transfer_capability_when_built() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")
    if SELF_NATIVE_HANDOFF_TRANSFER_FEATURE not in capabilities.get(
        "engine_features", ()
    ):
        pytest.skip("rebuild native_engine for F6 handoff_transfer capability")
    assert native_handoff_transfer_enabled() is True


def test_to_executable_ast_transfers_without_second_copy_python_ast_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_handoff_transfer_enabled():
        pytest.skip("F6 handoff_transfer capability not advertised")

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
        executable = built.to_executable_ast()

    counts = counters.snapshot()["counts"]
    assert counts.get("copy_python_ast", 0) == 1
    assert counts.get("native_materialize_workspace_copy", 0) == 0
    assert counts.get("to_executable_ast", 0) == 0
    assert executable is built.tree


def test_second_to_executable_ast_clones_after_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_handoff_transfer_enabled():
        pytest.skip("F6 handoff_transfer capability not advertised")

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
    built = scope.build()
    first = built.to_executable_ast()
    second = built.to_executable_ast()
    assert first is built.tree
    assert second is not first
    assert ast.dump(first, include_attributes=False) == ast.dump(
        second,
        include_attributes=False,
    )
