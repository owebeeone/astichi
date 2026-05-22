"""Golden case for additive elif clause targets."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def _root_source() -> str:
    return """
def dispatch(event_type, payload):
    if event_type == "":
        raise ValueError("empty event_type")
    elif astichi_elif(branches):
        pass
    elif event_type == "manual":
        return ("manual", payload)
    else:
        return ("fallback", event_type)


def nested_dispatch(enabled, event_type):
    if not enabled:
        return ("off", event_type)
    try:
        if event_type == "base":
            return ("base", event_type)
        elif astichi_elif(nested_branches):
            pass
        else:
            return ("nested-fallback", event_type)
    finally:
        marker = "done"
"""


def _create_branch_source() -> str:
    return """
def astichi_elif():
    astichi_import(event_type)
    astichi_import(payload)
    if event_type == "create":
        result = ("create", payload)
        return result
"""


def _delete_branch_source() -> str:
    return """
def astichi_elif():
    astichi_import(event_type)
    astichi_import(payload)
    if event_type == "delete":
        result = ("delete", payload)
        return result
"""


def _nested_branch_source() -> str:
    return """
def astichi_elif():
    astichi_import(event_type)
    if event_type == "nested":
        return ("nested", event_type)
"""


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            _root_source(),
            file_name="gold_src/elif_targets.py",
        )
    )
    builder.add.Create(
        astichi.compile(
            _create_branch_source(),
            file_name="gold_src/elif_targets.py",
        )
    )
    builder.add.Delete(
        astichi.compile(
            _delete_branch_source(),
            file_name="gold_src/elif_targets.py",
        )
    )
    builder.add.Nested(
        astichi.compile(
            _nested_branch_source(),
            file_name="gold_src/elif_targets.py",
        )
    )
    builder.Root.branches.add.Delete(order=20)
    builder.Root.branches.add.Create(order=10)
    builder.Root.nested_branches.add.Nested(order=0)
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<elif_targets>")
    assert namespace["dispatch"]("create", 1) == ("create", 1)
    assert namespace["dispatch"]("delete", 2) == ("delete", 2)
    assert namespace["dispatch"]("manual", 3) == ("manual", 3)
    assert namespace["dispatch"]("other", 4) == ("fallback", "other")
    assert namespace["nested_dispatch"](True, "nested") == ("nested", "nested")
    assert namespace["nested_dispatch"](True, "base") == ("base", "base")
    assert namespace["nested_dispatch"](False, "nested") == ("off", "nested")
    assert "@astichi_insert(branches, kind='elif'" in pre_source
    assert "@astichi_insert(nested_branches, kind='elif'" in pre_source
    assert "result__astichi_scoped_" in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("elif_targets.py", build_case, validate_case))
