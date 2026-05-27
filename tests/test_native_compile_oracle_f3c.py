"""F3c: compile structural oracle — python vs native lower templates."""

from __future__ import annotations

import pytest

import astichi
from astichi.lower_engine import LowerTemplateBinding
from astichi.lower_engine.native import load_native_extension
from astichi.structural_snapshot import write_structural_snapshot

_COMPILE_ORACLE_SOURCES: tuple[tuple[str, str], ...] = (
    ("hole_expression", "result = astichi_hole(value)\n"),
    (
        "bind_external",
        "value = astichi_bind_external(default)\nreturn astichi_hole(result)\n",
    ),
    (
        "func_with_hole",
        """
def make():
    value = astichi_bind_external(default)
    return astichi_hole(result)
""",
    ),
    ("keep_suffix", "name__astichi_keep__ = 1\n"),
)


@pytest.mark.parametrize("name,source", _COMPILE_ORACLE_SOURCES)
def test_compile_structural_oracle_python_matches_native(
    name: str,
    source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "python")
    python_composable = astichi.compile(source)
    python_template = python_composable._lower_template
    assert isinstance(python_template, LowerTemplateBinding)

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    native_composable = astichi.compile(source)
    native_template = native_composable._lower_template
    assert isinstance(native_template, LowerTemplateBinding)
    assert native_template.backend == "native-rust"

    python_snapshot = write_structural_snapshot(
        python_template.structural_snapshot()
    )
    native_snapshot = write_structural_snapshot(
        native_template.structural_snapshot()
    )
    assert native_snapshot == python_snapshot, (
        f"compile oracle fixture `{name}` structural mismatch"
    )
