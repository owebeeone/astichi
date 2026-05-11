"""Client-side assembler contracts.

These interfaces describe the narrow surface a client such as YIDL implements
to feed scope recipes and producer actions into an Astichi assembler driver.
"""

from astichi.assembler.client.actionapi import (
    ApplyResource,
    AssemblyAction,
    BuildChildScope,
    BuildIndex,
    apply_resource,
    build_child_scope,
    demand_selector,
)
from astichi.assembler.client.nodeapi import (
    AssemblyContext,
    ProducerNode,
    ScopeNode,
)
from astichi.assembler.client.producerapi import ProducerList
from astichi.assembler.client.scopeapi import (
    AssemblerClient,
    ScopeRecipe,
    scope_recipe,
)

__all__ = [
    "ApplyResource",
    "AssemblerClient",
    "AssemblyAction",
    "AssemblyContext",
    "BuildChildScope",
    "BuildIndex",
    "ProducerList",
    "ProducerNode",
    "ScopeNode",
    "ScopeRecipe",
    "apply_resource",
    "build_child_scope",
    "demand_selector",
    "scope_recipe",
]
