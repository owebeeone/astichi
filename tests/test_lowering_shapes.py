from __future__ import annotations

import astichi


def test_shape_inference_for_scalar_positional_named_and_block_sites() -> None:
    compiled = astichi.compile(
        """
astichi_hole(body)
value = astichi_hole(value_slot)
result = func(*astichi_hole(arg_list), **astichi_hole(kwarg_list))
items = (*astichi_hole(item_list),)
"""
    )

    body_hole, value_hole, arg_hole, kwarg_hole, item_hole = [
        marker for marker in compiled.markers if marker.source_name == "astichi_hole"
    ]

    assert body_hole.shape is not None
    assert body_hole.shape.is_block() is True

    assert value_hole.shape is not None
    assert value_hole.shape.is_scalar_expr() is True

    assert arg_hole.shape is not None
    assert arg_hole.shape.is_positional_variadic() is True

    assert kwarg_hole.shape is not None
    assert kwarg_hole.shape.is_named_variadic() is True

    assert item_hole.shape is not None
    assert item_hole.shape.is_positional_variadic() is True


def test_decorator_marker_shape_is_not_inferred_as_call_site_shape() -> None:
    compiled = astichi.compile(
        """
@astichi_insert(target_slot)
def insert_block():
    return 1
"""
    )

    insert_marker = compiled.markers[0]
    assert insert_marker.source_name == "astichi_insert"
    assert insert_marker.shape is None
