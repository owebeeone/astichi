"""Bind external tuple and mapping values before materialization."""

from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        """
astichi_bind_external(fields)
astichi_bind_external(config)

result = (fields, config["mode"], config["enabled"])
""",
        file_name="gold_src/bind_external_literal.py",
    ).bind(
        fields=("name", "email"),
        config={"mode": "fast", "enabled": True},
    )


if __name__ == "__main__":
    raise SystemExit(run_case("bind_external_literal.py", build_case))
