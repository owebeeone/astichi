from __future__ import annotations

import pytest

import astichi
from astichi.model import PARAMETER


def test_compile_recognizes_parameter_hole_demand_port() -> None:
    compiled = astichi.compile(
        """
def run(params__astichi_param_hole__):
    pass
"""
    )

    assert [(port.name, port.shape, port.placement, port.sources) for port in compiled.demand_ports] == [
        ("params", PARAMETER, "params", frozenset({"param_hole"}))
    ]


def test_compile_recognizes_astichi_params_supply_port() -> None:
    compiled = astichi.compile(
        """
def astichi_params(value, *, debug=False, **kwds):
    pass
"""
    )

    assert [(port.name, port.shape, port.placement, port.sources) for port in compiled.supply_ports] == [
        ("astichi_params", PARAMETER, "params", frozenset({"params"}))
    ]


def test_compile_recognizes_async_astichi_params_supply_port() -> None:
    compiled = astichi.compile(
        """
async def astichi_params(value):
    pass
"""
    )

    assert [(port.name, port.shape, port.placement, port.sources) for port in compiled.supply_ports] == [
        ("astichi_params", PARAMETER, "params", frozenset({"params"}))
    ]


def test_parameter_payload_rejects_non_empty_body() -> None:
    with pytest.raises(ValueError, match="payload body must be empty-equivalent"):
        astichi.compile(
            """
def astichi_params(value):
    generated = value
"""
        )


def test_parameter_payload_rejects_non_parameter_target() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(body)\n"))
    builder.add.Params(
        astichi.compile(
            """
def astichi_params(value):
    pass
"""
        )
    )
    builder.Root.body.add.Params()

    with pytest.raises(ValueError, match="cannot be wired into non-parameter target"):
        builder.build()


def test_parameter_target_rejects_non_parameter_payload() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    pass
"""
        )
    )
    builder.add.Body(astichi.compile("value = 1\n"))
    builder.Root.params.add.Body()

    with pytest.raises(ValueError, match="cannot satisfy parameter target"):
        builder.build()


def test_parameter_insertion_basic_signature_materializes() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    return session
"""
        )
    )
    builder.add.Params(
        astichi.compile(
            """
def astichi_params(session, *, debug=False, **kwds):
    pass
"""
        )
    )
    builder.Root.params.add.Params()

    built = builder.build()
    assert "kind='params'" in built.emit(provenance=False)
    materialized = built.materialize().emit(provenance=False)

    assert "params__astichi_param_hole__" not in materialized
    assert "astichi_insert" not in materialized
    assert "def run(session, *, debug=False, **kwds):" in materialized


def test_async_parameter_payload_materializes_into_async_target() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
async def run(params__astichi_param_hole__):
    return session
"""
        )
    )
    builder.add.Params(
        astichi.compile(
            """
async def astichi_params(session):
    pass
"""
        )
    )
    builder.Root.params.add.Params()

    materialized = builder.build().materialize().emit(provenance=False)

    assert "async def run(session):" in materialized
    assert "return session" in materialized


def test_multiple_parameter_holes_preserve_position_around_authored_parameter() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def foo(p1__astichi_param_hole__, user_param, p2__astichi_param_hole__):
    user_code(user_param)
    return before, user_param, after
"""
        )
    )
    builder.add.P1(
        astichi.compile(
            """
def astichi_params(before):
    pass
"""
        )
    )
    builder.add.P2(
        astichi.compile(
            """
def astichi_params(after):
    pass
"""
        )
    )
    builder.Root.p1.add.P1()
    builder.Root.p2.add.P2()

    materialized = builder.build().materialize().emit(provenance=False)

    assert "def foo(before, user_param, after):" in materialized
    assert "user_code(user_param)" in materialized
    assert "return (before, user_param, after)" in materialized


def test_parameter_name_collision_rejects_before_hygiene() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(existing, params__astichi_param_hole__):
    return existing
"""
        )
    )
    builder.add.Params(
        astichi.compile(
            """
def astichi_params(existing):
    pass
"""
        )
    )
    builder.Root.params.add.Params()

    with pytest.raises(ValueError, match="duplicate final parameter names: existing"):
        builder.build().materialize()


def test_parameter_vararg_duplicates_reject() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    pass
"""
        )
    )
    builder.add.First(
        astichi.compile(
            """
def astichi_params(*args):
    pass
"""
        )
    )
    builder.add.Second(
        astichi.compile(
            """
def astichi_params(**kwds):
    pass
"""
        )
    )
    builder.add.Third(
        astichi.compile(
            """
def astichi_params(*more_args):
    pass
"""
        )
    )
    builder.Root.params.add.First(order=0)
    builder.Root.params.add.Second(order=1)
    builder.Root.params.add.Third(order=2)

    with pytest.raises(ValueError, match="multiple \\*args parameters"):
        builder.build().materialize()


def test_parameter_kwarg_duplicates_reject() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    pass
"""
        )
    )
    builder.add.First(
        astichi.compile(
            """
def astichi_params(**kwds):
    pass
"""
        )
    )
    builder.add.Second(
        astichi.compile(
            """
def astichi_params(**more_kwds):
    pass
"""
        )
    )
    builder.Root.params.add.First(order=0)
    builder.Root.params.add.Second(order=1)

    with pytest.raises(ValueError, match="multiple \\*\\*kwargs parameters"):
        builder.build().materialize()


def test_parameter_annotation_hole_is_optional_when_unfilled() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    return limit
"""
        )
    )
    builder.add.Params(
        astichi.compile(
            """
def astichi_params(limit: astichi_hole(limit_type) = 0):
    pass
"""
        )
    )
    builder.Root.params.add.Params()

    materialized = builder.build().materialize().emit(provenance=False)

    assert "def run(limit=0):" in materialized


def test_parameter_annotation_hole_accepts_one_contribution() -> None:
    params_builder = astichi.build()
    params_builder.add.Params(
        astichi.compile(
            """
def astichi_params(limit: astichi_hole(limit_type) = 0):
    pass
"""
        )
    )
    params_builder.add.Type(astichi.compile("int\n"))
    params_builder.Params.limit_type.add.Type()

    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    return limit
"""
        )
    )
    builder.add.Params(params_builder.build())
    builder.Root.params.add.Params()

    materialized = builder.build().materialize().emit(provenance=False)

    assert "def run(limit: int=0):" in materialized


def test_parameter_annotation_hole_rejects_multiple_contributions() -> None:
    builder = astichi.build()
    builder.add.Params(
        astichi.compile(
            """
def astichi_params(limit: astichi_hole(limit_type) = 0):
    pass
"""
        )
    )
    builder.add.Int(astichi.compile("int\n"))
    builder.add.Str(astichi.compile("str\n"))
    builder.Params.limit_type.add.Int(order=0)
    builder.Params.limit_type.add.Str(order=1)

    with pytest.raises(ValueError, match="scalar expression target limit_type accepts at most one insert"):
        builder.build()
