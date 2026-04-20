"""Builder, instance, and target handles for Astichi V1."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from astichi.diagnostics import default_build_path_hint, format_astichi_error
from astichi.builder.graph import (
    AdditiveEdge,
    AssignBinding,
    BuilderGraph,
    TargetRef,
)
from astichi.model import Composable
from astichi.model.basic import BasicComposable
from astichi.path_resolution import (
    ShellIndex,
    collect_hole_names_in_body,
    collect_identifier_demands_in_body,
    collect_identifier_suppliers_in_body,
    format_instance_leaf,
)
from astichi.shell_refs import RefPath, format_ref_path, normalize_ref_path


@dataclass(frozen=True)
class TargetHandle:
    """Stable handle for a target path inside a root instance."""

    graph: BuilderGraph = field(compare=False, repr=False)
    target: TargetRef

    @property
    def add(self) -> "AddToTargetProxy":
        return AddToTargetProxy(graph=self.graph, target=self.target)

    def __getitem__(self, key: int | tuple[int, ...]) -> "TargetHandle":
        """Return a new target handle with accumulated indexes on the leaf."""
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
                ref_path=self.target.ref_path,
                path=self.target.path + items,
            ),
        )

    def __getattr__(self, name: str) -> "TargetHandle":
        """Advance one descendant hop and leave ``name`` as the new leaf."""
        if name.startswith("_"):
            raise AttributeError(name)
        candidate_ref = _descend_registered_ref(
            graph=self.graph,
            instance_name=self.target.root_instance,
            ref_path=self.target.ref_path,
            leaf_name=self.target.target_name,
            leaf_path=self.target.path,
            role="descendant path",
        )
        return TargetHandle(
            graph=self.graph,
            target=TargetRef(
                root_instance=self.target.root_instance,
                target_name=name,
                ref_path=candidate_ref,
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

    def __getitem__(self, key: int | tuple[int, ...]) -> "_IndexedInstanceHandle":
        if isinstance(key, tuple):
            items = key
        else:
            items = (key,)
        if any(not isinstance(item, int) for item in items):
            raise TypeError("target path indexes must be integers")
        return _IndexedInstanceHandle(
            graph=self.graph,
            root_instance=self.root_instance,
            path=items,
        )


@dataclass(frozen=True)
class _IndexedInstanceHandle:
    graph: BuilderGraph = field(compare=False, repr=False)
    root_instance: str
    path: tuple[int, ...]

    def __getattr__(self, name: str) -> TargetHandle:
        if name.startswith("_"):
            raise AttributeError(name)
        return TargetHandle(
            graph=self.graph,
            target=TargetRef(
                root_instance=self.root_instance,
                target_name=name,
                path=self.path,
            ),
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

    def __call__(
        self,
        *,
        order: int = 0,
        arg_names: Mapping[str, str] | None = None,
        keep_names: Iterable[str] | None = None,
    ) -> AdditiveEdge:
        """Wire ``self.source_instance`` into ``self.target`` additively.

        Issue 006 6c: when the source instance declares an
        ``astichi_import(name)`` boundary (equivalently an
        ``name__astichi_arg__`` suffix slot), ``arg_names`` names the
        outer-scope identifier the import should resolve to. Identity
        mappings (``{"total": "total"}``) are the common case — the
        user states which scope provides the name, while the value
        matches the inner declaration. Non-identity mappings
        (``{"total": "accumulator"}``) additionally rename the inner
        references to the outer name before hygiene runs.

        ``keep_names`` is the same surface as
        ``builder.add.<Name>(piece, keep_names=...)`` but scoped to
        the contributing instance. Both maps union with any bindings
        already attached to the instance via compile-time ``arg_names=``
        or an earlier ``builder.add.<Name>(...)`` call; conflicts
        raise.
        """
        if arg_names is not None or keep_names is not None:
            record = self.graph._instances.get(self.source_instance)
            if record is None:
                raise ValueError(
                    format_astichi_error(
                        "build",
                        f"unknown source instance: {self.source_instance}",
                        hint="register the instance with `builder.add.<Name>(...)` before wiring edges",
                    )
                )
            piece = record.composable
            if not isinstance(piece, BasicComposable):
                raise TypeError(
                    "arg_names/keep_names require a BasicComposable "
                    f"instance; got {type(piece).__name__}"
                )
            if keep_names is not None:
                piece = piece.with_keep_names(keep_names)
            if arg_names is not None:
                piece = piece.bind_identifier(arg_names)
            self.graph.replace_instance(self.source_instance, piece)
        _validate_registered_target_site(self.graph, self.target)
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


def _registered_shell_index(
    graph: BuilderGraph,
    instance_name: str,
 ) -> ShellIndex | None:
    record = graph._instances.get(instance_name)
    if record is None:
        return None
    piece = record.composable
    if not isinstance(piece, BasicComposable):
        return None
    return ShellIndex.from_tree(piece.tree)


def _descend_registered_ref(
    *,
    graph: BuilderGraph,
    instance_name: str,
    ref_path: RefPath,
    leaf_name: str,
    leaf_path: tuple[int, ...],
    role: str,
) -> RefPath:
    candidate_ref = normalize_ref_path(ref_path + (leaf_name,) + leaf_path)
    shell_index = _registered_shell_index(graph, instance_name)
    if shell_index is not None:
        shell_index.resolve(candidate_ref).require(
            instance_name=instance_name,
            role=role,
        )
    return candidate_ref


def _format_target_address(target: TargetRef) -> str:
    ref_prefix = ""
    target_ref_path = normalize_ref_path(target.ref_path)
    if target_ref_path:
        ref_prefix = f".{format_ref_path(target_ref_path)}"
    suffix = "".join(f"[{index}]" for index in target.path)
    return f"{target.root_instance}{ref_prefix}.{target.target_name}{suffix}"


def _validate_registered_target_site(
    graph: BuilderGraph,
    target: TargetRef,
) -> None:
    if not target.ref_path:
        return
    shell_index = _registered_shell_index(graph, target.root_instance)
    if shell_index is None:
        return
    shell = shell_index.resolve(target.ref_path).require(
        instance_name=target.root_instance,
        role="target path",
    )
    if target.target_name in collect_hole_names_in_body(shell.body):
        return
    raise ValueError(
        format_astichi_error(
            "build",
            f"unknown target site `{_format_target_address(target)}`",
            context=f"root instance {target.root_instance!r}",
            hint=default_build_path_hint(),
        )
    )


def _validate_registered_identifier_demand(
    *,
    graph: BuilderGraph,
    instance_name: str,
    ref_path: RefPath,
    inner_name: str,
) -> None:
    shell_index = _registered_shell_index(graph, instance_name)
    if shell_index is None:
        return
    shell = shell_index.resolve(ref_path).require(
        instance_name=instance_name,
        role="assign source path",
    )
    if inner_name in collect_identifier_demands_in_body(shell.body):
        return
    raise ValueError(
        format_astichi_error(
            "build",
            "no __astichi_arg__ / astichi_import slot named "
            f"`{inner_name}` at "
            f"`{format_instance_leaf(instance_name, ref_path, inner_name)}`",
            hint="declare the slot in the source snippet or fix the descendant path",
        )
    )


def _validate_registered_identifier_supplier(
    *,
    graph: BuilderGraph,
    instance_name: str,
    ref_path: RefPath,
    outer_name: str,
) -> None:
    if not ref_path:
        return
    shell_index = _registered_shell_index(graph, instance_name)
    if shell_index is None:
        return
    shell = shell_index.resolve(ref_path).require(
        instance_name=instance_name,
        role="assign target path",
    )
    if outer_name in collect_identifier_suppliers_in_body(shell.body):
        return
    raise ValueError(
        format_astichi_error(
            "build",
            "no readable supplier named "
            f"`{outer_name}` at "
            f"`{format_instance_leaf(instance_name, ref_path, outer_name)}`",
            hint="publish the name with `astichi_export(...)` or an assignable slot at that path",
        )
    )


@dataclass(frozen=True)
class _CommittedAssignBinding:
    """Finalized assign leaf that can still reject stray extra chaining."""

    graph: BuilderGraph = field(compare=False, repr=False)
    binding: AssignBinding
    binding_added: bool

    def __getattr__(self, name: str) -> None:
        if name.startswith("_"):
            raise AttributeError(name)
        self._rollback_if_needed()
        raise ValueError(
            format_astichi_error(
                "build",
                "assign target path cannot continue after final outer name "
                f"`{format_instance_leaf(self.binding.target_instance, self.binding.target_ref_path, self.binding.outer_name)}`",
                hint="stop chaining after the published outer identifier name",
            )
        )

    def __getitem__(self, key: int | tuple[int, ...]) -> None:
        del key
        self._rollback_if_needed()
        raise ValueError(
            format_astichi_error(
                "build",
                "assign target identifier paths may not continue with index segments "
                "after final outer name "
                f"`{format_instance_leaf(self.binding.target_instance, self.binding.target_ref_path, self.binding.outer_name)}`",
                hint="use only further name segments after the outer identifier in `assign` paths",
            )
        )

    def _rollback_if_needed(self) -> None:
        if not self.binding_added:
            return
        for index in range(len(self.graph._assigns) - 1, -1, -1):
            if self.graph._assigns[index] == self.binding:
                del self.graph._assigns[index]
                break


@dataclass(frozen=True)
class _AssignTargetHandle:
    """Target-side path handle after ``to().<Dst>`` has named the root."""

    graph: BuilderGraph = field(compare=False, repr=False)
    source_instance: str
    source_ref_path: RefPath
    inner_name: str
    target_instance: str
    target_ref_path: RefPath = ()

    def __getitem__(self, key: int | tuple[int, ...]) -> "_AssignTargetHandle":
        if isinstance(key, tuple):
            items = key
        else:
            items = (key,)
        if any(not isinstance(item, int) for item in items):
            raise TypeError("target path indexes must be integers")
        if not self.target_ref_path:
            raise ValueError(
                format_astichi_error(
                    "build",
                    "assign target descendant paths may not start with index segments",
                    hint="name the first shell segment before indexing (e.g. `to().Foo[0].bar`)",
                )
            )
        candidate_ref = normalize_ref_path(self.target_ref_path + items)
        shell_index = _registered_shell_index(self.graph, self.target_instance)
        if shell_index is not None:
            shell_index.resolve(candidate_ref).require(
                instance_name=self.target_instance,
                role="assign target path",
            )
        return _AssignTargetHandle(
            graph=self.graph,
            source_instance=self.source_instance,
            source_ref_path=self.source_ref_path,
            inner_name=self.inner_name,
            target_instance=self.target_instance,
            target_ref_path=candidate_ref,
        )

    def __getattr__(self, name: str) -> "_AssignTargetHandle | _CommittedAssignBinding":
        if name.startswith("_"):
            raise AttributeError(name)
        shell_index = _registered_shell_index(self.graph, self.target_instance)
        candidate_ref = normalize_ref_path(self.target_ref_path + (name,))
        if shell_index is not None:
            resolution = shell_index.resolve(candidate_ref)
            if resolution.is_resolved():
                resolution.require(
                    instance_name=self.target_instance,
                    role="assign target path",
                )
                return _AssignTargetHandle(
                    graph=self.graph,
                    source_instance=self.source_instance,
                    source_ref_path=self.source_ref_path,
                    inner_name=self.inner_name,
                    target_instance=self.target_instance,
                    target_ref_path=candidate_ref,
                )
        _validate_registered_identifier_supplier(
            graph=self.graph,
            instance_name=self.target_instance,
            ref_path=self.target_ref_path,
            outer_name=name,
        )
        before = len(self.graph._assigns)
        binding = self.graph.add_assign(
            AssignBinding(
                source_instance=self.source_instance,
                inner_name=self.inner_name,
                target_instance=self.target_instance,
                outer_name=name,
                source_ref_path=normalize_ref_path(self.source_ref_path),
                target_ref_path=normalize_ref_path(self.target_ref_path),
            )
        )
        return _CommittedAssignBinding(
            graph=self.graph,
            binding=binding,
            binding_added=len(self.graph._assigns) > before,
        )


@dataclass(frozen=True)
class _AssignTargetPicker:
    """Picks the target instance in the ``assign`` chain."""

    graph: BuilderGraph = field(compare=False, repr=False)
    source_instance: str
    source_ref_path: RefPath
    inner_name: str

    def __getattr__(self, target_instance: str) -> _AssignTargetHandle:
        if target_instance.startswith("_"):
            raise AttributeError(target_instance)
        return _AssignTargetHandle(
            graph=self.graph,
            source_instance=self.source_instance,
            source_ref_path=self.source_ref_path,
            inner_name=self.inner_name,
            target_instance=target_instance,
        )


@dataclass(frozen=True)
class _AssignSourceReady:
    """Holds one source-side path until ``to()`` is called.

    ``to()`` is the explicit phase separator between the source and
    target sides of the wiring. It keeps the chain unambiguous:
    everything before ``to()`` names the demand site, everything
    after names the supplier, and the sentence reads naturally left
    to right — "assign `<Src>.<inner>` to `<Dst>.<outer>`".
    """

    graph: BuilderGraph = field(compare=False, repr=False)
    source_instance: str
    source_ref_path: RefPath
    inner_name: str
    leaf_path: tuple[int, ...] = ()

    def __getitem__(self, key: int | tuple[int, ...]) -> "_AssignSourceReady":
        if isinstance(key, tuple):
            items = key
        else:
            items = (key,)
        if any(not isinstance(item, int) for item in items):
            raise TypeError("target path indexes must be integers")
        return _AssignSourceReady(
            graph=self.graph,
            source_instance=self.source_instance,
            source_ref_path=self.source_ref_path,
            inner_name=self.inner_name,
            leaf_path=self.leaf_path + items,
        )

    def __getattr__(self, name: str) -> "_AssignSourceReady":
        if name.startswith("_"):
            raise AttributeError(name)
        candidate_ref = _descend_registered_ref(
            graph=self.graph,
            instance_name=self.source_instance,
            ref_path=self.source_ref_path,
            leaf_name=self.inner_name,
            leaf_path=self.leaf_path,
            role="assign source path",
        )
        return _AssignSourceReady(
            graph=self.graph,
            source_instance=self.source_instance,
            source_ref_path=candidate_ref,
            inner_name=name,
        )

    def to(self) -> _AssignTargetPicker:
        _validate_registered_identifier_demand(
            graph=self.graph,
            instance_name=self.source_instance,
            ref_path=self.source_ref_path,
            inner_name=self.inner_name,
        )
        if self.leaf_path:
            raise ValueError(
                format_astichi_error(
                    "build",
                    "assign identifier paths may not end with index segments",
                    hint="end the path on the outer identifier name, not `[i]`",
                )
            )
        return _AssignTargetPicker(
            graph=self.graph,
            source_instance=self.source_instance,
            source_ref_path=self.source_ref_path,
            inner_name=self.inner_name,
        )


@dataclass(frozen=True)
class _AssignSourcePicker:
    """Picks the inner demand name inside the source instance."""

    graph: BuilderGraph = field(compare=False, repr=False)
    source_instance: str
    source_ref_path: RefPath = ()
    pending_leaf_path: tuple[int, ...] = ()

    def __getitem__(self, key: int | tuple[int, ...]) -> "_AssignSourcePicker":
        if isinstance(key, tuple):
            items = key
        else:
            items = (key,)
        if any(not isinstance(item, int) for item in items):
            raise TypeError("target path indexes must be integers")
        return _AssignSourcePicker(
            graph=self.graph,
            source_instance=self.source_instance,
            source_ref_path=self.source_ref_path,
            pending_leaf_path=self.pending_leaf_path + items,
        )

    def __getattr__(self, inner_name: str) -> _AssignSourceReady:
        if inner_name.startswith("_"):
            raise AttributeError(inner_name)
        return _AssignSourceReady(
            graph=self.graph,
            source_instance=self.source_instance,
            source_ref_path=self.source_ref_path,
            inner_name=inner_name,
            leaf_path=self.pending_leaf_path,
        )


@dataclass(frozen=True)
class AssignProxy:
    """Entry point for ``builder.assign.<Src>.<inner>.to().<Dst>.<outer>``.

    Issue 006 6c (assign surface): explicit, fully-qualified wiring
    from an inner boundary demand (``astichi_import`` /
    ``__astichi_arg__``) on ``<Src>`` to an outer supplier
    ``<Dst>.<outer>``. The target instance is named explicitly so it
    need not be the edge target, and it may be registered after this
    call — validation of both sides is deferred to ``build_merge``.
    """

    graph: BuilderGraph = field(compare=False, repr=False)

    def __getattr__(self, source_instance: str) -> _AssignSourcePicker:
        if source_instance.startswith("_"):
            raise AttributeError(source_instance)
        return _AssignSourcePicker(
            graph=self.graph,
            source_instance=source_instance,
        )


@dataclass
class BuilderHandle:
    """Public builder handle layered over the raw builder graph."""

    graph: BuilderGraph = field(default_factory=BuilderGraph)

    @property
    def add(self) -> AddProxy:
        return AddProxy(graph=self.graph)

    @property
    def assign(self) -> AssignProxy:
        return AssignProxy(graph=self.graph)

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
