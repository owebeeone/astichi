"""Absorb an emitted provenance trailer while keeping edited source authoritative."""

from __future__ import annotations

import astichi
from astichi.emit import extract_provenance, verify_round_trip
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    original = astichi.compile(
        """
value = 1
result = value
""",
        file_name="gold_src/provenance_absorb_roundtrip.py",
    )
    provenance_source = original.emit(provenance=True)
    verify_round_trip(provenance_source)
    assert extract_provenance(provenance_source) is not None

    edited_source = provenance_source.replace("value = 1", "value = 2")
    return astichi.compile(
        edited_source,
        file_name="gold_src/provenance_absorb_roundtrip.py",
    )


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<provenance_absorb_roundtrip>")
    assert namespace["result"] == 2
    assert "# astichi-provenance:" in pre_source


if __name__ == "__main__":
    raise SystemExit(run_case("provenance_absorb_roundtrip.py", build_case, validate_case))
