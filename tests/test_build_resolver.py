import pytest

import astichi


def _materialized_source(builder) -> str:
    return builder.build().materialize().emit(provenance=False)


def test_source_only_unused_definition_with_unresolved_hole_is_ignored() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("value = 1\n"))
    builder.define.Unused(astichi.compile("astichi_hole(missing)\n"))

    source = _materialized_source(builder)

    assert source == "value = 1\n"


def test_source_only_unused_definition_with_unresolved_bind_is_ignored() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("value = 1\n"))
    builder.define.Unused(astichi.compile("value = astichi_bind_external(seed)\n"))

    source = _materialized_source(builder)

    assert source == "value = 1\n"


def test_live_source_only_definition_validates_required_state() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(body)\n"))
    builder.define.Part(astichi.compile("value = astichi_bind_external(seed)\n"))
    builder.Root.body.add.Part()

    with pytest.raises(ValueError, match="external binding for `seed` was not supplied"):
        builder.build().materialize()


def test_source_only_definition_can_be_live_intermediate_target() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(body)\n"))
    builder.define.Mid(astichi.compile("before = 0\nastichi_hole(inner)\n"))
    builder.define.Leaf(astichi.compile("leaf = 1\n"))
    builder.Root.body.add.Mid()
    builder.Mid.inner.add.Leaf()

    source = _materialized_source(builder)

    assert source == "before = 0\nleaf = 1\n"


def test_builder_add_multi_root_behavior_is_unchanged() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("value = 1\n"))
    builder.add.Other(astichi.compile("astichi_hole(missing)\n"))

    with pytest.raises(ValueError, match="mandatory holes remain unresolved: missing"):
        builder.build().materialize()


def test_data_driven_define_matches_fluent_define() -> None:
    fluent = astichi.build()
    fluent.add.Root(astichi.compile("astichi_hole(body)\n"))
    fluent.define.Part(astichi.compile("value = 1\n"))
    fluent.Root.body.add.Part()

    named = astichi.build()
    named.add.Root(astichi.compile("astichi_hole(body)\n"))
    named.define("Part", astichi.compile("value = 1\n"))
    named.Root.body.add("Part")

    assert _materialized_source(named) == _materialized_source(fluent)


def test_source_only_definitions_are_not_output_roots() -> None:
    builder = astichi.build()
    builder.define.Unused(astichi.compile("value = 1\n"))

    with pytest.raises(ValueError, match="no root-capable output instances are live"):
        builder.build()
