"""Mutable builder graph and handle surfaces for Astichi."""

from astichi.builder.api import build
from astichi.builder.graph import (
    AdditiveEdge,
    BuilderGraph,
    EdgeSourceOverlay,
    IdentifierBinding,
    InstancePlacement,
    InstanceRecord,
    ROOT_CAPABLE_INSTANCE,
    RootCapableInstancePlacement,
    SOURCE_ONLY_INSTANCE,
    SourceOnlyInstancePlacement,
    TargetRef,
)
from astichi.builder.handles import (
    AddProxy,
    AddToTargetProxy,
    BindIdentifierProxy,
    BuilderHandle,
    DefineProxy,
    InstanceHandle,
    TargetHandle,
)

__all__ = [
    "AddProxy",
    "AddToTargetProxy",
    "AdditiveEdge",
    "BindIdentifierProxy",
    "BuilderGraph",
    "BuilderHandle",
    "DefineProxy",
    "EdgeSourceOverlay",
    "IdentifierBinding",
    "InstancePlacement",
    "InstanceHandle",
    "InstanceRecord",
    "ROOT_CAPABLE_INSTANCE",
    "RootCapableInstancePlacement",
    "SOURCE_ONLY_INSTANCE",
    "SourceOnlyInstancePlacement",
    "TargetHandle",
    "TargetRef",
    "build",
]
