"""Mutable builder graph and handle surfaces for Astichi."""

from astichi.builder.api import build
from astichi.builder.graph import (
    AdditiveEdge,
    BuilderGraph,
    EdgeSourceOverlay,
    IdentifierBinding,
    InstanceRecord,
    TargetRef,
)
from astichi.builder.handles import (
    AddProxy,
    AddToTargetProxy,
    BindIdentifierProxy,
    BuilderHandle,
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
    "EdgeSourceOverlay",
    "IdentifierBinding",
    "InstanceHandle",
    "InstanceRecord",
    "TargetHandle",
    "TargetRef",
    "build",
]
