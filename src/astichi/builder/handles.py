"""Builder, instance, and target handles for Astichi V1."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from astichi.builder.graph import AdditiveEdge, BuilderGraph, TargetRef
from astichi.model import Composable
from astichi.model.basic import BasicComposable


@dataclass(frozen=True)
class TargetHandle:
    """Stable handle for a target inside a root instance."""

    graph: BuilderGraph = field(compare=False, repr=False)
    target: TargetRef

    @property
    def add(self) -> "AddToTargetProxy":
        return AddToTargetProxy(graph=self.graph, target=self.target)

    def __getitem__(self, key: int | tuple[int, ...]) -> "TargetHandle":
        """Return a new target handle with an accumulated path."""
        if isinstance(key, tuple):
            items = key
        else:
            items = (key,)
        if any(not isinstance(item, int) for item in items):
            raise TypeError("target path indexes must be integers")
        return TargetHandle(
            graph=self.graph,
            target=TargetRef(
                root_instance=self.target.root_instance,
                target_name=self.target.target_name,
                path=self.target.path + items,
            ),
        )


@dataclass(frozen=True)
class InstanceHandle:
    """Stable handle for a named root instance."""

    graph: BuilderGraph = field(compare=False, repr=False)
    root_instance: str

    def __getattr__(self, name: str) -> TargetHandle:
        if name.startswith("_"):
            raise AttributeError(name)
        return TargetHandle(
            graph=self.graph,
            target=TargetRef(root_instance=self.root_instance, target_name=name),
        )


@dataclass(frozen=True)
class _NamedAdder:
    graph: BuilderGraph = field(compare=False, repr=False)
    instance_name: str

    def __call__(
        self,
        composable: Composable,
        *,
        arg_names: Mapping[str, str] | None = None,
        keep_names: Iterable[str] | None = None,
    ) -> InstanceHandle:
        """Register `composable` as a named root instance.

        Issue 005 §6 / 5d: `arg_names` resolves `__astichi_arg__` slots
        on the incoming piece via `.bind_identifier(...)` before it is
        registered; `keep_names` pins additional hygiene-preserved
        identifiers on the piece via `.with_keep_names(...)`. Both are
        applied to this instance only - the underlying composable is
        unchanged.
        """
        piece = composable
        if keep_names is not None:
            if not isinstance(piece, BasicComposable):
                raise TypeError(
                    "keep_names requires a BasicComposable instance; "
                    f"got {type(piece).__name__}"
                )
            piece = piece.with_keep_names(keep_names)
        if arg_names is not None:
            if not isinstance(piece, BasicComposable):
                raise TypeError(
                    "arg_names requires a BasicComposable instance; "
                    f"got {type(piece).__name__}"
                )
            piece = piece.bind_identifier(arg_names)
        self.graph.add_instance(self.instance_name, piece)
        return InstanceHandle(graph=self.graph, root_instance=self.instance_name)


@dataclass(frozen=True)
class AddProxy:
    """Dedicated proxy for builder.add.<Name>(...) syntax."""

    graph: BuilderGraph = field(compare=False, repr=False)

    def __getattr__(self, name: str) -> _NamedAdder:
        if name.startswith("_"):
            raise AttributeError(name)
        return _NamedAdder(graph=self.graph, instance_name=name)


@dataclass(frozen=True)
class _NamedTargetAdder:
    graph: BuilderGraph = field(compare=False, repr=False)
    target: TargetRef
    source_instance: str

    def __call__(self, *, order: int = 0) -> AdditiveEdge:
        return self.graph.add_additive_edge(
            target=self.target,
            source_instance=self.source_instance,
            order=order,
        )


@dataclass(frozen=True)
class AddToTargetProxy:
    """Dedicated proxy for target.add.<Name>(order=...) syntax."""

    graph: BuilderGraph = field(compare=False, repr=False)
    target: TargetRef

    def __getattr__(self, name: str) -> _NamedTargetAdder:
        if name.startswith("_"):
            raise AttributeError(name)
        return _NamedTargetAdder(
            graph=self.graph,
            target=self.target,
            source_instance=name,
        )


@dataclass
class BuilderHandle:
    """Public builder handle layered over the raw builder graph."""

    graph: BuilderGraph = field(default_factory=BuilderGraph)

    @property
    def add(self) -> AddProxy:
        return AddProxy(graph=self.graph)

    def build(self, *, unroll: bool | str = "auto") -> BasicComposable:
        """Merge the builder graph into a single composable.

        `unroll` controls `astichi_for` expansion before edge resolution
        (UnrollRevision §3). ``"auto"`` unrolls iff any edge references an
        indexed target path; ``True`` always unrolls; ``False`` never does
        and rejects indexed edges.
        """
        from astichi.materialize import build_merge

        return build_merge(self.graph, unroll=unroll)

    def __getattr__(self, name: str) -> InstanceHandle:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in {record.name for record in self.graph.instances}:
            raise AttributeError(f"unknown builder instance: {name}")
        return InstanceHandle(graph=self.graph, root_instance=name)
