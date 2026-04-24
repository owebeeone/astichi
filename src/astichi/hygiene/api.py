"""Name classification and hygiene support for Astichi V1."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from itertools import count
from typing import Literal

from astichi.lowering import RecognizedMarker
from astichi.model.basic import BasicComposable

Mode = Literal["strict", "permissive"]
LexicalRole = Literal["internal", "preserved", "external"]
BindingKind = Literal["binding", "reference"]


@dataclass(frozen=True)
class ImpliedDemand:
    """An unresolved free identifier promoted to a demand."""

    name: str


@dataclass(frozen=True)
class NameClassification:
    """Classification result for names in a lowered snippet."""

    locals: frozenset[str]
    kept: frozenset[str]
    preserved: frozenset[str]
    externals: frozenset[str]
    unresolved_free: frozenset[str]
    implied_demands: tuple[ImpliedDemand, ...]


@dataclass(frozen=True)
class HygieneResult:
    """Hygiene result for a frontend composable."""

    classification: NameClassification
    tree: ast.Module
    scope_analysis: "ScopeAnalysis | None" = None


@dataclass(frozen=True)
class ScopeId:
    """Opaque scope identity for lexical-name hygiene."""

    serial: int


@dataclass(frozen=True)
class LexicalOccurrence:
    """A lexical identifier occurrence annotated with scope identity."""

    raw_name: str
    scope_id: ScopeId
    collision_domain: int
    role: LexicalRole
    binding_kind: BindingKind
    ordinal: int
    node: ast.AST


@dataclass(frozen=True)
class ScopeAnalysis:
    """Scope-identity assignment for a lowered snippet."""

    occurrences: tuple[LexicalOccurrence, ...]
    # Issue 006 6c (trust model): names the user has declared as
    # trusted against hygiene rename via ``astichi_keep`` /
    # ``astichi_pass`` or the ``keep_names=`` surface. Populated by
    # ``assign_scope_identity`` so ``rename_scope_collisions`` can
    # short-circuit those names without a second arg-plumbing.
    trust_names: frozenset[str] = frozenset()


def analyze_names(
    composable: BasicComposable,
    *,
    mode: Mode = "strict",
    preserved_names: frozenset[str] = frozenset(),
) -> NameClassification:
    """Classify names for a frontend composable."""
    if mode not in ("strict", "permissive"):
        raise ValueError(f"unsupported hygiene mode: {mode}")

    ignored_name_nodes = _ignored_name_nodes(composable.markers)
    local_bindings = _collect_local_bindings(composable.tree)
    kept = frozenset(
        marker.name_id
        for marker in composable.markers
        if marker.source_name == "astichi_keep" and marker.name_id is not None
    )
    # Issue 005 §4: both the stripped identifier-shape name (`foo`) and
    # the raw suffixed form (`foo__astichi_keep__` / `foo__astichi_arg__`)
    # must be pinned in the preserved set before hygiene runs. The
    # stripped form protects the eventual keep-strip output from
    # colliding with any free `foo`; the raw form keeps `ast.Name` Load
    # references from being classified as implied demands (5b now
    # recognises Name/arg occurrences as suffix markers).
    identifier_suffix_preserved = _collect_identifier_suffix_preserved(
        composable.markers
    )
    # Issue 006: `astichi_import(name)` pins `name` against hygiene
    # rename and suppresses implied-demand classification for Load
    # references to it within the scope. `astichi_pass(name)` is
    # value-form only and does not preserve unrelated same-named
    # references in the surrounding scope.
    boundary_preserved = _collect_boundary_preserved(composable.markers)
    externals = frozenset(
        marker.name_id
        for marker in composable.markers
        if marker.source_name == "astichi_bind_external" and marker.name_id is not None
    )
    preserved = frozenset(
        set(kept)
        | set(preserved_names)
        | set(identifier_suffix_preserved)
        | set(boundary_preserved)
    )

    unresolved: set[str] = set()
    for node in ast.walk(composable.tree):
        if not isinstance(node, ast.Name):
            continue
        if id(node) in ignored_name_nodes:
            continue
        if not isinstance(node.ctx, ast.Load):
            continue
        if node.id in local_bindings:
            continue
        if node.id in preserved:
            continue
        if node.id in externals:
            continue
        unresolved.add(node.id)

    unresolved_free = frozenset(sorted(unresolved))
    implied_demands: tuple[ImpliedDemand, ...]
    if mode == "permissive":
        implied_demands = tuple(ImpliedDemand(name=name) for name in sorted(unresolved))
    else:
        if unresolved:
            names = ", ".join(sorted(unresolved))
            raise ValueError(f"unresolved free identifiers in strict mode: {names}")
        implied_demands = ()

    return NameClassification(
        locals=frozenset(sorted(local_bindings)),
        kept=frozenset(sorted(kept)),
        preserved=frozenset(sorted(preserved)),
        externals=frozenset(sorted(externals)),
        unresolved_free=unresolved_free,
        implied_demands=implied_demands,
    )


def rewrite_hygienically(
    composable: BasicComposable,
    *,
    preserved_names: frozenset[str] = frozenset(),
    mode: Mode = "strict",
) -> HygieneResult:
    """Rewrite colliding local names hygienically."""
    classification = analyze_names(
        composable,
        mode=mode,
        preserved_names=preserved_names,
    )
    renamer = _Renamer(classification.preserved)
    rewritten = renamer.visit(ast.fix_missing_locations(ast.parse(ast.unparse(composable.tree))))
    assert isinstance(rewritten, ast.Module)
    return HygieneResult(
        classification=classification,
        tree=rewritten,
    )


def assign_scope_identity(
    composable: BasicComposable,
    *,
    preserved_names: frozenset[str] = frozenset(),
    trust_names: frozenset[str] = frozenset(),
    external_names: frozenset[str] = frozenset(),
    fresh_scope_nodes: tuple[ast.AST, ...] = (),
) -> ScopeAnalysis:
    """Assign scope identity to lexical name occurrences.

    ``preserved_names`` names are pinned against the flat ``_Renamer``
    pass and surface as ``role="preserved"`` when loaded — they
    participate in rename tie-breaking (first preserved scope wins)
    and are suitable for "don't rename this, unless you must" pins
    such as identifier-arg resolution targets.

    ``trust_names`` is the stricter "user explicitly said keep" set.
    Trusted names are never renamed by ``rename_scope_collisions`` —
    they always emit literally across every Astichi scope.
    Marker-derived ``astichi_keep`` names are unioned in automatically;
    callers who have additional trust declarations (e.g.
    ``keep_names=`` from the builder) must pass them explicitly.
    Trusted names are also added to ``preserved_names`` so load-time
    classification remains consistent.
    """
    ignored_name_nodes = _ignored_name_nodes(composable.markers)
    # Issue 005 §4 + 5b: preserve both stripped and raw suffixed names
    # (see `analyze_names` for rationale).
    kept_preserved = frozenset(
        marker.name_id
        for marker in composable.markers
        if marker.source_name == "astichi_keep" and marker.name_id is not None
    )
    marker_preserved_names = (
        kept_preserved
        | _collect_identifier_suffix_preserved(composable.markers)
    )
    # Issue 006 6c (trust model): the effective trust set unions the
    # caller-supplied `trust_names` with trust-declaring markers
    # (`astichi_keep`). Callers that want preserved-
    # but-not-trusted semantics (e.g. identifier-arg resolution
    # targets that must not blanket-suppress rename on their raw
    # name) pass those through `preserved_names` only.
    effective_trust_names = frozenset(
        set(trust_names) | set(_collect_trust_preserved(composable.markers))
    )
    effective_preserved_names = frozenset(
        set(preserved_names) | set(marker_preserved_names) | set(effective_trust_names)
    )
    marker_external_names = frozenset(
        marker.name_id
        for marker in composable.markers
        if marker.source_name == "astichi_bind_external" and marker.name_id is not None
    )
    effective_fresh_scope_nodes = fresh_scope_nodes + _marker_fresh_scope_nodes(
        composable.tree
    )
    fresh_scope_local_bindings: dict[int, frozenset[str]] = {}
    for node in effective_fresh_scope_nodes:
        if isinstance(node, ast.Call) and _is_expression_insert(node):
            fresh_scope_local_bindings[id(node)] = _collect_expression_bindings(
                node.args[1]
            )
    # Issue 006 6c: names declared via `astichi_import(name)` at the top
    # of a fresh Astichi scope's body bind *outer-scope* references, not
    # inner-scope locals. We classify both Load and Store occurrences of
    # those names in the outer scope so `rename_scope_collisions`
    # unifies them with the outer scope's binding instead of treating
    # them as a fresh per-shell rename target.
    fresh_scope_imported_names = _collect_fresh_scope_imports(
        composable.tree, composable.markers
    )
    fresh_scope_trust_declarations = _collect_fresh_scope_trust_declarations(
        composable.tree, composable.markers
    )
    visitor = _ScopeIdentityVisitor(
        ignored_name_nodes=ignored_name_nodes,
        preserved_names=effective_preserved_names,
        trust_names=effective_trust_names,
        external_names=frozenset(set(external_names) | set(marker_external_names)),
        fresh_scope_nodes=effective_fresh_scope_nodes,
        fresh_scope_local_bindings=fresh_scope_local_bindings,
        fresh_scope_imported_names=fresh_scope_imported_names,
        fresh_scope_trust_declarations=fresh_scope_trust_declarations,
        module_trust_declarations=fresh_scope_trust_declarations.get(
            id(composable.tree), frozenset()
        ),
    )
    visitor.visit(composable.tree)
    return ScopeAnalysis(
        occurrences=tuple(visitor.occurrences),
        trust_names=effective_trust_names,
    )


def rename_scope_collisions(scope_analysis: ScopeAnalysis) -> None:
    """Rename colliding lexical names in-place based on scope identity.

    Issue 006 6c (trust / inheritance model): for names listed in
    ``scope_analysis.trust_names`` the rule is "user owns the name
    everywhere it appears with preserved intent" — *every* scope with
    a preserved occurrence keeps the raw spelling, and only scopes
    with purely internal bindings of that spelling get renamed. This
    lets a keep/pass declaration in one scope and an
    ``astichi_import`` re-projection into another scope co-emit the
    same literal name, without any scope-threading indirection.

    For names *not* in ``trust_names`` the pre-6c rule applies: the
    first scope with a preserved occurrence (or the earliest scope if
    none is preserved) wins; every other scope is renamed with a
    ``__astichi_scoped_N`` suffix.
    """
    grouped: dict[tuple[str, int], list[LexicalOccurrence]] = {}
    for occurrence in scope_analysis.occurrences:
        grouped.setdefault(
            (occurrence.raw_name, occurrence.collision_domain), []
        ).append(occurrence)

    emitted_counter = count(1)
    for raw_name, domain in sorted(grouped):
        occurrences = sorted(grouped[(raw_name, domain)], key=lambda item: item.ordinal)
        by_scope: dict[int, list[LexicalOccurrence]] = {}
        for occurrence in occurrences:
            by_scope.setdefault(occurrence.scope_id.serial, []).append(occurrence)
        if len(by_scope) <= 1:
            continue
        ordered_scopes = sorted(
            by_scope.items(),
            key=lambda item: item[1][0].ordinal,
        )
        preserved_scopes = {
            scope_serial
            for scope_serial, scope_occurrences in ordered_scopes
            if any(
                occurrence.role == "preserved"
                for occurrence in scope_occurrences
            )
        }
        is_trusted = raw_name in scope_analysis.trust_names
        if is_trusted:
            kept_scopes = preserved_scopes
        else:
            first_preserved = next(
                (
                    scope_serial
                    for scope_serial, _ in ordered_scopes
                    if scope_serial in preserved_scopes
                ),
                None,
            )
            keep_scope_serial = (
                first_preserved if first_preserved is not None else ordered_scopes[0][0]
            )
            kept_scopes = {keep_scope_serial}
        for scope_serial, scope_occurrences in ordered_scopes:
            emitted_name = raw_name
            if scope_serial not in kept_scopes:
                emitted_name = f"{raw_name}__astichi_scoped_{next(emitted_counter)}"
            for occurrence in scope_occurrences:
                if isinstance(occurrence.node, ast.Name):
                    occurrence.node.id = emitted_name
                elif isinstance(occurrence.node, ast.arg):
                    occurrence.node.arg = emitted_name


def _collect_identifier_suffix_preserved(
    markers: tuple[object, ...],
) -> frozenset[str]:
    """Names that must survive hygiene for identifier-shape slots.

    Issue 005 §4 + 5b: collect the stripped base (`foo`) so competing
    free names get renamed away, and the raw suffixed form
    (`foo__astichi_keep__` / `foo__astichi_arg__`) so `ast.Name` Load
    references that the marker visitor now recognises do not become
    implied demands and are not renamed by the scope-identity pass.
    """
    preserved: set[str] = set()
    for marker in markers:
        if not isinstance(marker, RecognizedMarker):
            continue
        if marker.source_name not in (
            "astichi_keep_identifier",
            "astichi_arg_identifier",
        ):
            continue
        if marker.name_id is not None:
            preserved.add(marker.name_id)
        raw = _raw_suffixed_name(marker.node)
        if raw is not None:
            preserved.add(raw)
    return frozenset(preserved)


def _collect_boundary_preserved(
    markers: tuple[object, ...],
) -> frozenset[str]:
    """Names declared by ``astichi_import`` (issue 006 6b).

    Import pins its name against hygiene rename and suppresses
    implied-demand classification for Load references within the scope.
    Per-shell scope override for imports is layered on by
    ``_collect_fresh_scope_imports`` (issue 006 6c); this set exists to
    seed the flat `preserved` set that `analyze_names` consumes.
    """
    preserved: set[str] = set()
    for marker in markers:
        if not isinstance(marker, RecognizedMarker):
            continue
        if marker.source_name != "astichi_import":
            continue
        if marker.name_id is not None:
            preserved.add(marker.name_id)
    return frozenset(preserved)


def _collect_trust_preserved(
    markers: tuple[object, ...],
) -> frozenset[str]:
    """Names the user has declared as *trusted* against hygiene rename.

    Issue 006 6c (inheritance / trust model): ``astichi_keep(name)`` is
    the user's "I know what I'm doing; trust me — this is my name"
    contract. A trusted name is never renamed by
    ``rename_scope_collisions``, even if occurrences span multiple
    Astichi scopes: the user owns the name across the composition and
    is responsible for preventing unintended collisions.

    ``astichi_import(name)`` is intentionally NOT a trust declaration.
    An import only states "this name is supplied by my enclosing
    scope"; it pins against implied-demand classification (see
    ``_collect_boundary_preserved``) and defers name identity to the
    enclosing Astichi scope's binding. When the import's target is
    itself trust-declared, the inheritance scan in the visitor lifts
    the import's occurrences into the trusted class so the literal
    name passes through hygiene unchanged.
    """
    trusted: set[str] = set()
    for marker in markers:
        if not isinstance(marker, RecognizedMarker):
            continue
        if marker.source_name != "astichi_keep":
            continue
        if marker.name_id is not None:
            trusted.add(marker.name_id)
    return frozenset(trusted)


def _collect_fresh_scope_trust_declarations(
    tree: ast.Module, markers: tuple[object, ...]
) -> dict[int, frozenset[str]]:
    """Map each Astichi scope node to the names it trust-declares.

    Issue 006 6c (inheritance / trust model): ``astichi_keep(name)`` at
    the top of a scope is the user's "I own this name in *this* scope"
    declaration. Trust is therefore a per-scope property — a keep on
    the module scope pins the module's name but leaves nested
    inner-shell bindings of the same spelling subject to normal rename,
    while a keep appearing inside a nested fresh Astichi scope pins
    *that* scope's name.

    The returned map is keyed by ``id(scope_node)`` where the scope
    node is either the ``ast.Module`` root or a fresh Astichi scope
    (``@astichi_insert``-decorated shell, expression-form
    ``astichi_insert`` call). ``astichi_import`` is intentionally not
    collected here — it surfaces via
    ``_collect_fresh_scope_imports`` with different semantics.
    """
    declarations: dict[int, set[str]] = {}
    trust_markers = [
        marker
        for marker in markers
        if isinstance(marker, RecognizedMarker)
        and marker.source_name == "astichi_keep"
        and marker.name_id is not None
    ]
    if not trust_markers:
        return {}
    parent_scope_node: dict[int, ast.AST] = {}

    def _enter(node: ast.AST, scope_node: ast.AST) -> None:
        parent_scope_node[id(node)] = scope_node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            child_scope = node if _has_insert_decorator(node.decorator_list) else scope_node
            for decorator in node.decorator_list:
                _enter(decorator, scope_node)
            for child in node.body:
                _enter(child, child_scope)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for argument in (
                    list(node.args.posonlyargs)
                    + list(node.args.args)
                    + list(node.args.kwonlyargs)
                ):
                    _enter(argument, child_scope)
            return
        if isinstance(node, ast.Call) and _is_expression_insert(node):
            _enter(node.func, scope_node)
            _enter(node.args[0], scope_node)
            _enter(node.args[1], node)
            for keyword in node.keywords:
                _enter(keyword, scope_node)
            return
        for child in ast.iter_child_nodes(node):
            _enter(child, scope_node)

    for child in tree.body:
        _enter(child, tree)
    for marker in trust_markers:
        scope_node = parent_scope_node.get(id(marker.node), tree)
        assert marker.name_id is not None
        declarations.setdefault(id(scope_node), set()).add(marker.name_id)
    return {
        scope_id: frozenset(names) for scope_id, names in declarations.items()
    }


def _collect_fresh_scope_imports(
    tree: ast.Module, markers: tuple[object, ...]
) -> dict[int, frozenset[str]]:
    """Map each fresh Astichi scope node to the names it ``astichi_import``\\s.

    Issue 006 6c: when a fresh scope (an ``@astichi_insert``-decorated
    shell or expression-form ``astichi_insert`` call) declares
    ``astichi_import(name)`` in its body, the inner scope's
    Store/Load references to `name` logically belong to the outer
    Astichi scope — the import is an alias-through, not a fresh
    per-shell rebind. We collect the per-shell set here so
    `_ScopeIdentityVisitor` can override scope classification when it
    descends into each shell.

    The root scope (module body) is intentionally omitted: module-level
    imports surface as IDENTIFIER demand ports on the composable and
    have no inner-scope rename to prevent.
    """
    imports_by_scope: dict[int, set[str]] = {}
    import_markers = [
        marker
        for marker in markers
        if isinstance(marker, RecognizedMarker)
        and marker.source_name == "astichi_import"
        and marker.name_id is not None
    ]
    if not import_markers:
        return {}
    parent_scope_node: dict[int, ast.AST] = {}
    stack: list[ast.AST] = [tree]

    def _enter(node: ast.AST, scope_node: ast.AST) -> None:
        parent_scope_node[id(node)] = scope_node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            child_scope = node if _has_insert_decorator(node.decorator_list) else scope_node
            for decorator in node.decorator_list:
                _enter(decorator, scope_node)
            for child in node.body:
                _enter(child, child_scope)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for argument in (
                    list(node.args.posonlyargs)
                    + list(node.args.args)
                    + list(node.args.kwonlyargs)
                ):
                    _enter(argument, child_scope)
            return
        if isinstance(node, ast.Call) and _is_expression_insert(node):
            _enter(node.func, scope_node)
            _enter(node.args[0], scope_node)
            _enter(node.args[1], node)
            for keyword in node.keywords:
                _enter(keyword, scope_node)
            return
        for child in ast.iter_child_nodes(node):
            _enter(child, scope_node)

    for child in tree.body:
        _enter(child, tree)
    for marker in import_markers:
        scope_node = parent_scope_node.get(id(marker.node), tree)
        if scope_node is tree:
            continue
        assert marker.name_id is not None
        imports_by_scope.setdefault(id(scope_node), set()).add(marker.name_id)
    return {
        scope_id: frozenset(names) for scope_id, names in imports_by_scope.items()
    }


def _raw_suffixed_name(node: ast.AST) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.arg):
        return node.arg
    return None


def _ignored_name_nodes(markers: tuple[object, ...]) -> set[int]:
    ignored: set[int] = set()
    for marker in markers:
        if not isinstance(marker, RecognizedMarker):
            continue
        if isinstance(marker.node, ast.Call):
            if isinstance(marker.node.func, ast.Name):
                ignored.add(id(marker.node.func))
            if marker.spec.is_name_bearing():
                first_arg = marker.node.args[0]
                if isinstance(first_arg, ast.Name):
                    ignored.add(id(first_arg))
            if marker.source_name == "astichi_insert":
                for keyword in marker.node.keywords:
                    if keyword.arg != "ref":
                        continue
                    for child in ast.walk(keyword.value):
                        if isinstance(child, ast.Name):
                            ignored.add(id(child))
    return ignored


def _marker_fresh_scope_nodes(tree: ast.Module) -> tuple[ast.AST, ...]:
    collector = _FreshScopeCollector()
    collector.visit(tree)
    return tuple(collector.nodes)


def _collect_local_bindings(tree: ast.Module) -> set[str]:
    collector = _BindingCollector()
    collector.visit(tree)
    return collector.bindings


class _BindingCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.bindings: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bindings.add(node.id)

    def visit_arg(self, node: ast.arg) -> None:
        self.bindings.add(node.arg)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.bindings.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.bindings.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bindings.add(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name)


class _FreshScopeCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.nodes: list[ast.AST] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if _has_insert_decorator(node.decorator_list):
            self.nodes.append(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if _has_insert_decorator(node.decorator_list):
            self.nodes.append(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if _has_insert_decorator(node.decorator_list):
            self.nodes.append(node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_expression_insert(node):
            self.nodes.append(node)
        self.generic_visit(node)


def _has_insert_decorator(decorators: list[ast.expr]) -> bool:
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        if isinstance(decorator.func, ast.Name) and decorator.func.id == "astichi_insert":
            return True
    return False


def _is_expression_insert(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Name)
        and node.func.id == "astichi_insert"
        and len(node.args) == 2
    )


def _collect_expression_bindings(node: ast.AST) -> frozenset[str]:
    """Collect Store-context names within an expression subtree."""
    bindings: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            bindings.add(child.id)
    return frozenset(bindings)


class _ScopeBindingCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.bindings_by_scope: dict[int, frozenset[str]] = {}
        self.parameter_bindings_by_scope: dict[int, frozenset[str]] = {}

    def visit_Module(self, node: ast.Module) -> None:
        self.bindings_by_scope[id(node)] = frozenset(self._collect_scope_bindings(node))
        self.parameter_bindings_by_scope[id(node)] = frozenset()
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.bindings_by_scope[id(node)] = frozenset(self._collect_scope_bindings(node))
        self.parameter_bindings_by_scope[id(node)] = frozenset(
            self._collect_parameter_bindings(node)
        )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.bindings_by_scope[id(node)] = frozenset(self._collect_scope_bindings(node))
        self.parameter_bindings_by_scope[id(node)] = frozenset(
            self._collect_parameter_bindings(node)
        )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bindings_by_scope[id(node)] = frozenset(self._collect_scope_bindings(node))
        self.parameter_bindings_by_scope[id(node)] = frozenset()
        self.generic_visit(node)

    def _collect_scope_bindings(
        self,
        node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> set[str]:
        collector = _SingleScopeBindingCollector()
        if isinstance(node, ast.Module):
            for statement in node.body:
                collector.visit(statement)
        else:
            for decorator in node.decorator_list:
                collector.visit(decorator)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for argument in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                    collector.bindings.add(argument.arg)
                if node.args.vararg is not None:
                    collector.bindings.add(node.args.vararg.arg)
                if node.args.kwarg is not None:
                    collector.bindings.add(node.args.kwarg.arg)
            for statement in node.body:
                collector.visit(statement)
        return collector.bindings

    def _collect_parameter_bindings(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> set[str]:
        bindings: set[str] = {
            argument.arg
            for argument in (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            )
        }
        if node.args.vararg is not None:
            bindings.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            bindings.add(node.args.kwarg.arg)
        return bindings


class _SingleScopeBindingCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.bindings: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bindings.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)


class _ScopeIdentityVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        ignored_name_nodes: set[int],
        preserved_names: frozenset[str],
        trust_names: frozenset[str],
        external_names: frozenset[str],
        fresh_scope_nodes: tuple[ast.AST, ...],
        fresh_scope_local_bindings: dict[int, frozenset[str]] | None = None,
        fresh_scope_imported_names: dict[int, frozenset[str]] | None = None,
        fresh_scope_trust_declarations: dict[int, frozenset[str]] | None = None,
        module_trust_declarations: frozenset[str] = frozenset(),
    ) -> None:
        self.ignored_name_nodes = ignored_name_nodes
        self.preserved_names = preserved_names
        self.trust_names = trust_names
        self.external_names = external_names
        self.fresh_scope_node_ids = {id(node) for node in fresh_scope_nodes}
        self.fresh_scope_local_bindings = fresh_scope_local_bindings or {}
        self.fresh_scope_imported_names = fresh_scope_imported_names or {}
        self.fresh_scope_trust_declarations = fresh_scope_trust_declarations or {}
        self.scope_counter = count(2)
        self.collision_domain_counter = count(1)
        self.scope_stack: list[ScopeId] = [ScopeId(0), ScopeId(1)]
        self.collision_domain_stack: list[int] = [0]
        self.astichi_scope_bindings_stack: list[frozenset[str] | None] = []
        self.astichi_scope_imports_stack: list[frozenset[str]] = []
        # Module scope (serial 1) carries its own trust declarations
        # at the base of the stack; fresh scopes push their own.
        self.astichi_scope_trusts_stack: list[frozenset[str]] = [
            module_trust_declarations
        ]
        # Imported-name origin is stable for a given Astichi scope, so
        # repeated reads of the same imported name in that scope can
        # reuse one ancestor-resolution result.
        self.import_origin_scope_cache: dict[tuple[ScopeId, str], ScopeId] = {}
        self.python_bindings = _ScopeBindingCollector().bindings_by_scope
        self.python_scope_bindings: dict[int, frozenset[str]] = {}
        self.python_scope_stack: list[frozenset[str]] = []
        self.python_parameter_bindings: dict[int, frozenset[str]] = {}
        self.python_parameter_stack: list[frozenset[str]] = []
        self.python_scope_owner_stack: list[ScopeId] = []
        self.occurrences: list[LexicalOccurrence] = []
        self.ordinal_counter = count()

    def visit(self, node: ast.AST) -> object:
        if not self.python_scope_bindings:
            collector = _ScopeBindingCollector()
            collector.visit(node)
            self.python_scope_bindings = collector.bindings_by_scope
            self.python_parameter_bindings = collector.parameter_bindings_by_scope
        return super().visit(node)

    def visit_Module(self, node: ast.Module) -> None:
        self._visit_python_scope(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_python_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_python_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_python_scope(node)

    def visit_Name(self, node: ast.Name) -> None:
        if id(node) in self.ignored_name_nodes:
            return
        imported = self._current_imported_names()
        if node.id in imported:
            # Issue 006 6c (inheritance / trust model): an import is an
            # alias-through to an enclosing Astichi scope's binding.
            # When the enclosing binding is trust-declared (keep /
            # pass) the import inherits that trust: we classify the
            # occurrence as `preserved` in the *local* scope so the
            # inheritance scan keeps the literal name intact through
            # rename. Untrusted imports default to the surrounding
            # Astichi scope's binding so same-root splices unify on a
            # single rename target and sibling roots rename apart. If
            # an ancestor scope also imports the same name, keep
            # walking outward until we reach the first non-importing
            # Astichi scope; imported chains are alias-through, not a
            # sequence of fresh intermediate bindings.
            binding_kind: BindingKind = (
                "reference" if isinstance(node.ctx, ast.Load) else "binding"
            )
            if node.id in self.trust_names:
                role: LexicalRole = "preserved"
                scope_id = self._current_scope()
            else:
                role = "internal"
                scope_id = self._import_origin_scope(node.id)
        elif isinstance(node.ctx, ast.Load):
            role = self._load_role(node.id)
            binding_kind = "reference"
            scope_id = (
                self._outer_scope() if role == "external" else self._current_scope()
            )
        else:
            # Issue 006 6c: a Store is `preserved` only when the
            # *current* Astichi scope explicitly declares trust on the
            # name (via ``astichi_keep`` / ``astichi_pass`` at that
            # scope's top). A global trust entry alone is not enough —
            # an inner shell that happens to bind the same spelling
            # without its own keep/pass is a fresh binding and must
            # stay `internal` so rename can separate it from the
            # trust-declaring scope.
            if node.id in self._current_trust_declarations():
                role = "preserved"
            else:
                role = "internal"
            binding_kind = "binding"
            scope_id = self._current_scope()
        self.occurrences.append(
            LexicalOccurrence(
                raw_name=node.id,
                scope_id=scope_id,
                collision_domain=self._current_collision_domain(),
                role=role,
                binding_kind=binding_kind,
                ordinal=next(self.ordinal_counter),
                node=node,
            )
        )

    def visit_arg(self, node: ast.arg) -> None:
        self.occurrences.append(
            LexicalOccurrence(
                raw_name=node.arg,
                scope_id=self._current_scope(),
                collision_domain=self._current_collision_domain(),
                role="internal",
                binding_kind="binding",
                ordinal=next(self.ordinal_counter),
                node=node,
            )
        )

    def _visit_python_scope(
        self,
        node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> None:
        bindings = self.python_scope_bindings.get(id(node), frozenset())
        parameter_bindings = self.python_parameter_bindings.get(
            id(node), frozenset()
        )
        self.python_scope_stack.append(bindings)
        self.python_parameter_stack.append(parameter_bindings)
        pushed_fresh = self._push_fresh_scope_if_needed(node)
        self.python_scope_owner_stack.append(self._current_scope())
        pushed_collision_domain = self._push_function_collision_domain_if_needed(node)
        try:
            self.generic_visit(node)
        finally:
            if pushed_collision_domain:
                self.collision_domain_stack.pop()
            if pushed_fresh:
                self.scope_stack.pop()
                self.astichi_scope_bindings_stack.pop()
                self.astichi_scope_imports_stack.pop()
                self.astichi_scope_trusts_stack.pop()
            self.python_scope_stack.pop()
            self.python_parameter_stack.pop()
            self.python_scope_owner_stack.pop()

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            super().generic_visit(node)
            return
        pushed_fresh = self._push_fresh_scope_if_needed(node)
        try:
            super().generic_visit(node)
        finally:
            if pushed_fresh:
                self.scope_stack.pop()
                self.astichi_scope_bindings_stack.pop()
                self.astichi_scope_imports_stack.pop()
                self.astichi_scope_trusts_stack.pop()

    def _push_fresh_scope_if_needed(self, node: ast.AST) -> bool:
        if id(node) not in self.fresh_scope_node_ids:
            return False
        self.scope_stack.append(ScopeId(next(self.scope_counter)))
        local = self.fresh_scope_local_bindings.get(id(node))
        self.astichi_scope_bindings_stack.append(local)
        imported = self.fresh_scope_imported_names.get(id(node), frozenset())
        self.astichi_scope_imports_stack.append(imported)
        trusts = self.fresh_scope_trust_declarations.get(id(node), frozenset())
        self.astichi_scope_trusts_stack.append(trusts)
        return True

    def _push_function_collision_domain_if_needed(self, node: ast.AST) -> bool:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        if _has_insert_decorator(node.decorator_list):
            return False
        self.collision_domain_stack.append(next(self.collision_domain_counter))
        return True

    def _current_scope(self) -> ScopeId:
        return self.scope_stack[-1]

    def _current_collision_domain(self) -> int:
        return self.collision_domain_stack[-1]

    def _outer_scope(self) -> ScopeId:
        if len(self.scope_stack) >= 2:
            return self.scope_stack[-2]
        return self.scope_stack[-1]

    def _import_origin_scope(self, raw_name: str) -> ScopeId:
        """Resolve the owning Astichi scope for an imported name.

        The current scope already imports ``raw_name``. Walk outward
        across ancestor Astichi scopes that also import the same name,
        and return the first enclosing Astichi scope that does *not*
        import it. That outer scope owns the binding that every import
        in the chain aliases through.
        """
        cache_key = (self._current_scope(), raw_name)
        cached = self.import_origin_scope_cache.get(cache_key)
        if cached is not None:
            return cached

        scope_index = len(self.scope_stack) - 1
        while scope_index > 1:
            parent_index = scope_index - 1
            if parent_index < 2:
                result = self.scope_stack[parent_index]
                self.import_origin_scope_cache[cache_key] = result
                return result
            imported_names = self.astichi_scope_imports_stack[parent_index - 2]
            if raw_name not in imported_names:
                result = self.scope_stack[parent_index]
                self.import_origin_scope_cache[cache_key] = result
                return result
            scope_index = parent_index
        result = self.scope_stack[1]
        self.import_origin_scope_cache[cache_key] = result
        return result

    def _current_python_bindings(self) -> frozenset[str]:
        if not self.python_scope_stack:
            return frozenset()
        return self.python_scope_stack[-1]

    def _current_python_parameters(self) -> frozenset[str]:
        if not self.python_parameter_stack:
            return frozenset()
        return self.python_parameter_stack[-1]

    def _current_python_scope_owner(self) -> ScopeId:
        if not self.python_scope_owner_stack:
            return self._current_scope()
        return self.python_scope_owner_stack[-1]

    def _current_astichi_bindings(self) -> frozenset[str] | None:
        for local in reversed(self.astichi_scope_bindings_stack):
            if local is not None:
                return local
        return None

    def _current_imported_names(self) -> frozenset[str]:
        if not self.astichi_scope_imports_stack:
            return frozenset()
        return self.astichi_scope_imports_stack[-1]

    def _current_trust_declarations(self) -> frozenset[str]:
        if not self.astichi_scope_trusts_stack:
            return frozenset()
        return self.astichi_scope_trusts_stack[-1]

    def _inside_fresh_scope(self) -> bool:
        return len(self.scope_stack) > 2

    def _load_role(self, raw_name: str) -> LexicalRole:
        astichi_local = self._current_astichi_bindings()
        if astichi_local is not None and raw_name in astichi_local:
            return "internal"
        if self._inside_fresh_scope():
            # ``astichi_insert`` creates the default isolation boundary:
            # unwired free names stay local to the inserted composable
            # instead of implicitly capturing from the enclosing Python
            # scope. Function parameters are the exception; they are
            # stable bindings of the enclosing function and remain
            # visible within inserted children of that function body.
            if raw_name in self._current_python_bindings():
                return "internal"
            if raw_name in self._current_python_parameters():
                if self._current_scope() == self._current_python_scope_owner():
                    return "internal"
                return "external"
            if raw_name in self.preserved_names:
                return "preserved"
            if raw_name in self.external_names:
                return "external"
            return "internal"
        if raw_name in self._current_python_bindings():
            return "internal"
        if raw_name in self.preserved_names:
            return "preserved"
        if raw_name in self.external_names:
            return "external"
        return "external"


class _Renamer(ast.NodeTransformer):
    def __init__(self, preserved: frozenset[str]) -> None:
        self._preserved = preserved
        self._counter = 0
        self._scopes: list[dict[str, str]] = []

    def visit_Module(self, node: ast.Module) -> ast.AST:
        return self._visit_scope(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if node.name in self._preserved:
            node.name = self._fresh(node.name)
        return self._visit_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        if node.name in self._preserved:
            node.name = self._fresh(node.name)
        return self._visit_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        if node.name in self._preserved:
            node.name = self._fresh(node.name)
        return self._visit_scope(node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        if node.arg in self._preserved:
            replacement = self._fresh(node.arg)
            self._current_scope()[node.arg] = replacement
            node.arg = replacement
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if isinstance(node.ctx, (ast.Store, ast.Del)) and node.id in self._preserved:
            replacement = self._scope_lookup(node.id)
            if replacement is None:
                replacement = self._fresh(node.id)
                self._current_scope()[node.id] = replacement
            node.id = replacement
            return node

        replacement = self._scope_lookup(node.id)
        if replacement is not None:
            node.id = replacement
        return node

    def _visit_scope(
        self,
        node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> ast.AST:
        self._scopes.append({})
        try:
            return self.generic_visit(node)
        finally:
            self._scopes.pop()

    def _current_scope(self) -> dict[str, str]:
        return self._scopes[-1]

    def _scope_lookup(self, name: str) -> str | None:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        return None

    def _fresh(self, name: str) -> str:
        self._counter += 1
        return f"__astichi_local_{name}_{self._counter}"
