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
    assert "native.lower_template_package_v2.v1" in capabilities["engine_features"]


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
        (
            'value = astichi_ref("pkg.mod")\n'
            'astichi_ref("self.field")._ = 1\n'
            'del astichi_ref("self.deleted").astichi_v\n'
        ),
        (
            "for x in astichi_for((1, 2)):\n"
            "    astichi_keep(slot)\n"
            "    for y, z in astichi_for(DOMAIN):\n"
            "        value = x + y + z\n"
            "for n in astichi_for(range(2)):\n"
            "    other = n\n"
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


def test_native_template_package_v2_rejects_ref_statement_context_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    with pytest.raises(ValueError, match="unsupported astichi_ref statement"):
        module.extract_template_package_v2_snapshot(
            _engine_with_current_bundle(module),
            'astichi_ref("pkg.mod")\n',
            "package_v2.py",
            1,
        )


def test_native_template_package_v2_source_registration_stores_package_rows_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = (
        "def run():\n"
        "    result = astichi_hole(value)\n"
        "    return astichi_ref(\"pkg.value\")\n"
    )
    engine = _engine_with_current_bundle(module)
    template = module.register_template_package_v2_source(
        engine,
        source,
        "package_v2.py",
        1,
    )
    actual = module.template_package_v2_snapshot(engine, template)
    expected = astichi.compile(source)._lower_template.package_v2.snapshot()

    assert actual == expected

    state = module.assembly_state_create(engine)
    module.assembly_state_append_occurrence(engine, state, template, ("Root",))
    structural = module.assembly_state_snapshot(engine, state)
    assert structural["templates"][0]["record_count"] == len(expected["records"])
    assert structural["records"][0]["resource_name"] == "value"


def test_native_template_package_v2_source_registration_is_deterministic_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = "result = astichi_hole(value)\n"
    engine = _engine_with_current_bundle(module)
    first = module.register_template_package_v2_source(engine, source, "package_v2.py", 1)
    second = module.register_template_package_v2_source(engine, source, "package_v2.py", 1)

    assert module.template_package_v2_snapshot(
        engine,
        first,
    ) == module.template_package_v2_snapshot(engine, second)


def test_native_template_package_v2_snapshot_harness_has_no_stored_package_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    structural = module.extract_template_snapshot(
        engine,
        "result = astichi_hole(value)\n",
        "package_v2.py",
        1,
    )
    template = module.register_template_snapshot(engine, structural)

    with pytest.raises(ValueError, match="does not carry package-v2 rows"):
        module.template_package_v2_snapshot(engine, template)


def _engine_with_current_bundle(module: object) -> object:
    handle = module.engine_create()
    engine = LowerEngine()
    bundle = engine.surface_registry.register_bundle(
        current_surface_bundle_spec()
    ).snapshot()
    module.register_surface_bundle(handle, deepcopy(bundle))
    return handle
