from __future__ import annotations

import astichi


def test_emit_produces_valid_python() -> None:
    compiled = astichi.compile("value = 1\n")
    result = compiled.emit(provenance=False)
    assert "value = 1" in result
    compile(result, "<test>", "exec")


def test_emit_trailing_newline() -> None:
    compiled = astichi.compile("x = 1\n")
    result = compiled.emit(provenance=False)
    assert result.endswith("\n")


def test_emit_after_materialize() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile("astichi_hole(body)\nastichi_export(result)\n")
    )
    builder.add.Impl(astichi.compile("result = 42\n"))
    builder.Root.body.add.Impl()

    built = builder.build()
    materialized = built.materialize()
    source = materialized.emit(provenance=False)

    assert "result = 42" in source
    assert "astichi_hole" not in source
    compile(source, "<test>", "exec")


def test_emit_empty_module() -> None:
    compiled = astichi.compile("")
    result = compiled.emit(provenance=False)
    assert result == "\n"


def test_emit_multi_statement() -> None:
    compiled = astichi.compile("x = 1\ny = 2\nz = x + y\n")
    result = compiled.emit(provenance=False)
    assert "x = 1" in result
    assert "y = 2" in result
    assert "z = x + y" in result
    compile(result, "<test>", "exec")
