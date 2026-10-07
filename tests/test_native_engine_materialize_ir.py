from __future__ import annotations

import ast
from copy import deepcopy
from textwrap import indent

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
    artifact = module.materialization_workspace_copy_to_python_ast(engine, workspace)
    assert isinstance(artifact, ast.Module)
    compile(artifact, "workspace.py", "exec")
    assert module.materialization_workspace_to_source(engine, workspace) == "result = 40 + 2"


def test_native_materialization_workspace_applies_block_edge_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    root_template = module.register_template_package_v2_source(
        engine,
        "def run():\n"
        "    astichi_hole(body)\n"
        "    return item\n",
        "workspace.py",
        1,
    )
    block_template = module.register_template_package_v2_source(
        engine,
        "item = 1\n",
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
    block = module.assembly_state_append_occurrence(
        engine,
        state,
        block_template,
        ("Root", "Body"),
        root,
    )
    target = module.assembly_state_record_handle(engine, state, root, 0)
    edge = module.assembly_state_append_edge(
        engine,
        state,
        target,
        block,
        "astichi.operation.splice_body_at_marker",
        0,
    )
    workspace = module.materialization_workspace_create(engine, root_template)

    assert module.materialization_workspace_resolve_ast_path(
        engine,
        workspace,
        "body[0]/body[0]",
    )["resolved_kind"] == "Expr"
    module.materialization_workspace_apply_block_edge(engine, workspace, state, edge)

    assert module.materialization_workspace_resolve_ast_path(
        engine,
        workspace,
        "body[0]/body[0]",
    )["resolved_kind"] == "Assign"
    assert (
        module.materialization_workspace_to_source(engine, workspace)
        == "def run():\n    item = 1\n    return item"
    )


def test_native_materialization_workspace_applies_parameter_edge_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    root_template = module.register_template_package_v2_source(
        engine,
        "def run(value__astichi_param_hole__):\n"
        "    pass\n",
        "workspace.py",
        1,
    )
    params_template = module.register_template_package_v2_source(
        engine,
        "def astichi_params(item):\n"
        "    pass\n",
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
    params = module.assembly_state_append_occurrence(
        engine,
        state,
        params_template,
        ("Root", "Params"),
        root,
    )
    target = module.assembly_state_record_handle(engine, state, root, 0)
    edge = module.assembly_state_append_edge(
        engine,
        state,
        target,
        params,
        "astichi.operation.splice_parameters",
        0,
    )
    workspace = module.materialization_workspace_create(engine, root_template)

    module.materialization_workspace_apply_parameter_edge(engine, workspace, state, edge)

    assert (
        module.materialization_workspace_to_source(engine, workspace)
        == "def run(item):\n    pass"
    )


def test_native_materialization_workspace_applies_keyword_only_parameter_edge_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    root_template = module.register_template_package_v2_source(
        engine,
        "def run(value__astichi_param_hole__):\n"
        "    pass\n",
        "workspace.py",
        1,
    )
    params_template = module.register_template_package_v2_source(
        engine,
        "def astichi_params(*, item=None):\n"
        "    pass\n",
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
    params = module.assembly_state_append_occurrence(
        engine,
        state,
        params_template,
        ("Root", "Params"),
        root,
    )
    target = module.assembly_state_record_handle(engine, state, root, 0)
    edge = module.assembly_state_append_edge(
        engine,
        state,
        target,
        params,
        "astichi.operation.splice_parameters",
        0,
    )
    workspace = module.materialization_workspace_create(engine, root_template)

    module.materialization_workspace_apply_parameter_edge(engine, workspace, state, edge)

    assert (
        module.materialization_workspace_to_source(engine, workspace)
        == "def run(*, item=None):\n    pass"
    )


def test_native_materialization_workspace_applies_nested_parameter_edge_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    root_template = module.register_template_package_v2_source(
        engine,
        "class Root:\n"
        "    def run(self, value__astichi_param_hole__):\n"
        "        pass\n",
        "workspace.py",
        1,
    )
    params_template = module.register_template_package_v2_source(
        engine,
        "def astichi_params(item=1):\n"
        "    pass\n",
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
    params = module.assembly_state_append_occurrence(
        engine,
        state,
        params_template,
        ("Root", "Params"),
        root,
    )
    target = module.assembly_state_record_handle(engine, state, root, 0)
    edge = module.assembly_state_append_edge(
        engine,
        state,
        target,
        params,
        "astichi.operation.splice_parameters",
        0,
    )
    workspace = module.materialization_workspace_create(engine, root_template)

    module.materialization_workspace_apply_parameter_edge(engine, workspace, state, edge)

    assert (
        module.materialization_workspace_to_source(engine, workspace)
        == "class Root:\n\n    def run(self, item=1):\n        pass"
    )


def test_native_assembly_state_parameter_splice_finds_shifted_hole_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    root_template = module.register_template_package_v2_source(
        engine,
        "class Root:\n"
        "    with astichi_hole(prelude) as astichi_fallback:\n"
        "        pass\n"
        "    def __init__(self, init_params__astichi_param_hole__):\n"
        "        pass\n"
        "    def count(self, value):\n"
        "        pass\n",
        "workspace.py",
        1,
    )
    block_template = module.register_template_package_v2_source(
        engine,
        "first = 1\n"
        "second = 2\n",
        "workspace.py",
        1,
    )
    params_template = module.register_template_package_v2_source(
        engine,
        "def astichi_params(count=0, *, transaction_manager=None):\n"
        "    pass\n",
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
    block = module.assembly_state_append_occurrence(
        engine,
        state,
        block_template,
        ("Root", "Prelude"),
        root,
    )
    params = module.assembly_state_append_occurrence(
        engine,
        state,
        params_template,
        ("Root", "Params"),
        root,
    )
    prelude_record = _template_record_handle_by_name(
        module,
        engine,
        state,
        root_template,
        root,
        "prelude",
    )
    init_params_record = _template_record_handle_by_name(
        module,
        engine,
        state,
        root_template,
        root,
        "init_params",
    )
    module.assembly_state_append_edge(
        engine,
        state,
        prelude_record,
        block,
        "astichi.operation.splice_body_at_marker",
        0,
    )
    module.assembly_state_append_edge(
        engine,
        state,
        init_params_record,
        params,
        "astichi.operation.splice_parameters",
        1,
    )

    artifact = module.assembly_state_materialize_to_python_ast(
        engine,
        state,
        {},
        root.index,
    )

    assert ast.unparse(artifact) == (
        "class Root:\n"
        "    first = 1\n"
        "    second = 2\n\n"
        "    def __init__(self, count=0, *, transaction_manager=None):\n"
        "        pass\n\n"
        "    def count(self, value):\n"
        "        pass"
    )


def test_native_materialization_workspace_applies_call_argument_edge_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    root_template = module.register_template_package_v2_source(
        engine,
        "result = func(*astichi_hole(args))\n",
        "workspace.py",
        1,
    )
    args_template = module.register_template_package_v2_source(
        engine,
        "astichi_funcargs(1, 2)\n",
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
    args = module.assembly_state_append_occurrence(
        engine,
        state,
        args_template,
        ("Root", "Args"),
        root,
    )
    target = module.assembly_state_record_handle(engine, state, root, 0)
    edge = module.assembly_state_append_edge(
        engine,
        state,
        target,
        args,
        "astichi.operation.splice_call_arguments",
        0,
    )
    workspace = module.materialization_workspace_create(engine, root_template)

    module.materialization_workspace_apply_call_argument_edge(
        engine,
        workspace,
        state,
        edge,
    )

    assert module.materialization_workspace_to_source(engine, workspace) == (
        "result = func(1, 2)"
    )


def test_native_materialization_workspace_applies_sequence_call_argument_edge_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    root_template = module.register_template_package_v2_source(
        engine,
        "__slots__ = (*astichi_hole(state_slots),)\n",
        "workspace.py",
        1,
    )
    slots_template = module.register_template_package_v2_source(
        engine,
        "astichi_funcargs('_count', '_label')\n",
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
    slots = module.assembly_state_append_occurrence(
        engine,
        state,
        slots_template,
        ("Root", "Slots"),
        root,
    )
    target = module.assembly_state_record_handle(engine, state, root, 0)
    edge = module.assembly_state_append_edge(
        engine,
        state,
        target,
        slots,
        "astichi.operation.splice_call_arguments",
        0,
    )
    workspace = module.materialization_workspace_create(engine, root_template)

    module.materialization_workspace_apply_call_argument_edge(
        engine,
        workspace,
        state,
        edge,
    )

    assert module.materialization_workspace_to_source(engine, workspace) == (
        "__slots__ = ('_count', '_label')"
    )


@pytest.mark.parametrize(
    ("source", "payload", "expected"),
    [
        (
            "if ready:\n    result = func(*astichi_hole(args))\n",
            "astichi_funcargs(1)\n",
            "if ready:\n    result = func(1)",
        ),
        (
            "result = outer((*astichi_hole(args),))\n",
            "astichi_funcargs(1, 2)\n",
            "result = outer((1, 2))",
        ),
        (
            "result = outer(inner(**astichi_hole(args)))\n",
            "astichi_funcargs(answer=42)\n",
            "result = outer(inner(answer=42))",
        ),
        (
            "result = (*astichi_hole(args),) == (1, 2)\n",
            "astichi_funcargs(1, 2)\n",
            "result = (1, 2) == (1, 2)",
        ),
        (
            "result = (1, 2) == (*astichi_hole(args),)\n",
            "astichi_funcargs(1, 2)\n",
            "result = (1, 2) == (1, 2)",
        ),
    ],
)
def test_native_materialization_workspace_applies_nested_call_argument_edge_when_available(
    source: str,
    payload: str,
    expected: str,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    root_template = module.register_template_package_v2_source(
        engine,
        source,
        "workspace.py",
        1,
    )
    args_template = module.register_template_package_v2_source(
        engine,
        payload,
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
    args = module.assembly_state_append_occurrence(
        engine,
        state,
        args_template,
        ("Root", "Args"),
        root,
    )
    target = module.assembly_state_record_handle(engine, state, root, 0)
    edge = module.assembly_state_append_edge(
        engine,
        state,
        target,
        args,
        "astichi.operation.splice_call_arguments",
        0,
    )
    workspace = module.materialization_workspace_create(engine, root_template)

    module.materialization_workspace_apply_call_argument_edge(
        engine,
        workspace,
        state,
        edge,
    )

    assert module.materialization_workspace_to_source(engine, workspace) == expected


@pytest.mark.parametrize(
    "source",
    [
        "result = {'before': 0, **astichi_hole(entries), 'after': 3}\n",
        "result = outer(options={'before': 0, **astichi_hole(entries), 'after': 3})\n",
    ],
)
def test_native_assembly_state_splices_dict_displays_when_available(source: str) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    template = module.register_template_package_v2_source(
        engine, source, "workspace.py", 1
    )
    state = module.assembly_state_create(engine)
    root = module.assembly_state_append_occurrence(engine, state, template, ("Root",))
    target = _template_record_handle_by_name(
        module, engine, state, template, root, "entries"
    )
    for order, payload in enumerate(("{'first': 1}\n", "{**extra, 2: 'second'}\n")):
        child_template = module.register_template_package_v2_source(
            engine, payload, "workspace.py", 1
        )
        child = module.assembly_state_append_occurrence(
            engine, state, child_template, ("Root", f"Entry{order}"), root
        )
        module.assembly_state_append_edge(
            engine, state, target, child, "astichi.operation.splice_call_arguments", order
        )

    artifact = module.assembly_state_materialize_to_python_ast(engine, state, {}, root.index)

    assert ast.unparse(artifact) == source.strip().replace(
        "**astichi_hole(entries)", "'first': 1, **extra, 2: 'second'"
    )


def test_native_assembly_state_materializes_elif_clause_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    root_template = module.register_template_package_v2_source(
        engine,
        "def dispatch(kind):\n"
        "    if kind == 'base':\n"
        "        return 'base'\n"
        "    elif astichi_elif(branches):\n"
        "        pass\n"
        "    else:\n"
        "        return 'fallback'\n",
        "workspace.py",
        1,
    )
    branch_template = module.register_template_package_v2_source(
        engine,
        "def astichi_elif():\n"
        "    if kind == 'create':\n"
        "        return 'created'\n",
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
    branch = module.assembly_state_append_occurrence(
        engine,
        state,
        branch_template,
        ("Root", "Create"),
        root,
    )
    target = module.assembly_state_record_handle(engine, state, root, 0)
    module.assembly_state_append_edge(
        engine,
        state,
        target,
        branch,
        "astichi.operation.append_clause",
        0,
    )

    artifact = module.assembly_state_materialize_to_python_ast(
        engine,
        state,
        {},
        root.index,
    )

    assert ast.unparse(artifact) == (
        "def dispatch(kind):\n"
        "    if kind == 'base':\n"
        "        return 'base'\n"
        "    elif kind == 'create':\n"
        "        return 'created'\n"
        "    else:\n"
        "        return 'fallback'"
    )


_STATEMENT_SUITES = (
    ("plain", "{body}", 0, False),
    ("if.body", "if True:\n{body}", 1, False),
    ("if.else", "if False:\n    pass\nelse:\n{body}", 1, False),
    ("for.body", "for item in items:\n{body}", 1, False),
    ("for.else", "for item in items:\n    pass\nelse:\n{body}", 1, False),
    ("while.body", "while False:\n{body}", 1, False),
    ("while.else", "while False:\n    pass\nelse:\n{body}", 1, False),
    ("async_for.body", "async for item in items:\n{body}", 1, True),
    ("async_for.else", "async for item in items:\n    pass\nelse:\n{body}", 1, True),
    ("with.body", "with guard():\n{body}", 1, False),
    ("async_with.body", "async with guard():\n{body}", 1, True),
    ("try.body", "try:\n{body}except Exception:\n    pass\n", 1, False),
    ("try.except", "try:\n    pass\nexcept Exception:\n{body}", 1, False),
    (
        "try.else",
        "try:\n    pass\nexcept Exception:\n    pass\nelse:\n{body}",
        1,
        False,
    ),
    ("try.finally", "try:\n    pass\nfinally:\n{body}", 1, False),
    ("try_star.body", "try:\n{body}except* Exception:\n    pass\n", 1, False),
    ("try_star.except", "try:\n    pass\nexcept* Exception:\n{body}", 1, False),
    (
        "try_star.else",
        "try:\n    pass\nexcept* Exception:\n    pass\nelse:\n{body}",
        1,
        False,
    ),
    (
        "try_star.finally",
        "try:\n    pass\nexcept* Exception:\n    pass\nfinally:\n{body}",
        1,
        False,
    ),
    ("match.case", "match value:\n    case _:\n{body}", 2, False),
)

_NESTED_INSERTIONS = (
    (
        "elif",
        "if False:\n    pass\nelif astichi_elif(site):\n    pass\n",
        "def astichi_elif():\n    if True:\n        result = 7\n",
        "astichi.operation.append_clause",
        "if False:\n    pass\nelif True:\n    result = 7\n",
    ),
    (
        "block",
        "astichi_hole(site)\n",
        "result = 7\n",
        "astichi.operation.splice_body_at_marker",
        "result = 7\n",
    ),
    (
        "expression",
        "result = astichi_hole(site)\n",
        "7\n",
        "astichi.operation.replace_expression",
        "result = 7\n",
    ),
    (
        "call_args",
        "result = func(*astichi_hole(site))\n",
        "astichi_funcargs(7)\n",
        "astichi.operation.splice_call_arguments",
        "result = func(7)\n",
    ),
    (
        "parameters",
        "def nested(site__astichi_param_hole__):\n    pass\n",
        "def astichi_params(value):\n    pass\n",
        "astichi.operation.splice_parameters",
        "def nested(value):\n    pass\n",
    ),
)


def _wrap_statement_suite(frame: str, depth: int, asynchronous: bool, body: str) -> str:
    function = "async def run():\n" if asynchronous else "def run():\n"
    return function + indent(frame.format(body=indent(body, "    " * depth)), "    ")


@pytest.mark.parametrize(
    "_name,frame,depth,asynchronous",
    _STATEMENT_SUITES,
    ids=[row[0] for row in _STATEMENT_SUITES],
)
@pytest.mark.parametrize(
    "_operation,body,payload,operation_key,expected_body",
    _NESTED_INSERTIONS,
    ids=[row[0] for row in _NESTED_INSERTIONS],
)
def test_native_nested_insertions_do_not_need_python_fallback(
    _name: str,
    frame: str,
    depth: int,
    asynchronous: bool,
    _operation: str,
    body: str,
    payload: str,
    operation_key: str,
    expected_body: str,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")
    engine = _engine_with_current_bundle(module)
    source = _wrap_statement_suite(frame, depth, asynchronous, body)
    template = module.register_template_package_v2_source(
        engine, source, "workspace.py", 1
    )
    payload_template = module.register_template_package_v2_source(
        engine, payload, "payload.py", 1
    )
    state = module.assembly_state_create(engine)
    root = module.assembly_state_append_occurrence(engine, state, template, ("Root",))
    child = module.assembly_state_append_occurrence(
        engine, state, payload_template, ("Root", "Payload"), root
    )
    target = _template_record_handle_by_name(
        module, engine, state, template, root, "site"
    )
    module.assembly_state_append_edge(engine, state, target, child, operation_key, 0)

    # Call native assembly directly: the scope's secondary path would mask gaps.
    artifact = module.assembly_state_materialize_to_python_ast(
        engine, state, {}, root.index
    )

    expected = ast.parse(
        _wrap_statement_suite(frame, depth, asynchronous, expected_body)
    )
    assert ast.dump(artifact, include_attributes=False) == ast.dump(
        expected, include_attributes=False
    )
    compile(artifact, "workspace.py", "exec")


@pytest.mark.parametrize(
    "_name,frame,depth,asynchronous",
    _STATEMENT_SUITES,
    ids=[row[0] for row in _STATEMENT_SUITES],
)
def test_native_rejects_unfilled_parameter_holes_before_cleanup(
    _name: str, frame: str, depth: int, asynchronous: bool
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")
    engine = _engine_with_current_bundle(module)
    source = _wrap_statement_suite(
        frame,
        depth,
        asynchronous,
        "def nested(site__astichi_param_hole__):\n    pass\n",
    )
    template = module.register_template_package_v2_source(
        engine, source, "workspace.py", 1
    )
    state = module.assembly_state_create(engine)
    root = module.assembly_state_append_occurrence(engine, state, template, ("Root",))

    with pytest.raises(
        ValueError, match="mandatory parameter holes remain unresolved: site"
    ):
        module.assembly_state_materialize_to_python_ast(engine, state, {}, root.index)


def test_native_scope_cannot_certify_an_unfilled_parameter_hole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    import astichi
    from astichi.assembler import AssemblyScope

    scope = AssemblyScope(astichi.build())
    scope.add(
        "Root", astichi.compile("def run(args__astichi_param_hole__):\n    return 42\n")
    )
    with pytest.raises(
        (ValueError, RuntimeError), match="mandatory|native materialization"
    ):
        scope.build().to_executable_ast()


def test_native_materialization_workspace_applies_identifier_overlay_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    template = module.register_template_package_v2_source(
        engine,
        "class class_name__astichi_arg__:\n"
        "    pass\n",
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
    target = module.assembly_state_record_handle(engine, state, root, 0)
    overlay = module.assembly_state_append_overlay(
        engine,
        state,
        target,
        "identifier",
        "GeneratedClass",
    )
    workspace = module.materialization_workspace_create(engine, template)

    count = module.materialization_workspace_apply_identifier_overlay(
        engine,
        workspace,
        state,
        overlay,
    )

    assert count == 1
    assert module.materialization_workspace_to_source(engine, workspace) == (
        "class GeneratedClass:\n    pass"
    )


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


def test_native_assembly_state_lowers_method_ref_without_dropping_receiver_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    engine = _engine_with_current_bundle(module)
    template = module.register_template_package_v2_source(
        engine,
        "astichi_pass(state, outer_bind=True).astichi_ref(external=slot)._ = value\n",
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
    external_record = _template_record_handle_by_name(
        module,
        engine,
        state,
        template,
        root,
        "slot",
    )
    overlay = module.assembly_state_append_overlay(
        engine,
        state,
        external_record,
        "external",
        "slot",
    )

    artifact = module.assembly_state_materialize_to_python_ast(
        engine,
        state,
        {overlay.index: "'_field'"},
        root.index,
    )

    assert ast.unparse(artifact) == "state._field = value"


@pytest.mark.parametrize(
    ("source", "expected_count", "expected_source"),
    [
        pytest.param(
            "astichi_bind_external(value)\nresult = value\n",
            2,
            "result = 7",
            id="direct-marker-removed-and-load-replaced",
        ),
        pytest.param(
            "astichi_bind_external(value)\n",
            1,
            "7",
            id="single-expression-payload-materializes-to-literal",
        ),
        pytest.param(
            "def f(value):\n"
            "    return value\n"
            "result = astichi_bind_external(value)\n",
            1,
            "def f(value):\n    return value\nresult = 7",
            id="function-parameter-shadows-body",
        ),
        pytest.param(
            "def f(value=value):\n"
            "    return value\n"
            "result = value\n",
            2,
            "def f(value=7):\n    return value\nresult = 7",
            id="function-default-sees-outer-name",
        ),
        pytest.param(
            "handler = lambda value: value\n"
            "result = value\n",
            1,
            "handler = lambda value: value\nresult = 7",
            id="lambda-parameter-shadows-body",
        ),
        pytest.param(
            "items = value\n"
            "for value in range(2):\n"
            "    print(value)\n"
            "else:\n"
            "    print(value)\n"
            "print(value)\n",
            2,
            "items = 7\n"
            "for value in range(2):\n"
            "    print(value)\n"
            "else:\n"
            "    print(value)\n"
            "print(7)",
            id="loop-target-shadows-body-and-else",
        ),
        pytest.param(
            "items = [value for value in range(3)]\n"
            "result = value\n",
            1,
            "items = [value for value in range(3)]\nresult = 7",
            id="comprehension-target-shadows-element",
        ),
        pytest.param(
            "class C:\n"
            "    value = 1\n"
            "    result = value\n"
            "result = value\n",
            1,
            "class C:\n    value = 1\n    result = value\nresult = 7",
            id="class-local-assignment-shadows-body",
        ),
    ],
)
def test_native_materialization_workspace_external_overlay_is_scope_aware_when_available(
    source: str,
    expected_count: int,
    expected_source: str,
) -> None:
    result = _apply_native_external_overlay_literal(source, "value", "7")

    assert result == (expected_count, expected_source)


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


def _template_record_handle_by_name(
    module: object,
    engine: object,
    state: object,
    template: object,
    occurrence: object,
    resource_name: str,
) -> object:
    snapshot = module.template_package_v2_snapshot(engine, template)
    record_index = next(
        record["template_record_id"]
        for record in snapshot["records"]
        if record["resource_name"] == resource_name
    )
    return module.assembly_state_record_handle(
        engine,
        state,
        occurrence,
        record_index,
    )


def _apply_native_external_overlay_literal(
    source: str,
    name: str,
    expression_source: str,
) -> tuple[int, str]:
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
        name,
    )
    workspace = module.materialization_workspace_create(engine, template)

    count = module.materialization_workspace_apply_external_overlay_literal(
        engine,
        workspace,
        state,
        overlay,
        expression_source,
    )
    return count, module.materialization_workspace_to_source(engine, workspace)
