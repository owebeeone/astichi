from __future__ import annotations

import pytest

import astichi
from astichi.lower_engine.native import load_native_extension, native_capabilities
from astichi.lower_engine.native_compile_validate import (
    native_compile_validate_source,
    native_compile_validation_enabled,
)
from astichi.lower_engine.self_native import SELF_NATIVE_COMPILE_VALIDATION_FEATURE
from astichi.perf_counters import collect_perf_counters


def test_native_compile_validation_capability_when_built() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")
    if SELF_NATIVE_COMPILE_VALIDATION_FEATURE not in capabilities.get(
        "engine_features", ()
    ):
        pytest.skip("rebuild native_engine for F3b compile_validation capability")

    assert native_compile_validation_enabled() is True


def test_native_compile_validate_rejects_authored_astichi_insert() -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_compile_validation_enabled():
        pytest.skip("F3b compile_validation capability not advertised")

    with pytest.raises(Exception, match="astichi_insert"):
        native_compile_validate_source("astichi_insert('block')\n")


def test_native_compile_matches_python_funcargs_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_compile_validation_enabled():
        pytest.skip("F3b compile_validation capability not advertised")

    source = "astichi_funcargs(__astichi_ph_0__=astichi_pass(total))\n"
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "python")
    with pytest.raises(ValueError, match="directive placeholders"):
        astichi.compile(source)

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    with pytest.raises(ValueError, match="directive placeholders"):
        astichi.compile(source)


def test_native_compile_increments_validate_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_compile_validation_enabled():
        pytest.skip("F3b compile_validation capability not advertised")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    with collect_perf_counters() as counters:
        astichi.compile("result = astichi_hole(value)\n")

    assert counters.snapshot()["counts"].get("native_compile_validate_source", 0) == 1
