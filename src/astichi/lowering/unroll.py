"""Body-copy unroll engine for `astichi_for` loops.

`unroll_tree(tree)` returns a deep copy of `tree` in which every
`astichi_for` loop has been expanded in place: the loop body is duplicated
once per iteration, loop-variable `Load` references are substituted with
the iteration's literal value, and `astichi_hole(target)` markers inside
each copy are renamed to `target__iter_<i>[_<j>...]`.

Unrolling is macro expansion, not scope introduction: copies share the
enclosing scope (`UnrollRevision.md` §6). Nested loops unroll outer-first
so the outer iteration value is substituted into the inner domain before
the inner domain is resolved (`UnrollRevision.md` §5.4).

Rejects at unroll time:
- non-literal domain (bubbled from `resolve_domain`)
- same-scope rebinding of a loop variable via plain assignment, augmented
  assignment, annotated assignment, or walrus at the top level of the
  loop body (`UnrollRevision.md` §5.3)
- a name-bearing marker whose identifier argument is a loop variable
  (`UnrollRevision.md` §5.5)
- port-creating or binding name-bearing markers inside a loop body
  (`UnrollRevision.md` §4.3): `astichi_export`, `astichi_bind_external`,
  `astichi_bind_once`, `astichi_bind_shared`, `astichi_insert`. Hygiene
  directives (`astichi_keep`, `astichi_definitional_name`) are idempotent
  and permitted.
- `astichi_for` loops with an `else` clause (V2 reserves the shape)
"""

from __future__ import annotations

import ast
import copy
import re
from typing import Iterable

from astichi.lowering.markers import FOR, MARKERS_BY_NAME
from astichi.lowering.unroll_domain import DomainValue, resolve_domain

__all__ = ["unroll_tree", "iter_target_name"]

_ITER_SUFFIX_RE = re.compile(r"__iter_\d+(?:_\d+)*$")


def unroll_tree(tree: ast.AST) -> ast.AST:
    """Unroll every `astichi_for` loop in `tree` and return the result.

    The input tree is not modified; a deep copy is transformed and
    returned. If no `astichi_for` loops are present the returned tree is
    structurally equivalent to the input.
    """
    new_tree = copy.deepcopy(tree)
    new_tree = _UnrollTransformer().visit(new_tree)
    ast.fix_missing_locations(new_tree)
    return new_tree


class _UnrollTransformer(ast.NodeTransformer):
    def visit_For(self, node: ast.For) -> ast.AST | list[ast.stmt]:
        if not _is_astichi_for_iter(node.iter):
            self.generic_visit(node)
            return node
        if node.orelse:
            raise ValueError(
                "astichi_for loops may not have an `else` clause"
            )
        return self._expand(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.AST:
        if _is_astichi_for_iter(node.iter):
            raise ValueError(
                "astichi_for may not be used with `async for`"
            )
        self.generic_visit(node)
        return node

    def _expand(self, node: ast.For) -> list[ast.stmt]:
        assert isinstance(node.iter, ast.Call)
        if len(node.iter.args) != 1 or node.iter.keywords:
            raise ValueError(
                "astichi_for takes exactly one positional argument (the domain)"
            )
        domain = resolve_domain(node.iter.args[0])
        loop_vars = _collect_target_names(node.target)
        _BodyValidator(loop_vars).run(node.body)

        out: list[ast.stmt] = []
        for i, value in enumerate(domain):
            binding = _bind_target(node.target, value)
            copied = [copy.deepcopy(s) for s in node.body]
            _SubstituteAndRename(binding, i).run(copied)
            for stmt in copied:
                result = self.visit(stmt)
                if isinstance(result, list):
                    out.extend(result)
                else:
                    out.append(result)
        return out


def _is_astichi_for_iter(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == FOR.source_name
    )


def _collect_target_names(target: ast.expr) -> set[str]:
    names: set[str] = set()
    _collect_into(target, names)
    return names


def _collect_into(target: ast.expr, names: set[str]) -> None:
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _collect_into(elt, names)
    elif isinstance(target, ast.Starred):
        _collect_into(target.value, names)
    else:
        raise ValueError(
            f"astichi_for target must be a name or tuple of names; "
            f"got {type(target).__name__}"
        )


def _bind_target(target: ast.expr, value: DomainValue) -> dict[str, DomainValue]:
    bindings: dict[str, DomainValue] = {}
    _bind_into(target, value, bindings)
    return bindings


def _bind_into(
    target: ast.expr, value: DomainValue, bindings: dict[str, DomainValue]
) -> None:
    if isinstance(target, ast.Name):
        bindings[target.id] = value
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        if not isinstance(value, tuple):
            raise ValueError(
                f"astichi_for target {ast.unparse(target)} expects a tuple "
                f"per iteration, got {value!r}"
            )
        if len(value) != len(target.elts):
            raise ValueError(
                f"astichi_for target arity {len(target.elts)} does not match "
                f"iteration arity {len(value)} (value={value!r})"
            )
        for elt, v in zip(target.elts, value):
            _bind_into(elt, v, bindings)
        return
    raise ValueError(
        f"astichi_for target must be a name or tuple of names; "
        f"got {type(target).__name__}"
    )


class _BodyValidator(ast.NodeVisitor):
    """Reject disallowed shapes inside an astichi_for loop body.

    - top-level rebind (Assign/AugAssign/AnnAssign/NamedExpr) of a loop
      variable (`UnrollRevision.md` §5.3)
    - any non-`astichi_hole` name-bearing marker (`§4.3`)
    - any name-bearing marker whose identifier argument is a loop var
      (`§5.5`)
    """

    def __init__(self, loop_vars: set[str]) -> None:
        self._loop_vars = loop_vars
        self._depth = 0  # 0 == same scope as the astichi_for
        self._errors: list[str] = []

    def run(self, body: list[ast.stmt]) -> None:
        for stmt in body:
            self.visit(stmt)
        if self._errors:
            raise ValueError("; ".join(self._errors))

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._depth == 0:
            for t in node.targets:
                self._flag_rebind(t)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if self._depth == 0:
            self._flag_rebind(node.target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._depth == 0:
            self._flag_rebind(node.target)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        if self._depth == 0:
            self._flag_rebind(node.target)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_like(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_like(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        self._depth += 1
        self.visit(node.body)
        self._depth -= 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for dec in node.decorator_list:
            self.visit(dec)
        for base in node.bases:
            self.visit(base)
        for kw in node.keywords:
            self.visit(kw)
        self._depth += 1
        for stmt in node.body:
            self.visit(stmt)
        self._depth -= 1

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            marker = MARKERS_BY_NAME.get(node.func.id)
            if marker is not None and marker.is_name_bearing():
                if not marker.is_permitted_in_unroll_body():
                    self._errors.append(
                        f"{marker.source_name}(...) is not allowed inside an "
                        f"astichi_for body"
                    )
                elif node.args:
                    first = node.args[0]
                    if (
                        isinstance(first, ast.Name)
                        and first.id in self._loop_vars
                    ):
                        self._errors.append(
                            f"{marker.source_name} may not use loop variable "
                            f"{first.id!r} as its name argument"
                        )
        self.generic_visit(node)

    def _visit_function_like(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        for dec in node.decorator_list:
            self.visit(dec)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        self._depth += 1
        if node.returns is not None:
            self.visit(node.returns)
        for arg in (*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs):
            if arg.annotation is not None:
                self.visit(arg.annotation)
        for stmt in node.body:
            self.visit(stmt)
        self._depth -= 1

    def _visit_comprehension(self, node: ast.expr) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def _flag_rebind(self, target: ast.expr) -> None:
        names: set[str] = set()
        try:
            _collect_into(target, names)
        except ValueError:
            # Non-name targets (attribute/subscript) can't rebind a loop var.
            return
        for name in names & self._loop_vars:
            self._errors.append(
                f"astichi_for loop variable {name!r} may not be rebound in "
                f"the same scope"
            )


class _SubstituteAndRename(ast.NodeTransformer):
    """Substitute loop-variable `Load` references with literal values and
    rename `astichi_hole(name)` arguments per iteration.

    Scope-aware: substitution halts at function, lambda, class, and
    comprehension boundaries, and at inner loops whose target re-binds a
    loop variable.
    """

    def __init__(
        self, binding: dict[str, DomainValue], iter_index: int
    ) -> None:
        super().__init__()
        self._binding = binding
        self._iter_index = iter_index
        # Stack of sets of loop-var names currently shadowed by inner scopes.
        self._shadow_stack: list[frozenset[str]] = []

    def run(self, body: list[ast.stmt]) -> None:
        for i, stmt in enumerate(body):
            body[i] = self.visit(stmt)  # type: ignore[assignment]

    # ---- Name / hole rewriting ------------------------------------------

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if isinstance(node.ctx, ast.Load) and node.id in self._active:
            return _literal_node(self._binding[node.id])
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name):
            marker = MARKERS_BY_NAME.get(node.func.id)
            if marker is not None and marker.is_renamed_per_iteration():
                idx = marker.iter_rename_arg_index()
                if idx < len(node.args) and isinstance(node.args[idx], ast.Name):
                    node.args[idx].id = _append_iter_suffix(
                        node.args[idx].id, self._iter_index
                    )
        return node

    # ---- Scope boundaries -----------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._visit_function_like(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._visit_function_like(node)

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        for i, default in enumerate(node.args.defaults):
            node.args.defaults[i] = self.visit(default)
        for i, default in enumerate(node.args.kw_defaults):
            if default is not None:
                node.args.kw_defaults[i] = self.visit(default)
        shadow = _params_shadowing(node.args, self._binding)
        self._push(shadow)
        node.body = self.visit(node.body)
        self._pop()
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        for i, dec in enumerate(node.decorator_list):
            node.decorator_list[i] = self.visit(dec)
        for i, base in enumerate(node.bases):
            node.bases[i] = self.visit(base)
        for kw in node.keywords:
            kw.value = self.visit(kw.value)
        # Class body is a separate scope for name resolution; treat all
        # loop vars as shadowed inside it to match Python semantics.
        self._push(frozenset(self._binding))
        for i, stmt in enumerate(node.body):
            node.body[i] = self.visit(stmt)
        self._pop()
        return node

    def visit_ListComp(self, node: ast.ListComp) -> ast.AST:
        return self._visit_comprehension(node)

    def visit_SetComp(self, node: ast.SetComp) -> ast.AST:
        return self._visit_comprehension(node)

    def visit_DictComp(self, node: ast.DictComp) -> ast.AST:
        return self._visit_comprehension(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> ast.AST:
        return self._visit_comprehension(node)

    def visit_For(self, node: ast.For) -> ast.AST:
        # Iter runs in the enclosing scope.
        node.iter = self.visit(node.iter)
        shadow = _names_shadowing(node.target, self._binding)
        self._push(shadow)
        for i, stmt in enumerate(node.body):
            node.body[i] = self.visit(stmt)
        self._pop()
        for i, stmt in enumerate(node.orelse):
            node.orelse[i] = self.visit(stmt)
        return node

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.AST:
        node.iter = self.visit(node.iter)
        shadow = _names_shadowing(node.target, self._binding)
        self._push(shadow)
        for i, stmt in enumerate(node.body):
            node.body[i] = self.visit(stmt)
        self._pop()
        for i, stmt in enumerate(node.orelse):
            node.orelse[i] = self.visit(stmt)
        return node

    # ---- helpers --------------------------------------------------------

    def _visit_function_like(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.AST:
        for i, dec in enumerate(node.decorator_list):
            node.decorator_list[i] = self.visit(dec)
        for i, default in enumerate(node.args.defaults):
            node.args.defaults[i] = self.visit(default)
        for i, default in enumerate(node.args.kw_defaults):
            if default is not None:
                node.args.kw_defaults[i] = self.visit(default)
        if node.returns is not None:
            node.returns = self.visit(node.returns)
        shadow = _params_shadowing(node.args, self._binding)
        self._push(shadow)
        for arg in (*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs):
            if arg.annotation is not None:
                arg.annotation = self.visit(arg.annotation)
        for i, stmt in enumerate(node.body):
            node.body[i] = self.visit(stmt)
        self._pop()
        return node

    def _visit_comprehension(self, node: ast.expr) -> ast.AST:
        # A comprehension's leading iter expression evaluates in the enclosing
        # scope; everything else (targets, conditions, element) in a nested one.
        generators: list[ast.comprehension] = node.generators  # type: ignore[attr-defined]
        if generators:
            generators[0].iter = self.visit(generators[0].iter)
        shadow: set[str] = set()
        for gen in generators:
            shadow |= _collect_target_names(gen.target)
        self._push(frozenset(shadow & set(self._binding)))
        for gen in generators[1:]:
            gen.iter = self.visit(gen.iter)
        for gen in generators:
            for i, test in enumerate(gen.ifs):
                gen.ifs[i] = self.visit(test)
        if isinstance(node, ast.DictComp):
            node.key = self.visit(node.key)
            node.value = self.visit(node.value)
        else:
            node.elt = self.visit(node.elt)  # type: ignore[attr-defined]
        self._pop()
        return node

    @property
    def _active(self) -> set[str]:
        shadowed: set[str] = set()
        for frame in self._shadow_stack:
            shadowed |= frame
        return set(self._binding) - shadowed

    def _push(self, shadow: frozenset[str]) -> None:
        self._shadow_stack.append(shadow)

    def _pop(self) -> None:
        self._shadow_stack.pop()


def _params_shadowing(
    args: ast.arguments, binding: dict[str, DomainValue]
) -> frozenset[str]:
    names = {
        a.arg
        for a in (*args.args, *args.kwonlyargs, *args.posonlyargs)
    }
    if args.vararg is not None:
        names.add(args.vararg.arg)
    if args.kwarg is not None:
        names.add(args.kwarg.arg)
    return frozenset(names & set(binding))


def _names_shadowing(
    target: ast.expr, binding: dict[str, DomainValue]
) -> frozenset[str]:
    return frozenset(_collect_target_names(target) & set(binding))


def _literal_node(value: DomainValue) -> ast.expr:
    if isinstance(value, tuple):
        return ast.Tuple(
            elts=[_literal_node(v) for v in value], ctx=ast.Load()
        )
    return ast.Constant(value=value)


def _append_iter_suffix(name: str, index: int) -> str:
    if _ITER_SUFFIX_RE.search(name):
        return f"{name}_{index}"
    return f"{name}__iter_{index}"


def iter_target_name(base: str, path: Iterable[int]) -> str:
    """Return the post-unroll synthetic target name for a given path.

    For a target referenced as `A.slot[i][j]` by the builder, the matching
    `astichi_hole` site inside A's unrolled tree is `slot__iter_<i>_<j>`.
    This helper applies the same suffix convention used by the unroll
    pass (see `__iter_<i>` / `__iter_<i>_<j>` in UnrollRevision §4.1), so
    the builder and the materializer agree on target names without
    either side duplicating the rule.
    """
    name = base
    for index in path:
        name = _append_iter_suffix(name, index)
    return name
