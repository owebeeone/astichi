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


def test_native_template_extract_rejects_bad_insert_metadata_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    with pytest.raises(ValueError, match="ref= is only valid on decorator-form"):
        module.extract_template_snapshot(
            _engine_with_current_bundle(module),
            "result = astichi_insert(slot, payload, ref=Root)\n",
            "bad_insert.py",
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


@pytest.mark.parametrize(
    "source",
    [
        "result = astichi_hole(value)\n",
        "astichi_hole(body)\n",
        "value = astichi_bind_external(default)\n",
        "value = astichi_ref(external=thing)\n",
        "astichi_export(result)\nresult = 1\n",
        "astichi_import(name)\nresult = name\n",
        "value = astichi_pass(name)\n",
        "astichi_pyimport(module=foo, names=(a,))\nresult = a\n",
        "astichi_keep(name)\nresult = name\n",
        "astichi_comment(\"hello\")\n",
    ],
)
def test_native_template_extract_direct_call_markers_match_python_reference_when_available(
    source: str,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    actual = module.extract_template_snapshot(
        _engine_with_current_bundle(module),
        source,
        "direct_call.py",
        1,
    )
    expected = astichi.compile(source)._lower_template.structural_snapshot()

    assert actual == expected


def test_native_template_extract_rejects_bad_direct_call_shape_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    with pytest.raises(ValueError, match="name argument must be a bare identifier"):
        module.extract_template_snapshot(
            _engine_with_current_bundle(module),
            "result = astichi_hole('value')\n",
            "bad_marker.py",
            1,
        )


@pytest.mark.parametrize(
    "source",
    [
        "result = name__astichi_arg__\n",
        "class Name__astichi_arg__:\n    pass\n",
        "def func__astichi_arg__():\n    pass\n",
        "def f(value__astichi_arg__):\n    pass\n",
        "result = target(first__astichi_arg__=1)\n",
        "from module_name__astichi_arg__ import symbol__astichi_arg__\n",
        "result = name__astichi_keep__\n",
    ],
)
def test_native_template_extract_identifier_suffixes_match_python_reference_when_available(
    source: str,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    actual = module.extract_template_snapshot(
        _engine_with_current_bundle(module),
        source,
        "identifier_suffix.py",
        1,
    )
    expected = astichi.compile(source)._lower_template.structural_snapshot()

    assert actual == expected


@pytest.mark.parametrize(
    "source",
    [
        "1\n",
        "name\n",
        "target(a)\n",
        "def build():\n    x = 1\n",
        "def astichi_params(timeout=1):\n    pass\n",
        "def astichi_params(name__astichi_arg__=1):\n    pass\n",
        "astichi_funcargs(a, key=b)\n",
        "astichi_funcargs(name__astichi_arg__, key__astichi_arg__=b)\n",
    ],
)
def test_native_template_extract_payload_markers_match_python_reference_when_available(
    source: str,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    actual = module.extract_template_snapshot(
        _engine_with_current_bundle(module),
        source,
        "payload_marker.py",
        1,
    )
    expected = astichi.compile(source)._lower_template.structural_snapshot()

    assert actual == expected


@pytest.mark.parametrize(
    "source",
    [
        "result = astichi_insert(slot, payload)\n",
        (
            "result = astichi_insert("
            "slot, astichi_funcargs(name__astichi_arg__), "
            "pyimport=(astichi_pyimport(module=foo, names=(bar,)),)"
            ")\n"
        ),
        "@astichi_insert(body)\ndef contrib():\n    x = astichi_hole(value)\n",
        "@astichi_insert(params, kind='params')\ndef contrib(x):\n    pass\n",
        (
            "astichi_hole(root)\n\n"
            "@astichi_insert(root, ref=Root)\n"
            "def root():\n"
            "    astichi_hole(body)\n\n"
            "    @astichi_insert(body, order=1, ref=Root.Step)\n"
            "    def step():\n"
            "        x = 1\n"
        ),
    ],
)
def test_native_template_extract_insert_metadata_matches_python_reference_when_available(
    source: str,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    actual = module.extract_template_snapshot(
        _engine_with_current_bundle(module),
        source,
        "insert_metadata.py",
        1,
    )
    expected = astichi.compile(
        source,
        source_kind="astichi-emitted",
    )._lower_template.structural_snapshot()

    assert actual == expected


def _engine_with_current_bundle(module: object) -> object:
    handle = module.engine_create()
    module.register_surface_bundle(handle, deepcopy(_current_bundle_snapshot()))
    return handle


def _current_bundle_snapshot() -> dict[str, object]:
    engine = LowerEngine()
    return engine.surface_registry.register_bundle(current_surface_bundle_spec()).snapshot()
