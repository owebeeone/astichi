"""Measure Astichi counters for the YIDL lifecycle import workload."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import time
from types import ModuleType


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--module",
        default="pyrolyze.runtime.context_lcm",
        help="module import that triggers the lifecycle decorator workload",
    )
    args = parser.parse_args(argv)

    _configure_import_paths()
    _install_black_stub_if_needed()

    from astichi.perf_counters import collect_perf_counters
    import yidl_lifecycle.lifecycle as lifecycle_module

    rows: list[dict[str, float | str]] = []
    totals: defaultdict[str, float] = defaultdict(float)
    original_lifecycle = lifecycle_module.lifecycle

    def timed_lifecycle(cls: type[object]) -> type[object]:
        row: dict[str, float | str] = {"class": f"{cls.__module__}.{cls.__qualname__}"}

        start = time.perf_counter()
        harvested = lifecycle_module.harvest_lifecycle_definition(cls)
        row["harvest"] = time.perf_counter() - start

        start = time.perf_counter()
        composable = lifecycle_module._build_lifecycle_composable(harvested)
        row["assembly"] = time.perf_counter() - start

        start = time.perf_counter()
        module_ast = composable.to_executable_ast()
        row["materialize_ast"] = time.perf_counter() - start

        namespace: dict[str, object] = {"__name__": cls.__module__}
        start = time.perf_counter()
        code = compile(
            module_ast,
            f"<timed.{cls.__module__}.{cls.__qualname__}>",
            "exec",
            dont_inherit=True,
        )
        exec(code, namespace)
        row["compile_exec_ast"] = time.perf_counter() - start

        start = time.perf_counter()
        generated = namespace["build_lifecycle_class"](
            cls,
            **dict(harvested.build_kwargs),
        )
        row["build_class"] = time.perf_counter() - start

        row["total"] = sum(
            value for key, value in row.items() if key != "class"
        )
        rows.append(row)
        for key, value in row.items():
            if key != "class":
                totals[key] += float(value)
        return generated

    lifecycle_module.lifecycle = timed_lifecycle
    try:
        with collect_perf_counters() as counters:
            started = time.perf_counter()
            __import__(args.module)
            elapsed = time.perf_counter() - started
    finally:
        lifecycle_module.lifecycle = original_lifecycle

    summary = {
        "case": args.module,
        "decorated_classes": len(rows),
        "timings_seconds": {
            "import_wall": elapsed,
            **dict(sorted(totals.items())),
        },
        "rows": rows,
        "astichi_counters": counters.snapshot(),
    }
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _configure_import_paths() -> None:
    astichi_root = Path(__file__).resolve().parents[3]
    workspace_root = astichi_root.parent
    required_projects = ("yidl", "yidl-lifecycle", "pyrolyze")
    optional_projects = (
        "grip-py",
        "grip-py-demo",
        "grip-pyrolyze",
        "grip-pyrolyze-examples",
        "huggy",
    )
    import_paths = [astichi_root / "src"]
    for project in required_projects + optional_projects:
        path = workspace_root / project / "src"
        if path.exists():
            import_paths.append(path)
        elif project in required_projects:
            raise SystemExit(f"missing expected sibling checkout: {project}")
    for path in reversed(import_paths):
        sys.path.insert(0, str(path))


def _install_black_stub_if_needed() -> None:
    try:
        __import__("black")
    except ModuleNotFoundError:
        module = ModuleType("black")

        class FileMode:
            pass

        def format_str(source: str, *, mode: object) -> str:
            return source

        module.FileMode = FileMode
        module.format_str = format_str
        sys.modules["black"] = module


if __name__ == "__main__":
    raise SystemExit(main())
