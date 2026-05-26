"""Funcargs payload with astichi_ref(external=...) plus edge-local bind overlays.

Regression for native source specialization: ``bind_identifier`` on a shared
funcargs payload must leave ``astichi_bind_external`` demand ports available
so a later edge ``bind={"value_path": ...}`` can resolve ``astichi_ref`` paths.
"""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case

_CASE_FILE = "gold_src/native_funcargs_ref_edge_bind.py"


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def func_kw(**kwds):
    return kwds

class vals:
    v1 = 100
    v2 = 200

result_kw_ref = func_kw(**astichi_hole(kw_ref))
""",
            file_name=_CASE_FILE,
        )
    )
    payload = astichi.compile(
        """
astichi_funcargs(
    param__astichi_arg__=astichi_ref(external=value_path),
    __astichi_ph_0__=astichi_import(vals),
)
""",
        file_name=_CASE_FILE,
    )
    for index, (param, attribute) in enumerate((("a", "v1"), ("b", "v2"))):
        builder.add.KwRef[index](payload, arg_names={"param": param})
        builder.Root.kw_ref.add.KwRef[index](
            bind={"value_path": f"vals.{attribute}"}
        )
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<native_funcargs_ref_edge_bind>")
    assert namespace["result_kw_ref"] == {"a": 100, "b": 200}


if __name__ == "__main__":
    raise SystemExit(
        run_case("native_funcargs_ref_edge_bind.py", build_case, validate_case)
    )
