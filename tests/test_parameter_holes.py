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


def test_nested_astichi_params_name_is_reserved() -> None:
    with pytest.raises(ValueError, match="astichi_params is reserved"):
        astichi.compile(
            """
def helper():
    def astichi_params(value):
        return value
    return astichi_params(1)
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


def test_duplicate_inserted_parameter_names_reject_before_hygiene() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    return total
"""
        )
    )
    builder.add.First(
        astichi.compile(
            """
def astichi_params(total):
    pass
"""
        )
    )
    builder.add.Second(
        astichi.compile(
            """
def astichi_params(total):
    pass
"""
        )
    )
    builder.Root.params.add.First(order=0)
    builder.Root.params.add.Second(order=1)

    with pytest.raises(ValueError, match="duplicate final parameter names: total"):
        builder.build().materialize()


def test_inserted_non_default_after_target_default_rejects() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    return optional, inserted
"""
        )
    )
    builder.add.Defaulted(
        astichi.compile(
            """
def astichi_params(optional=1):
    pass
"""
        )
    )
    builder.add.Required(
        astichi.compile(
            """
def astichi_params(inserted):
    pass
"""
        )
    )
    builder.Root.params.add.Defaulted(order=0)
    builder.Root.params.add.Required(order=1)

    with pytest.raises(ValueError, match="non-default parameter after a default"):
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


def test_inserted_vararg_rejects_when_target_already_has_vararg() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__, *args):
    pass
"""
        )
    )
    builder.add.Params(
        astichi.compile(
            """
def astichi_params(*more_args):
    pass
"""
        )
    )
    builder.Root.params.add.Params()

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


def test_inserted_kwarg_rejects_when_target_already_has_kwarg() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__, **kwds):
    pass
"""
        )
    )
    builder.add.Params(
        astichi.compile(
            """
def astichi_params(**more_kwds):
    pass
"""
        )
    )
    builder.Root.params.add.Params()

    with pytest.raises(ValueError, match="multiple \\*\\*kwargs parameters"):
        builder.build().materialize()


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


def test_unresolved_arg_identifier_in_parameter_default_rejects() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    return value
"""
        )
    )
    builder.add.Params(
        astichi.compile(
            """
def astichi_params(value=default_value__astichi_arg__):
    pass
"""
        )
    )
    builder.Root.params.add.Params()

    with pytest.raises(ValueError, match="default_value__astichi_arg__"):
        builder.build().materialize()


def test_unresolved_arg_identifier_in_parameter_annotation_rejects() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    return value
"""
        )
    )
    builder.add.Params(
        astichi.compile(
            """
def astichi_params(value: value_type__astichi_arg__):
    pass
"""
        )
    )
    builder.Root.params.add.Params()

    with pytest.raises(ValueError, match="value_type__astichi_arg__"):
        builder.build().materialize()
