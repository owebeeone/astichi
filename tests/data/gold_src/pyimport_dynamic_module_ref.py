"""Managed from-import from an externally bound dynamic module path."""

from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        """
astichi_bind_external(module_path)
astichi_pyimport(module=astichi_ref(external=module_path), names=(thing,))

result = thing()
""",
        file_name="gold_src/pyimport_dynamic_module_ref.py",
    ).bind(module_path="pkg.mod")


if __name__ == "__main__":
    raise SystemExit(run_case("pyimport_dynamic_module_ref.py", build_case))
