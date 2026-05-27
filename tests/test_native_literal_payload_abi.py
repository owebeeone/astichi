from __future__ import annotations

import ast

import pytest

from astichi.model.external_values import (
    external_value_to_source,
    reference_external_value_source,
    validate_external_value,
)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        -1,
        42,
        3.5,
        "",
        "line\nbreak",
        "quote\"mix",
        (),
        (1,),
        (1, 2),
        [],
        [1, 2, 3],
        {},
        {"a": 1, "b": 2},
        ({"k": [1, (2,)]},),
        [{"nested": {"x": None}}],
    ],
)
def test_external_value_to_source_matches_oracle(value: object) -> None:
    validate_external_value(value)
    assert external_value_to_source(value) == reference_external_value_source(value)
    ast.parse(external_value_to_source(value), mode="eval")


def test_external_value_to_source_rejects_unsupported() -> None:
    with pytest.raises(ValueError, match="unsupported external binding"):
        external_value_to_source(object())
