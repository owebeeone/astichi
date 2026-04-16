"""Mutable builder graph and handle surfaces for Astichi."""

from astichi.builder.api import build
from astichi.builder.graph import AdditiveEdge, BuilderGraph, InstanceRecord, TargetRef
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
    "InstanceHandle",
    "InstanceRecord",
    "TargetHandle",
    "TargetRef",
    "build",
]
