"""Build the same additive graph from ordinary data records.

The named builder API is the data-driven equivalent of the fluent surface:
``builder.add("Root", root)`` mirrors ``builder.add.Root(root)`` and
``builder.instance("Root").target("body").add("Step")`` mirrors
``builder.Root.body.add.Step()``.
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
    builder.add(
        "Root",
        piece(
            """
            result = []
            astichi_hole(body)
            final = tuple(result)
            """
        ),
    )

    step_specs = (
        {"name": "First", "label": "first", "order": 0},
        {"name": "Second", "label": "second", "order": 1},
    )
    for spec in step_specs:
        builder.add(
            spec["name"],
            piece(
                f"""
                astichi_pass(result, outer_bind=True).append({spec["label"]!r})
                """
            ),
        )

    for spec in step_specs:
        builder.instance("Root").target("body").add(
            spec["name"],
            order=spec["order"],
        )

    return ast.unparse(builder.build().materialize().tree)
