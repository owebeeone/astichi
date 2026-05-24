from __future__ import annotations

from copy import deepcopy

import pytest

import astichi
from astichi.lower_engine import LowerEngine, current_surface_bundle_spec
from astichi.lower_engine.native import load_native_extension, native_capabilities
from astichi.structural_snapshot import write_structural_snapshot


def test_native_template_extract_capability_when_available() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")

    assert "native.template_snapshot.empty.v1" in capabilities["engine_features"]


@pytest.mark.parametrize(
    "source",
    [
        "result = 1\n",
        "def f():\n    return 1\n",
        "class Box:\n    value = 1\n",
    ],
)
def test_native_template_extract_marker_free_matches_python_reference_when_available(
    source: str,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    handle = _engine_with_current_bundle(module)
    actual = module.extract_template_snapshot(handle, source, "marker_free.py", 1)
    expected = astichi.compile(source)._lower_template.structural_snapshot()

    assert actual == expected
    assert write_structural_snapshot(actual) == write_structural_snapshot(expected)


def test_native_template_extract_is_deterministic_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = "value = {'a': 1, 'b': 2}\n"
    first = module.extract_template_snapshot(
        _engine_with_current_bundle(module),
        source,
        "deterministic.py",
        1,
    )
    second = module.extract_template_snapshot(
        _engine_with_current_bundle(module),
        source,
        "deterministic.py",
        1,
    )

    assert first == second


def test_native_template_extract_requires_registered_bundle_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    with pytest.raises(ValueError, match="surface bundle has not been registered"):
        module.extract_template_snapshot(module.engine_create(), "result = 1\n")


def test_native_template_extract_rejects_marker_source_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    with pytest.raises(ValueError, match="marker-free source"):
        module.extract_template_snapshot(
            _engine_with_current_bundle(module),
            "result = astichi_hole(value)\n",
            "marker.py",
            1,
        )


def test_native_template_extract_rejects_syntax_error_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    with pytest.raises(SyntaxError):
        module.extract_template_snapshot(
            _engine_with_current_bundle(module),
            "def broken(:\n    pass\n",
            "broken.py",
            1,
        )


def _engine_with_current_bundle(module: object) -> object:
    handle = module.engine_create()
    module.register_surface_bundle(handle, deepcopy(_current_bundle_snapshot()))
    return handle


def _current_bundle_snapshot() -> dict[str, object]:
    engine = LowerEngine()
    return engine.surface_registry.register_bundle(current_surface_bundle_spec()).snapshot()
