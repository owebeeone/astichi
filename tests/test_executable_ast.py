from __future__ import annotations

import ast
from collections.abc import Callable

import astichi
from astichi.model import BasicComposable


def _exec_source(composable: BasicComposable) -> dict[str, object]:
    namespace: dict[str, object] = {}
    source = composable.materialize().emit(provenance=False)
    exec(compile(source, "<astichi-source>", "exec"), namespace)  # noqa: S102
    return namespace


def _exec_ast(composable: BasicComposable) -> dict[str, object]:
    namespace: dict[str, object] = {}
    tree = composable.to_executable_ast()
    exec(compile(tree, "<astichi-ast>", "exec"), namespace)  # noqa: S102
    return namespace


def _block_case() -> BasicComposable:
    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(body)\n"))
    builder.add.Body(astichi.compile("value = 40\nanswer = value + 2\n"))
    builder.Root.body.add.Body()
    return builder.build()


def _expression_case() -> BasicComposable:
    builder = astichi.build()
    builder.add.Root(astichi.compile("answer = astichi_hole(value)\n"))
    builder.add.Value(astichi.compile("40 + 2\n"))
    builder.Root.value.add.Value()
    return builder.build()


def _funcargs_case() -> BasicComposable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def call(*args, **kwargs):
    return args, kwargs

result = call(*astichi_hole(args), **astichi_hole(kwargs))
"""
        )
    )
    builder.add.Args(astichi.compile("astichi_funcargs(1, 2)\n"))
    builder.add.Kwargs(astichi.compile('astichi_funcargs(name="Ada")\n'))
    builder.Root.args.add.Args()
    builder.Root.kwargs.add.Kwargs()
    return builder.build()


def _params_case() -> BasicComposable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    return value
"""
        )
    )
    builder.add.Params(
        astichi.compile(
            """
def astichi_params(value=42):
    pass
"""
        )
    )
    builder.Root.params.add.Params()
    return builder.build()


def _pyimport_case() -> BasicComposable:
    return astichi.compile(
        """
astichi_pyimport(module=math, names=(sqrt,))
answer = sqrt(81)
"""
    )


def _comment_case() -> BasicComposable:
    return astichi.compile('astichi_comment("generated")\nanswer = 42\n')


def _answer(namespace: dict[str, object]) -> object:
    return namespace["answer"]


def _result(namespace: dict[str, object]) -> object:
    return namespace["result"]


def _run_default(namespace: dict[str, object]) -> object:
    return namespace["run"]()


def test_to_executable_ast_matches_emitted_source_runtime() -> None:
    cases: tuple[tuple[Callable[[], BasicComposable], Callable[[dict[str, object]], object]], ...] = (
        (_block_case, _answer),
        (_expression_case, _answer),
        (_funcargs_case, _result),
        (_params_case, _run_default),
        (_pyimport_case, _answer),
        (_comment_case, _answer),
    )

    for factory, probe in cases:
        composable = factory()

        assert probe(_exec_ast(composable)) == probe(_exec_source(composable))


def test_to_executable_ast_returns_caller_owned_tree() -> None:
    composable = astichi.compile("answer = 42\n")
    first = composable.to_executable_ast()
    assign = first.body[0]
    assert isinstance(assign, ast.Assign)
    assign.value = ast.Constant(value=0)
    ast.fix_missing_locations(first)

    mutated_namespace: dict[str, object] = {}
    exec(compile(first, "<mutated>", "exec"), mutated_namespace)  # noqa: S102
    assert mutated_namespace["answer"] == 0

    second_namespace = _exec_ast(composable)
    assert second_namespace["answer"] == 42


def test_emit_commented_remains_source_text_surface() -> None:
    composable = _comment_case()

    assert composable.emit_commented() == "# generated\nanswer = 42\n"
    assert _exec_ast(composable)["answer"] == 42
