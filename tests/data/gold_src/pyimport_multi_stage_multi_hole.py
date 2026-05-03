"""Managed imports collide correctly across staged multi-hole builds."""

from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    root = astichi.compile(
        """
def f1():
    astichi_hole(f1_body)

def f2():
    astichi_hole(f2_body)

def f3():
    astichi_hole(f3_body)
""",
        file_name="gold_src/pyimport_multi_stage_multi_hole.py",
    )
    mod1 = astichi.compile(
        """
astichi_pyimport(module=mod1, names=(a, b, c))
return (a, b, c)
""",
        file_name="gold_src/pyimport_multi_stage_multi_hole.py",
    )
    mod2a = astichi.compile(
        """
astichi_pyimport(module=mod2, names=(a, b))
return (a, b)
""",
        file_name="gold_src/pyimport_multi_stage_multi_hole.py",
    )
    mod2b = astichi.compile(
        """
astichi_pyimport(module=mod2, names=(a, d))
return (a, d)
""",
        file_name="gold_src/pyimport_multi_stage_multi_hole.py",
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


if __name__ == "__main__":
    raise SystemExit(run_case("pyimport_multi_stage_multi_hole.py", build_case))
