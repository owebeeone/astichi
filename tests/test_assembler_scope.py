from __future__ import annotations

import pytest

import astichi
from astichi.assembler import (
    AssemblyScope,
    as_composable,
    as_external_value,
    as_identifier,
    find_candidates,
    require_one,
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
