"""Measure Astichi counters for the YIDL lifecycle import workload."""

from __future__ import annotations

import argparse
from collections import Counter
from collections import defaultdict
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType


HOT_COUNTERS = (
    "rebuild_composable",
    "candidate_lookup_lower",
    "assembly_scope_apply",
    "to_executable_ast",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--module",
        default="pyrolyze.runtime.context_lcm",
        help="module import that triggers the lifecycle decorator workload",
    )
    parser.add_argument(
        "--engine",
        choices=("python", "auto", "native"),
        default="auto",
        help=(
            "lower-engine request for this process; auto clears "
            "ASTICHI_LOWER_ENGINE"
        ),
    )
    parser.add_argument(
        "--require-native-counters",
        action="store_true",
        help="fail if no Astichi native_* counters are observed",
    )
    args = parser.parse_args(argv)

    _configure_engine_request(args.engine)
    _configure_import_paths()
    _install_black_stub_if_needed()

    from astichi.lower_engine.native import select_lower_engine
    from astichi.perf_counters import collect_perf_counters
    import yidl.generation.assembly_runtime as assembly_runtime
    import yidl_lifecycle.lifecycle as lifecycle_module

    lower_engine = select_lower_engine(args.engine)
    rows: list[dict[str, float | str]] = []
    totals: defaultdict[str, float] = defaultdict(float)
    yidl_counts: Counter[str] = Counter()
    yidl_counts.update(
        {
            "contribution_apply_calls": 0,
            "contribution_no_match": 0,
            "contribution_select_calls": 0,
            "edge_calls": 0,
            "empty_resource_noops": 0,
        }
    )
    yidl_seconds: defaultdict[str, float] = defaultdict(float)
    original_lifecycle = lifecycle_module.lifecycle
    original_run_edge = assembly_runtime._run_edge
    original_select_contribution = assembly_runtime._select_contribution
    original_apply_contribution = assembly_runtime._apply_contribution

    def time_yidl(name: str, func, *args, **kwargs):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            yidl_seconds[name] += time.perf_counter() - start

    def counted_run_edge(*args, **kwargs):  # type: ignore[no-untyped-def]
        yidl_counts["edge_calls"] += 1
        return time_yidl("edge_seconds", original_run_edge, *args, **kwargs)

    def counted_select_contribution(*args, **kwargs):  # type: ignore[no-untyped-def]
        yidl_counts["contribution_select_calls"] += 1
        result = time_yidl(
            "contribution_select_seconds",
            original_select_contribution,
            *args,
            **kwargs,
        )
        if result is None:
            yidl_counts["contribution_no_match"] += 1
        return result

    def counted_apply_contribution(
        concept,  # type: ignore[no-untyped-def]
        contribution,
        *args,
        **kwargs,
    ):
        yidl_counts["contribution_apply_calls"] += 1
        if (
            not contribution.diagnostic
            and assembly_runtime._is_empty_resource_contribution(concept, contribution)
        ):
            yidl_counts["empty_resource_noops"] += 1
        return time_yidl(
            "contribution_apply_seconds",
            original_apply_contribution,
            concept,
            contribution,
            *args,
            **kwargs,
        )

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
    assembly_runtime._run_edge = counted_run_edge
    assembly_runtime._select_contribution = counted_select_contribution
    assembly_runtime._apply_contribution = counted_apply_contribution
    try:
        with collect_perf_counters() as counters:
            started = time.perf_counter()
            __import__(args.module)
            elapsed = time.perf_counter() - started
    finally:
        lifecycle_module.lifecycle = original_lifecycle
        assembly_runtime._run_edge = original_run_edge
        assembly_runtime._select_contribution = original_select_contribution
        assembly_runtime._apply_contribution = original_apply_contribution

    astichi_snapshot = counters.snapshot()
    counter_summary = _counter_summary(astichi_snapshot)
    if args.require_native_counters and not counter_summary["native_counts"]:
        raise SystemExit("expected at least one native_* Astichi counter")

    summary = {
        "case": args.module,
        "decorated_classes": len(rows),
        "engine_request": args.engine,
        "selected_lower_engine": lower_engine.snapshot(),
        "timings_seconds": {
            "import_wall": elapsed,
            **dict(sorted(totals.items())),
        },
        "rows": rows,
        "astichi_counters": astichi_snapshot,
        "astichi_counter_summary": counter_summary,
        "yidl_runtime_counters": {
            "counts": dict(sorted(yidl_counts.items())),
            "seconds": dict(sorted(yidl_seconds.items())),
        },
    }
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _configure_engine_request(engine: str) -> None:
    if engine == "auto":
        os.environ.pop("ASTICHI_LOWER_ENGINE", None)
    else:
        os.environ["ASTICHI_LOWER_ENGINE"] = engine


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


def _counter_summary(
    snapshot: dict[str, dict[str, int | float]],
) -> dict[str, dict[str, int | float] | list[dict[str, int | float | str]]]:
    counts = snapshot["counts"]
    seconds = snapshot["seconds"]
    native_counts = {
        key: value for key, value in counts.items() if key.startswith("native_")
    }
    native_seconds = {
        key: value for key, value in seconds.items() if key.startswith("native_")
    }
    python_counts = {
        key: value for key, value in counts.items() if not key.startswith("native_")
    }
    python_seconds = {
        key: value for key, value in seconds.items() if not key.startswith("native_")
    }
    return {
        "hot_counts": {key: counts.get(key, 0) for key in HOT_COUNTERS},
        "hot_seconds": {key: seconds.get(key, 0.0) for key in HOT_COUNTERS},
        "native_counts": dict(sorted(native_counts.items())),
        "native_seconds": dict(sorted(native_seconds.items())),
        "top_python_counts": _top_counter_items(python_counts, "count"),
        "top_python_seconds": _top_counter_items(python_seconds, "seconds"),
    }


def _top_counter_items(
    values: dict[str, int | float],
    value_key: str,
    *,
    limit: int = 12,
) -> list[dict[str, int | float | str]]:
    rows = [
        {"name": key, value_key: value}
        for key, value in sorted(
            values.items(),
            key=lambda item: (-float(item[1]), item[0]),
        )
        if value
    ]
    return rows[:limit]


if __name__ == "__main__":
    raise SystemExit(main())
