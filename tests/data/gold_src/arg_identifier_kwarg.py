"""Resolve identifier slots that sit in a call keyword-argument name position.

Exercises the 005 §1 identifier-suffix surface in the ``ast.keyword.arg``
slot: authored kwarg names like ``slot__astichi_arg__=value`` become
identifier demand ports and are rewritten by ``.bind_identifier(...)``
before materialize, exactly as for def/class names, ``ast.Name``, and
``ast.arg`` parameters.
"""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        """
def target(width, height=0, keep=0):
    return (width, height, keep)


first_result = target(first__astichi_arg__=1, second__astichi_arg__=2)
second_result = target(first__astichi_arg__=10, keep=20)
""",
        file_name="gold_src/arg_identifier_kwarg.py",
    ).bind_identifier(first="width", second="height")


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<arg_identifier_kwarg>")
    assert namespace["first_result"] == (1, 2, 0)
    # `keep` is a plain kwarg (no `__astichi_arg__` suffix) so its name
    # must survive unchanged; only suffixed kwarg names resolve.
    assert namespace["second_result"] == (10, 0, 20)
    assert "__astichi_arg__" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("arg_identifier_kwarg.py", build_case, validate_case))
