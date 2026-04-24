"""Register indexed builder instances and wire a specific family member later.

`builder.add.Step[i](...)` creates distinct source instances under one family
stem. `builder.Root.body.add.Step[i](...)` picks which family member to insert,
and `builder.Step[2].extra.add.Helper(...)` reaches back into one specific
member after registration.
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

    builder.add.Step[0](
        piece(
            """
            result.append("step-0")
            """
        )
    )
    builder.add.Step[1](
        piece(
            """
            result.append("step-1")
            """
        )
    )
    builder.add.Step[2](
        piece(
            """
            result.append("step-2")
            astichi_hole(extra)
            """
        )
    )
    builder.add.Step[3](
        piece(
            """
            result.append("step-3")
            """
        )
    )
    builder.add.Helper(
        piece(
            """
            astichi_pass(result, outer_bind=True).append("step-2-extra")
            """
        )
    )

    builder.Root.body.add.Step[0](order=0)
    builder.Root.body.add.Step[1](order=1)
    builder.Root.body.add.Step[2](order=2)
    builder.Root.body.add.Step[3](order=3)
    builder.Step[2].extra.add.Helper(order=0)
    return ast.unparse(builder.build().materialize().tree)
