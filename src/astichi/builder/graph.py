"""Raw mutable builder graph for Astichi V1."""

from __future__ import annotations

from dataclasses import dataclass, field

from astichi.model import Composable
from astichi.shell_refs import RefPath


@dataclass(frozen=True)
class TargetRef:
    """Explicit raw target reference for additive wiring."""

    root_instance: str
    target_name: str
    ref_path: RefPath = ()
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


@dataclass(frozen=True)
class AssignBinding:
    """Explicit cross-instance identifier wiring for boundary imports.

    Issue 006 6c (assign surface): declares that inside
    ``source_instance`` the inner identifier ``inner_name`` (an
    ``astichi_import`` / ``__astichi_arg__`` demand) resolves to
    ``outer_name`` as published by ``target_instance`` in the merged
    program. The target instance may be registered after the
    ``builder.assign`` call — validation is deferred to ``build_merge``
    so the wiring can point at pieces that do not yet exist.
    """

    source_instance: str
    inner_name: str
    target_instance: str
    outer_name: str
    source_ref_path: RefPath = ()
    target_ref_path: RefPath = ()


@dataclass
class BuilderGraph:
    """Underlying mutable graph for Astichi composition."""

    _instances: dict[str, InstanceRecord] = field(default_factory=dict)
    _edges: list[AdditiveEdge] = field(default_factory=list)
    _assigns: list[AssignBinding] = field(default_factory=list)

    def add_instance(self, name: str, composable: Composable) -> InstanceRecord:
        """Register a named composable instance."""
        if not name.isidentifier():
            raise ValueError(f"instance name must be a valid identifier: {name!r}")
        if name in self._instances:
            raise ValueError(f"duplicate instance name: {name}")
        record = InstanceRecord(name=name, composable=composable)
        self._instances[name] = record
        return record

    def replace_instance(self, name: str, composable: Composable) -> InstanceRecord:
        """Replace an existing instance's composable.

        Issue 006 6c: the target-adder surface
        (``target.add.X(order=0, arg_names=..., keep_names=...)``) layers
        per-edge identifier wiring onto the source instance's piece by
        unioning the supplied ``arg_names`` / ``keep_names`` into the
        existing instance via ``bind_identifier`` / ``with_keep_names``
        and swapping the registered record. Both helper methods are
        conflict-detecting, so wiring the same instance from multiple
        edges with compatible bindings unions cleanly and incompatible
        bindings raise.
        """
        if name not in self._instances:
            raise ValueError(f"unknown instance: {name}")
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

    def add_assign(self, binding: AssignBinding) -> AssignBinding:
        """Record an ``builder.assign`` cross-instance wiring.

        Idempotent for exact-duplicate declarations; raises if the same
        ``(source_instance, inner_name)`` pair is bound to a different
        ``(target_instance, outer_name)``. Validation that the
        referenced instances / ports actually exist is deferred to
        ``build_merge`` so the user may declare wirings against pieces
        that have not yet been registered.
        """
        for name in (
            binding.source_instance,
            binding.inner_name,
            binding.target_instance,
            binding.outer_name,
        ):
            if not isinstance(name, str) or not name.isidentifier():
                raise ValueError(
                    "assign binding names must be valid Python "
                    f"identifiers; got {name!r}"
                )
        for existing in self._assigns:
            if (
                existing.source_instance == binding.source_instance
                and existing.source_ref_path == binding.source_ref_path
                and existing.inner_name == binding.inner_name
            ):
                if existing == binding:
                    return existing
                raise ValueError(
                    f"conflicting assign for `{binding.source_instance}"
                    f".{binding.inner_name}`: already bound to "
                    f"`{existing.target_instance}.{existing.outer_name}`, "
                    f"cannot rebind to `{binding.target_instance}"
                    f".{binding.outer_name}`"
                )
        self._assigns.append(binding)
        return binding

    @property
    def instances(self) -> tuple[InstanceRecord, ...]:
        """Inspectable named instances."""
        return tuple(self._instances[name] for name in sorted(self._instances))

    @property
    def edges(self) -> tuple[AdditiveEdge, ...]:
        """Inspectable additive edges."""
        return tuple(self._edges)

    @property
    def assigns(self) -> tuple[AssignBinding, ...]:
        """Inspectable cross-instance identifier assignments."""
        return tuple(self._assigns)
