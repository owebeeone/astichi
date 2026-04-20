"""External seed via ``astichi_bind_external(seed)`` inside ``astichi_funcargs``, supplied
through ``.bind(seed=…)`` on the merged composable before ``materialize()``.

Here the bind site lives in the ``**`` hole: a **dict unpack**
``astichi_funcargs(**{"seed": astichi_bind_external(seed)})`` merges into the call’s
keyword mapping. The ``*`` hole still uses repeated adds for ordinary positionals.

The call uses one ``*`` hole and one ``**`` hole, plus authored ``fixed=1``.
"""

def run() -> str:
    import ast
    import textwrap

    import astichi
    from astichi.builder import BuilderHandle
    from astichi import Composable

    def piece(src: str) -> Composable:
        return astichi.compile(textwrap.dedent(src).strip() + "\n")

    builder: BuilderHandle = astichi.build()
    builder.add.Root(
        piece(
            """
            def func(*args, **kwds):
                return (args, kwds)

            result = func(*astichi_hole(varargs), fixed=1, **astichi_hole(kwargs))
            """
        )
    )
    # *varargs: repeated positional payloads only.
    builder.add.ExtraPos(
        piece(
            """
            astichi_funcargs(2)
            """
        )
    )
    builder.Root.varargs.add.ExtraPos(order=0)

    # **kwargs: dict unpack supplies bound seed; then plain keyword fragments.
    builder.add.SeedDict(
        piece(
            """
            astichi_funcargs(**{'seed': astichi_bind_external(seed)})
            """
        )
    )
    builder.add.KwName(
        piece(
            """
            astichi_funcargs(name="x")
            """
        )
    )
    builder.add.KwFlag(
        piece(
            """
            astichi_funcargs(flag=True)
            """
        )
    )
    builder.Root.kwargs.add.SeedDict(order=0)
    builder.Root.kwargs.add.KwName(order=1)
    builder.Root.kwargs.add.KwFlag(order=2)

    merged = builder.build()
    return ast.unparse(merged.bind(seed=10).materialize().tree)
