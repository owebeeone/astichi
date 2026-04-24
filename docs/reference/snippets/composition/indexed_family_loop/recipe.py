"""Register an indexed ``Step`` family via a ``for`` loop and wire each in order.

A loop-based simplification of ``indexed_instance_family/``: three
``Step[i]`` instances are registered and wired with the same shape. The
per-step label is declared as ``astichi_bind_external(label)`` on the shared
``Step`` source and supplied per instance via ``.bind(label=...)`` at
registration, so one compiled payload serves every iteration.

See ``indexed_instance_family/`` for the hand-written N=4 variant with an
inner hole on ``Step[2]`` and a later ``builder.Step[2].extra.add.Helper``
reach-in.
"""


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
            result = []
            astichi_hole(body)
            final = tuple(result)
            """
        )
    )

    step_composable = piece("""
    astichi_pass(result, outer_bind=True).append(astichi_bind_external(label))
    """)

    for i in range(3):
        builder.add.Step[i](step_composable.bind(label=f"step-{i}"))
        builder.Root.body.add.Step[i](order=i)

    return ast.unparse(builder.build().materialize().tree)
