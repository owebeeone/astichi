"""Inventory snapshots for compile-time bindable resources."""

from __future__ import annotations

import copy
from dataclasses import replace

import astichi
from astichi.model import (
    ClassCodePathNode,
    CodeNodeResourceName,
    FunctionCodePathNode,
)


def test_compile_inventory_snapshots_bindable_resources() -> None:
    composable = astichi.compile(
        """
class cname__astichi_arg__:
    def fname__astichi_arg__(
        self,
        params__astichi_param_hole__,
    ):
        astichi_import(total)
        astichi_export(result)
        astichi_hole(body)
        result = total
"""
    )
    rendered = str(composable.inventory)

    assert repr(composable.inventory) == rendered
    assert rendered == (
        "records:\n"
        "  #1 build_path=. code_owner=. name=cname kind=identifier.demand locator=body[0]\n"
        "  #2 build_path=. code_owner=cname name=fname kind=identifier.demand locator=body[0]/body[0]\n"
        "  #3 build_path=. code_owner=cname/fname name=params kind=hole.params locator=body[0]/body[0]/args/args[1]\n"
        "  #4 build_path=. code_owner=cname/fname name=total kind=identifier.demand locator=body[0]/body[0]/body[0]/value\n"
        "  #5 build_path=. code_owner=cname/fname name=result kind=identifier.supply locator=body[0]/body[0]/body[1]/value\n"
        "  #6 build_path=. code_owner=cname/fname name=body kind=hole.block locator=body[0]/body[0]/body[2]/value\n"
        "  #7 build_path=. code_owner=. name=__block__ kind=production.block locator=.\n"
        "\n"
        "resource_map:\n"
        "  __block__: #7\n"
        "  body: #6\n"
        "  cname: #1\n"
        "  fname: #2\n"
        "  params: #3\n"
        "  result: #5\n"
        "  total: #4\n"
        "\n"
        "port_map:\n"
        "  __block__: #7\n"
        "  body: #6\n"
        "  cname: #1\n"
        "  fname: #2\n"
        "  params: #3\n"
        "  result: #5\n"
        "  total: #4\n"
        "\n"
        "hole_map:\n"
        "  body: #6\n"
        "  params: #3\n"
        "\n"
        "identifier_map:\n"
        "  cname: #1\n"
        "  fname: #2\n"
        "  result: #5\n"
        "  total: #4\n"
        "\n"
        "production_map:\n"
        "  __block__: #7"
    )
    assert composable.inventory.hole_record_ids("body") == ("#6",)
    assert composable.inventory.identifier_record_ids("total") == ("#4",)
    assert composable.inventory.port_record_ids("params") == ("#3",)
    assert composable.inventory.resource_record_ids("missing") == ()
    assert (
        composable.inventory.records_for_ids(("#6",))[0].kind
        == "hole.block"
    )


def test_empty_inventory_prints_only_records_section() -> None:
    composable = astichi.compile("value = 1\n")

    assert str(composable.inventory) == (
        "records:\n"
        "  #1 build_path=. code_owner=. name=__block__ kind=production.block locator=.\n"
        "\n"
        "resource_map:\n"
        "  __block__: #1\n"
        "\n"
        "port_map:\n"
        "  __block__: #1\n"
        "\n"
        "production_map:\n"
        "  __block__: #1"
    )


def test_describe_aggregate_ports_are_inventory_backed() -> None:
    composable = astichi.compile(
        """
astichi_bind_external(value)
astichi_hole(body)
astichi_export(result)
"""
    )
    params = astichi.compile(
        """
def astichi_params(item):
    pass
"""
    )
    inventory_only = replace(composable, demand_ports=(), supply_ports=())
    params_inventory_only = replace(params, demand_ports=(), supply_ports=())
    description = inventory_only.describe()
    params_description = params_inventory_only.describe()

    assert [port.name for port in description.demand_ports] == ["body", "value"]
    assert [port.name for port in description.supply_ports] == ["result"]
    assert [port.name for port in params_description.supply_ports] == [
        "astichi_params"
    ]


def test_inventory_maps_list_multiple_record_ids() -> None:
    composable = astichi.compile(
        """
astichi_hole(body)
astichi_hole(body)
"""
    )

    assert str(composable.inventory) == (
        "records:\n"
        "  #1 build_path=. code_owner=. name=body kind=hole.block locator=body[0]/value\n"
        "  #2 build_path=. code_owner=. name=body kind=hole.block locator=body[1]/value\n"
        "  #3 build_path=. code_owner=. name=__block__ kind=production.block locator=.\n"
        "\n"
        "resource_map:\n"
        "  __block__: #3\n"
        "  body: #1, #2\n"
        "\n"
        "port_map:\n"
        "  __block__: #3\n"
        "  body: #1, #2\n"
        "\n"
        "hole_map:\n"
        "  body: #1, #2\n"
        "\n"
        "production_map:\n"
        "  __block__: #3"
    )


def test_identifier_binding_rebuild_removes_resolved_identifier_records() -> None:
    composable = astichi.compile(
        """
class cname__astichi_arg__:
    def fname__astichi_arg__(self):
        astichi_hole(body)
""",
        arg_names={"cname": "User", "fname": "load"},
    )

    assert str(composable.inventory) == (
        "records:\n"
        "  #1 build_path=. code_owner=User/load name=body kind=hole.block locator=body[0]/body[0]/body[0]/value\n"
        "  #2 build_path=. code_owner=. name=__block__ kind=production.block locator=.\n"
        "\n"
        "resource_map:\n"
        "  __block__: #2\n"
        "  body: #1\n"
        "\n"
        "port_map:\n"
        "  __block__: #2\n"
        "  body: #1\n"
        "\n"
        "hole_map:\n"
        "  body: #1\n"
        "\n"
        "production_map:\n"
        "  __block__: #2"
    )
    assert composable.inventory.identifier_record_ids("cname") == ()
    assert composable.inventory.identifier_record_ids("fname") == ()
    assert composable.inventory.hole_record_ids("body") == ("#1",)


def test_ast_backed_names_compare_by_stripped_logical_name() -> None:
    left_class = ClassCodePathNode(
        astichi.compile("class User__astichi_arg__:\n    pass\n").tree.body[0]
    )
    right_class = ClassCodePathNode(astichi.compile("class User:\n    pass\n").tree.body[0])
    left_function = FunctionCodePathNode(
        astichi.compile("def load__astichi_arg__():\n    pass\n").tree.body[0]
    )
    right_function = FunctionCodePathNode(
        astichi.compile("def load():\n    pass\n").tree.body[0]
    )

    assert left_class == right_class
    assert CodeNodeResourceName(left_class) == CodeNodeResourceName(right_class)
    assert left_function == right_function
    assert CodeNodeResourceName(left_function) == CodeNodeResourceName(right_function)


def test_deepcopy_preserves_inventory_ids_and_repoints_wrappers() -> None:
    original = astichi.compile(
        """
class cname__astichi_arg__:
    def fname__astichi_arg__(
        self,
        params__astichi_param_hole__,
    ):
        pass
"""
    )

    copied = copy.deepcopy(original)
    copied_record = copied.inventory.records["#3"]
    original_record = original.inventory.records["#3"]
    class_owner = copied_record.code_owner.nodes[0]
    function_owner = copied_record.code_owner.nodes[1]

    assert copied_record.record_id == "#3"
    assert copied_record.record_id is original_record.record_id
    assert isinstance(class_owner, ClassCodePathNode)
    assert class_owner.class_ast_node is copied.tree.body[0]
    assert class_owner.class_ast_node is not original.tree.body[0]
    assert isinstance(function_owner, FunctionCodePathNode)
    assert function_owner.function_ast_node is copied.tree.body[0].body[0]
    assert function_owner.function_ast_node is not original.tree.body[0].body[0]
    assert str(copied.inventory) == str(original.inventory)


def test_builder_inventory_prefixes_records_by_build_path() -> None:
    root = astichi.compile(
        """
def run():
    astichi_hole(body)
    astichi_hole(other)
"""
    )
    step = astichi.compile(
        """
astichi_bind_external(value)
astichi_hole(inner)
"""
    )

    builder = astichi.build()
    root_handle = builder.add.Root(root)
    builder.add.Step(step)
    root_handle.body.add.Step()

    built = builder.build()

    assert str(built.inventory) == (
        "records:\n"
        "  #1 build_path=. code_owner=. name=__block__ kind=production.block locator=.\n"
        "  Root/#2 build_path=Root code_owner=run name=other kind=hole.block locator=body[0]/body[1]/value\n"
        "  Root/Step/#1 build_path=Root/Step code_owner=. name=value kind=external.bind locator=body[0]/value\n"
        "  Root/Step/#2 build_path=Root/Step code_owner=. name=inner kind=hole.block locator=body[1]/value\n"
        "\n"
        "resource_map:\n"
        "  __block__: #1\n"
        "  inner: Root/Step/#2\n"
        "  other: Root/#2\n"
        "  value: Root/Step/#1\n"
        "\n"
        "port_map:\n"
        "  __block__: #1\n"
        "  inner: Root/Step/#2\n"
        "  other: Root/#2\n"
        "  value: Root/Step/#1\n"
        "\n"
        "hole_map:\n"
        "  inner: Root/Step/#2\n"
        "  other: Root/#2\n"
        "\n"
        "production_map:\n"
        "  __block__: #1"
    )
    assert built.describe().single_hole_named("inner").address.ref_path == (
        "Root",
        "Step",
    )


def test_builder_add_arg_names_removes_identifier_inventory_record() -> None:
    step = astichi.compile(
        """
def step__astichi_arg__():
    astichi_hole(body)
"""
    )

    builder = astichi.build()
    builder.add.Step(step, arg_names={"step": "run"})
    built = builder.build()

    assert built.inventory.identifier_record_ids("step") == ()
    assert built.inventory.hole_record_ids("body") == ("Step/#1",)
    assert [hole.address.ref_path for hole in built.describe().holes] == [
        ("Step",)
    ]


def test_edge_arg_names_removes_identifier_record_for_occurrence_only() -> None:
    root = astichi.compile("astichi_hole(body)\n")
    step = astichi.compile(
        """
astichi_import(total)
astichi_hole(inner)
"""
    )

    builder = astichi.build()
    root_handle = builder.add.Root(root)
    builder.add.Step(step)
    root_handle.body.add.Step(arg_names={"total": "outer_total"})
    built = builder.build()
    registered_step = next(
        record.composable
        for record in builder.graph.instances
        if record.name == "Step"
    )

    assert registered_step.inventory.identifier_record_ids("total") == ("#1",)
    assert built.inventory.identifier_record_ids("total") == ()
    assert built.inventory.hole_record_ids("inner") == ("Root/Step/#2",)


def test_edge_bind_removes_external_bind_inventory_record() -> None:
    root = astichi.compile("astichi_hole(body)\n")
    step = astichi.compile(
        """
astichi_bind_external(value)
astichi_hole(inner)
"""
    )

    builder = astichi.build()
    root_handle = builder.add.Root(root)
    builder.add.Step(step)
    root_handle.body.add.Step(bind={"value": 10})
    built = builder.build()

    assert built.inventory.resource_record_ids("value") == ()
    assert built.describe().external_binds == ()
    assert built.inventory.hole_record_ids("inner") == ("Root/Step/#1",)


def test_two_stage_bind_identifier_removes_demand_and_preserves_build_path() -> None:
    root = astichi.compile(
        """
astichi_export(total)
astichi_hole(body)
"""
    )
    step = astichi.compile(
        """
astichi_import(total)
astichi_hole(inner)
"""
    )
    stage1 = astichi.build()
    root_handle = stage1.add.Root(root)
    stage1.add.Step(step)
    root_handle.body.add.Step()
    pipeline = stage1.build()
    pipeline_description = pipeline.describe()
    demand = next(
        item
        for item in pipeline_description.identifier_demands
        if item.name == "total"
    )
    supply = next(
        item
        for item in pipeline_description.identifier_supplies
        if item.name == "total"
    )

    stage2 = astichi.build()
    stage2.add.Pipeline(pipeline)
    stage2.bind_identifier(
        source_instance="Pipeline",
        identifier=demand,
        target_instance="Pipeline",
        to=supply,
    )
    built = stage2.build()

    assert built.describe().identifier_demands == ()
    assert built.inventory.identifier_record_ids("total") == ("Pipeline/Root/#1",)
    assert built.inventory.hole_record_ids("inner") == (
        "Pipeline/Root/Step/#2",
    )
    assert built.describe().single_hole_named("inner").address.ref_path == (
        "Pipeline",
        "Root",
        "Step",
    )


def test_two_stage_assign_removes_demand_and_preserves_build_path() -> None:
    root = astichi.compile(
        """
astichi_export(total)
astichi_hole(body)
"""
    )
    step = astichi.compile(
        """
astichi_import(total)
astichi_hole(inner)
"""
    )
    stage1 = astichi.build()
    root_handle = stage1.add.Root(root)
    stage1.add.Step(step)
    root_handle.body.add.Step()
    pipeline = stage1.build()

    stage2 = astichi.build()
    stage2.add.Pipeline(pipeline)
    stage2.assign.Pipeline.Root.Step.total.to().Pipeline.Root.total
    built = stage2.build()

    assert built.describe().identifier_demands == ()
    assert built.inventory.identifier_record_ids("total") == ("Pipeline/Root/#1",)
    assert built.inventory.hole_record_ids("inner") == (
        "Pipeline/Root/Step/#2",
    )
    assert built.inventory.identifier_record_ids(
        "__astichi_assign__inst__Pipeline__ref__Root__name__total"
    ) == ()
