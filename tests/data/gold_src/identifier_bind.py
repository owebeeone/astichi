"""Resolve identifier slots while preserving an explicit keep suffix."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        """
class Holder__astichi_keep__:
    pass


def step__astichi_arg__(item__astichi_arg__):
    item__astichi_arg__ = item__astichi_arg__ + 1
    return item__astichi_arg__


alias = Holder__astichi_keep__
result = step__astichi_arg__(1)
""",
        file_name="gold_src/identifier_bind.py",
    ).bind_identifier(step="run", item="value")


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<identifier_bind>")
    assert namespace["result"] == 2
    assert namespace["alias"] is namespace["Holder"]


if __name__ == "__main__":
    raise SystemExit(run_case("identifier_bind.py", build_case, validate_case))
