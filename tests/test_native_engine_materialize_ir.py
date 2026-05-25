from __future__ import annotations

from copy import deepcopy

import pytest

from astichi.lower_engine import LowerEngine, current_surface_bundle_spec
from astichi.lower_engine.native import load_native_extension, native_capabilities


def test_native_materialization_workspace_capability_when_available() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")

    assert "native.materialization_workspace.v1" in capabilities["engine_features"]


def test_native_materialization_workspace_clones_and_resolves_locator_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    template = module.register_template_package_v2_source(
        engine,
        "result = astichi_hole(value)\n",
        "workspace.py",
        1,
    )
    workspace = module.materialization_workspace_create(engine, template)

    snapshot = module.materialization_workspace_snapshot(engine, workspace)
    resolved = module.materialization_workspace_resolve_locator(engine, workspace, 0)
    root = module.materialization_workspace_resolve_locator(engine, workspace, 1)

    assert snapshot == {
        "body_kinds": ["Assign"],
        "body_len": 1,
        "kind": "materialization-workspace",
        "locator_count": 2,
        "template_id": 0,
    }
    assert resolved == {
        "ast_path": "body[0]/value",
        "locator_id": 0,
        "resolved_kind": "Call",
        "template_id": 0,
    }
    assert root == {
        "ast_path": ".",
        "locator_id": 1,
        "resolved_kind": "Module",
        "template_id": 0,
    }


def test_native_materialization_workspace_replaces_statement_with_pass_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    template = module.register_template_package_v2_source(
        engine,
        "astichi_hole(body)\n",
        "workspace.py",
        1,
    )
    workspace = module.materialization_workspace_create(engine, template)

    assert module.materialization_workspace_snapshot(engine, workspace)["body_kinds"] == [
        "Expr"
    ]
    module.materialization_workspace_replace_statement_with_pass(engine, workspace, 0)

    assert module.materialization_workspace_snapshot(engine, workspace)["body_kinds"] == [
        "Pass"
    ]


def test_native_materialization_workspace_applies_expression_edge_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    root_template = module.register_template_package_v2_source(
        engine,
        "result = astichi_hole(value)\n",
        "workspace.py",
        1,
    )
    expression_template = module.register_template_package_v2_source(
        engine,
        "40 + 2\n",
        "workspace.py",
        1,
    )
    state = module.assembly_state_create(engine)
    root = module.assembly_state_append_occurrence(
        engine,
        state,
        root_template,
        ("Root",),
    )
    expression = module.assembly_state_append_occurrence(
        engine,
        state,
        expression_template,
        ("Root", "Expression"),
        root,
    )
    target = module.assembly_state_record_handle(engine, state, root, 0)
    edge = module.assembly_state_append_edge(
        engine,
        state,
        target,
        expression,
        "astichi.operation.replace_expression",
        0,
    )
    workspace = module.materialization_workspace_create(engine, root_template)

    assert module.materialization_workspace_resolve_locator(engine, workspace, 0)[
        "resolved_kind"
    ] == "Call"
    module.materialization_workspace_apply_expression_edge(
        engine,
        workspace,
        state,
        edge,
    )

    assert module.materialization_workspace_resolve_locator(engine, workspace, 0) == {
        "ast_path": "body[0]/value",
        "locator_id": 0,
        "resolved_kind": "BinOp",
        "template_id": 0,
    }


@pytest.mark.parametrize(
    ("source", "probe_path", "before_kind", "after_kind"),
    [
        pytest.param(
            "value = astichi_ref('pkg.mod')\n",
            "body[0]/value",
            "Call",
            "Attribute",
            id="value-form",
        ),
        pytest.param(
            "astichi_ref('self.f0')._ = 42\n",
            "body[0]/targets[0]/value",
            "Call",
            "Name",
            id="store-sentinel",
        ),
        pytest.param(
            "del astichi_ref('self.f0').astichi_v\n",
            "body[0]/targets[0]/value",
            "Call",
            "Name",
            id="delete-sentinel",
        ),
    ],
)
def test_native_materialization_workspace_lowers_literal_refs_when_available(
    source: str,
    probe_path: str,
    before_kind: str,
    after_kind: str,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    template = module.register_template_package_v2_source(
        engine,
        source,
        "workspace.py",
        1,
    )
    workspace = module.materialization_workspace_create(engine, template)

    assert module.materialization_workspace_resolve_ast_path(
        engine,
        workspace,
        probe_path,
    )["resolved_kind"] == before_kind
    count = module.materialization_workspace_lower_literal_refs(engine, workspace)

    assert count == 1
    assert module.materialization_workspace_resolve_ast_path(
        engine,
        workspace,
        probe_path,
    )["resolved_kind"] == after_kind


def test_native_materialization_workspace_applies_external_overlay_literal_ref_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    template = module.register_template_package_v2_source(
        engine,
        "value = astichi_ref(astichi_bind_external(path))\n",
        "workspace.py",
        1,
    )
    state = module.assembly_state_create(engine)
    root = module.assembly_state_append_occurrence(
        engine,
        state,
        template,
        ("Root",),
    )
    external_record = module.assembly_state_record_handle(engine, state, root, 0)
    overlay = module.assembly_state_append_overlay(
        engine,
        state,
        external_record,
        "external",
        "path",
    )
    workspace = module.materialization_workspace_create(engine, template)

    assert module.materialization_workspace_resolve_ast_path(
        engine,
        workspace,
        "body[0]/value/args[0]",
    )["resolved_kind"] == "Call"
    external_count = module.materialization_workspace_apply_external_overlay_literal(
        engine,
        workspace,
        state,
        overlay,
        "'pkg.mod'",
    )
    assert external_count == 1
    assert module.materialization_workspace_resolve_ast_path(
        engine,
        workspace,
        "body[0]/value/args[0]",
    )["resolved_kind"] == "Constant"

    ref_count = module.materialization_workspace_lower_literal_refs(engine, workspace)
    assert ref_count == 1
    assert module.materialization_workspace_resolve_ast_path(
        engine,
        workspace,
        "body[0]/value",
    )["resolved_kind"] == "Attribute"


def test_native_materialization_workspace_bad_locator_diagnostic_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    template = module.register_template_package_v2_source(
        engine,
        "result = astichi_hole(value)\n",
        "workspace.py",
        1,
    )
    workspace = module.materialization_workspace_create(engine, template)

    with pytest.raises(RuntimeError, match="unknown native locator"):
        module.materialization_workspace_resolve_locator(engine, workspace, 99)


def test_native_materialization_workspace_requires_source_registered_template_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    structural = module.extract_template_snapshot(
        engine,
        "result = astichi_hole(value)\n",
        "workspace.py",
        1,
    )
    template = module.register_template_snapshot(engine, structural)

    with pytest.raises(ValueError, match="does not carry native parser IR"):
        module.materialization_workspace_create(engine, template)


def _engine_with_current_bundle(module: object) -> object:
    handle = module.engine_create()
    engine = LowerEngine()
    bundle = engine.surface_registry.register_bundle(
        current_surface_bundle_spec()
    ).snapshot()
    module.register_surface_bundle(handle, deepcopy(bundle))
    return handle
