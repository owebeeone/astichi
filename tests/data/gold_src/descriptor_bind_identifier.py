"""Descriptor-driven direct identifier binding across build stages."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def _piece(source: str) -> astichi.Composable:
    return astichi.compile(source, file_name="gold_src/descriptor_bind_identifier.py")


def build_case() -> astichi.Composable:
    stage1 = astichi.build()
    stage1.add.Root(
        _piece(
            """
result = []
astichi_hole(cells)
astichi_hole(consumers)
final = tuple(result)
"""
        )
    )
    stage1.add.Cell(
        _piece(
            """
shared = 10
astichi_export(shared)
"""
        )
    )
    stage1.Root.cells.add.Cell()
    pipeline = stage1.build()

    consumer = _piece(
        """
astichi_import(shared)
astichi_pass(result, outer_bind=True).append(shared + 5)
"""
    )
    pipeline_desc = pipeline.describe()
    consumer_desc = consumer.describe()
    consumer_hole = pipeline_desc.single_hole_named("consumers")
    shared_demand = next(
        demand
        for demand in consumer_desc.identifier_demands
        if demand.name == "shared"
    )
    shared_supply = next(
        supply
        for supply in pipeline_desc.identifier_supplies
        if supply.name == "shared" and supply.ref_path == ("Root", "Cell")
    )

    stage2 = astichi.build()
    stage2.add.Pipeline(pipeline)
    stage2.add.Consumer(consumer)
    stage2.target(consumer_hole.with_root_instance("Pipeline")).add.Consumer()
    stage2.bind_identifier(
        source_instance="Consumer",
        identifier=shared_demand,
        target_instance="Pipeline",
        to=shared_supply,
    )
    return stage2.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    del composable, materialized, pre_source
    namespace = exec_source(materialized_source, "<descriptor_bind_identifier>")
    assert namespace["final"] == (15,)
    assert "__astichi_assign__" not in materialized_source
    assert "result.append(shared + 5)" in materialized_source


if __name__ == "__main__":
    raise SystemExit(
        run_case("descriptor_bind_identifier.py", build_case, validate_case)
    )
