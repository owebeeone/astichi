"""F4d: scope.build rejects Python materialize fallback when cap is advertised."""

from __future__ import annotations

import pytest

import astichi
from astichi.assembler import AssemblyScope, as_composable, require_one
from astichi.lower_engine.native import load_native_extension
from astichi.lower_engine.self_native import (
    SELF_NATIVE_MATERIALIZE_NO_PYTHON_FALLBACK_FEATURE,
)
from astichi.lower_engine.self_native_gates import (
    native_materialize_no_python_fallback_enabled,
)


def test_materialize_no_python_fallback_capability_when_built() -> None:
    from astichi.lower_engine.native import native_capabilities

    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")
    if SELF_NATIVE_MATERIALIZE_NO_PYTHON_FALLBACK_FEATURE not in capabilities.get(
        "engine_features", ()
    ):
        pytest.skip("rebuild native_engine for F4d materialize_no_python_fallback")
    assert native_materialize_no_python_fallback_enabled() is True


def test_scope_build_native_materialize_succeeds_with_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_materialize_no_python_fallback_enabled():
        pytest.skip("F4d materialize_no_python_fallback capability not advertised")

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
    emitted = scope.build().materialize().emit(provenance=False)
    assert "result = 1" in emitted
