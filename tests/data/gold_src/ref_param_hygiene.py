"""Function parameters stay stable across inserted ref-path payloads."""

from __future__ import annotations

from textwrap import dedent

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def _piece(source: str) -> astichi.Composable:
    return astichi.compile(
        dedent(source).strip() + "\n",
        file_name="gold_src/ref_param_hygiene.py",
    )


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        _piece(
            """
            from types import SimpleNamespace


            def consume(class_name):
                return class_name


            def generate(function):
                def wrapper(wrapper_params__astichi_param_hole__):
                    return function(astichi_hole(function_params))

                return wrapper


            result = generate(consume)(SimpleNamespace(class_name="Counter"))
            """
        )
    )
    builder.add.Param(
        _piece(
            """
            def astichi_params(provider_arg__astichi_arg__):
                pass
            """
        ),
        keep_names=["cls_ctx"],
    )
    builder.add.Kw(
        _piece(
            """
            astichi_funcargs(
                param_name__astichi_arg__=
                    astichi_ref(external=segment_0).astichi_ref(external=segment_1),
            )
            """
        ),
        keep_names=["cls_ctx"],
    )

    builder.Root.wrapper_params.add.Param(
        order=0,
        arg_names={"provider_arg": "cls_ctx"},
    )
    builder.Root.function_params.add.Kw(
        order=0,
        arg_names={"param_name": "class_name"},
        bind={"segment_0": "cls_ctx", "segment_1": "class_name"},
    )
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<ref_param_hygiene>")
    assert namespace["result"] == "Counter"
    assert "def wrapper(cls_ctx):" in materialized_source
    assert "class_name=cls_ctx.class_name" in materialized_source
    assert "cls_ctx__astichi_scoped_" not in materialized_source
    assert "astichi_ref" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("ref_param_hygiene.py", build_case, validate_case))
