"""F4c: materialize output oracle — python vs native scope assembly."""

from __future__ import annotations

from collections.abc import Callable

import pytest

import astichi
from astichi.assembler import (
    AssemblyScope,
    as_composable,
    as_external_value,
    require_one,
)
from astichi.lower_engine.native import load_native_extension


def _run_block_insert(monkeypatch: pytest.MonkeyPatch, engine: str) -> str:
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", engine)
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
    return scope.build().materialize().emit(provenance=False)


def _run_external_overlay(monkeypatch: pytest.MonkeyPatch, engine: str) -> str:
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", engine)
    root = astichi.compile("value = astichi_bind_external(value)\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)
    check = scope.find_candidates(
        as_external_value(42),
        name="value",
        build_match=("Root",),
    )
    scope.apply(require_one(check))
    return scope.build().materialize().emit(provenance=False)


@pytest.mark.parametrize(
    "runner",
    (
        _run_block_insert,
        _run_external_overlay,
    ),
)
def test_materialize_emit_oracle_python_matches_native(
    runner: Callable[[pytest.MonkeyPatch, str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    python_emit = runner(monkeypatch, "python")
    native_emit = runner(monkeypatch, "native")
    assert native_emit == python_emit
