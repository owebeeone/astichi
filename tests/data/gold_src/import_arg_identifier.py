"""Resolve __astichi_arg__ slots inside ordinary import statements."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        """
def f():
    from module_name__astichi_arg__ import symbol__astichi_arg__
    return symbol__astichi_arg__
""",
        file_name="gold_src/import_arg_identifier.py",
        arg_names={"module_name": "realmod", "symbol": "thing"},
    )


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    assert "__astichi_arg__" not in materialized_source
    assert "from realmod import thing" in materialized_source
    assert "return thing" in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("import_arg_identifier.py", build_case, validate_case))
