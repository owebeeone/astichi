"""Call-argument holes are anchor-preserved through ``build()``.

Bug #1: ``_HoleReplacementTransformer.visit_Call`` previously *replaced*
the authored ``astichi_hole(name)`` slot with the single ``astichi_insert``
call it built. That violates the published contract:

    "the originating `astichi_hole(...)` statement is removed"
    only at materialize (``AstichiApiDesignV1-CompositionUnification.md §2.2``).

Because the anchor was consumed at build-time, call-arg holes behaved
differently from block holes and could not accumulate additional
ordered inserts through subsequent wiring passes.

These tests pin the corrected contract:

  * build() keeps the authored ``astichi_hole(name)`` in place
  * wired ``astichi_insert(name, payload)`` entries land as siblings
    next to the anchor, mirroring the block-hole pattern in
    ``_HoleReplacementTransformer.visit_Expr``
  * multiple ordered inserts against the same call-arg hole survive
  * ``materialize()`` is the single pass that collapses the anchor +
    siblings into the final call shape.

Cross-stage composition (wiring into a target inside a previously-built
root shell) is a *separate* addressing bug shared by block and call-arg
holes alike; tracked as Bug #2 and out of scope here.
"""

from __future__ import annotations

import ast
import textwrap

import astichi


def _compile(src: str) -> astichi.Composable:
    return astichi.compile(textwrap.dedent(src).strip() + "\n")


# --------------------------------------------------------------------------- #
# **kwargs variadic holes                                                     #
# --------------------------------------------------------------------------- #


def test_build_preserves_dstar_kwargs_hole_anchor_single_insert() -> None:
    root = _compile("result = f(**astichi_hole(kwargs))")

    b = astichi.build()
    b.add.Root(root)
    b.add.Pa(_compile('astichi_funcargs(a=ctxt["a"])'))
    b.Root.kwargs.add.Pa(order=0)
    built = b.build()

    rendered = ast.unparse(built.tree)
    assert "astichi_hole(kwargs)" in rendered, (
        f"kwargs hole anchor was consumed at build time; tree:\n{rendered}"
    )
    assert "astichi_insert(kwargs" in rendered


def test_build_preserves_dstar_kwargs_hole_anchor_multiple_ordered_inserts() -> None:
    root = _compile("result = f(**astichi_hole(kwargs))")

    b = astichi.build()
    b.add.Root(root)
    b.add.Pa(_compile('astichi_funcargs(a=ctxt["a"])'))
    b.add.Pb(_compile('astichi_funcargs(b=ctxt["b"])'))
    b.add.Pc(_compile('astichi_funcargs(c=ctxt["c"])'))
    b.Root.kwargs.add.Pa(order=0)
    b.Root.kwargs.add.Pb(order=1)
    b.Root.kwargs.add.Pc(order=2)
    built = b.build()

    rendered = ast.unparse(built.tree)
    assert "astichi_hole(kwargs)" in rendered, (
        f"kwargs hole anchor was consumed at build time; tree:\n{rendered}"
    )
    assert rendered.count("astichi_insert(kwargs") == 3

    final = ast.unparse(built.materialize().tree)
    assert "astichi_hole" not in final
    assert "astichi_insert" not in final
    assert "result = f(a=ctxt['a'], b=ctxt['b'], c=ctxt['c'])" in final


# --------------------------------------------------------------------------- #
# *args variadic holes                                                        #
# --------------------------------------------------------------------------- #


def test_build_preserves_star_args_hole_anchor_multiple_ordered_inserts() -> None:
    root = _compile("result = f(*astichi_hole(args))")

    b = astichi.build()
    b.add.Root(root)
    b.add.Pa(_compile('astichi_funcargs(ctxt["a"])'))
    b.add.Pb(_compile('astichi_funcargs(ctxt["b"])'))
    b.Root.args.add.Pa(order=0)
    b.Root.args.add.Pb(order=1)
    built = b.build()

    rendered = ast.unparse(built.tree)
    assert "astichi_hole(args)" in rendered, (
        f"args hole anchor was consumed at build time; tree:\n{rendered}"
    )
    assert rendered.count("astichi_insert(args") == 2

    final = ast.unparse(built.materialize().tree)
    assert "astichi_hole" not in final
    assert "astichi_insert" not in final
    assert "result = f(ctxt['a'], ctxt['b'])" in final


# --------------------------------------------------------------------------- #
# plain positional call-region holes                                          #
# --------------------------------------------------------------------------- #


def test_build_preserves_plain_call_region_hole_anchor_multiple_ordered_inserts() -> None:
    root = _compile("result = f(astichi_hole(items))")

    b = astichi.build()
    b.add.Root(root)
    b.add.Pa(_compile('astichi_funcargs(ctxt["a"])'))
    b.add.Pb(_compile('astichi_funcargs(ctxt["b"])'))
    b.Root.items.add.Pa(order=0)
    b.Root.items.add.Pb(order=1)
    built = b.build()

    rendered = ast.unparse(built.tree)
    assert "astichi_hole(items)" in rendered, (
        f"plain call-region hole anchor was consumed at build time; tree:\n{rendered}"
    )
    assert rendered.count("astichi_insert(items") == 2

    final = ast.unparse(built.materialize().tree)
    assert "astichi_hole" not in final
    assert "astichi_insert" not in final
    assert "result = f(ctxt['a'], ctxt['b'])" in final
