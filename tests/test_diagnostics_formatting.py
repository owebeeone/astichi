"""Tests for `format_astichi_error` shape (phase prefix + optional fields)."""

from __future__ import annotations

import re

import pytest

from astichi.diagnostics import VALID_PHASES, format_astichi_error


@pytest.mark.parametrize("phase", sorted(VALID_PHASES))
def test_phase_prefix_in_output(phase: str) -> None:
    msg = format_astichi_error(phase, "something went wrong")
    assert msg.startswith(f"{phase}: ")


def test_field_order_context_source_hint_provenance() -> None:
    msg = format_astichi_error(
        "compile",
        "bad marker",
        context="shell body",
        source="f.py:12",
        hint="fix it",
        provenance="none",
    )
    assert msg.index("context:") < msg.index("source:")
    assert msg.index("source:") < msg.index("hint:")
    assert msg.index("hint:") < msg.index("provenance:")


def test_invalid_phase_raises() -> None:
    with pytest.raises(ValueError, match="phase must be one of"):
        format_astichi_error("badphase", "x")


def test_optional_fields_omitted() -> None:
    msg = format_astichi_error("build", "oops", hint="try again")
    assert "context:" not in msg
    assert "hint: try again" in msg


def test_message_matches_phase_anchor_regex() -> None:
    msg = format_astichi_error("materialize", "missing bind", hint="use bind()")
    assert re.match(
        r"^materialize: .+; hint: .+$",
        msg,
    )
