from __future__ import annotations

import ast

import pytest

import astichi
from astichi.lowering import (
    MARKERS_BY_NAME,
    marker_metadata_name_nodes,
)
from astichi.lowering.markers import (
    ELIF,
    EXPORT,
    IMPORT,
    KEEP,
    scan_statement_prefix,
)


def test_marker_registry_exposes_behavior_objects_by_source_name() -> None:
    assert "astichi_hole" in MARKERS_BY_NAME
    assert MARKERS_BY_NAME["astichi_hole"].is_name_bearing() is True
    assert MARKERS_BY_NAME["astichi_elif"] is ELIF
    assert MARKERS_BY_NAME["astichi_elif"].is_renamed_per_iteration() is True
    assert "astichi_bind_once" in MARKERS_BY_NAME
    assert "astichi_bind_shared" in MARKERS_BY_NAME
    insert = MARKERS_BY_NAME["astichi_insert"]
    assert insert.is_name_bearing() is True
    assert insert.is_decorator_only() is False


def test_marker_metadata_name_nodes_reports_marker_owned_names() -> None:
    compiled = astichi.compile(
        """
astichi_keep(pinned)

@astichi_insert(target, ref=Root.Slot)
def shell():
    return 1
""",
        source_kind="astichi-emitted",
    )

    metadata_names = {
        node.id for node in marker_metadata_name_nodes(compiled.markers)
    }

    assert {"astichi_keep", "pinned", "astichi_insert", "target", "Root"} <= (
        metadata_names
    )


def test_scan_statement_prefix_stops_at_first_non_prefix_statement() -> None:
    tree = ast.parse(
        """
astichi_import(value)
astichi_keep(value)
real_statement()
astichi_export(value)
"""
    )

    scan = scan_statement_prefix(
        tree.body,
        allowed_specs=(IMPORT, KEEP, EXPORT),
    )

    assert scan.first_non_prefix_index == 2
    assert len(scan.prefix_statements) == 2


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


def test_compile_recognizes_defaulted_block_hole_marker() -> None:
    compiled = astichi.compile(
        """
def validate():
    with astichi_hole(validate_body) as astichi_fallback:
        return True
"""
    )

    hole_markers = [
        marker for marker in compiled.markers if marker.source_name == "astichi_hole"
    ]
    assert len(hole_markers) == 1
    assert hole_markers[0].name_id == "validate_body"
    assert hole_markers[0].shape.name == "block"
    assert isinstance(hole_markers[0].node, ast.With)


def test_defaulted_block_hole_fallback_body_is_branch_inactive_at_compile() -> None:
    compiled = astichi.compile(
        """
def validate():
    with astichi_hole(validate_body) as astichi_fallback:
        astichi_hole(nested_body)
        return missing_name
"""
    )

    assert [port.name for port in compiled.demand_ports] == ["validate_body"]
    assert compiled.classification is not None
    assert compiled.classification.unresolved_free == frozenset()


@pytest.mark.parametrize(
    ("source", "pattern"),
    [
        (
            """
with astichi_hole(body):
    pass
""",
            "as astichi_fallback",
        ),
        (
            """
with astichi_hole(body) as fallback:
    pass
""",
            "as astichi_fallback",
        ),
        (
            """
with astichi_hole(body) as astichi_fallback, other_context():
    pass
""",
            "exactly one context manager",
        ),
        (
            """
with astichi_hole(body) as astichi_fallback:
    astichi_pyimport(module=os)
""",
            r"astichi_pyimport\(\.\.\.\) is not allowed",
        ),
    ],
)
def test_defaulted_block_hole_invalid_surfaces_reject(
    source: str, pattern: str
) -> None:
    with pytest.raises(ValueError, match=pattern):
        astichi.compile(source)


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


def test_compile_recognizes_elif_clause_target_marker() -> None:
    compiled = astichi.compile(
        """
if enabled:
    pass
elif astichi_elif(branches):
    astichi_comment("generated branches")
    pass
else:
    fallback()
"""
    )

    elif_markers = [
        marker for marker in compiled.markers if marker.source_name == "astichi_elif"
    ]

    assert len(elif_markers) == 1
    assert elif_markers[0].name_id == "branches"
    assert elif_markers[0].shape is not None
    assert elif_markers[0].shape.is_elif_clause()


def test_compile_recognizes_elif_contribution_payload() -> None:
    compiled = astichi.compile(
        """
def astichi_elif():
    astichi_import(event_type)
    if event_type == "create":
        return "created"
"""
    )

    elif_markers = [
        marker for marker in compiled.markers if marker.source_name == "astichi_elif"
    ]

    assert len(elif_markers) == 1
    assert elif_markers[0].context == "definitional"
    assert elif_markers[0].name_id == "astichi_elif"
    assert elif_markers[0].shape is not None
    assert elif_markers[0].shape.is_elif_clause()


@pytest.mark.parametrize(
    ("source", "match"),
    [
        (
            """
if astichi_elif(branches):
    pass
""",
            "real elif position",
        ),
        (
            """
if enabled:
    pass
elif astichi_elif("branches"):
    pass
""",
            "bare identifier-like",
        ),
        (
            """
if enabled:
    pass
elif astichi_elif(_):
    pass
""",
            "may not be `_`",
        ),
        (
            """
if enabled:
    pass
elif astichi_elif(branches, other):
    pass
""",
            "expects 1 positional",
        ),
        (
            """
if enabled:
    pass
elif astichi_elif(branches, optional=True):
    pass
""",
            "keyword arguments",
        ),
        (
            """
if enabled:
    pass
elif astichi_elif(branches):
    real_statement()
""",
            "empty-equivalent",
        ),
        (
            """
if first:
    pass
elif astichi_elif(branches):
    pass

if second:
    pass
elif astichi_elif(branches):
    pass
""",
            "duplicate astichi_elif target",
        ),
    ],
)
def test_compile_rejects_invalid_elif_target_forms(source: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        astichi.compile(source)


@pytest.mark.parametrize(
    ("source", "match"),
    [
        (
            """
@decorator
def astichi_elif():
    if enabled:
        pass
""",
            "decorators",
        ),
        (
            """
def astichi_elif(value):
    if enabled:
        pass
""",
            "must not declare parameters",
        ),
        (
            """
def astichi_elif() -> str:
    if enabled:
        pass
""",
            "return annotation",
        ),
        (
            """
def astichi_elif():
    astichi_pass(value)
    if enabled:
        pass
""",
            "value-form only",
        ),
        (
            """
def astichi_elif():
    if enabled:
        pass
    if other:
        pass
""",
            "exactly one if",
        ),
        (
            """
def astichi_elif():
    if enabled:
        pass
    else:
        pass
""",
            "if.orelse",
        ),
        (
            """
def astichi_elif():
    if (value := enabled):
        pass
""",
            "walrus",
        ),
        (
            """
def astichi_elif():
    if enabled:
        yield value
""",
            "yield",
        ),
    ],
)
def test_compile_rejects_invalid_elif_contribution_forms(
    source: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        astichi.compile(source)


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
