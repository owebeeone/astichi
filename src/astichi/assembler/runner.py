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
    ScopeNode,
)
from astichi.assembler.scope import (
    AssemblyScope,
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
                    self.apply_action(scope, action, context)

        return scope.build()

    def apply_action(
        self,
        scope: AssemblyScope,
        action: AssemblyAction,
        context: AssemblyContext,
    ) -> None:
        """Apply one client action to an assembly scope."""
        if isinstance(action, ApplyResource):
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
            return
        if isinstance(action, BuildChildScope):
            child_context = self.client.context_for_child(context, action.node)
            child = self.build_scope(action.node, child_context)
            resource = as_composable(
                child,
                build_name=action.build_name,
                build_index=action.build_index,
                order=action.order,
            )
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
            return
        raise TypeError(f"unsupported assembly action: {type(action).__name__}")
