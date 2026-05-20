from __future__ import annotations

import pytest

import astichi
from astichi.assembler import (
    AssemblyScope,
    BindingCandidate,
    as_composable,
    as_external_value,
    as_identifier,
    find_candidates,
    require_one,
)
from astichi.model import empty_inventory


class UnsupportedCandidate(BindingCandidate):
    """Concrete unsupported candidate for dispatch diagnostics."""

    def diagnostic_lines(self) -> tuple[str, ...]:
        return ("unsupported",)


def test_scope_inventory_is_empty_before_add() -> None:
    scope = AssemblyScope(astichi.build())

    assert scope.inventory == empty_inventory()


def test_require_one_reports_zero_candidates() -> None:
    with pytest.raises(ValueError) as exc_info:
        require_one(())

    assert str(exc_info.value) == "expected exactly one candidate, found 0"


def test_scope_apply_rejects_unsupported_candidate_type() -> None:
    scope = AssemblyScope(astichi.build())

    with pytest.raises(TypeError) as exc_info:
        scope.apply(UnsupportedCandidate())

    assert str(exc_info.value) == (
        "unsupported binding candidate: UnsupportedCandidate"
    )


def test_scope_applies_resource_candidates_to_builder_graph() -> None:
    root = astichi.compile(
        """
class class_name__astichi_arg__:
    default = astichi_bind_external(default_value)

    def method_name__astichi_arg__(self, params__astichi_param_hole__):
        service = []
        astichi_hole(body)
        return service
"""
    )
    params = astichi.compile(
        """
def astichi_params(item):
    pass
"""
    )
    body = astichi.compile(
        """
astichi_pass(service).append(astichi_bind_external(delta))
"""
    )

    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_identifier("GeneratedClass"),
                name="class_name",
                build_match=("Root",),
            )
        )
    )
    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_identifier("run"),
                name="method_name",
                build_match=("Root",),
                owner_match=("GeneratedClass",),
            )
        )
    )
    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_external_value(42),
                name="default_value",
                build_match=("Root",),
                owner_match=("GeneratedClass",),
            )
        )
    )
    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_composable(params, build_name="Params"),
                name="params",
                build_match=("Root",),
                owner_match=("GeneratedClass", "."),
            )
        )
    )
    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_composable(body, build_name="Body"),
                name="body",
                build_match=("Root",),
                owner_match=("GeneratedClass", "."),
            )
        )
    )
    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_identifier("service"),
                name="service",
                build_match=("Root", "Body"),
            )
        )
    )
    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_external_value(1),
                name="delta",
                build_match=("Root", "Body"),
            )
        )
    )

    built = scope.build()
    source = built.materialize().emit(provenance=False)
    namespace = {}
    exec(source, namespace)

    generated = namespace["GeneratedClass"]()
    assert namespace["GeneratedClass"].default == 42
    assert generated.run("ignored") == [1]


def test_require_one_reports_ambiguous_targets_with_locations() -> None:
    root = astichi.compile(
        "def left():\n"
        "    astichi_hole(body)\n"
        "\n"
        "def right():\n"
        "    astichi_hole(body)\n",
        file_name="assembler/ambiguous_root.py",
        line_number=10,
    )
    body = astichi.compile(
        "value = 1\n",
        file_name="assembler/body.py",
        line_number=50,
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    candidates = find_candidates(
        scope.inventory,
        as_composable(body, build_name="Body"),
        name="body",
        build_match=("Root",),
    )

    with pytest.raises(ValueError) as exc_info:
        require_one(candidates)

    assert str(exc_info.value) == (
        "expected exactly one candidate, found 2\n"
        "candidate 1:\n"
        "  demand: build_path=Root owner=left@assembler/ambiguous_root.py:10 "
        "name=body kind=hole.block location=assembler/ambiguous_root.py:11 "
        "locator=body[0]/body[0]/value\n"
        "  resource: composable build_name=Body\n"
        "    production: name=__block__ kind=production.block "
        "location=assembler/body.py:50 locator=.\n"
        "candidate 2:\n"
        "  demand: build_path=Root owner=right@assembler/ambiguous_root.py:13 "
        "name=body kind=hole.block location=assembler/ambiguous_root.py:14 "
        "locator=body[1]/body[0]/value\n"
        "  resource: composable build_name=Body\n"
        "    production: name=__block__ kind=production.block "
        "location=assembler/body.py:50 locator=."
    )


def test_require_one_reports_ambiguous_external_bind_targets() -> None:
    root = astichi.compile(
        "left = astichi_bind_external(value)\n"
        "right = astichi_bind_external(value)\n",
        file_name="assembler/ambiguous_external.py",
        line_number=20,
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    candidates = find_candidates(
        scope.inventory,
        as_external_value(1),
        name="value",
        build_match=("Root",),
    )

    with pytest.raises(ValueError) as exc_info:
        require_one(candidates)

    assert str(exc_info.value) == (
        "expected exactly one candidate, found 2\n"
        "candidate 1:\n"
        "  demand: build_path=Root owner=. name=value kind=external.bind "
        "location=assembler/ambiguous_external.py:20 locator=body[0]/value\n"
        "  resource: external value\n"
        "candidate 2:\n"
        "  demand: build_path=Root owner=. name=value kind=external.bind "
        "location=assembler/ambiguous_external.py:21 locator=body[1]/value\n"
        "  resource: external value"
    )


def test_require_one_reports_ambiguous_identifier_demand_targets() -> None:
    root = astichi.compile(
        "class thing__astichi_arg__:\n"
        "    pass\n"
        "\n"
        "class thing__astichi_arg__:\n"
        "    pass\n",
        file_name="assembler/ambiguous_identifier.py",
        line_number=30,
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    candidates = find_candidates(
        scope.inventory,
        as_identifier("SelectedThing"),
        name="thing",
        build_match=("Root",),
    )

    with pytest.raises(ValueError) as exc_info:
        require_one(candidates)

    assert str(exc_info.value) == (
        "expected exactly one candidate, found 2\n"
        "candidate 1:\n"
        "  demand: build_path=Root owner=. name=thing kind=identifier.demand "
        "location=assembler/ambiguous_identifier.py:30 locator=body[0]\n"
        "  resource: identifier SelectedThing\n"
        "candidate 2:\n"
        "  demand: build_path=Root owner=. name=thing kind=identifier.demand "
        "location=assembler/ambiguous_identifier.py:33 locator=body[1]\n"
        "  resource: identifier SelectedThing"
    )


def test_find_candidates_without_name_scans_all_records_in_map() -> None:
    root = astichi.compile(
        """
astichi_hole(body)
astichi_hole(other)
"""
    )
    body = astichi.compile("value = 1\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    candidates = find_candidates(
        scope.inventory,
        as_composable(body, build_name="Body"),
        build_match=("Root",),
    )

    assert tuple(
        candidate.target_record.name.logical_name()
        for candidate in candidates
    ) == ("body", "other")


def test_build_match_operators_filter_assembler_candidates() -> None:
    root = astichi.compile("astichi_hole(body)\n")
    body_shell = astichi.compile("astichi_hole(inner)\n")
    step = astichi.compile("value = 1\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)
    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_composable(body_shell, build_name="Body"),
                name="body",
                build_match=("Root",),
            )
        )
    )

    candidates = find_candidates(
        scope.inventory,
        as_composable(step, build_name="Step"),
        name="inner",
        build_match=("Root", "*", "Body"),
    )

    candidate = require_one(candidates)
    assert candidate.target_record.build_path.parts == ("Root", "Body")


def test_owner_match_operators_filter_assembler_candidates() -> None:
    root = astichi.compile(
        """
class class_name__astichi_arg__:
    def method_name__astichi_arg__(self):
        astichi_hole(body)
"""
    )
    body = astichi.compile("value = 1\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)
    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_identifier("GeneratedClass"),
                name="class_name",
                build_match=("Root",),
            )
        )
    )
    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_identifier("run"),
                name="method_name",
                build_match=("Root",),
                owner_match=("GeneratedClass",),
            )
        )
    )

    candidates = find_candidates(
        scope.inventory,
        as_composable(body, build_name="Body"),
        name="body",
        build_match=("Root",),
        owner_match=("GeneratedClass", "+"),
    )

    candidate = require_one(candidates)
    assert (
        tuple(
            node.logical_name()
            for node in candidate.target_record.code_owner.nodes
        )
        == ("GeneratedClass", "run")
    )


def test_composable_resource_filters_incompatible_productions() -> None:
    root = astichi.compile("value = astichi_hole(expr)\n")
    block_only = astichi.compile("value = 1\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    assert find_candidates(
        scope.inventory,
        as_composable(block_only, build_name="Block"),
        name="expr",
        build_match=("Root",),
    ) == ()


def test_external_value_resource_skips_non_external_bind_records() -> None:
    root = astichi.compile("astichi_hole(body)\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    assert find_candidates(
        scope.inventory,
        as_external_value(1),
        name="body",
        build_match=("Root",),
    ) == ()


def test_identifier_resource_skips_non_identifier_demand_records() -> None:
    root = astichi.compile("astichi_export(total)\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    assert find_candidates(
        scope.inventory,
        as_identifier("total"),
        name="total",
        build_match=("Root",),
    ) == ()


def test_expression_production_composable_fills_scalar_expression_hole() -> None:
    root = astichi.compile("answer = astichi_hole(value)\n")
    expression = astichi.compile("40 + 2\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    candidate = require_one(
        find_candidates(
            scope.inventory,
            as_composable(expression, build_name="Expression"),
            name="value",
            build_match=("Root",),
        )
    )

    assert "kind=production.expression" in "\n".join(candidate.diagnostic_lines())

    scope.apply(candidate)
    source = scope.build().materialize().emit(provenance=False)

    assert source == "answer = 40 + 2\n"


def test_funcargs_production_composable_fills_variadic_hole() -> None:
    root = astichi.compile("result = func(*astichi_hole(args))\n")
    args = astichi.compile("astichi_funcargs(1, 2)\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    candidate = require_one(
        find_candidates(
            scope.inventory,
            as_composable(args, build_name="Args"),
            name="args",
            build_match=("Root",),
        )
    )

    assert "kind=production.funcargs" in "\n".join(candidate.diagnostic_lines())

    scope.apply(candidate)
    source = scope.build().materialize().emit(provenance=False)

    assert source == "result = func(1, 2)\n"


def test_as_composable_build_index_creates_indexed_build_path() -> None:
    root = astichi.compile(
        """
def run():
    result = []
    astichi_hole(body)
    return result
"""
    )
    getter_body = astichi.compile(
        """
astichi_pass(result, outer_bind=True).append(astichi_bind_external(delta))
"""
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_composable(
                    getter_body,
                    build_name="GetterBody",
                    build_index=1,
                ),
                name="body",
                build_match=("Root",),
            )
        )
    )
    delta_candidate = require_one(
        find_candidates(
            scope.inventory,
            as_external_value(9),
            name="delta",
            build_match=("Root", "GetterBody[1]"),
        )
    )

    assert "build_path=Root/GetterBody[1]" in "\n".join(
        delta_candidate.diagnostic_lines()
    )

    scope.apply(delta_candidate)
    source = scope.build().materialize().emit(provenance=False)
    namespace = {}
    exec(source, namespace)

    assert namespace["run"]() == [9]


def test_as_composable_build_index_tuple_creates_indexed_build_path() -> None:
    root = astichi.compile(
        """
def run():
    result = []
    astichi_hole(body)
    return result
"""
    )
    getter_body = astichi.compile(
        """
astichi_pass(result, outer_bind=True).append(astichi_bind_external(delta))
"""
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_composable(
                    getter_body,
                    build_name="GetterBody",
                    build_index=(1, 2),
                ),
                name="body",
                build_match=("Root",),
            )
        )
    )
    delta_candidate = require_one(
        find_candidates(
            scope.inventory,
            as_external_value(9),
            name="delta",
            build_match=("Root", "GetterBody[1,2]"),
        )
    )

    assert "build_path=Root/GetterBody[1,2]" in "\n".join(
        delta_candidate.diagnostic_lines()
    )


def test_composable_targets_hole_inside_indexed_build_path() -> None:
    root = astichi.compile(
        """
def run():
    result = []
    astichi_hole(body)
    return result
"""
    )
    wrapper = astichi.compile(
        """
astichi_pass(result, outer_bind=True).append("wrapper")
astichi_hole(inner)
"""
    )
    inner = astichi.compile(
        """
astichi_pass(result, outer_bind=True).append("inner")
"""
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_composable(
                    wrapper,
                    build_name="Wrapper",
                    build_index=1,
                ),
                name="body",
                build_match=("Root",),
            )
        )
    )
    inner_candidate = require_one(
        find_candidates(
            scope.inventory,
            as_composable(inner, build_name="Inner"),
            name="inner",
            build_match=("Root", "Wrapper[1]"),
        )
    )

    assert "build_path=Root/Wrapper[1]" in "\n".join(
        inner_candidate.diagnostic_lines()
    )

    scope.apply(inner_candidate)
    source = scope.build().materialize().emit(provenance=False)
    namespace = {}
    exec(source, namespace)

    assert namespace["run"]() == ["wrapper", "inner"]


def test_as_composable_order_controls_additive_insert_order() -> None:
    root = astichi.compile(
        """
def run():
    result = []
    astichi_hole(body)
    return result
"""
    )
    first = astichi.compile(
        """
astichi_pass(result, outer_bind=True).append("first")
"""
    )
    second = astichi.compile(
        """
astichi_pass(result, outer_bind=True).append("second")
"""
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_composable(second, build_name="Second", order=20),
                name="body",
                build_match=("Root",),
            )
        )
    )
    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_composable(first, build_name="First", order=10),
                name="body",
                build_match=("Root",),
            )
        )
    )

    source = scope.build().materialize().emit(provenance=False)
    namespace = {}
    exec(source, namespace)

    assert namespace["run"]() == ["first", "second"]


def test_scope_inventory_refreshes_after_apply() -> None:
    root = astichi.compile("astichi_hole(body)\n")
    body = astichi.compile("value = astichi_bind_external(value)\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    candidate = require_one(
        find_candidates(
            scope.inventory,
            as_composable(body, build_name="Body"),
            name="body",
            build_match=("Root",),
        )
    )

    assert scope.inventory.hole_record_ids("body") == ("Root/#1",)
    assert scope.inventory.resource_record_ids("value") == ()

    scope.apply(candidate)

    assert scope.inventory.hole_record_ids("body") == ("Root/#1",)
    assert scope.inventory.resource_record_ids("value") == ("Root/Body/#1",)

    value_candidate = require_one(
        find_candidates(
            scope.inventory,
            as_external_value(1),
            name="value",
            build_match=("Root", "Body"),
        )
    )
    scope.apply(value_candidate)

    assert scope.inventory.resource_record_ids("value") == ()
    assert find_candidates(
        scope.inventory,
        as_external_value(2),
        name="value",
        build_match=("Root", "Body"),
    ) == ()
