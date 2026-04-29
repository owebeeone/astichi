"""Bind two same-named descriptor supplies into different demands."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def _piece(source: str) -> astichi.Composable:
    return astichi.compile(
        source,
        file_name="gold_src/descriptor_bind_identifier_same_name_collision.py",
    )


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
    stage1.add.CellA(
        _piece(
            """
shared = 10
astichi_export(shared)
"""
        )
    )
    stage1.add.CellB(
        _piece(
            """
shared = 20
astichi_export(shared)
"""
        )
    )
    stage1.Root.cells.add.CellA()
    stage1.Root.cells.add.CellB()
    pipeline = stage1.build()

    consumer_a = _piece(
        """
astichi_import(shared)
astichi_pass(result, outer_bind=True).append(("a", shared))
"""
    )
    consumer_b = _piece(
        """
astichi_import(shared)
astichi_pass(result, outer_bind=True).append(("b", shared))
"""
    )

    pipeline_desc = pipeline.describe()
    consumer_a_desc = consumer_a.describe()
    consumer_b_desc = consumer_b.describe()
    consumer_hole = pipeline_desc.single_hole_named("consumers")
    shared_supply_a = next(
        supply
        for supply in pipeline_desc.identifier_supplies
        if supply.name == "shared" and supply.ref_path == ("Root", "CellA")
    )
    shared_supply_b = next(
        supply
        for supply in pipeline_desc.identifier_supplies
        if supply.name == "shared" and supply.ref_path == ("Root", "CellB")
    )
    shared_demand_a = next(
        demand
        for demand in consumer_a_desc.identifier_demands
        if demand.name == "shared"
    )
    shared_demand_b = next(
        demand
        for demand in consumer_b_desc.identifier_demands
        if demand.name == "shared"
    )

    stage2 = astichi.build()
    stage2.add.Pipeline(pipeline)
    stage2.add.ConsumerA(consumer_a)
    stage2.add.ConsumerB(consumer_b)
    stage2.target(consumer_hole.with_root_instance("Pipeline")).add.ConsumerA()
    stage2.target(consumer_hole.with_root_instance("Pipeline")).add.ConsumerB()
    stage2.bind_identifier(
        source_instance="ConsumerA",
        identifier=shared_demand_a,
        target_instance="Pipeline",
        to=shared_supply_a,
    )
    stage2.bind_identifier(
        source_instance="ConsumerB",
        identifier=shared_demand_b,
        target_instance="Pipeline",
        to=shared_supply_b,
    )
    return stage2.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    del composable, materialized, pre_source
    namespace = exec_source(materialized_source, "<descriptor_bind_collision>")
    assert namespace["final"] == (("a", 10), ("b", 20))
    assert "shared = 10" in materialized_source
    assert "shared__astichi_scoped_" in materialized_source
    assert "result.append(('a', shared))" in materialized_source
    assert "result.append(('b', shared__astichi_scoped_" in materialized_source
    assert "__astichi_assign__" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(
        run_case(
            "descriptor_bind_identifier_same_name_collision.py",
            build_case,
            validate_case,
        )
    )
