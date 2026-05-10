from __future__ import annotations

import pytest

from astichi.pathmatch import (
    RESERVED_CHARS,
    matches_path,
    parse_path_selector,
)


def test_matches_exact_literal_paths() -> None:
    assert matches_path(("Root", "Step"), ("Root", "Step"))
    assert not matches_path(("Root", "Step"), ("Root",))
    assert not matches_path(("Root", "Step"), ("Root", "Other"))


def test_dot_matches_exactly_one_segment() -> None:
    assert matches_path((".", "Leaf"), ("Root", "Leaf"))
    assert not matches_path((".", "Leaf"), ("Leaf",))
    assert not matches_path((".", "Leaf"), ("Root", "Branch", "Leaf"))


def test_question_matches_zero_or_one_segment() -> None:
    assert matches_path(("Root", "?"), ("Root",))
    assert matches_path(("Root", "?"), ("Root", "Step"))
    assert not matches_path(("Root", "?"), ("Root", "Step", "Leaf"))


def test_star_matches_zero_or_more_segments() -> None:
    assert matches_path(("Root", "*"), ("Root",))
    assert matches_path(("Root", "*"), ("Root", "Step"))
    assert matches_path(("Root", "*"), ("Root", "Step", "Leaf"))
    assert matches_path(("*", "Leaf"), ("Leaf",))
    assert matches_path(("*", "Leaf"), ("Root", "Step", "Leaf"))


def test_plus_matches_one_or_more_segments() -> None:
    assert not matches_path(("Root", "+"), ("Root",))
    assert matches_path(("Root", "+"), ("Root", "Step"))
    assert matches_path(("Root", "+"), ("Root", "Step", "Leaf"))
    assert not matches_path(("+", "Leaf"), ("Leaf",))
    assert matches_path(("+", "Leaf"), ("Root", "Leaf"))


def test_composes_selector_operators() -> None:
    assert matches_path(("Root", "*", "Leaf"), ("Root", "Leaf"))
    assert matches_path(("Root", "*", "Leaf"), ("Root", "Step", "Leaf"))
    assert matches_path(("Root", "+", "Leaf"), ("Root", "Step", "Leaf"))
    assert not matches_path(("Root", "+", "Leaf"), ("Root", "Leaf"))
    assert matches_path(("Root", "?", "Leaf"), ("Root", "Leaf"))
    assert matches_path(("Root", "?", "Leaf"), ("Root", "Step", "Leaf"))
    assert not matches_path(("Root", "?", "Leaf"), ("Root", "Step", "Mid", "Leaf"))


def test_empty_selector_matches_only_empty_path() -> None:
    assert matches_path((), ())
    assert not matches_path((), ("Root",))


def test_non_operator_strings_match_literally() -> None:
    assert matches_path(("[0]",), ("[0]",))
    assert matches_path(("Step[0]",), ("Step[0]",))
    assert not matches_path(("RootStep",), ("Root", "Step"))


def test_allows_identifier_and_indexed_build_names() -> None:
    assert matches_path(("Root", "Step[0]"), ("Root", "Step[0]"))
    assert matches_path(("Root", "."), ("Root", "Step[10]"))


def test_reserved_chars_include_operators_and_separator() -> None:
    assert RESERVED_CHARS == ".+?*/"


def test_matches_path_rejects_reserved_chars_in_literal_selector_parts() -> None:
    for selector in (
        ("Root.Step",),
        ("Root+Step",),
        ("Root?Step",),
        ("Root*Step",),
        ("Root/Step",),
    ):
        with pytest.raises(ValueError, match="reserved path selector character"):
            matches_path(selector, selector)


def test_parse_path_selector_splits_slash_separated_parts() -> None:
    assert parse_path_selector("A/B/?/C") == ("A", "B", "?", "C")
    assert parse_path_selector("Root/GetterBody[1,2]") == (
        "Root",
        "GetterBody[1,2]",
    )


def test_parse_path_selector_keeps_operator_parts_literal() -> None:
    assert parse_path_selector(".") == (".",)
    assert parse_path_selector("?") == ("?",)
    assert parse_path_selector("*") == ("*",)
    assert parse_path_selector("+") == ("+",)


def test_parse_path_selector_empty_string_is_empty_selector() -> None:
    assert parse_path_selector("") == ()


def test_parse_path_selector_rejects_empty_parts() -> None:
    with pytest.raises(ValueError, match="empty path selector part"):
        parse_path_selector("/Root")
    with pytest.raises(ValueError, match="empty path selector part"):
        parse_path_selector("Root/")
    with pytest.raises(ValueError, match="empty path selector part"):
        parse_path_selector("Root//Step")


def test_parse_path_selector_rejects_reserved_chars_inside_literal_parts() -> None:
    for text in ("Root.Step", "Root+Step", "Root?Step", "Root*Step"):
        with pytest.raises(ValueError, match="reserved path selector character"):
            parse_path_selector(text)


def test_parsed_path_selector_matches_paths() -> None:
    selector = parse_path_selector("A/B/?/C")

    assert matches_path(selector, ("A", "B", "C"))
    assert matches_path(selector, ("A", "B", "X", "C"))
    assert not matches_path(selector, ("A", "B", "X", "Y", "C"))
