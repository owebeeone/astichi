"""Parity probe for registration from a transformed native tree."""

from __future__ import annotations

import ast

import pytest

import astichi
from astichi.lower_engine.facade import (
    _extract_native_package_snapshot,
    _extract_native_template_snapshot,
)
from astichi.lower_engine.native import load_native_extension
from astichi.model.basic import (
    _native_overlay_state,
    _native_record_index,
    _native_specialization_session,
)


@pytest.mark.parametrize(
    "source",
    [
        "result = field__astichi_arg__\n",
        "result = field__astichi_arg__\nastichi_hole(body)\n",
        "# comment\n\nresult = field__astichi_arg__\nastichi_hole(body)\n",
        "def run():\n    result = field__astichi_arg__\n    astichi_export(result)\n",
    ],
)
def test_workspace_registration_preserves_original_locations_and_emitted_identity(
    monkeypatch: pytest.MonkeyPatch, source: str,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    piece = astichi.compile(source, file_name="registration_probe.py", line_number=7)
    original_tree = ast.dump(piece.tree, include_attributes=True)
    session = _native_specialization_session(piece)
    assert session is not None
    module, engine, template, workspace = session
    try:
        state, root = _native_overlay_state(module, engine, template)
        index = _native_record_index(piece, "identifier.demand", "field")
        assert index is not None
        target = module.assembly_state_record_handle(engine, state, root, index)
        overlay = module.assembly_state_append_overlay(
            engine, state, target, "identifier_suffix", "actual",
        )
        module.materialization_workspace_apply_identifier_overlay(
            engine, workspace, state, overlay,
        )
        rendered = module.materialization_workspace_to_source(engine, workspace) + "\n"
        location_source = piece._lower_template.native_source
        actual_package, actual_structural, _ = module._workspace_registration_snapshots(
            engine, workspace, rendered, location_source, piece.origin.line_number,
        )
        expected_package = _extract_native_package_snapshot(
            module=module, source=rendered, origin=piece.origin,
        )
        expected_structural = _extract_native_template_snapshot(
            module=module, source=rendered, origin=piece.origin,
        )
        original_package = _extract_native_package_snapshot(
            module=module, source=location_source, origin=piece.origin,
        )
        original_locators = {row["ast_path"]: row for row in original_package["locators"]}
        for row in actual_package["locators"]:
            assert row["authored_summary"] == original_locators[row["ast_path"]]["authored_summary"]
        assert actual_package["template_key"] == expected_package["template_key"]
        assert actual_structural["templates"][0]["template_key"] == expected_structural["templates"][0]["template_key"]
        assert len(actual_package["records"]) == len(expected_package["records"])
        assert ast.dump(piece.tree, include_attributes=True) == original_tree
    finally:
        module.engine_close(engine)


def test_native_identifier_binding_retains_locations_and_original_piece(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    piece = astichi.compile(
        "# authored comment\n\nresult = first__astichi_arg__ + second__astichi_arg__\nastichi_hole(body)\n",
        file_name="authored.py", line_number=7,
    )
    original = ast.dump(piece.tree, include_attributes=True)
    first = piece.bind_identifier(first="a")
    final = first.bind_identifier(second="b")
    original_hole = piece.tree.body[-1]
    assert final.tree.body[-1].lineno == original_hole.lineno
    assert final.tree.body[-1].col_offset == original_hole.col_offset
    assert final.tree.body[-1].end_lineno == original_hole.end_lineno
    assert final.tree.body[-1].end_col_offset == original_hole.end_col_offset
    assert ast.unparse(final.tree).startswith("result = a + b")
    assert ast.dump(piece.tree, include_attributes=True) == original
    assert sum(port.is_identifier_demand() for port in first.demand_ports) == 1
    assert sum(port.is_identifier_demand() for port in final.demand_ports) == 0


def test_native_binding_copies_registered_tree_without_source_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    piece = astichi.compile("result = first__astichi_arg__ + second__astichi_arg__\n")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("binding must carry the native tree instead of registering source")

    monkeypatch.setattr(module, "register_template_package_v2_source", forbidden)
    monkeypatch.setattr(module, "extract_template_package_v2_snapshot", forbidden)
    monkeypatch.setattr(module, "extract_template_snapshot", forbidden)
    first = piece.bind_identifier(first="a")
    final = first.bind_identifier(second="b")
    assert ast.unparse(final.tree) == "result = a + b"


def test_native_template_copy_rejects_wrong_owner_and_closed_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    piece = astichi.compile("result = field__astichi_arg__\n").bind_identifier(field="actual")
    binding = piece._lower_template
    other = module.engine_create()
    try:
        with pytest.raises(RuntimeError, match="another native engine"):
            module._copy_template(other, binding.native_compile_template_handle, binding.native_template_engine)
        module.engine_close(binding.native_template_engine)
        with pytest.raises(RuntimeError, match="closed"):
            module._copy_template(binding.native_template_engine, binding.native_compile_template_handle, other)
    finally:
        module.engine_close(other)
