from __future__ import annotations

import ast

import pytest

import astichi
from astichi.model import BasicComposable


def test_build_simple_block_hole_replacement() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(body)\n"))
    builder.add.B(astichi.compile("value = 1\n"))
    builder.A.body.add.B()

    result = builder.build()

    assert isinstance(result, BasicComposable)
    rendered = ast.unparse(result.tree)
    assert "value = 1" in rendered
    assert "astichi_hole(body)" in rendered
    assert "@astichi_insert(body)" in rendered
    assert [p.name for p in result.demand_ports] == []

    materialized = result.materialize()
    materialized_src = ast.unparse(materialized.tree)
    assert "value = 1" in materialized_src
    assert "astichi_hole" not in materialized_src
    assert "astichi_insert" not in materialized_src


def test_build_preserves_surrounding_code() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("x = 1\nastichi_hole(body)\ny = 2\n"))
    builder.add.B(astichi.compile("z = 3\n"))
    builder.A.body.add.B()

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert "x = 1" in rendered
    assert "z = 3" in rendered
    assert "y = 2" in rendered
    assert "astichi_hole(body)" in rendered
    assert "@astichi_insert(body)" in rendered

    materialized_src = ast.unparse(result.materialize().tree)
    assert "x = 1" in materialized_src
    assert "z = 3" in materialized_src
    assert "y = 2" in materialized_src
    assert "astichi_hole" not in materialized_src
    assert "astichi_insert" not in materialized_src
    assert materialized_src.index("x = 1") < materialized_src.index("z = 3")
    assert materialized_src.index("z = 3") < materialized_src.index("y = 2")


def test_build_multiple_sources_ordered() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(body)\n"))
    builder.add.B(astichi.compile("x = 1\n"))
    builder.add.C(astichi.compile("y = 2\n"))
    builder.A.body.add.C(order=5)
    builder.A.body.add.B(order=10)

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert rendered.index("y = 2") < rendered.index("x = 1")


def test_build_equal_order_preserves_insertion_order() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(body)\n"))
    builder.add.B(astichi.compile("x = 1\n"))
    builder.add.C(astichi.compile("y = 2\n"))
    builder.A.body.add.B(order=0)
    builder.A.body.add.C(order=0)

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert rendered.index("x = 1") < rendered.index("y = 2")


def test_build_unresolved_holes_remain() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile("astichi_hole(filled)\nastichi_hole(unfilled)\n")
    )
    builder.add.B(astichi.compile("value = 1\n"))
    builder.A.filled.add.B()

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert "value = 1" in rendered
    assert "astichi_hole(unfilled)" in rendered
    assert [p.name for p in result.demand_ports] == ["unfilled"]


def test_build_chain_resolution() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(outer)\n"))
    builder.add.B(astichi.compile("x = 1\nastichi_hole(inner)\n"))
    builder.add.C(astichi.compile("y = 2\n"))
    builder.A.outer.add.B()
    builder.B.inner.add.C()

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert "x = 1" in rendered
    assert "y = 2" in rendered
    assert "astichi_hole(outer)" in rendered
    assert "astichi_hole(inner)" in rendered
    assert "@astichi_insert(outer)" in rendered
    assert "@astichi_insert(inner)" in rendered
    assert [p.name for p in result.demand_ports] == []

    materialized_src = ast.unparse(result.materialize().tree)
    assert "x = 1" in materialized_src
    assert "y = 2" in materialized_src
    assert "astichi_hole" not in materialized_src
    assert "astichi_insert" not in materialized_src
    assert materialized_src.index("x = 1") < materialized_src.index("y = 2")


def test_build_no_edges_concatenates_bodies() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("x = 1\n"))
    builder.add.B(astichi.compile("y = 2\n"))

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert "x = 1" in rendered
    assert "y = 2" in rendered


def test_build_updates_demand_and_supply_ports() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(slot)\nastichi_export(out)\n"))
    builder.add.B(astichi.compile("value = 1\n"))
    builder.A.slot.add.B()

    result = builder.build()

    demand_names = [p.name for p in result.demand_ports]
    supply_names = [p.name for p in result.supply_ports]
    assert "slot" not in demand_names
    assert "out" in supply_names


def test_build_empty_graph_raises() -> None:
    builder = astichi.build()

    with pytest.raises(ValueError, match="cannot build from empty graph"):
        builder.build()


# ---- 2c / 2d: indexed-edge routing + unroll kwarg -----------------------


def test_indexed_edge_autounrolls_and_routes_per_index() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            "for x in astichi_for((1, 2)):\n"
            "    astichi_hole(slot)\n"
        )
    )
    builder.add.B0(astichi.compile("zero = 0\n"))
    builder.add.B1(astichi.compile("one = 1\n"))
    builder.A.slot[0].add.B0()
    builder.A.slot[1].add.B1()

    result = builder.build()

    rendered = ast.unparse(result.tree)
    # Loop is gone after auto-unroll, and each synthetic slot got its
    # own contribution.
    assert "astichi_for" not in rendered
    assert "@astichi_insert(slot__iter_0)" in rendered
    assert "@astichi_insert(slot__iter_1)" in rendered
    assert "zero = 0" in rendered
    assert "one = 1" in rendered
    assert [p.name for p in result.demand_ports] == []


def test_indexed_edges_materialize_end_to_end() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            "for x in astichi_for((1, 2, 3)):\n"
            "    astichi_hole(slot)\n"
        )
    )
    builder.add.B0(astichi.compile("a = 10\n"))
    builder.add.B1(astichi.compile("b = 20\n"))
    builder.add.B2(astichi.compile("c = 30\n"))
    builder.A.slot[0].add.B0()
    builder.A.slot[1].add.B1()
    builder.A.slot[2].add.B2()

    result = builder.build()
    materialized_src = ast.unparse(result.materialize().tree)

    assert "a = 10" in materialized_src
    assert "b = 20" in materialized_src
    assert "c = 30" in materialized_src
    assert "astichi_for" not in materialized_src
    assert "astichi_hole" not in materialized_src
    # Order follows unrolled iteration order.
    assert (
        materialized_src.index("a = 10")
        < materialized_src.index("b = 20")
        < materialized_src.index("c = 30")
    )


def test_indexed_edge_leaves_unfilled_synthetic_as_demand_port() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            "for x in astichi_for((1, 2, 3)):\n"
            "    astichi_hole(slot)\n"
        )
    )
    builder.add.B0(astichi.compile("a = 10\n"))
    builder.add.B2(astichi.compile("c = 30\n"))
    builder.A.slot[0].add.B0()
    builder.A.slot[2].add.B2()

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert "a = 10" in rendered
    assert "c = 30" in rendered
    assert "astichi_hole(slot__iter_1)" in rendered
    assert [p.name for p in result.demand_ports] == ["slot__iter_1"]


def test_unroll_true_forces_expansion_without_indexed_edges() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            "for x in astichi_for((7, 9)):\n"
            "    z = x\n"
        )
    )

    result = builder.build(unroll=True)

    rendered = ast.unparse(result.tree)
    assert "astichi_for" not in rendered
    assert "z = 7" in rendered
    assert "z = 9" in rendered


def test_unroll_false_with_indexed_edges_raises() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            "for x in astichi_for((1, 2)):\n"
            "    astichi_hole(slot)\n"
        )
    )
    builder.add.B(astichi.compile("value = 1\n"))
    builder.A.slot[0].add.B()

    with pytest.raises(
        ValueError,
        match=r"unroll=False conflicts with indexed target edges.*A\.slot\[0\]",
    ):
        builder.build(unroll=False)


def test_indexed_edge_out_of_range_raises() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            "for x in astichi_for((1, 2)):\n"
            "    astichi_hole(slot)\n"
        )
    )
    builder.add.B(astichi.compile("value = 1\n"))
    builder.A.slot[5].add.B()

    with pytest.raises(
        ValueError,
        match=r"indexed target A\.slot\[5\] has no matching astichi_hole",
    ):
        builder.build()


def test_indexed_edge_on_non_unrolled_target_rejected() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(other)\n"))
    builder.add.B(astichi.compile("value = 1\n"))
    builder.A.other[0].add.B()

    with pytest.raises(
        ValueError,
        match=r"indexed target A\.other\[0\] has no matching astichi_hole",
    ):
        builder.build()


def test_mixed_indexed_and_plain_targets_coexist() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            "astichi_hole(head)\n"
            "for x in astichi_for((1, 2)):\n"
            "    astichi_hole(slot)\n"
        )
    )
    builder.add.H(astichi.compile("head_val = 1\n"))
    builder.add.S0(astichi.compile("s0 = 0\n"))
    builder.add.S1(astichi.compile("s1 = 1\n"))
    builder.A.head.add.H()
    builder.A.slot[0].add.S0()
    builder.A.slot[1].add.S1()

    result = builder.build()
    materialized_src = ast.unparse(result.materialize().tree)

    assert "head_val = 1" in materialized_src
    assert "s0 = 0" in materialized_src
    assert "s1 = 1" in materialized_src
    assert "astichi_for" not in materialized_src
    assert "astichi_hole" not in materialized_src


def test_invalid_unroll_value_raises() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("x = 1\n"))

    with pytest.raises(ValueError, match="unroll must be True, False, or 'auto'"):
        builder.build(unroll="always")


# ---- 2e gate: bind-fed literal domain + provenance round-trip ----------


def test_bind_fed_tuple_domain_autounrolls_and_routes() -> None:
    """Domain supplied via astichi_bind_external resolves through unroll.

    Confirms the pipeline order: bind-external substitutes the literal at
    the `astichi_for(DOMAIN)` site, then build()'s auto-unroll sees a
    literal-tuple domain and expands it into per-iteration holes that
    indexed edges can address.
    """
    A = astichi.compile(
        "astichi_bind_external(DOMAIN)\n"
        "for x in astichi_for(DOMAIN):\n"
        "    astichi_hole(slot)\n"
    ).bind(DOMAIN=(10, 20, 30))

    builder = astichi.build()
    builder.add.A(A)
    builder.add.B0(astichi.compile("a = 10\n"))
    builder.add.B1(astichi.compile("b = 20\n"))
    builder.add.B2(astichi.compile("c = 30\n"))
    builder.A.slot[0].add.B0()
    builder.A.slot[1].add.B1()
    builder.A.slot[2].add.B2()

    result = builder.build()
    materialized_src = ast.unparse(result.materialize().tree)

    assert "astichi_for" not in materialized_src
    assert "astichi_hole" not in materialized_src
    assert "a = 10" in materialized_src
    assert "b = 20" in materialized_src
    assert "c = 30" in materialized_src
    assert (
        materialized_src.index("a = 10")
        < materialized_src.index("b = 20")
        < materialized_src.index("c = 30")
    )


def test_bind_fed_list_domain_autounrolls() -> None:
    A = astichi.compile(
        "astichi_bind_external(VALUES)\n"
        "for v in astichi_for(VALUES):\n"
        "    astichi_hole(slot)\n"
    ).bind(VALUES=[7, 9])

    builder = astichi.build()
    builder.add.A(A)
    builder.add.B0(astichi.compile("first = 7\n"))
    builder.add.B1(astichi.compile("second = 9\n"))
    builder.A.slot[0].add.B0()
    builder.A.slot[1].add.B1()

    result = builder.build()
    materialized_src = ast.unparse(result.materialize().tree)

    assert "first = 7" in materialized_src
    assert "second = 9" in materialized_src
    assert "astichi_for" not in materialized_src


def test_bind_fed_domain_unroll_true_expands_without_indexed_edges() -> None:
    """unroll=True must unroll even when the domain comes from bind()."""
    A = astichi.compile(
        "astichi_bind_external(DOMAIN)\n"
        "for x in astichi_for(DOMAIN):\n"
        "    z = x\n"
    ).bind(DOMAIN=(1, 2))

    builder = astichi.build()
    builder.add.A(A)

    result = builder.build(unroll=True)

    rendered = ast.unparse(result.tree)
    assert "astichi_for" not in rendered
    assert "z = 1" in rendered
    assert "z = 2" in rendered


def test_bind_fed_domain_unbound_rejected_by_unroll() -> None:
    """Unroll cannot guess a domain: a bare Name must be bound first."""
    A = astichi.compile(
        "astichi_bind_external(DOMAIN)\n"
        "for x in astichi_for(DOMAIN):\n"
        "    astichi_hole(slot)\n"
    )

    builder = astichi.build()
    builder.add.A(A)
    builder.add.B(astichi.compile("v = 1\n"))
    # An indexed edge forces auto-unroll, which sees the still-bound-
    # name domain and refuses it at domain-resolution time.
    builder.A.slot[0].add.B()
    with pytest.raises(
        ValueError,
        match=r"astichi_for domain must be a literal tuple/list or range",
    ):
        builder.build()


def test_unrolled_build_provenance_round_trip() -> None:
    """Emitted source of an unrolled build re-parses to the same AST."""
    from astichi.emit import verify_round_trip

    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            "for x in astichi_for((1, 2, 3)):\n"
            "    astichi_hole(slot)\n"
        )
    )
    builder.add.B(astichi.compile("v = 1\n"))
    builder.A.slot[0].add.B()

    result = builder.build()
    verify_round_trip(result.emit())


def test_unrolled_materialized_provenance_round_trip() -> None:
    """Emitted source of a materialized unrolled build round-trips too."""
    from astichi.emit import verify_round_trip

    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            "for x in astichi_for((1, 2)):\n"
            "    astichi_hole(slot)\n"
        )
    )
    builder.add.B0(astichi.compile("a = 1\n"))
    builder.add.B1(astichi.compile("b = 2\n"))
    builder.A.slot[0].add.B0()
    builder.A.slot[1].add.B1()

    result = builder.build()
    verify_round_trip(result.materialize().emit())


def test_bind_fed_unrolled_build_provenance_round_trip() -> None:
    """The full pipeline (bind → unroll → emit) preserves provenance."""
    from astichi.emit import verify_round_trip

    A = astichi.compile(
        "astichi_bind_external(DOMAIN)\n"
        "for x in astichi_for(DOMAIN):\n"
        "    astichi_hole(slot)\n"
    ).bind(DOMAIN=(1, 2))

    builder = astichi.build()
    builder.add.A(A)
    builder.add.B0(astichi.compile("a = 1\n"))
    builder.add.B1(astichi.compile("b = 2\n"))
    builder.A.slot[0].add.B0()
    builder.A.slot[1].add.B1()

    result = builder.build()
    verify_round_trip(result.emit())
    verify_round_trip(result.materialize().emit())
