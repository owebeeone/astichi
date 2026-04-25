"""Use named target refs and named assign wiring in a staged graph.

This is the data-driven form for code that would otherwise be written as
``builder.Pipeline.Root.consumers.add.Consumer(...)`` and
``builder.assign.Consumer.shared.to().Pipeline.Root.Cell.shared``.
"""


def run() -> str:
    import ast
    import textwrap

    import astichi
    from astichi import Composable
    from astichi.builder import BuilderHandle

    def piece(src: str) -> Composable:
        return astichi.compile(textwrap.dedent(src).strip() + "\n")

    stage1: BuilderHandle = astichi.build()
    stage1.add(
        "Root",
        piece(
            """
            result = []
            astichi_hole(cells)
            astichi_hole(consumers)
            final = tuple(result)
            """
        ),
    )
    stage1.add(
        "Cell",
        piece(
            """
            shared = 10
            astichi_export(shared)
            """
        ),
    )
    stage1.instance("Root").target("cells").add("Cell")
    pipeline = stage1.build()

    stage2: BuilderHandle = astichi.build()
    stage2.add("Pipeline", pipeline)
    stage2.add(
        "Consumer",
        piece(
            """
            astichi_import(shared)
            astichi_pass(result, outer_bind=True).append(shared + 5)
            """
        ),
    )
    stage2.target(
        root_instance="Pipeline",
        ref_path=("Root",),
        target_name="consumers",
    ).add("Consumer")
    stage2.assign(
        source_instance="Consumer",
        inner_name="shared",
        target_instance="Pipeline",
        outer_name="shared",
        target_ref_path=("Root", "Cell"),
    )

    return ast.unparse(stage2.build().materialize().tree)
