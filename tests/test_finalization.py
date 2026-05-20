import ast

import pytest

import astichi
import astichi.emit.api as emit_api
import astichi.materialize.api as materialize_api


def test_build_defers_output_finalization_work(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("output finalization ran during build")

    monkeypatch.setattr(materialize_api, "rename_scope_collisions", fail)
    monkeypatch.setattr(materialize_api, "_emit_commented_tree", fail)
    monkeypatch.setattr(emit_api, "encode_provenance", fail)

    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            'astichi_comment("generated")\n'
            "astichi_hole(body)\n",
            file_name="tests/finalization.py",
        )
    )
    builder.add.Body(astichi.compile("value = 1\n"))
    builder.Root.body.add.Body()

    built = builder.build()

    raw_names = {
        node.func.id
        for node in ast.walk(built.tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "astichi_comment" in raw_names
    assert "astichi_hole" in raw_names
