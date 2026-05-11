from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import astichi
from astichi.assembler import (
    AssemblyRunner,
    as_composable,
    as_external_value,
    as_identifier,
)
from astichi.assembler.client import (
    ApplyResource,
    AssemblerClient,
    AssemblyAction,
    AssemblyContext,
    ProducerList,
    ProducerNode,
    ScopeNode,
    ScopeRecipe,
    apply_resource,
    build_child_scope,
    scope_recipe,
)


@dataclass(frozen=True)
class _Node(ScopeNode):
    label: str

    def scope_label(self) -> str:
        return self.label


@dataclass(frozen=True)
class _ProducerNode(ProducerNode):
    label: str

    def producer_label(self) -> str:
        return self.label


@dataclass(frozen=True)
class _Context(AssemblyContext):
    node: _Node

    def scope_node(self) -> ScopeNode:
        return self.node

    def parent_context(self) -> AssemblyContext | None:
        return None

    def lookup_resource(self, name: str):
        return None


@dataclass(frozen=True)
class _BodyProducerList(ProducerList):
    def producer_nodes(self, context: AssemblyContext) -> Iterable[ProducerNode]:
        return (_ProducerNode("body"),)

    def actions_for(
        self,
        node: ProducerNode,
        context: AssemblyContext,
    ) -> Iterable[AssemblyAction]:
        body = astichi.compile("value = astichi_bind_external(default)\n")
        return (
            apply_resource(
                as_composable(body, build_name="Body"),
                name="body",
                build_match=("Root",),
            ),
            apply_resource(
                as_external_value(42),
                name="default",
                build_match=("Root", "Body"),
            ),
        )


@dataclass(frozen=True)
class _Client(AssemblerClient):
    root: _Node = _Node("root")

    def root_nodes(self) -> Iterable[ScopeNode]:
        return (self.root,)

    def context_for_root(self, node: ScopeNode) -> AssemblyContext:
        if not isinstance(node, _Node):
            raise TypeError(type(node).__name__)
        return _Context(node)

    def context_for_child(
        self,
        parent_context: AssemblyContext,
        node: ScopeNode,
    ) -> AssemblyContext:
        raise AssertionError("no child scopes in this test")

    def recipe_for(
        self,
        node: ScopeNode,
        context: AssemblyContext,
    ) -> ScopeRecipe:
        root = astichi.compile(
            """
class class_name__astichi_arg__:
    astichi_hole(body)
"""
        )
        return scope_recipe(
            as_composable(root, build_name="Root"),
            root_actions=(
                apply_resource(
                    as_identifier("Generated"),
                    name="class_name",
                    build_match=("Root",),
                ),
            ),
            producer_lists=(_BodyProducerList(),),
        )


def test_assembly_runner_builds_client_scope() -> None:
    result = AssemblyRunner(_Client()).build_roots()[0].materialize()
    source = result.emit(provenance=False)

    namespace: dict[str, object] = {}
    exec(source, namespace)

    generated = namespace["Generated"]
    assert generated.value == 42
    assert "astichi_bind_external" not in source


@dataclass(frozen=True)
class _RecursiveContext(AssemblyContext):
    node: _Node
    parent: AssemblyContext | None = None

    def scope_node(self) -> ScopeNode:
        return self.node

    def parent_context(self) -> AssemblyContext | None:
        return self.parent

    def lookup_resource(self, name: str):
        return None


@dataclass(frozen=True)
class _ChildProducerList(ProducerList):
    child: _Node

    def producer_nodes(self, context: AssemblyContext) -> Iterable[ProducerNode]:
        return (_ProducerNode("child"),)

    def actions_for(
        self,
        node: ProducerNode,
        context: AssemblyContext,
    ) -> Iterable[AssemblyAction]:
        return (
            build_child_scope(
                self.child,
                build_name="Child",
                name="body",
                build_match=("Root",),
            ),
        )


@dataclass(frozen=True)
class _RecursiveClient(AssemblerClient):
    parent: _Node = _Node("parent")
    child: _Node = _Node("child")

    def root_nodes(self) -> Iterable[ScopeNode]:
        return (self.parent,)

    def context_for_root(self, node: ScopeNode) -> AssemblyContext:
        if not isinstance(node, _Node):
            raise TypeError(type(node).__name__)
        return _RecursiveContext(node)

    def context_for_child(
        self,
        parent_context: AssemblyContext,
        node: ScopeNode,
    ) -> AssemblyContext:
        if not isinstance(node, _Node):
            raise TypeError(type(node).__name__)
        return _RecursiveContext(node, parent=parent_context)

    def recipe_for(
        self,
        node: ScopeNode,
        context: AssemblyContext,
    ) -> ScopeRecipe:
        if node == self.parent:
            parent = astichi.compile("astichi_hole(body)\n")
            return scope_recipe(
                as_composable(parent, build_name="Root"),
                producer_lists=(_ChildProducerList(self.child),),
            )
        if node == self.child:
            child = astichi.compile("answer = astichi_bind_external(value)\n")
            return scope_recipe(
                as_composable(child, build_name="Root"),
                root_actions=(
                    apply_resource(
                        as_external_value(7),
                        name="value",
                        build_match=("Root",),
                    ),
                ),
            )
        raise TypeError(type(node).__name__)


def test_assembly_runner_builds_child_scope_actions_recursively() -> None:
    result = AssemblyRunner(_RecursiveClient()).build_roots()[0].materialize()
    namespace: dict[str, object] = {}

    exec(result.emit(provenance=False), namespace)

    assert namespace["answer"] == 7
