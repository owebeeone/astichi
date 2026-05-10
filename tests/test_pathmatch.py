from __future__ import annotations

from astichi.pathmatch import matches_path


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
    assert matches_path(("Root.Step",), ("Root.Step",))
    assert matches_path(("[0]",), ("[0]",))
    assert matches_path(("",), ("",))
    assert not matches_path(("Root.Step",), ("Root", "Step"))


def test_allows_identifier_and_indexed_build_names() -> None:
    assert matches_path(("Root", "Step[0]"), ("Root", "Step[0]"))
    assert matches_path(("Root", "."), ("Root", "Step[10]"))
