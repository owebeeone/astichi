"""Drive indexed loop targets from descriptor address data.

The built stage-1 descriptor exposes the base ``step`` hole inside the preserved
``Root.Loop`` shell path. Stage 2 resolves that descriptor target under the
``Pipeline`` instance, then uses ``target[i]`` plus indexed ``Step[i]`` source
instances to attach one payload per unrolled loop iteration.
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
            events = []
            astichi_hole(body)
            final = tuple(events)
            """
        ),
    )
    stage1.add(
        "Loop",
        piece(
            """
            astichi_import(events, outer_bind=True)
            for item in astichi_for((0, 1, 2)):
                astichi_hole(step)
            """
        ),
    )
    stage1.instance("Root").target("body").add("Loop")
    pipeline = stage1.build()

    step_template = piece(
        """
        events = astichi_pass(events, outer_bind=True)
        events.append(astichi_bind_external(label))
        """
    )
    label_bind = step_template.describe().external_binds[0]

    stage2: BuilderHandle = astichi.build()
    stage2.add("Pipeline", pipeline)

    step_hole = pipeline.describe().single_hole_named("step")
    step_target = stage2.target(step_hole.with_root_instance("Pipeline"))
    for i, label in enumerate(("first", "second", "third")):
        stage2.add("Step", step_template, indexes=(i,))
        step_target[i].add(
            "Step",
            indexes=(i,),
            order=i,
            bind={label_bind.name: label},
        )

    return ast.unparse(stage2.build().materialize().tree)
