"""Managed plain imports with and without aliases."""

from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        """
astichi_pyimport(module=numpy, as_=np)
astichi_pyimport(module=os)

result = (np.array([1, 2]), os.getcwd())
""",
        file_name="gold_src/pyimport_plain_alias.py",
    )


if __name__ == "__main__":
    raise SystemExit(run_case("pyimport_plain_alias.py", build_case))
