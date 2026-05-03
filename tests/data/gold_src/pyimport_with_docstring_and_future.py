"""Managed imports are placed after module docstring and future imports."""

from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        '''"""Module docs."""
from __future__ import annotations
astichi_pyimport(module=foo, names=(a,))

result: a
''',
        file_name="gold_src/pyimport_with_docstring_and_future.py",
    )


if __name__ == "__main__":
    raise SystemExit(run_case("pyimport_with_docstring_and_future.py", build_case))
