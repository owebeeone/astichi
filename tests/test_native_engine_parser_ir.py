from __future__ import annotations

from pathlib import Path

import pytest

from astichi.lower_engine.native import load_native_extension, native_capabilities


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_GOLD_SOURCE_DIR = _PROJECT_ROOT / "tests" / "data" / "gold_src"
_GOLD_SOURCES = tuple(sorted(_GOLD_SOURCE_DIR.glob("*.py")))


def test_native_engine_parser_capabilities_when_available() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")

    assert "native.parser_ir.v1" in capabilities["engine_features"]
    assert capabilities["parser_backend"] == "rustpython-parser 0.4.0"
    assert capabilities["parsing_releases_gil"] is True


def test_native_engine_parser_ir_smoke_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = "def f(x):\n    return x + 1\n"
    native_module = module.compile_composable(source, "native-smoke.py")
    python_ast = module.copy_to_python_ast(native_module)

    compile(python_ast, "native-smoke.py", "exec")
    assert native_module.filename == "native-smoke.py"
    assert native_module.parser_backend == "rustpython-parser 0.4.0"
    assert native_module.node_counts()["FunctionDef"] == 1
    assert module.to_source(native_module) == "def f(x):\n    return x + 1"


@pytest.mark.parametrize("source_path", _GOLD_SOURCES, ids=lambda path: path.name)
def test_native_engine_parser_ir_compiles_gold_sources_when_available(
    source_path: Path,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = source_path.read_text(encoding="utf-8")
    filename = str(source_path.relative_to(_PROJECT_ROOT))
    native_module = module.compile_composable(source, filename)
    python_ast = module.copy_to_python_ast(native_module)

    compile(python_ast, filename, "exec")


def test_native_engine_parser_ir_reports_syntax_errors_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    with pytest.raises(SyntaxError):
        module.compile_composable("def broken(:\n    pass\n", "broken.py")
