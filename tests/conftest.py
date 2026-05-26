"""Pytest hooks for dual python/native lower-engine coverage."""

from __future__ import annotations

import sys

import pytest

from tests.lower_engine_matrix import (
    ENGINE_SELECTION_ENV,
    available_matrix_engines,
    matrix_enabled,
    matrix_exempt_module,
    matrix_variant_suffix,
    node_uses_matrix_variant,
)

# Canonical structural snapshots are regenerated with Python 3.14 (see tests/README.md).
_CANONICAL_STRUCTURAL_RUNTIME = (3, 14)


def _is_structural_golden_test(item: pytest.Item) -> bool:
    name = item.name
    return (
        "structural_golden" in name
        or "structural_snapshot" in name
        or "shared_lower_engine" in name
    )


@pytest.fixture(autouse=True, params=available_matrix_engines(), ids=str)
def _astichi_lower_engine_matrix(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test once per requested lower engine unless the module is exempt."""
    monkeypatch.setenv(ENGINE_SELECTION_ENV, request.param)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Drop duplicate matrix variants for native-only modules and unavailable engines."""
    if not matrix_enabled():
        return

    engines = available_matrix_engines()
    deselected: list[pytest.Item] = []
    kept: list[pytest.Item] = []

    for item in items:
        nodeid = item.nodeid
        if not node_uses_matrix_variant(nodeid):
            kept.append(item)
            continue

        module_name = item.module.__name__.rsplit(".", 1)[-1]
        if matrix_exempt_module(module_name):
            if nodeid.endswith(matrix_variant_suffix("python")):
                deselected.append(item)
                continue
            kept.append(item)
            continue

        matched_engine = next(
            (engine for engine in engines if nodeid.endswith(matrix_variant_suffix(engine))),
            None,
        )
        if matched_engine is None:
            kept.append(item)
            continue
        if matched_engine in engines:
            kept.append(item)
        else:
            deselected.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = kept

    runtime = sys.version_info[:2]
    if runtime != _CANONICAL_STRUCTURAL_RUNTIME:
        skip_structural = pytest.mark.skip(
            reason=(
                "structural goldens are canonical on Python "
                f"{_CANONICAL_STRUCTURAL_RUNTIME[0]}.{_CANONICAL_STRUCTURAL_RUNTIME[1]}; "
                f"running on Python {runtime[0]}.{runtime[1]}"
            ),
        )
        for item in items:
            if _is_structural_golden_test(item):
                item.add_marker(skip_structural)
