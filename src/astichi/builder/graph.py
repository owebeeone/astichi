"""Raw mutable builder graph for Astichi V1."""

from __future__ import annotations

from dataclasses import dataclass, field

from astichi.model import Composable


@dataclass(frozen=True)
class TargetRef:
    """Explicit raw target reference for additive wiring."""

    root_instance: str
    target_name: str
    path: tuple[int, ...] = ()


@dataclass(frozen=True)
class InstanceRecord:
    """Named composable instance in the builder graph."""

    name: str
    composable: Composable


@dataclass(frozen=True)
class AdditiveEdge:
    """Additive composition edge."""

    target: TargetRef
    source_instance: str
    order: int = 0


@dataclass
class BuilderGraph:
    """Underlying mutable graph for Astichi composition."""

    _instances: dict[str, InstanceRecord] = field(default_factory=dict)
    _edges: list[AdditiveEdge] = field(default_factory=list)

    def add_instance(self, name: str, composable: Composable) -> InstanceRecord:
        """Register a named composable instance."""
        if not name.isidentifier():
            raise ValueError(f"instance name must be a valid identifier: {name!r}")
        if name in self._instances:
            raise ValueError(f"duplicate instance name: {name}")
        record = InstanceRecord(name=name, composable=composable)
        self._instances[name] = record
        return record

    def add_additive_edge(
        self,
        *,
        target: TargetRef,
        source_instance: str,
        order: int = 0,
    ) -> AdditiveEdge:
        """Register an additive edge from a source instance into a target."""
        if target.root_instance not in self._instances:
            raise ValueError(f"unknown target root instance: {target.root_instance}")
        if source_instance not in self._instances:
            raise ValueError(f"unknown source instance: {source_instance}")
        edge = AdditiveEdge(
            target=target,
            source_instance=source_instance,
            order=order,
        )
        self._edges.append(edge)
        return edge

    @property
    def instances(self) -> tuple[InstanceRecord, ...]:
        """Inspectable named instances."""
        return tuple(self._instances[name] for name in sorted(self._instances))

    @property
    def edges(self) -> tuple[AdditiveEdge, ...]:
        """Inspectable additive edges."""
        return tuple(self._edges)
