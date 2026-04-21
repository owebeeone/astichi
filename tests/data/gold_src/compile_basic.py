"""Basic compile/materialize flow with ordinary Python definitions."""

from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        """
value = 1

def add(left: int, right: int) -> int:
    return left + right


class Box:
    item = add(value, 2)


result = Box.item
""",
        file_name="gold_src/compile_basic.py",
    )


if __name__ == "__main__":
    raise SystemExit(run_case("compile_basic.py", build_case))
