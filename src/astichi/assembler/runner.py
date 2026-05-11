"""Generic driver for client-described Astichi assembly."""

from __future__ import annotations

from dataclasses import dataclass

import astichi
from astichi.assembler.client import (
    ApplyResource,
    AssemblerClient,
    AssemblyAction,
    AssemblyContext,
    BuildChildScope,
    ProducerNode,
    ScopeNode,
)
from astichi.assembler.scope import (
    AssemblyScope,
    DemandSelector,
    as_composable,
    find_candidates,
    require_one,
)
from astichi.model import BasicComposable


@dataclass(frozen=True)
class AssemblyRunner:
    """Build Astichi composables from client scope recipes and actions."""

    client: AssemblerClient

    def build_roots(self) -> tuple[BasicComposable, ...]:
        """Build all root nodes requested by the client."""
        return tuple(self.build_root(node) for node in self.client.root_nodes())

    def build_root(self, node: ScopeNode) -> BasicComposable:
        """Build one root node requested by the client."""
        context = self.client.context_for_root(node)
        return self.build_scope(node, context)

    def build_scope(
        self,
        node: ScopeNode,
        context: AssemblyContext,
    ) -> BasicComposable:
        """Build one scope node using an existing client context."""
        recipe = self.client.recipe_for(node, context)
        scope = AssemblyScope(astichi.build())
        if recipe.root.build_index is not None:
            raise ValueError("scope root resources may not use build_index")
        scope.add(recipe.root.build_name, recipe.root.composable)

        for action in recipe.root_actions:
            self.apply_action(scope, action, context)
        for producer_list in recipe.producer_lists:
            for producer_node in producer_list.producer_nodes(context):
                for action in producer_list.actions_for(producer_node, context):
                    self.apply_action(
                        scope,
                        action,
                        context,
                        producer_node=producer_node,
                    )

        return scope.build()

    def apply_action(
        self,
        scope: AssemblyScope,
        action: AssemblyAction,
        context: AssemblyContext,
        *,
        producer_node: ProducerNode | None = None,
    ) -> None:
        """Apply one client action to an assembly scope."""
        if isinstance(action, ApplyResource):
            try:
                scope.apply(
                    require_one(
                        find_candidates(
                            scope.inventory,
                            action.resource,
                            name=action.selector.name,
                            build_match=action.selector.build_match,
                            owner_match=action.selector.owner_match,
                        )
                    )
                )
            except ValueError as exc:
                raise ValueError(
                    _action_failure_message(action, context, producer_node, exc)
                ) from exc
            return
        if isinstance(action, BuildChildScope):
            child_context = self.client.context_for_child(context, action.node)
            try:
                child = self.build_scope(action.node, child_context)
            except ValueError as exc:
                raise ValueError(
                    _child_scope_failure_message(action, context, producer_node, exc)
                ) from exc
            resource = as_composable(
                child,
                build_name=action.build_name,
                build_index=action.build_index,
                order=action.order,
            )
            try:
                scope.apply(
                    require_one(
                        find_candidates(
                            scope.inventory,
                            resource,
                            name=action.selector.name,
                            build_match=action.selector.build_match,
                            owner_match=action.selector.owner_match,
                        )
                    )
                )
            except ValueError as exc:
                raise ValueError(
                    _action_failure_message(action, context, producer_node, exc)
                ) from exc
            return
        raise TypeError(f"unsupported assembly action: {type(action).__name__}")


def _action_failure_message(
    action: AssemblyAction,
    context: AssemblyContext,
    producer_node: ProducerNode | None,
    cause: ValueError,
) -> str:
    lines = [
        "assembly action failed",
        *_action_context_lines(action, context, producer_node),
        str(cause),
    ]
    return "\n".join(lines)


def _child_scope_failure_message(
    action: BuildChildScope,
    context: AssemblyContext,
    producer_node: ProducerNode | None,
    cause: ValueError,
) -> str:
    lines = [
        "child scope build failed",
        *_action_context_lines(action, context, producer_node),
        f"child_scope: {action.node.scope_label()}",
        str(cause),
    ]
    return "\n".join(lines)


def _action_context_lines(
    action: AssemblyAction,
    context: AssemblyContext,
    producer_node: ProducerNode | None,
) -> tuple[str, ...]:
    selector: DemandSelector | None = None
    lines = [
        f"scope: {context.scope_node().scope_label()}",
        f"producer: {_producer_label(producer_node)}",
        f"action: {_action_name(action)}",
    ]
    if isinstance(action, ApplyResource):
        lines.extend(action.resource.diagnostic_lines())
        selector = action.selector
    if isinstance(action, BuildChildScope):
        lines.append(f"child_build_name: {action.build_name}")
        selector = action.selector
    if selector is not None:
        lines.append(f"selector: {_selector_text(selector)}")
    return tuple(lines)


def _producer_label(producer_node: ProducerNode | None) -> str:
    if producer_node is None:
        return "<root action>"
    return producer_node.producer_label()


def _action_name(action: AssemblyAction) -> str:
    if isinstance(action, ApplyResource):
        return "apply_resource"
    if isinstance(action, BuildChildScope):
        return "build_child_scope"
    return type(action).__name__


def _selector_text(selector: DemandSelector) -> str:
    parts: list[str] = []
    if selector.name is not None:
        parts.append(f"name={selector.name}")
    if selector.build_match is not None:
        parts.append(f"build={'/'.join(selector.build_match)}")
    if selector.owner_match is not None:
        parts.append(f"owner={'/'.join(selector.owner_match)}")
    return " ".join(parts) if parts else "<any compatible demand>"
