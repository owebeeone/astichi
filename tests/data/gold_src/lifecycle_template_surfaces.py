"""Lifecycle-shaped templates compose through Astichi marker surfaces."""

from __future__ import annotations

from textwrap import dedent

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def _piece(source: str) -> astichi.Composable:
    return astichi.compile(
        dedent(source).strip() + "\n",
        file_name="gold_src/lifecycle_template_surfaces.py",
    )


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        _piece(
            """
            astichi_pyimport(module=types, names=(SimpleNamespace,))
            astichi_comment("lifecycle template module")

            class state_name__astichi_arg__:
                __slots__ = (*astichi_hole(state_slots),)

                def __init__(self, state_params__astichi_param_hole__):
                    astichi_hole(state_init_body)


            class class_name__astichi_arg__(*astichi_hole(class_bases)):
                __slots__ = ("_state",)

                def __init__(self, facade_params__astichi_param_hole__):
                    self._state = state_name__astichi_arg__(
                        astichi_hole(state_ctor_args)
                    )

                astichi_hole(properties)


            result = class_name__astichi_arg__(count=1, label="alpha")
            result.count = 2
            summary = SimpleNamespace(
                count=result.count,
                label=result.label,
                class_name=type(result).__name__,
            )
            """
        ).bind_identifier(
            class_name="Example",
            state_name="ExampleState",
        )
    )
    builder.add.Base(_piece("object"))
    builder.add.CountSlot(
        _piece(
            """
            astichi_bind_external(slot_name)
            slot_name
            """
        ).bind(slot_name="_count_current"),
    )
    builder.add.LabelSlot(
        _piece(
            """
            astichi_bind_external(slot_name)
            slot_name
            """
        ).bind(slot_name="_label_value"),
    )
    builder.add.StateParams(
        _piece(
            """
            def astichi_params(
                *,
                count: astichi_ref(external=count_type) = astichi_bind_external(count_default),
                label: astichi_ref(external=label_type) = astichi_bind_external(label_default),
            ):
                pass
            """
        ).bind(
            count_type="int",
            label_type="str",
            count_default=0,
            label_default="x",
        ),
    )
    builder.add.FacadeParams(
        _piece(
            """
            def astichi_params(
                *,
                count: astichi_ref(external=count_type) = astichi_bind_external(count_default),
                label: astichi_ref(external=label_type) = astichi_bind_external(label_default),
            ):
                pass
            """
        ).bind(
            count_type="int",
            label_type="str",
            count_default=0,
            label_default="x",
        ),
    )
    builder.add.StateInitBody(
        _piece(
            """
            astichi_comment("state field initialization")
            astichi_import(self)
            self.astichi_ref(external=count_slot)._ = astichi_pass(count, outer_bind=True)
            self.astichi_ref(external=label_slot)._ = astichi_pass(label, outer_bind=True)
            """
        ).bind(count_slot="_count_current", label_slot="_label_value"),
    )
    builder.add.StateCtorArgs(
        _piece(
            """
            astichi_funcargs(
                count=astichi_pass(count, outer_bind=True),
                label=astichi_pass(label, outer_bind=True),
            )
            """
        )
    )
    builder.add.CountProperty(
        _piece(
            """
            astichi_comment("count property template")

            @property
            def field_name__astichi_arg__(self):
                return self._state.astichi_ref(external=storage_path)

            @field_name__astichi_arg__.setter
            def field_name__astichi_arg__(self, value):
                self._state.astichi_ref(external=storage_path)._ = value
            """
        ).bind(storage_path="_count_current"),
    )
    builder.add.LabelProperty(
        _piece(
            """
            astichi_comment("label property template")

            @property
            def field_name__astichi_arg__(self):
                return self._state.astichi_ref(external=storage_path)
            """
        ).bind(storage_path="_label_value"),
    )

    builder.Root.class_bases.add.Base(order=0)
    builder.Root.state_slots.add.CountSlot(order=0)
    builder.Root.state_slots.add.LabelSlot(order=1)
    builder.Root.state_params.add.StateParams(order=0)
    builder.Root.facade_params.add.FacadeParams(order=0)
    builder.Root.state_init_body.add.StateInitBody(order=0)
    builder.Root.state_ctor_args.add.StateCtorArgs(order=0)
    builder.Root.properties.add.CountProperty(
        order=0,
        arg_names={"field_name": "count"},
    )
    builder.Root.properties.add.LabelProperty(
        order=1,
        arg_names={"field_name": "label"},
    )
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    executable_source = materialized.emit(provenance=False)
    namespace = exec_source(executable_source, "<lifecycle_template_surfaces>")
    summary = namespace["summary"]
    assert summary.count == 2
    assert summary.label == "alpha"
    assert summary.class_name == "Example"

    assert "astichi_pyimport" in pre_source
    assert "kind='params'" in pre_source
    assert "astichi_comment" in pre_source
    assert "from types import SimpleNamespace" in materialized_source
    assert "# lifecycle template module" in materialized_source
    assert "# state field initialization" in materialized_source
    assert "# count property template" in materialized_source
    assert "class Example(object):" in materialized_source
    assert "__slots__ = ('_count_current', '_label_value')" in materialized_source
    assert "def __init__(self, *, count: int=0, label: str='x'):" in materialized_source
    assert "self._count_current = count" in materialized_source
    assert "self._state = ExampleState(count=count, label=label)" in materialized_source
    assert "@count.setter" in materialized_source
    assert "self._state._count_current = value" in materialized_source
    assert "return self._state._label_value" in materialized_source
    assert "astichi_ref" not in executable_source
    assert "astichi_hole" not in executable_source
    assert "astichi_insert" not in executable_source
    assert "astichi_comment" not in executable_source


if __name__ == "__main__":
    raise SystemExit(
        run_case(
            "lifecycle_template_surfaces.py",
            build_case,
            validate_case,
            emit_commented=True,
        )
    )
