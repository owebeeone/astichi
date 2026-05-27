"""Template identity: Python and native SHA-256 of registration source."""

from __future__ import annotations

import hashlib

import pytest

from astichi.lower_engine.facade import _current_surface_bundle_snapshot
from astichi.lower_engine.native import load_native_extension
from astichi.lower_engine.template_key import template_key_from_source


def test_template_key_from_source_matches_hashlib() -> None:
    source = "result = astichi_hole(value)\n"
    expected = "template:" + hashlib.sha256(source.encode()).hexdigest()[:16]
    assert template_key_from_source(source) == expected


def test_native_template_key_matches_python_when_extension_built() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = "def f():\n    return 1\n"
    engine = module.engine_create()
    try:
        module.register_surface_bundle(engine, _current_surface_bundle_snapshot())
        package = module.extract_template_package_v2_snapshot(
            engine, source, "key_parity.py", 1
        )
        assert package["template_key"] == template_key_from_source(source)
    finally:
        module.engine_close(engine)
