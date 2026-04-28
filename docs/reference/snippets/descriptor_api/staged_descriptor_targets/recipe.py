"""Use descriptor addresses with the data-driven builder in a staged graph.

Stage 1 builds a pipeline root with a descendant ``Cell`` supplier and an open
``consumers`` hole. Stage 2 inspects the built pipeline descriptor, uses the
hole's address with ``builder.target(...)``, and uses identifier descriptors to
drive named ``builder.assign(...)`` wiring.
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

    consumer = piece(
        """
        astichi_import(shared)
        astichi_pass(result, outer_bind=True).append(shared + 5)
        """
    )

    pipeline_desc = pipeline.describe()
    consumer_hole = pipeline_desc.single_hole_named("consumers")
    shared_supply = next(
        supply for supply in pipeline_desc.identifier_supplies if supply.name == "shared"
    )
    shared_demand = next(
        demand for demand in consumer.describe().identifier_demands if demand.name == "shared"
    )

    stage2: BuilderHandle = astichi.build()
    stage2.add("Pipeline", pipeline)
    stage2.add("Consumer", consumer)
    stage2.target(consumer_hole.with_root_instance("Pipeline")).add("Consumer")
    stage2.assign(
        source_instance="Consumer",
        source_ref_path=shared_demand.ref_path,
        inner_name=shared_demand.name,
        target_instance="Pipeline",
        target_ref_path=shared_supply.ref_path,
        outer_name=shared_supply.name,
    )

    return ast.unparse(stage2.build().materialize().tree)
