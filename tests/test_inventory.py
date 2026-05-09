"""Inventory snapshots for compile-time bindable resources."""

from __future__ import annotations

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
        "\n"
        "resource_map:\n"
        "  body: #6\n"
        "  cname: #1\n"
        "  fname: #2\n"
        "  params: #3\n"
        "  result: #5\n"
        "  total: #4\n"
        "\n"
        "port_map:\n"
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
        "  total: #4"
    )


def test_empty_inventory_prints_only_records_section() -> None:
    composable = astichi.compile("value = 1\n")

    assert str(composable.inventory) == "records:"


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
        "\n"
        "resource_map:\n"
        "  body: #1, #2\n"
        "\n"
        "port_map:\n"
        "  body: #1, #2\n"
        "\n"
        "hole_map:\n"
        "  body: #1, #2"
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
        "\n"
        "resource_map:\n"
        "  body: #1\n"
        "\n"
        "port_map:\n"
        "  body: #1\n"
        "\n"
        "hole_map:\n"
        "  body: #1"
    )


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
