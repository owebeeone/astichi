"""Generate a dict-backed lambda wrapper and an attribute-backed wrapper.

Compiles::

    def generate_dict(function):
        return lambda ctxt: function(a=ctxt['a'], b=ctxt['b'], c=ctxt['c'])

    def call_attr(function, cls_ctx):
        return function(a=cls_ctx.a, b=cls_ctx.b, c=cls_ctx.c)

The dict-backed wrapper uses ordinary subscription syntax inside
``astichi_funcargs(...)``. The attribute-backed wrapper uses
``astichi_ref(external=path_name)`` so an edge-bound compile-time path such as
``"cls_ctx.a"`` lowers into a real attribute chain during materialize.

Both wrappers are built from shared payload instances wired into the same hole
multiple times. Per-edge identifier resolution (``field`` -> ``a``/``b``/``c``)
and compile-time binds are supplied on the target-adder edge via
``arg_names={...}`` and ``bind={...}``.
"""


from typing import Callable
from types import SimpleNamespace


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
            def generate_dict(function):
                return lambda ctxt: function(astichi_hole(dict_kwargs))

            def call_attr(function, cls_ctx):
                return function(astichi_hole(attr_kwargs))
            """
        )
    )
    dict_arg_composable = piece(
        """
        astichi_funcargs(
            field__astichi_arg__=astichi_pass(ctxt, outer_bind=True)[
                astichi_bind_external(field_key)
            ],
        )
        """
    )
    attr_arg_composable = piece(
        """
        astichi_funcargs(
            field__astichi_arg__=astichi_ref(external=path_name),
            _=astichi_import(cls_ctx),
        )
        """
    )

    for order, field in enumerate(("a", "b", "c")):
        builder.add.DictKw[order](dict_arg_composable)
        builder.Root.dict_kwargs.add.DictKw[order](
            order=order,
            arg_names={"field": field},
            bind={"field_key": field},
        )
        builder.add.AttrKw[order](attr_arg_composable)
        builder.Root.attr_kwargs.add.AttrKw[order](
            order=order,
            arg_names={"field": field},
            bind={"path_name": f"cls_ctx.{field}"},
        )

    source_tree = builder.build().materialize().tree

    namespace: dict[str, object] = {}
    exec(compile(source_tree, "<lambda_kwarg_wrapper>", "exec"), namespace)

    def func(b: int, c: int, a: int) -> tuple[int, int, int]:
        return (a, b, c)

    generate_dict: Callable[
        [Callable[[int, int, int], tuple[int, int, int]]],
        Callable[[dict[str, int]], tuple[int, int, int]],
    ] = namespace["generate_dict"]  # pyright: ignore[reportAssignmentType]
    call_attr: Callable[
        [Callable[[int, int, int], tuple[int, int, int]], object],
        tuple[int, int, int],
    ] = namespace["call_attr"]  # pyright: ignore[reportAssignmentType]
    dict_wrapper = generate_dict(func)
    assert dict_wrapper({"a": 1, "b": 2, "c": 3}) == (1, 2, 3)
    assert call_attr(func, SimpleNamespace(a=1, b=2, c=3)) == (1, 2, 3)

    return ast.unparse(source_tree)
