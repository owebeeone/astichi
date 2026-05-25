from __future__ import annotations

from copy import deepcopy

import pytest

import astichi
from astichi.lower_engine import LowerEngine, current_surface_bundle_spec
from astichi.lower_engine.native import load_native_extension, native_capabilities
from astichi.lower_engine.package_v2 import write_package_snapshot


def test_native_template_package_v2_partial_capability_when_available() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")

    assert (
        "native.lower_template_package_v2.snapshot.partial.v1"
        in capabilities["engine_features"]
    )
    assert "native.lower_template_package_v2.v1" not in capabilities["engine_features"]


@pytest.mark.parametrize(
    "source",
    [
        "result = astichi_hole(value)\n",
        (
            "import os\n"
            "from pkg import thing as alias\n"
            "value = 1\n"
            "del stale\n"
            "for item in items:\n"
            "    loop_value = item\n"
            "\n"
            "class Box:\n"
            "    import math as m\n"
            "    field = 1\n"
            "\n"
            "    def make(self, x, *args, y, **kw):\n"
            "        local = x\n"
            "        del old\n"
            "        import json as js\n"
            "        for child in args:\n"
            "            pass\n"
            "\n"
            "        def helper():\n"
            "            return local\n"
            "\n"
            "        class Inner:\n"
            "            pass\n"
            "\n"
            "        return child\n"
        ),
        (
            "astichi_import(inbound, bound=True)\n"
            "astichi_export(outbound)\n"
            "value = astichi_pass(shared, outer_bind=True)\n"
        ),
        (
            "astichi_pyimport(module=foo, names=(a, b))\n"
            "astichi_pyimport(module=foo, names=(a,))\n"
            "astichi_pyimport(module=foo.bar, as_=foobar)\n"
            "astichi_pyimport(module=os)\n"
            "a = 1\n"
        ),
        (
            'astichi_comment("module note")\n'
            "\n"
            "class Box:\n"
            '    astichi_comment("class note")\n'
        ),
    ],
)
def test_native_template_package_v2_snapshot_matches_python_reference_when_available(
    source: str,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    actual = module.extract_template_package_v2_snapshot(
        _engine_with_current_bundle(module),
        source,
        "package_v2.py",
        1,
    )
    expected = astichi.compile(source)._lower_template.package_v2.snapshot()

    assert actual == expected
    assert write_package_snapshot(actual) == write_package_snapshot(expected)


def _engine_with_current_bundle(module: object) -> object:
    handle = module.engine_create()
    engine = LowerEngine()
    bundle = engine.surface_registry.register_bundle(
        current_surface_bundle_spec()
    ).snapshot()
    module.register_surface_bundle(handle, deepcopy(bundle))
    return handle
