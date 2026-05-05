"""Parameter-hole payload names remain API names across sibling scopes."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
astichi_hole(body)
""",
            file_name="gold_src/parameter_hole_api_names.py",
        )
    )
    init_method = astichi.compile(
        """
def __init__(self, params__astichi_param_hole__):
    astichi_hole(body)
""",
        file_name="gold_src/parameter_hole_api_names.py",
        keep_names=("self",),
    )
    param = astichi.compile(
        """
def astichi_params(*, field_name__astichi_arg__):
    pass
""",
        file_name="gold_src/parameter_hole_api_names.py",
    )
    assignment = astichi.compile(
        """
astichi_import(self)
self.astichi_ref(external=target_path)._ = astichi_pass(
    source_name,
    outer_bind=True,
)
""",
        file_name="gold_src/parameter_hole_api_names.py",
    )

    for order, class_name in enumerate(("A", "B")):
        class_instance = f"Class{class_name}"
        init_instance = f"Init{class_name}"
        builder.add(
            class_instance,
            astichi.compile(
                """
class class_name__astichi_arg__:
    astichi_hole(body)
""",
                file_name="gold_src/parameter_hole_api_names.py",
            ),
            arg_names={"class_name": class_name},
            keep_names=(class_name,),
        )
        builder.Root.body.add(class_instance, order=order)
        builder.add(init_instance, init_method)
        builder.instance(class_instance).target("body").add(init_instance)
        for field_order, field_name in enumerate(("count", "label")):
            param_instance = f"Param{class_name}{field_name.title()}"
            body_instance = f"Body{class_name}{field_name.title()}"
            builder.add(param_instance, param)
            builder.instance(init_instance).target("params").add(
                param_instance,
                order=field_order,
                arg_names={"field_name": field_name},
                keep_names=(field_name,),
            )
            builder.add(body_instance, assignment)
            builder.instance(init_instance).target("body").add(
                body_instance,
                order=field_order,
                arg_names={"source_name": field_name},
                bind={"target_path": field_name},
            )
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    del composable, materialized, pre_source
    assert "def __init__(self, *, count, label):" in materialized_source
    assert "self__astichi_scoped_" not in materialized_source
    assert "count__astichi_scoped_" not in materialized_source
    assert "label__astichi_scoped_" not in materialized_source
    namespace: dict[str, object] = {}
    exec(compile(materialized_source, "<parameter_hole_api_names>", "exec"), namespace)
    for class_name in ("A", "B"):
        instance = namespace[class_name](count=1, label="x")
        assert instance.count == 1
        assert instance.label == "x"


if __name__ == "__main__":
    raise SystemExit(
        run_case("parameter_hole_api_names.py", build_case, validate_case)
    )
