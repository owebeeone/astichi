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


def test_dict_double_star_hole_infers_named_variadic() -> None:
    compiled = astichi.compile(
        """
d = {**astichi_hole(entries), other_key: 1}
"""
    )

    holes = [m for m in compiled.markers if m.source_name == "astichi_hole"]
    assert len(holes) == 1
    assert holes[0].name_id == "entries"
    assert holes[0].shape is not None
    assert holes[0].shape.is_named_variadic() is True


def test_dict_key_position_hole_infers_scalar_expr() -> None:
    compiled = astichi.compile(
        """
d = {astichi_hole(single_key): sentinel, other_key: 2}
"""
    )

    holes = [m for m in compiled.markers if m.source_name == "astichi_hole"]
    assert len(holes) == 1
    assert holes[0].name_id == "single_key"
    assert holes[0].shape is not None
    assert holes[0].shape.is_scalar_expr() is True


def test_dict_value_position_hole_infers_scalar_expr() -> None:
    compiled = astichi.compile(
        """
d = {some_key: astichi_hole(val)}
"""
    )

    holes = [m for m in compiled.markers if m.source_name == "astichi_hole"]
    assert len(holes) == 1
    assert holes[0].name_id == "val"
    assert holes[0].shape is not None
    assert holes[0].shape.is_scalar_expr() is True


def test_decorator_marker_shape_is_not_inferred_as_call_site_shape() -> None:
    compiled = astichi.compile(
        """
@astichi_insert(target_slot)
def insert_block():
    return 1
""",
        source_kind="astichi-emitted",
    )

    insert_marker = compiled.markers[0]
    assert insert_marker.source_name == "astichi_insert"
    assert insert_marker.context == "decorator"
    assert insert_marker.shape is None


def test_expression_insert_is_recognized_as_call_context() -> None:
    compiled = astichi.compile(
        """
value = astichi_insert(target_slot, 42)
""",
        source_kind="astichi-emitted",
    )

    inserts = [m for m in compiled.markers if m.source_name == "astichi_insert"]
    assert len(inserts) == 1
    assert inserts[0].context == "call"
    assert inserts[0].name_id == "target_slot"
    assert inserts[0].shape is not None
    assert inserts[0].shape.is_scalar_expr() is True


def test_expression_insert_with_order_keyword() -> None:
    compiled = astichi.compile(
        """
value = astichi_insert(target_slot, some_expr, order=10)
""",
        source_kind="astichi-emitted",
    )

    inserts = [m for m in compiled.markers if m.source_name == "astichi_insert"]
    assert len(inserts) == 1
    assert inserts[0].context == "call"
    assert inserts[0].name_id == "target_slot"


def test_expression_insert_standalone_statement_is_scalar_not_block() -> None:
    compiled = astichi.compile(
        """
astichi_insert(target_slot, some_expr)
""",
        source_kind="astichi-emitted",
    )

    inserts = [m for m in compiled.markers if m.source_name == "astichi_insert"]
    assert len(inserts) == 1
    assert inserts[0].context == "call"
    assert inserts[0].shape is not None
    assert inserts[0].shape.is_scalar_expr() is True
    assert inserts[0].shape.is_block() is False


def test_decorator_insert_still_works_alongside_expression_insert() -> None:
    compiled = astichi.compile(
        """
@astichi_insert(block_target)
def inject_block():
    return 1

value = astichi_insert(expr_target, 42)
""",
        source_kind="astichi-emitted",
    )

    inserts = [m for m in compiled.markers if m.source_name == "astichi_insert"]
    assert len(inserts) == 2

    decorator_inserts = [m for m in inserts if m.context == "decorator"]
    call_inserts = [m for m in inserts if m.context == "call"]

    assert len(decorator_inserts) == 1
    assert decorator_inserts[0].name_id == "block_target"
    assert decorator_inserts[0].shape is None

    assert len(call_inserts) == 1
    assert call_inserts[0].name_id == "expr_target"
    assert call_inserts[0].shape is not None
    assert call_inserts[0].shape.is_scalar_expr() is True
