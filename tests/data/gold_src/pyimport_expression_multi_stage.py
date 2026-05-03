"""Managed imports carried by staged expression inserts alias correctly."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    root = astichi.compile(
        """
def f1():
    return astichi_hole(f1_body) + astichi_hole(f2_body) + astichi_hole(f3_body)
""",
        file_name="gold_src/pyimport_expression_multi_stage.py",
    )
    mod1 = astichi.compile(
        """
astichi_pyimport(module=mod1, names=(a, b, c))
(a, b, c)
""",
        file_name="gold_src/pyimport_expression_multi_stage.py",
    )
    mod2a = astichi.compile(
        """
astichi_pyimport(module=mod2, names=(a, b))
(a, b)
""",
        file_name="gold_src/pyimport_expression_multi_stage.py",
    )
    mod2b = astichi.compile(
        """
astichi_pyimport(module=mod2, names=(a, d))
(a, d)
""",
        file_name="gold_src/pyimport_expression_multi_stage.py",
    )

    stage1 = astichi.build()
    stage1.add.Root(root)
    stage1.add.Mod1(mod1)
    stage1.Root.f1_body.add.Mod1()
    build1 = stage1.build()

    stage2 = astichi.build()
    stage2.add.Root(build1)
    stage2.add.Mod2a(mod2a)
    stage2.Root.f2_body.add.Mod2a()
    build2 = stage2.build()

    stage3 = astichi.build()
    stage3.add.Root(build2)
    stage3.add.Mod2b(mod2b)
    stage3.Root.f3_body.add.Mod2b()
    return stage3.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    assert "pyimport=(" in pre_source
    assert "astichi_pyimport" not in materialized_source
    assert "astichi_insert" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(
        run_case("pyimport_expression_multi_stage.py", build_case, validate_case)
    )
