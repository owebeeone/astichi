"""Mutable builder graph and handle surfaces for Astichi."""

from astichi.builder.api import build
from astichi.builder.graph import (
    AdditiveEdge,
    BuilderGraph,
    EdgeSourceOverlay,
    InstanceRecord,
    TargetRef,
)
from astichi.builder.handles import (
    AddProxy,
    AddToTargetProxy,
    BuilderHandle,
    InstanceHandle,
    TargetHandle,
)

__all__ = [
    "AddProxy",
    "AddToTargetProxy",
    "AdditiveEdge",
    "BuilderGraph",
    "BuilderHandle",
    "EdgeSourceOverlay",
    "InstanceHandle",
    "InstanceRecord",
    "TargetHandle",
    "TargetRef",
    "build",
]
