from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import cast

import astichi
from astichi.assembler.production import (
    BindingSpec,
    BuildProductionSpec,
    ProductionCatalog,
    ProductionRequest,
    ProductionSpec,
    ProductionTemplateProvider,
    ProductionValueProvider,
    SourceProvider,
    TargetSpec,
    TemplateChoice,
    TemplateProducerSpec,
    build_production_roots,
)
from astichi.assembler.scope import ExternalValue


FrameCondition = Callable[["_Frame"], bool]
FrameValue = str | int | tuple["_Frame", ...]


@dataclass(frozen=True)
class _Frame:
    values: Mapping[str, FrameValue]


@dataclass(frozen=True)
class _Catalog(ProductionCatalog[_Frame, FrameCondition]):
    roots: tuple[ProductionRequest[_Frame], ...]
    productions: Mapping[str, ProductionSpec[FrameCondition]]

    def root_requests(self) -> Iterable[ProductionRequest[_Frame]]:
        return self.roots

    def production(self, name: str) -> ProductionSpec[FrameCondition]:
        return self.productions[name]


@dataclass(frozen=True)
class _Templates(ProductionTemplateProvider[_Frame]):
    sources: Mapping[str, str]

    def composable_for(self, template_name: str, frame: _Frame) -> astichi.Composable:
        return astichi.compile(self.sources[template_name])


class _Sources(SourceProvider[_Frame]):
    def frames_for(self, source_name: str, frame: _Frame) -> Iterable[_Frame]:
        value = frame.values[source_name]
        if not isinstance(value, tuple):
            raise TypeError(f"{source_name} must be child frames")
        return value


class _Values(ProductionValueProvider[_Frame, FrameCondition]):
    def frame_label(self, production_name: str, frame: _Frame) -> str:
        value = frame.values.get("label")
        if isinstance(value, str):
            return value
        return production_name

    def matches(self, condition: FrameCondition | None, frame: _Frame) -> bool:
        return condition is None or condition(frame)

    def format_text(self, template: str, frame: _Frame) -> str:
        return template.format_map(frame.values)

    def build_index(
        self,
        source_name: str | None,
        frame: _Frame,
        sequence_index: int,
    ) -> int | tuple[int, ...] | None:
        if source_name is None:
            return None
        if source_name == "sequence_index":
            return sequence_index
        raise TypeError(f"unsupported build index source: {source_name}")

    def order_value(
        self,
        order: int,
        source_name: str | None,
        frame: _Frame,
        sequence_index: int,
    ) -> int:
        if source_name is None:
            return order
        if source_name == "sequence_index":
            return order + sequence_index
        raise TypeError(f"unsupported order source: {source_name}")

    def identifier_value(self, value_name: str, frame: _Frame) -> str:
        value = frame.values[value_name]
        if not isinstance(value, str):
            raise TypeError(f"{value_name} must be a string")
        return value

    def external_value(self, value_name: str, frame: _Frame) -> ExternalValue:
        value = frame.values[value_name]
        if isinstance(value, tuple):
            raise TypeError(f"{value_name} must be an external value")
        return cast(ExternalValue, value)


def test_production_interpreter_builds_child_productions_and_template_steps() -> None:
    first_method = _Frame({"method_name": "first", "value": 10})
    second_method = _Frame({"method_name": "second", "value": 20})
    child = _Frame(
        {
            "label": "generated class",
            "class_name": "Generated",
            "methods": (first_method, second_method),
        }
    )
    root = _Frame({"children": (child,)})
    catalog = _Catalog(
        roots=(ProductionRequest("Module", root),),
        productions={
            "Module": ProductionSpec(
                root=TemplateChoice("module_root", build_name="Root"),
                producers=(
                    BuildProductionSpec(
                        producer_id="class",
                        source_name="children",
                        production_name="Class",
                        build_name_template="Child",
                        target=TargetSpec(name="body", build_match=("Root",)),
                    ),
                ),
            ),
            "Class": ProductionSpec(
                root=TemplateChoice(
                    "class_root",
                    build_name="Root",
                    identifier_binds=(
                        BindingSpec("class_name", "class_name"),
                    ),
                ),
                producers=(
                    TemplateProducerSpec(
                        producer_id="method",
                        source_name="methods",
                        template=TemplateChoice(
                            "method",
                            identifier_binds=(
                                BindingSpec("method_name", "method_name"),
                            ),
                            external_binds=(
                                BindingSpec("value", "value"),
                            ),
                        ),
                        build_name_template="Method",
                        build_index_source="sequence_index",
                        order_source="sequence_index",
                        target=TargetSpec(name="body", build_match=("Root",)),
                    ),
                ),
            ),
        },
    )
    templates = _Templates(
        {
            "module_root": "astichi_hole(body)\n",
            "class_root": "class class_name__astichi_arg__:\n    astichi_hole(body)\n",
            "method": (
                "def method_name__astichi_arg__(self):\n"
                "    return astichi_bind_external(value)\n"
            ),
        }
    )

    result = build_production_roots(
        catalog,
        templates,
        _Sources(),
        _Values(),
    )[0].materialize()
    namespace: dict[str, type] = {}

    exec(result.emit(provenance=False), namespace)

    generated = namespace["Generated"]()
    assert generated.first() == 10
    assert generated.second() == 20


def test_template_choices_use_first_matching_rule() -> None:
    root = _Frame({})
    catalog = _Catalog(
        roots=(ProductionRequest("Module", root),),
        productions={
            "Module": ProductionSpec(
                root=(
                    TemplateChoice(
                        "selected",
                        build_name="Root",
                        condition=lambda frame: True,
                    ),
                    TemplateChoice("fallback", build_name="Root"),
                ),
            ),
        },
    )
    templates = _Templates(
        {
            "selected": "selected = 1\n",
            "fallback": "selected = 2\n",
        }
    )

    result = build_production_roots(
        catalog,
        templates,
        _Sources(),
        _Values(),
    )[0].materialize()
    namespace: dict[str, int] = {}

    exec(result.emit(provenance=False), namespace)

    assert namespace["selected"] == 1
