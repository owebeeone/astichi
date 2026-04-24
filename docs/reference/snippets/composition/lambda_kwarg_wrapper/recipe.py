"""Generate a function-generating lambda wrapper and exec it inside the recipe.

Compiles::

    def generate(function):
        return lambda ctxt: function(a=ctxt['a'], b=ctxt['b'], c=ctxt['c'])

from *one* shared ``Kw`` payload wired into ``Root.kwargs`` three times. The
per-edge identifier resolution (``field`` → ``a``/``b``/``c``) and external
value binding (``field_key`` → the matching dict key) are supplied on the
target-adder edge via ``arg_names={...}`` and ``bind={...}`` — the
multi-bind surface that lets a single registered instance fan out to N
distinct kwargs without mutating the registered record.

After materializing, the recipe execs the emitted source, obtains the
``generate`` factory, wraps a target ``func(a, b, c)``, and dispatches
``{"a": 1, "b": 2, "c": 3}`` through it to prove the generated wrapper
works end-to-end. The asserted result is ``(1, 2, 3)``.
"""


from typing import Callable


def run() -> str:
    import ast
    import textwrap

    import astichi
    from astichi import Composable
    from astichi.builder import BuilderHandle

    def piece(src: str) -> Composable:
        return astichi.compile(textwrap.dedent(src).strip() + "\n")

    builder: BuilderHandle = astichi.build()
    builder.add.Root(
        piece(
            """
            def generate(function):
                return lambda ctxt: function(astichi_hole(kwargs))
            """
        )
    )
    arg_composable = piece(
        """
        astichi_funcargs(
            field__astichi_arg__=astichi_pass(ctxt, outer_bind=True)[
                astichi_bind_external(field_key)
            ],
        )
        """
    )

    for order, field in enumerate(("a", "b", "c")):
        builder.add.Kw[order](arg_composable)
        builder.Root.kwargs.add.Kw[order](
            order=order,
            arg_names={"field": field},
            bind={"field_key": field},
        )

    source_tree = builder.build().materialize().tree

    namespace: dict[str, object] = {}
    exec(compile(source_tree, "<lambda_kwarg_wrapper>", "exec"), namespace)

    def func(b: int, c: int, a: int) -> tuple[int, int, int]:
        return (a, b, c)

    generate : Callable[[Callable[[int, int, int], tuple[int, int, int]]], Callable[[dict[str, int]], tuple[int, int, int]]] = namespace["generate"]  # pyright: ignore[reportAssignmentType]
    wrapper = generate(func)
    assert wrapper({"a": 1, "b": 2, "c": 3}) == (1, 2, 3)

    return ast.unparse(source_tree)
