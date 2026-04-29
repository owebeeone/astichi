"""Raw mutable builder graph for Astichi V1."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from astichi.diagnostics import format_astichi_error
from astichi.model import Composable
from astichi.model.basic import BasicComposable
from astichi.path_resolution import ShellIndex
from astichi.shell_refs import RefPath, normalize_ref_path


_INDEXED_INSTANCE_NAME_RE = re.compile(
    r"^(?P<stem>[A-Za-z_][A-Za-z0-9_]*)\[(?P<indexes>-?\d+(?:,-?\d+)*)\]$"
)


def parse_indexed_instance_name(name: str) -> tuple[str, tuple[int, ...]] | None:
    """Return ``(stem, indexes)`` for ``Stem[1,2]`` family members."""
    match = _INDEXED_INSTANCE_NAME_RE.fullmatch(name)
    if match is None:
        return None
    indexes = tuple(int(part) for part in match.group("indexes").split(","))
    return match.group("stem"), indexes


def format_indexed_instance_name(stem: str, indexes: tuple[int, ...]) -> str:
    """Render a builder instance family member name."""
    if not stem.isidentifier():
        raise ValueError(
            format_astichi_error(
                "build",
                f"instance family stem must be a valid identifier: {stem!r}",
                hint="use a valid Python identifier before `[i]` in `builder.add.<Name>[i]`",
            )
        )
    if not indexes or any(not isinstance(index, int) for index in indexes):
        raise TypeError("instance family indexes must be integers")
    return f"{stem}[{','.join(str(index) for index in indexes)}]"


def instance_family_stem(name: str) -> str:
    parsed = parse_indexed_instance_name(name)
    if parsed is not None:
        return parsed[0]
    return name


def instance_name_sort_key(name: str) -> tuple[str, int, tuple[int, ...]]:
    parsed = parse_indexed_instance_name(name)
    if parsed is None:
        return name, 0, ()
    stem, indexes = parsed
    return stem, 1, indexes


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
class EdgeSourceOverlay:
    """Per-edge source specialization without mutating the instance record."""

    arg_names: tuple[tuple[str, str], ...] = ()
    keep_names: frozenset[str] = frozenset()
    bind_values: tuple[tuple[str, object], ...] = ()

    def arg_names_map(self) -> dict[str, str]:
        return dict(self.arg_names)

    def bind_values_map(self) -> dict[str, object]:
        return dict(self.bind_values)


@dataclass(frozen=True)
class AdditiveEdge:
    """Additive composition edge."""

    target: TargetRef
    source_instance: str
    order: int = 0
    overlay: EdgeSourceOverlay = field(default_factory=EdgeSourceOverlay)


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


@dataclass(frozen=True)
class IdentifierBinding:
    """Direct scope-aware identifier binding for builder graphs."""

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
    _identifier_bindings: list[IdentifierBinding] = field(default_factory=list)

    def _validate_instance_composable(
        self,
        name: str,
        composable: Composable,
    ) -> None:
        if not isinstance(composable, BasicComposable):
            return
        ShellIndex.from_tree(composable.tree).require_unique_non_root_paths(
            instance_name=name
        )

    def add_instance(self, name: str, composable: Composable) -> InstanceRecord:
        """Register a named composable instance."""
        parsed = parse_indexed_instance_name(name)
        if not name.isidentifier() and parsed is None:
            raise ValueError(
                format_astichi_error(
                    "build",
                    f"instance name must be a valid identifier: {name!r}",
                    hint="use `builder.add.<Name>(...)` or `builder.add.<Name>[i](...)` with integer indexes",
                )
            )
        if name in self._instances:
            raise ValueError(
                format_astichi_error(
                    "build",
                    f"duplicate instance name: {name}",
                    hint="choose a unique instance name for each `builder.add`",
                )
            )
        new_stem = instance_family_stem(name)
        new_is_family = parsed is not None
        for existing_name in self._instances:
            existing_is_family = parse_indexed_instance_name(existing_name) is not None
            if instance_family_stem(existing_name) != new_stem:
                continue
            if existing_is_family != new_is_family:
                raise ValueError(
                    format_astichi_error(
                        "build",
                        f"cannot mix base instance `{new_stem}` with indexed family members `{new_stem}[...]`",
                        hint="choose either `builder.add.<Name>(...)` or `builder.add.<Name>[i](...)` for a given stem",
                    )
                )
        self._validate_instance_composable(name, composable)
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
            raise ValueError(
                format_astichi_error(
                    "build",
                    f"unknown instance: {name}",
                    hint="register the instance first with `builder.add.<Name>(...)`",
                )
            )
        self._validate_instance_composable(name, composable)
        record = InstanceRecord(name=name, composable=composable)
        self._instances[name] = record
        return record

    def add_additive_edge(
        self,
        *,
        target: TargetRef,
        source_instance: str,
        order: int = 0,
        overlay: EdgeSourceOverlay | None = None,
    ) -> AdditiveEdge:
        """Register an additive edge from a source instance into a target."""
        if target.root_instance not in self._instances:
            raise ValueError(
                format_astichi_error(
                    "build",
                    f"unknown target root instance: {target.root_instance}",
                    hint="register the target root with `builder.add` before wiring edges",
                )
            )
        if source_instance not in self._instances:
            raise ValueError(
                format_astichi_error(
                    "build",
                    f"unknown source instance: {source_instance}",
                    hint="register the source instance with `builder.add` before wiring edges",
                )
            )
        edge = AdditiveEdge(
            target=target,
            source_instance=source_instance,
            order=order,
            overlay=EdgeSourceOverlay() if overlay is None else overlay,
        )
        self._edges.append(edge)
        return edge

    def _validate_identifier_wiring_names(
        self,
        *,
        surface: str,
        source_instance: str,
        inner_name: str,
        target_instance: str,
        outer_name: str,
    ) -> None:
        for name in (
            source_instance,
            inner_name,
            target_instance,
            outer_name,
        ):
            if not isinstance(name, str) or not name.isidentifier():
                raise ValueError(
                    format_astichi_error(
                        "build",
                        f"{surface} binding names must be valid Python "
                        f"identifiers; got {name!r}",
                        hint=(
                            "use identifier tokens for source/target/inner/"
                            f"outer names in `{surface}`"
                        ),
                    )
                )

    def _find_identifier_binding_for_source(
        self,
        *,
        source_instance: str,
        source_ref_path: RefPath,
        inner_name: str,
    ) -> IdentifierBinding | None:
        for existing in self._identifier_bindings:
            if (
                existing.source_instance == source_instance
                and existing.source_ref_path == source_ref_path
                and existing.inner_name == inner_name
            ):
                return existing
        return None

    def _find_assign_for_source(
        self,
        *,
        source_instance: str,
        source_ref_path: RefPath,
        inner_name: str,
    ) -> AssignBinding | None:
        for existing in self._assigns:
            if (
                existing.source_instance == source_instance
                and existing.source_ref_path == source_ref_path
                and existing.inner_name == inner_name
            ):
                return existing
        return None

    def add_assign(self, binding: AssignBinding) -> AssignBinding:
        """Record an ``builder.assign`` cross-instance wiring.

        Idempotent for exact-duplicate declarations; raises if the same
        ``(source_instance, inner_name)`` pair is bound to a different
        ``(target_instance, outer_name)``. Validation that the
        referenced instances / ports actually exist is deferred to
        ``build_merge`` so the user may declare wirings against pieces
        that have not yet been registered.
        """
        binding = AssignBinding(
            source_instance=binding.source_instance,
            inner_name=binding.inner_name,
            target_instance=binding.target_instance,
            outer_name=binding.outer_name,
            source_ref_path=normalize_ref_path(binding.source_ref_path),
            target_ref_path=normalize_ref_path(binding.target_ref_path),
        )
        self._validate_identifier_wiring_names(
            surface="assign",
            source_instance=binding.source_instance,
            inner_name=binding.inner_name,
            target_instance=binding.target_instance,
            outer_name=binding.outer_name,
        )
        existing = self._find_assign_for_source(
            source_instance=binding.source_instance,
            source_ref_path=binding.source_ref_path,
            inner_name=binding.inner_name,
        )
        if existing is not None:
            if existing == binding:
                return existing
            raise ValueError(
                format_astichi_error(
                    "build",
                    f"conflicting assign for `{binding.source_instance}"
                    f".{binding.inner_name}`: already bound to "
                    f"`{existing.target_instance}.{existing.outer_name}`, "
                    f"cannot rebind to `{binding.target_instance}"
                    f".{binding.outer_name}`",
                    hint="remove or reconcile duplicate `builder.assign` declarations",
                )
            )
        existing_binding = self._find_identifier_binding_for_source(
            source_instance=binding.source_instance,
            source_ref_path=binding.source_ref_path,
            inner_name=binding.inner_name,
        )
        if existing_binding is not None:
            raise ValueError(
                format_astichi_error(
                    "build",
                    f"conflicting identifier wiring for `{binding.source_instance}"
                    f".{binding.inner_name}`: already bound with "
                    "`builder.bind_identifier`, cannot also use `builder.assign`",
                    hint="use exactly one explicit identifier wiring surface for each source demand",
                )
            )
        self._assigns.append(binding)
        return binding

    def add_identifier_binding(
        self, binding: IdentifierBinding
    ) -> IdentifierBinding:
        """Record a direct scope-aware identifier binding."""
        binding = IdentifierBinding(
            source_instance=binding.source_instance,
            inner_name=binding.inner_name,
            target_instance=binding.target_instance,
            outer_name=binding.outer_name,
            source_ref_path=normalize_ref_path(binding.source_ref_path),
            target_ref_path=normalize_ref_path(binding.target_ref_path),
        )
        self._validate_identifier_wiring_names(
            surface="bind_identifier",
            source_instance=binding.source_instance,
            inner_name=binding.inner_name,
            target_instance=binding.target_instance,
            outer_name=binding.outer_name,
        )
        existing = self._find_identifier_binding_for_source(
            source_instance=binding.source_instance,
            source_ref_path=binding.source_ref_path,
            inner_name=binding.inner_name,
        )
        if existing is not None:
            if existing == binding:
                return existing
            raise ValueError(
                format_astichi_error(
                    "build",
                    "conflicting bind_identifier for "
                    f"`{binding.source_instance}.{binding.inner_name}`: "
                    f"already bound to `{existing.target_instance}."
                    f"{existing.outer_name}`, cannot rebind to "
                    f"`{binding.target_instance}.{binding.outer_name}`",
                    hint="remove or reconcile duplicate `builder.bind_identifier` declarations",
                )
            )
        existing_assign = self._find_assign_for_source(
            source_instance=binding.source_instance,
            source_ref_path=binding.source_ref_path,
            inner_name=binding.inner_name,
        )
        if existing_assign is not None:
            raise ValueError(
                format_astichi_error(
                    "build",
                    f"conflicting identifier wiring for `{binding.source_instance}"
                    f".{binding.inner_name}`: already bound with "
                    "`builder.assign`, cannot also use `builder.bind_identifier`",
                    hint="use exactly one explicit identifier wiring surface for each source demand",
                )
            )
        self._identifier_bindings.append(binding)
        return binding

    @property
    def instances(self) -> tuple[InstanceRecord, ...]:
        """Inspectable named instances."""
        return tuple(
            self._instances[name]
            for name in sorted(self._instances, key=instance_name_sort_key)
        )

    @property
    def edges(self) -> tuple[AdditiveEdge, ...]:
        """Inspectable additive edges."""
        return tuple(self._edges)

    @property
    def assigns(self) -> tuple[AssignBinding, ...]:
        """Inspectable cross-instance identifier assignments."""
        return tuple(self._assigns)

    @property
    def identifier_bindings(self) -> tuple[IdentifierBinding, ...]:
        """Inspectable direct identifier bindings."""
        return tuple(self._identifier_bindings)
