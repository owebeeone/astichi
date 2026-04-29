"""Use descriptor-driven bind_identifier next to assign alias wiring."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def _piece(source: str) -> astichi.Composable:
    return astichi.compile(
        source,
        file_name="gold_src/descriptor_assign_and_bind_identifier.py",
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
    stage1.add.DirectCell(
        _piece(
            """
shared = 10
astichi_export(shared)
"""
        )
    )
    stage1.add.AliasCell(
        _piece(
            """
total = 20
astichi_export(total)
"""
        )
    )
    stage1.Root.cells.add.DirectCell()
    stage1.Root.cells.add.AliasCell()
    pipeline = stage1.build()

    direct_consumer = _piece(
        """
astichi_import(shared)
astichi_pass(result, outer_bind=True).append(("bind", shared + 5))
"""
    )
    assigned_consumer = _piece(
        """
astichi_import(total)
astichi_pass(result, outer_bind=True).append(("assign", total + 7))
"""
    )

    pipeline_desc = pipeline.describe()
    direct_desc = direct_consumer.describe()
    consumer_hole = pipeline_desc.single_hole_named("consumers")
    shared_demand = next(
        demand
        for demand in direct_desc.identifier_demands
        if demand.name == "shared"
    )
    shared_supply = next(
        supply
        for supply in pipeline_desc.identifier_supplies
        if supply.name == "shared" and supply.ref_path == ("Root", "DirectCell")
    )

    stage2 = astichi.build()
    stage2.add.Pipeline(pipeline)
    stage2.add.DirectConsumer(direct_consumer)
    stage2.add.AssignedConsumer(assigned_consumer)
    stage2.target(consumer_hole.with_root_instance("Pipeline")).add.DirectConsumer()
    stage2.target(consumer_hole.with_root_instance("Pipeline")).add.AssignedConsumer()
    stage2.bind_identifier(
        source_instance="DirectConsumer",
        identifier=shared_demand,
        target_instance="Pipeline",
        to=shared_supply,
    )
    stage2.assign(
        source_instance="AssignedConsumer",
        inner_name="total",
        target_instance="Pipeline",
        outer_name="total",
        target_ref_path=("Root", "AliasCell"),
    )
    return stage2.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    del composable, materialized, pre_source
    namespace = exec_source(materialized_source, "<descriptor_assign_and_bind>")
    assert namespace["final"] == (("bind", 15), ("assign", 27))
    assert "result.append(('bind', shared + 5))" in materialized_source
    assert (
        "__astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total"
        in materialized_source
    )
    assert "result.append(('assign', __astichi_assign__" in materialized_source


if __name__ == "__main__":
    raise SystemExit(
        run_case(
            "descriptor_assign_and_bind_identifier.py",
            build_case,
            validate_case,
        )
    )
