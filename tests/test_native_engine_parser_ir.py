from __future__ import annotations

import ast
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


def test_native_engine_parser_ir_copies_augassign_and_namedexpr_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = "total = 0\ntotal += (value := 2)\n"
    native_module = module.compile_composable(source, "native-augassign.py")
    python_ast = module.copy_to_python_ast(native_module)

    compile(python_ast, "native-augassign.py", "exec")
    assert native_module.node_counts()["AugAssign"] == 1
    assert native_module.node_counts()["NamedExpr"] == 1


@pytest.mark.parametrize(
    "source",
    [
        "def sequence(items):\n    for item in items:\n        yield item\n",
        "def sequence(items):\n    yield from items\n",
        "def make_adder(x):\n    return lambda y: x + y\n",
        "async def wait_for(value):\n    return await value\n",
    ],
)
def test_native_engine_parser_ir_copies_common_expression_nodes_when_available(
    source: str,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    native_module = module.compile_composable(source, "native-generator.py")
    python_ast = module.copy_to_python_ast(native_module)

    compile(python_ast, "native-generator.py", "exec")


def test_native_engine_parser_ir_copies_async_control_nodes_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = (
        "async def run(seq, cm):\n"
        "    async for item in seq:\n"
        "        pass\n"
        "    async with cm as value:\n"
        "        return value\n"
    )
    native_module = module.compile_composable(source, "native-async-control.py")
    python_ast = module.copy_to_python_ast(native_module)

    compile(python_ast, "native-async-control.py", "exec")
    assert native_module.node_counts()["AsyncFor"] == 1
    assert native_module.node_counts()["AsyncWith"] == 1


@pytest.mark.skipif(not hasattr(ast, "TryStar"), reason="requires Python 3.11 AST")
def test_native_engine_parser_ir_copies_trystar_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = (
        "def handle():\n"
        "    try:\n"
        "        raise ExceptionGroup('x', [])\n"
        "    except* ValueError as exc:\n"
        "        seen = exc\n"
        "    else:\n"
        "        seen = None\n"
        "    finally:\n"
        "        done = True\n"
        "    return seen\n"
    )
    native_module = module.compile_composable(source, "native-trystar.py")
    python_ast = module.copy_to_python_ast(native_module)

    compile(python_ast, "native-trystar.py", "exec")
    assert native_module.node_counts()["TryStar"] == 1


def test_native_engine_parser_ir_copies_match_patterns_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = (
        "def classify(value):\n"
        "    match value:\n"
        "        case {'kind': 'point', 'x': x, **rest} if x > 0:\n"
        "            return rest\n"
        "        case Point(0, y=y) | Point(x=1, y=y):\n"
        "            return y\n"
        "        case [head, *tail] as items:\n"
        "            return items\n"
        "        case None:\n"
        "            return 'none'\n"
        "        case _:\n"
        "            return 'other'\n"
    )
    native_module = module.compile_composable(source, "native-match.py")
    python_ast = module.copy_to_python_ast(native_module)

    compile(python_ast, "native-match.py", "exec")
    counts = native_module.node_counts()
    assert counts["Match"] == 1
    assert counts["MatchMapping"] == 1
    assert counts["MatchClass"] == 2
    assert counts["MatchOr"] == 1
    assert counts["MatchSequence"] == 1


@pytest.mark.skipif(not hasattr(ast, "TypeAlias"), reason="requires Python 3.12 AST")
def test_native_engine_parser_ir_copies_type_params_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = (
        "type Response[T] = list[T]\n"
        "class Box[T]:\n"
        "    pass\n"
        "def ident[T](value: T) -> T:\n"
        "    return value\n"
    )
    native_module = module.compile_composable(source, "native-typealias.py")
    python_ast = module.copy_to_python_ast(native_module)

    compile(python_ast, "native-typealias.py", "exec")
    assert native_module.node_counts()["TypeAlias"] == 1
    assert native_module.node_counts()["TypeVar"] == 3


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
