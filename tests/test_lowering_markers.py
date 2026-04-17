from __future__ import annotations

import pytest

import astichi
from astichi.lowering import MARKERS_BY_NAME


def test_marker_registry_exposes_behavior_objects_by_source_name() -> None:
    assert "astichi_hole" in MARKERS_BY_NAME
    assert MARKERS_BY_NAME["astichi_hole"].is_name_bearing() is True
    insert = MARKERS_BY_NAME["astichi_insert"]
    assert insert.is_name_bearing() is True
    assert insert.is_decorator_only() is False


def test_compile_recognizes_v1_markers() -> None:
    compiled = astichi.compile(
        """
astichi_hole(body)
astichi_bind_once(temp, value)
astichi_bind_shared(total, value)
astichi_bind_external(items)
astichi_keep(sys)
astichi_export(result)

for x in astichi_for(items):
    astichi_hole(inner)

@astichi_insert(target_slot)
def insert_block():
    return result
"""
    )

    names = [marker.source_name for marker in compiled.markers]
    assert names == [
        "astichi_hole",
        "astichi_bind_once",
        "astichi_bind_shared",
        "astichi_bind_external",
        "astichi_keep",
        "astichi_export",
        "astichi_for",
        "astichi_hole",
        "astichi_insert",
    ]

    name_ids = [marker.name_id for marker in compiled.markers]
    assert name_ids == [
        "body",
        "temp",
        "total",
        "items",
        "sys",
        "result",
        None,
        "inner",
        "target_slot",
    ]

    assert compiled.markers[-1].context == "decorator"


def test_marker_recognition_is_bare_name_only() -> None:
    compiled = astichi.compile(
        """
ns.astichi_hole(body)
"""
    )

    assert compiled.markers == ()


def test_marker_validation_rejects_non_identifier_name_args() -> None:
    with pytest.raises(
        ValueError,
        match="astichi_hole requires a bare identifier-like first argument",
    ):
        astichi.compile(
            """
astichi_hole("body")
"""
        )


def test_compile_recognizes_keep_and_arg_identifier_sites() -> None:
    # Issue 005 §1: `__astichi_keep__` and `__astichi_arg__` suffixes on
    # class/def names both register as `"definitional"`-context markers,
    # discriminated by `source_name`.
    compiled = astichi.compile(
        """
class kept__astichi_keep__:
    pass


def arg_func__astichi_arg__():
    return 1
"""
    )

    suffix_markers = [
        marker
        for marker in compiled.markers
        if marker.source_name
        in ("astichi_keep_identifier", "astichi_arg_identifier")
    ]

    assert [marker.context for marker in suffix_markers] == [
        "definitional",
        "definitional",
    ]
    assert [(marker.source_name, marker.name_id) for marker in suffix_markers] == [
        ("astichi_keep_identifier", "kept"),
        ("astichi_arg_identifier", "arg_func"),
    ]


def test_invalid_keep_identifier_site_fails_clearly() -> None:
    with pytest.raises(
        ValueError,
        match=r"identifier prefix before __astichi_keep__",
    ):
        astichi.compile(
            """
class __astichi_keep__:
    pass
"""
        )


def test_invalid_arg_identifier_site_fails_clearly() -> None:
    with pytest.raises(
        ValueError,
        match=r"identifier prefix before __astichi_arg__",
    ):
        astichi.compile(
            """
class __astichi_arg__:
    pass
"""
        )
