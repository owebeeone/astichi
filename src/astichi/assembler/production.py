"""Generic production-driven assembler expansion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar

from astichi.assembler.client import (
    AssemblerClient,
    AssemblyAction,
    AssemblyContext,
    BuildIndex,
    ProducerList,
    ProducerNode,
    ScopeNode,
    apply_resource,
    build_child_scope,
    scope_recipe,
)
from astichi.assembler.runner import AssemblyRunner
from astichi.assembler.scope import (
    BindingResource,
    ExternalValue,
    as_composable,
    as_external_value,
    as_identifier,
)
from astichi.model import BasicComposable, Composable


FrameT = TypeVar("FrameT")
ConditionT = TypeVar("ConditionT")


@dataclass(frozen=True)
class BindingSpec:
    """Bind one Astichi demand from one client value name."""

    demand_name: str
    value_name: str


@dataclass(frozen=True)
class TargetSpec:
    """Selector for the demand that should receive a produced resource."""

    name: str | None = None
    build_match: tuple[str, ...] | None = None
    owner_match: tuple[str, ...] | None = None


@dataclass(frozen=True)
class TemplateChoice(Generic[ConditionT]):
    """One selectable Astichi template plus its bindings."""

    template_name: str
    build_name: str | None = None
    condition: ConditionT | None = None
    identifier_binds: tuple[BindingSpec, ...] = ()
    external_binds: tuple[BindingSpec, ...] = ()


@dataclass(frozen=True)
class TemplateProducerSpec(Generic[ConditionT]):
    """Producer that applies a template resource to the current production."""

    producer_id: str
    source_name: str
    template: TemplateChoice[ConditionT] | tuple[TemplateChoice[ConditionT], ...]
    build_name_template: str
    target: TargetSpec
    condition: ConditionT | None = None
    build_index_source: str | None = None
    order: int = 0
    order_source: str | None = None


@dataclass(frozen=True)
class BuildProductionSpec(Generic[ConditionT]):
    """Producer that recursively builds and applies a child production."""

    producer_id: str
    source_name: str
    production_name: str
    build_name_template: str
    target: TargetSpec
    condition: ConditionT | None = None
    build_index_source: str | None = None
    order: int = 0
    order_source: str | None = None


@dataclass(frozen=True)
class ProductionSpec(Generic[ConditionT]):
    """Complete recipe for producing one Astichi composable."""

    root: TemplateChoice[ConditionT] | tuple[TemplateChoice[ConditionT], ...]
    producers: tuple[
        TemplateProducerSpec[ConditionT] | BuildProductionSpec[ConditionT], ...
    ] = ()


@dataclass(frozen=True)
class ProductionRequest(Generic[FrameT]):
    """Request to build one root production from one client frame."""

    production_name: str
    frame: FrameT


class ProductionCatalog(ABC, Generic[FrameT, ConditionT]):
    """Client catalog of root requests and named production specs."""

    @abstractmethod
    def root_requests(self) -> Iterable[ProductionRequest[FrameT]]:
        """Return requested root productions."""

    @abstractmethod
    def production(self, name: str) -> ProductionSpec[ConditionT]:
        """Return the spec for one named production."""


class ProductionTemplateProvider(ABC, Generic[FrameT]):
    """Client provider that resolves template names to Astichi composables."""

    @abstractmethod
    def composable_for(self, template_name: str, frame: FrameT) -> Composable:
        """Return the composable for ``template_name`` in ``frame``."""


class SourceProvider(ABC, Generic[FrameT]):
    """Client source expander for producer records."""

    @abstractmethod
    def frames_for(self, source_name: str, frame: FrameT) -> Iterable[FrameT]:
        """Return frames produced by ``source_name`` from ``frame``."""


class ProductionValueProvider(ABC, Generic[FrameT, ConditionT]):
    """Client adapter for frame labels, conditions, and value extraction."""

    @abstractmethod
    def frame_label(self, production_name: str, frame: FrameT) -> str:
        """Return a diagnostic label for one production frame."""

    @abstractmethod
    def matches(self, condition: ConditionT | None, frame: FrameT) -> bool:
        """Return whether ``condition`` accepts ``frame``."""

    @abstractmethod
    def format_text(self, template: str, frame: FrameT) -> str:
        """Format a client template string using ``frame``."""

    @abstractmethod
    def build_index(
        self,
        source_name: str | None,
        frame: FrameT,
        sequence_index: int,
    ) -> BuildIndex | None:
        """Return a builder family index for a producer result."""

    @abstractmethod
    def order_value(
        self,
        order: int,
        source_name: str | None,
        frame: FrameT,
        sequence_index: int,
    ) -> int:
        """Return the additive insertion order for a producer result."""

    @abstractmethod
    def identifier_value(self, value_name: str, frame: FrameT) -> str:
        """Return an identifier spelling from ``frame``."""

    @abstractmethod
    def external_value(self, value_name: str, frame: FrameT) -> ExternalValue:
        """Return an external bind value from ``frame``."""


@dataclass(frozen=True)
class _ProductionScopeNode(ScopeNode, Generic[FrameT]):
    production_name: str
    frame: FrameT
    label: str

    def scope_label(self) -> str:
        return self.label


@dataclass(frozen=True)
class _ProductionContext(AssemblyContext, Generic[FrameT]):
    node: _ProductionScopeNode[FrameT]
    parent: AssemblyContext | None = None

    def scope_node(self) -> ScopeNode:
        return self.node

    def parent_context(self) -> AssemblyContext | None:
        return self.parent

    def lookup_resource(self, name: str) -> BindingResource | None:
        return None


@dataclass(frozen=True)
class _TemplateProducerNode(ProducerNode, Generic[FrameT, ConditionT]):
    producer: TemplateProducerSpec[ConditionT]
    frame: FrameT
    sequence_index: int
    template: TemplateChoice[ConditionT]

    def producer_label(self) -> str:
        return self.producer.producer_id


@dataclass(frozen=True)
class _ChildProductionNode(ProducerNode, Generic[FrameT, ConditionT]):
    producer: BuildProductionSpec[ConditionT]
    child: _ProductionScopeNode[FrameT]
    frame: FrameT
    sequence_index: int

    def producer_label(self) -> str:
        return self.producer.producer_id


@dataclass(frozen=True)
class _ProductionProducerList(ProducerList, Generic[FrameT, ConditionT]):
    production: ProductionSpec[ConditionT]
    root_name: str
    templates: ProductionTemplateProvider[FrameT]
    sources: SourceProvider[FrameT]
    values: ProductionValueProvider[FrameT, ConditionT]

    def producer_nodes(self, context: AssemblyContext) -> Iterable[ProducerNode]:
        production_context = _production_context(context)
        for producer in self.production.producers:
            for index, frame in enumerate(
                self.sources.frames_for(
                    producer.source_name,
                    production_context.node.frame,
                )
            ):
                if not self.values.matches(producer.condition, frame):
                    continue
                if isinstance(producer, BuildProductionSpec):
                    yield _ChildProductionNode(
                        producer=producer,
                        child=_ProductionScopeNode(
                            producer.production_name,
                            frame,
                            self.values.frame_label(producer.production_name, frame),
                        ),
                        frame=frame,
                        sequence_index=index,
                    )
                    continue
                if isinstance(producer, TemplateProducerSpec):
                    yield _TemplateProducerNode(
                        producer=producer,
                        frame=frame,
                        sequence_index=index,
                        template=_select_template(
                            producer.template,
                            self.values,
                            frame,
                            subject=f"producer {producer.producer_id}",
                        ),
                    )
                    continue
                raise TypeError(f"unsupported producer spec: {type(producer).__name__}")

    def actions_for(
        self,
        node: ProducerNode,
        context: AssemblyContext,
    ) -> Iterable[AssemblyAction]:
        if isinstance(node, _ChildProductionNode):
            return self._child_actions(node)
        if isinstance(node, _TemplateProducerNode):
            return _template_actions(
                node,
                self.root_name,
                self.templates,
                self.values,
            )
        raise TypeError(f"unsupported producer node: {type(node).__name__}")

    def _child_actions(
        self,
        node: _ChildProductionNode[FrameT, ConditionT],
    ) -> tuple[AssemblyAction, ...]:
        producer = node.producer
        target = producer.target
        return (
            build_child_scope(
                node.child,
                build_name=self.values.format_text(
                    producer.build_name_template,
                    node.frame,
                ),
                build_index=self.values.build_index(
                    producer.build_index_source,
                    node.frame,
                    node.sequence_index,
                ),
                name=target.name,
                build_match=target.build_match,
                owner_match=target.owner_match,
                order=self.values.order_value(
                    producer.order,
                    producer.order_source,
                    node.frame,
                    node.sequence_index,
                ),
            ),
        )


@dataclass(frozen=True)
class _ProductionClient(AssemblerClient, Generic[FrameT, ConditionT]):
    catalog: ProductionCatalog[FrameT, ConditionT]
    templates: ProductionTemplateProvider[FrameT]
    sources: SourceProvider[FrameT]
    values: ProductionValueProvider[FrameT, ConditionT]

    def root_nodes(self) -> Iterable[ScopeNode]:
        return tuple(
            _ProductionScopeNode(
                request.production_name,
                request.frame,
                self.values.frame_label(request.production_name, request.frame),
            )
            for request in self.catalog.root_requests()
        )

    def context_for_root(self, node: ScopeNode) -> AssemblyContext:
        if not isinstance(node, _ProductionScopeNode):
            raise TypeError(f"unsupported production node: {type(node).__name__}")
        return _ProductionContext(node)

    def context_for_child(
        self,
        parent_context: AssemblyContext,
        node: ScopeNode,
    ) -> AssemblyContext:
        if not isinstance(node, _ProductionScopeNode):
            raise TypeError(f"unsupported production node: {type(node).__name__}")
        return _ProductionContext(node, parent=parent_context)

    def recipe_for(
        self,
        node: ScopeNode,
        context: AssemblyContext,
    ):
        production_context = _production_context(context)
        production = self.catalog.production(production_context.node.production_name)
        root = _select_template(
            production.root,
            self.values,
            production_context.node.frame,
            subject=f"production {production_context.node.production_name}",
        )
        if root.build_name is None:
            raise ValueError("production root template must define build_name")
        return scope_recipe(
            as_composable(
                self.templates.composable_for(
                    root.template_name,
                    production_context.node.frame,
                ),
                build_name=root.build_name,
            ),
            root_actions=_binding_actions(
                root,
                (root.build_name,),
                production_context.node.frame,
                self.values,
            ),
            producer_lists=(
                _ProductionProducerList(
                    production,
                    root.build_name,
                    self.templates,
                    self.sources,
                    self.values,
                ),
            ),
        )


def build_production_roots(
    catalog: ProductionCatalog[FrameT, ConditionT],
    templates: ProductionTemplateProvider[FrameT],
    sources: SourceProvider[FrameT],
    values: ProductionValueProvider[FrameT, ConditionT],
) -> tuple[BasicComposable, ...]:
    """Build all root productions requested by ``catalog``."""
    return AssemblyRunner(
        _ProductionClient(catalog, templates, sources, values)
    ).build_roots()


def _production_context(context: AssemblyContext) -> _ProductionContext:
    if not isinstance(context, _ProductionContext):
        raise TypeError(f"unsupported production context: {type(context).__name__}")
    return context


def _select_template(
    choices: TemplateChoice[ConditionT] | tuple[TemplateChoice[ConditionT], ...],
    values: ProductionValueProvider[FrameT, ConditionT],
    frame: FrameT,
    *,
    subject: str,
) -> TemplateChoice[ConditionT]:
    candidates = choices if isinstance(choices, tuple) else (choices,)
    for choice in candidates:
        if values.matches(choice.condition, frame):
            return choice
    raise ValueError(f"{subject} has no matching template")


def _template_actions(
    node: _TemplateProducerNode[FrameT, ConditionT],
    root_name: str,
    templates: ProductionTemplateProvider[FrameT],
    values: ProductionValueProvider[FrameT, ConditionT],
) -> tuple[AssemblyAction, ...]:
    producer = node.producer
    resource = as_composable(
        templates.composable_for(node.template.template_name, node.frame),
        build_name=values.format_text(producer.build_name_template, node.frame),
        build_index=values.build_index(
            producer.build_index_source,
            node.frame,
            node.sequence_index,
        ),
        order=values.order_value(
            producer.order,
            producer.order_source,
            node.frame,
            node.sequence_index,
        ),
    )
    return (
        apply_resource(
            resource,
            name=producer.target.name,
            build_match=producer.target.build_match,
            owner_match=producer.target.owner_match,
        ),
        *_binding_actions(
            node.template,
            (root_name, resource.instance_name),
            node.frame,
            values,
        ),
    )


def _binding_actions(
    template: TemplateChoice[ConditionT],
    build_match: tuple[str, ...],
    frame: FrameT,
    values: ProductionValueProvider[FrameT, ConditionT],
) -> tuple[AssemblyAction, ...]:
    actions: list[AssemblyAction] = []
    for binding in template.identifier_binds:
        actions.append(
            apply_resource(
                as_identifier(values.identifier_value(binding.value_name, frame)),
                name=binding.demand_name,
                build_match=build_match,
            )
        )
    for binding in template.external_binds:
        actions.append(
            apply_resource(
                as_external_value(values.external_value(binding.value_name, frame)),
                name=binding.demand_name,
                build_match=build_match,
            )
        )
    return tuple(actions)


__all__ = [
    "BindingSpec",
    "BuildProductionSpec",
    "ProductionCatalog",
    "ProductionRequest",
    "ProductionSpec",
    "ProductionTemplateProvider",
    "ProductionValueProvider",
    "SourceProvider",
    "TargetSpec",
    "TemplateChoice",
    "TemplateProducerSpec",
    "build_production_roots",
]
