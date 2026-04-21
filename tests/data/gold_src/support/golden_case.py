from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
import sys

import astichi
from astichi.model import BasicComposable


Validation = Callable[[astichi.Composable, BasicComposable, str, str], None]


def write_source(path: str | Path, source: str) -> None:
    if not source.endswith("\n"):
        source += "\n"
    if str(path) == "-":
        sys.stdout.write(source)
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(source, encoding="utf-8")


def exec_source(source: str, file_name: str) -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(compile(source, file_name, "exec"), namespace)  # noqa: S102
    return namespace


def run_case(
    case_name: str,
    build_case: Callable[[], astichi.Composable],
    validate: Validation | None = None,
    argv: Sequence[str] | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        raise SystemExit(
            f"usage: {case_name} <pre-materialized-output.py> <materialized-output.py>"
        )

    composable = build_case()
    materialized = composable.materialize()
    if not isinstance(materialized, BasicComposable):
        raise TypeError(f"{case_name}: materialize() returned {type(materialized)!r}")

    pre_source = composable.emit(provenance=True)
    materialized_source = materialized.emit(provenance=False)
    if validate is not None:
        validate(composable, materialized, pre_source, materialized_source)

    write_source(args[0], pre_source)
    write_source(args[1], materialized_source)
    return 0
