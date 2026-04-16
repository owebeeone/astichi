from __future__ import annotations

import ast

import astichi
from astichi.emit import decode_provenance, encode_provenance, extract_provenance


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


def test_encode_decode_provenance_round_trips() -> None:
    tree = ast.parse("x = 1\ny = x + 2\n")
    payload = encode_provenance(tree)
    restored = decode_provenance(payload)
    assert ast.dump(restored) == ast.dump(tree)


def test_emit_with_provenance_includes_comment() -> None:
    compiled = astichi.compile("value = 1\n")
    result = compiled.emit(provenance=True)
    assert "# astichi-provenance: " in result
    compile(result, "<test>", "exec")


def test_emit_without_provenance_excludes_comment() -> None:
    compiled = astichi.compile("value = 1\n")
    result = compiled.emit(provenance=False)
    assert "# astichi-provenance: " not in result


def test_extract_provenance_from_emitted_source() -> None:
    compiled = astichi.compile("x = 1\ny = 2\n")
    source = compiled.emit(provenance=True)
    restored = extract_provenance(source)
    assert restored is not None
    assert ast.dump(restored) == ast.dump(compiled.tree)


def test_extract_provenance_returns_none_without_comment() -> None:
    source = "x = 1\n"
    assert extract_provenance(source) is None
