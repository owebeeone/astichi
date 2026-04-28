from __future__ import annotations

import pytest

import astichi
from astichi.model import MULTI_ADD, SINGLE_ADD
from astichi.builder import TargetRef


def test_describe_exposes_root_holes_with_add_policies() -> None:
    compiled = astichi.compile(
        """
astichi_hole(body)
value = astichi_hole(expr)
result = fn(*astichi_hole(args), **astichi_hole(kwargs))
def run(params__astichi_param_hole__):
    pass
"""
    )

    description = compiled.describe()

    holes = {hole.name: hole for hole in description.holes}
    assert holes["body"].address.ref_path == ()
    assert holes["body"].address.root_instance is None
    assert holes["body"].address.target_name == "body"
    assert holes["body"].add_policy is MULTI_ADD
    assert holes["body"].is_multi_addable() is True
    assert holes["expr"].add_policy is SINGLE_ADD
    assert holes["args"].add_policy is MULTI_ADD
    assert holes["kwargs"].add_policy is MULTI_ADD
    assert holes["params"].add_policy is MULTI_ADD


def test_describe_exposes_external_and_identifier_surfaces() -> None:
    compiled = astichi.compile(
        """
astichi_import(input_name)
value = astichi_bind_external(config)
astichi_export(output_name)
"""
    )

    description = compiled.describe()

    assert [item.name for item in description.external_binds] == ["config"]
    assert [item.name for item in description.identifier_demands] == ["input_name"]
    assert [item.name for item in description.identifier_supplies] == ["output_name"]


def test_describe_uses_shell_ref_paths_for_built_descendant_holes() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    stage1.add.Inner(astichi.compile("astichi_hole(slot)\n"))
    stage1.Root.body.add.Inner()
    built = stage1.build()

    hole = built.describe().single_hole_named("slot")

    assert hole.address.root_instance is None
    assert hole.address.ref_path == ("Root", "Inner")
    assert hole.address.target_name == "slot"


def test_builder_target_accepts_descriptor_hole_addresses() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    stage1.add.Inner(astichi.compile("astichi_hole(slot)\n"))
    stage1.Root.body.add.Inner()
    built = stage1.build()
    hole = built.describe().single_hole_named("slot")

    builder = astichi.build()
    builder.add.Pipeline(built)
    builder.add.Step(astichi.compile("value = 1\n"))
    edge = builder.target(hole.with_root_instance("Pipeline")).add.Step()

    assert edge.target == TargetRef(
        root_instance="Pipeline",
        ref_path=("Root", "Inner"),
        target_name="slot",
    )


def test_builder_target_rejects_unresolved_descriptor_address() -> None:
    root = astichi.compile("astichi_hole(body)\n")
    hole = root.describe().single_hole_named("body")
    builder = astichi.build()
    builder.add.Root(root)

    with pytest.raises(ValueError, match="requires a resolved root_instance"):
        builder.target(hole)


def test_describe_exposes_block_and_expression_productions() -> None:
    block = astichi.compile("value = 1\n")
    expr = astichi.compile("42\n")

    block_productions = block.describe().productions
    expr_productions = expr.describe().productions

    assert any(production.port.shape.is_block() for production in block_productions)
    assert any(production.port.shape.is_scalar_expr() for production in expr_productions)
    assert any(production.port.shape.is_block() for production in expr_productions)


def test_describe_exposes_payload_productions_conservatively() -> None:
    funcargs = astichi.compile("astichi_funcargs(first, named=value)\n")
    params = astichi.compile(
        """
def astichi_params(value):
    pass
"""
    )

    assert [production.name for production in funcargs.describe().productions] == [
        "__funcargs__"
    ]
    assert [
        production.port.shape.name for production in params.describe().productions
    ] == ["parameter"]


def test_description_filters_compatible_productions() -> None:
    root = astichi.compile(
        """
astichi_hole(body)
value = astichi_hole(expr)
result = fn(*astichi_hole(args))
"""
    )
    description = root.describe()
    body = description.single_hole_named("body")
    expr = description.single_hole_named("expr")
    args = description.single_hole_named("args")
    block_production = astichi.compile("value = 1\n").describe().productions
    expression_production = astichi.compile("42\n").describe().productions
    funcargs_production = astichi.compile("astichi_funcargs(first)\n").describe().productions

    assert any(
        production.satisfies(body.descriptor).is_accepted()
        for production in block_production
    )
    assert any(
        production.satisfies(expr.descriptor).is_accepted()
        for production in expression_production
    )
    assert any(
        production.satisfies(args.descriptor).is_accepted()
        for production in funcargs_production
    )


def test_funcargs_productions_are_region_aware() -> None:
    root = astichi.compile(
        """
result = fn(*astichi_hole(args), **astichi_hole(kwargs))
"""
    )
    description = root.describe()
    args = description.single_hole_named("args")
    kwargs = description.single_hole_named("kwargs")
    positional_payload = astichi.compile("astichi_funcargs(first)\n").describe()
    keyword_payload = astichi.compile("astichi_funcargs(named=value)\n").describe()
    mixed_payload = astichi.compile("astichi_funcargs(first, named=value)\n").describe()

    assert positional_payload.productions_compatible_with(args)
    assert not positional_payload.productions_compatible_with(kwargs)
    assert keyword_payload.productions_compatible_with(kwargs)
    assert not keyword_payload.productions_compatible_with(args)
    assert not mixed_payload.productions_compatible_with(args)
    assert not mixed_payload.productions_compatible_with(kwargs)


def test_named_variadic_expression_productions_require_dict_displays() -> None:
    root = astichi.compile("result = {**astichi_hole(entries)}\n")
    entries = root.describe().single_hole_named("entries")

    assert astichi.compile("{key: value}\n").describe().productions_compatible_with(
        entries
    )
    assert not astichi.compile("value\n").describe().productions_compatible_with(
        entries
    )


def test_descriptor_selected_productions_can_build_materialized_function() -> None:
    root = astichi.compile(
        """
def run(params__astichi_param_hole__):
    return fn(*astichi_hole(args))
"""
    )
    params = astichi.compile(
        """
def astichi_params(value):
    pass
"""
    )
    args = astichi.compile("astichi_funcargs(value)\n")

    root_description = root.describe()
    params_hole = root_description.single_hole_named("params")
    args_hole = root_description.single_hole_named("args")

    assert params.describe().productions_compatible_with(params_hole)
    assert args.describe().productions_compatible_with(args_hole)

    builder = astichi.build()
    builder.add.Root(root)
    builder.add.Params(params)
    builder.add.Args(args)
    builder.target(params_hole.with_root_instance("Root")).add.Params()
    builder.target(args_hole.with_root_instance("Root")).add.Args()

    source = builder.build().materialize().emit(provenance=False)

    assert "def run(value):" in source
    assert "return fn(value)" in source
