"""Bug #2 (addressing): staged param-hole composition across `build()` boundaries.

Context
-------
A parameter hole (``name__astichi_param_hole__``) is anchor-preserving at
``build()`` time: the authored parameter stays in ``node.args.args`` and
matching ``@astichi_insert(name, kind='params', ref=...)`` shells accumulate
as siblings of the owning ``FunctionDef``. That means a param hole does not
suffer the Bug #1 failure mode that bit call-argument holes (which used to
be replaced wholesale at ``build()``).

However, the builder's target-site resolution still breaks when the root
composable passed to a *second* builder has already been built. The
previously-built root ends up as a single outer ``astichi_hole(__astichi_root__Root__)``
statement whose shell body holds the surviving ``params__astichi_param_hole__``
parameter, and ``builder.Root.params`` is looked up at ref_path ``()`` —
which doesn't know about ``params`` (that name lives at ``('Root',)`` inside
the shell). So the second-stage ``Root.params.add.Stage2(order=1)`` call
raises::

    build: unknown target site `Root.params`;
    context: root instance 'Root';
    hint: check fluent ref spelling and that the instance is registered
          before deep traversal

This golden case is a **red TDD target**: it is written as the happy-path
the author wants — two staged contributions into one param hole, merged in
order — and currently fails at the stage-2 ``add`` call. When Bug #2
(addressing across previously-built root shells) is fixed, this case should
pass with the expected stage-2 signature and regenerated goldens.
"""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    root = astichi.compile(
        """
def run(params__astichi_param_hole__):
    pass
""",
        file_name="gold_src/param_hole_staged_compose.py",
    )

    stage1_builder = astichi.build()
    stage1_builder.add.Root(root)
    stage1_builder.add.Stage1(
        astichi.compile(
            """
def astichi_params(a):
    pass
""",
            file_name="gold_src/param_hole_staged_compose.py",
        )
    )
    stage1_builder.Root.params.add.Stage1(order=0)
    stage1 = stage1_builder.build()

    stage2_builder = astichi.build()
    stage2_builder.add.Root(stage1)
    stage2_builder.add.Stage2(
        astichi.compile(
            """
def astichi_params(b):
    pass
""",
            file_name="gold_src/param_hole_staged_compose.py",
        )
    )
    stage2_builder.Root.params.add.Stage2(order=1)
    return stage2_builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    assert "params__astichi_param_hole__" in pre_source
    assert "kind='params'" in pre_source
    assert "def run(a, b):" in materialized_source
    assert "astichi_insert" not in materialized_source
    assert "__astichi_param_hole__" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("param_hole_staged_compose.py", build_case, validate_case))
