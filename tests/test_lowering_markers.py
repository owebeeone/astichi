from __future__ import annotations

import pytest

import astichi
from astichi.lowering import MARKERS_BY_NAME


def test_marker_registry_exposes_behavior_objects_by_source_name() -> None:
    assert "astichi_hole" in MARKERS_BY_NAME
    assert MARKERS_BY_NAME["astichi_hole"].is_name_bearing() is True
    assert "astichi_bind_once" in MARKERS_BY_NAME
    assert "astichi_bind_shared" in MARKERS_BY_NAME
    insert = MARKERS_BY_NAME["astichi_insert"]
    assert insert.is_name_bearing() is True
    assert insert.is_decorator_only() is False


def test_compile_recognizes_supported_call_markers() -> None:
    compiled = astichi.compile(
        """
astichi_hole(body)
astichi_bind_external(items)
astichi_keep(sys)
astichi_export(result)

for x in astichi_for(items):
    astichi_hole(inner)
"""
    )

    names = [marker.source_name for marker in compiled.markers]
    assert names == [
        "astichi_hole",
        "astichi_bind_external",
        "astichi_keep",
        "astichi_export",
        "astichi_for",
        "astichi_hole",
    ]

    name_ids = [marker.name_id for marker in compiled.markers]
    assert name_ids == [
        "body",
        "items",
        "sys",
        "result",
        None,
        "inner",
    ]

    assert compiled.markers[-1].context == "call"


@pytest.mark.parametrize(
    "source",
    [
        """
@astichi_insert(target)
def insert_block():
    return 1
""",
        "value = astichi_insert(target, 1)\n",
    ],
)
def test_authored_compile_rejects_astichi_insert(source: str) -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_insert\(\.\.\.\) is internal emitted-source metadata",
    ):
        astichi.compile(source)


def test_compile_rejects_unknown_source_kind() -> None:
    with pytest.raises(ValueError, match="source_kind must be"):
        astichi.compile("value = 1\n", source_kind="external")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("source_name", "hint"),
    [
        ("astichi_bind_once", "ordinary Python assignment"),
        ("astichi_bind_shared", "enclosing Python state"),
    ],
)
def test_compile_rejects_reserved_obsolete_bind_markers(
    source_name: str,
    hint: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=rf"{source_name}\(\.\.\.\) is reserved and obsolete.*{hint}",
    ):
        astichi.compile(f"{source_name}(value, 1)\n")


def test_insert_ref_accepts_fluent_descendant_path_syntax() -> None:
    astichi.compile(
        """
@astichi_insert(target, ref=Foo.Parse[1, 2].Normalize)
def insert_block():
    return 1
""",
        source_kind="astichi-emitted",
    )


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


def test_compile_recognizes_suffix_identifier_occurrences_on_name_and_arg() -> None:
    # Issue 005 §1 / 5b: identifier-shape slot occurrences must be
    # collected from every binding position - class/def names, `ast.arg`
    # parameter positions, and `ast.Name` Load/Store references -
    # grouped by stripped name at port-extraction time.
    compiled = astichi.compile(
        """
def wrapper__astichi_keep__(callback__astichi_arg__):
    result__astichi_arg__ = callback__astichi_arg__()
    return result__astichi_arg__
"""
    )

    suffix_markers = [
        marker
        for marker in compiled.markers
        if marker.source_name
        in ("astichi_keep_identifier", "astichi_arg_identifier")
    ]
    by_kind: dict[tuple[str, str], list[str]] = {}
    for marker in suffix_markers:
        assert marker.name_id is not None
        by_kind.setdefault((marker.source_name, marker.context), []).append(
            marker.name_id
        )

    # one definitional class/def keep occurrence
    assert by_kind[("astichi_keep_identifier", "definitional")] == ["wrapper"]
    # one `ast.arg` arg occurrence for the parameter
    assert ("astichi_arg_identifier", "identifier") in by_kind
    identifier_names = sorted(by_kind[("astichi_arg_identifier", "identifier")])
    # `callback` appears as arg + two Load refs (call + return? actually
    # only the call site load ref); `result` appears as Store + Load.
    assert "callback" in identifier_names
    assert "result" in identifier_names

    # Port-merging collapses per-occurrence markers to one DemandPort per
    # stripped name.
    demand_names = sorted(port.name for port in compiled.demand_ports)
    assert demand_names == ["callback", "result"]
    for port in compiled.demand_ports:
        assert port.placement == "identifier"
        assert "arg" in port.sources


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


def test_typo_in_identifier_suffix_warns_and_is_not_recognised() -> None:
    # Issue 005 §1 / marker recognition: a class/def name that matches the
    # reserved `<identifier>__astichi_<tag>__` shape but whose `<tag>` is
    # not a registered suffix is almost certainly a typo. The marker
    # visitor emits a `UserWarning` listing the known suffixes, does not
    # register a marker, and leaves the binding intact as an ordinary name.
    with pytest.warns(UserWarning, match=r"unrecognised Astichi suffix"):
        compiled = astichi.compile(
            """
class foo__astichi_kep__:
    pass
"""
        )
    suffix_markers = [
        marker
        for marker in compiled.markers
        if marker.source_name
        in ("astichi_keep_identifier", "astichi_arg_identifier")
    ]
    assert suffix_markers == []


def test_strip_identifier_suffix_is_regex_driven_and_silent_for_plain_names() -> None:
    # The recogniser must not emit spurious warnings for ordinary names
    # that don't match the reserved suffix shape at all.
    from astichi.lowering.markers import (
        ARG_IDENTIFIER,
        KEEP_IDENTIFIER,
        strip_identifier_suffix,
    )
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning becomes a test failure
        assert strip_identifier_suffix("plain_name") == ("plain_name", None)
        assert strip_identifier_suffix("foo__astichi_keep__") == (
            "foo",
            KEEP_IDENTIFIER,
        )
        assert strip_identifier_suffix("bar__astichi_arg__") == (
            "bar",
            ARG_IDENTIFIER,
        )
        # Bare suffix with no identifier prefix does not match the regex
        # and is reported as (name, None) without a warning; the marker
        # visitor handles that case via the validator so users still see
        # a clear error at compile time.
        assert strip_identifier_suffix("__astichi_keep__") == (
            "__astichi_keep__",
            None,
        )
