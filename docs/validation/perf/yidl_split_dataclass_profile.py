"""Profile the YIDL split dataclass workload from the Astichi checkout.

This script is intentionally a validation helper. It discovers the sibling
``yidl`` checkout from the current Astichi repository layout, instruments hot
Astichi call sites with local monkeypatches, and prints a JSON timing summary.
It does not modify production code.
"""

from __future__ import annotations

import argparse
import cProfile
from collections import Counter
from collections.abc import Callable
import json
import os
from pathlib import Path
import pstats
import sys
import time
from types import ModuleType
from typing import Any, TypeVar

T = TypeVar("T")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="measure parse/generator/exec phases only",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        help="write a cProfile dump for the decorator-runtime phase",
    )
    parser.add_argument(
        "--profile-top",
        type=int,
        default=0,
        help="also print the top N cumulative profiler rows to stderr",
    )
    args = parser.parse_args(argv)

    yidl_root = _configure_import_paths()
    _install_black_stub_if_needed()
    profile_path = args.profile
    if profile_path is not None and not profile_path.is_absolute():
        profile_path = Path.cwd() / profile_path

    previous_cwd = Path.cwd()
    os.chdir(yidl_root)
    try:
        return _run_probe(args, profile_path)
    finally:
        os.chdir(previous_cwd)


def _run_probe(args: argparse.Namespace, profile_path: Path | None) -> int:
    import astichi.materialize as materialize_pkg
    import astichi.materialize.api as materialize_api
    from astichi.assembler.scope import AssemblyScope
    from yidl.generation.data_def_sys import emit_concept_runtime_source
    from yidl_update_a_dataclasses_split import _compile_concept, _container

    counts: Counter[str] = Counter()
    timings: dict[str, float] = {}

    def timed(name: str, func: Callable[[], T]) -> T:
        start = time.perf_counter()
        try:
            return func()
        finally:
            timings[name] = time.perf_counter() - start

    concept = timed("compile_concept", _compile_concept)
    decorator_source = timed(
        "emit_concept_runtime_source",
        lambda: emit_concept_runtime_source(
            concept.plan.build_data_definition(),
            resources=concept.resources,
            assembly_plan=concept,
        ),
    )
    namespace: dict[str, Any] = {}
    timed("exec_decorator_source", lambda: exec(decorator_source, namespace))
    container = timed("container_build", lambda: _container(namespace))

    if not args.skip_runtime:
        original_refresh = getattr(AssemblyScope, "_refresh_inventory", None)
        original_build_merge = materialize_pkg.build_merge
        original_shell = materialize_api._make_block_insert_shell
        original_deepcopy = materialize_api.copy.deepcopy

        def refresh_wrapper(self: AssemblyScope) -> None:
            if original_refresh is None:
                raise AssertionError("refresh wrapper installed without target")
            counts["refresh_calls"] += 1
            before = counts["build_merge_total"]
            result = original_refresh(self)
            counts["build_merge_from_refresh"] += (
                counts["build_merge_total"] - before
            )
            return result

        def build_merge_wrapper(*wrapper_args: Any, **wrapper_kwargs: Any) -> Any:
            counts["build_merge_total"] += 1
            start = time.perf_counter()
            try:
                return original_build_merge(*wrapper_args, **wrapper_kwargs)
            finally:
                counts["build_merge_seconds"] += time.perf_counter() - start

        def shell_wrapper(*wrapper_args: Any, **wrapper_kwargs: Any) -> Any:
            counts["make_block_insert_shell_calls"] += 1
            start = time.perf_counter()
            try:
                return original_shell(*wrapper_args, **wrapper_kwargs)
            finally:
                counts["make_block_insert_shell_seconds"] += (
                    time.perf_counter() - start
                )

        def deepcopy_wrapper(*wrapper_args: Any, **wrapper_kwargs: Any) -> Any:
            counts["deepcopy_calls"] += 1
            start = time.perf_counter()
            try:
                return original_deepcopy(*wrapper_args, **wrapper_kwargs)
            finally:
                counts["deepcopy_seconds"] += time.perf_counter() - start

        if original_refresh is not None:
            AssemblyScope._refresh_inventory = refresh_wrapper
        materialize_pkg.build_merge = build_merge_wrapper
        materialize_api._make_block_insert_shell = shell_wrapper
        materialize_api.copy.deepcopy = deepcopy_wrapper
        try:
            if profile_path is None:
                generated_source = timed(
                    "build_dataclass_module_emit_commented",
                    lambda: namespace["build_DataclassModule"](
                        container
                    ).emit_commented(),
                )
            else:
                profile = cProfile.Profile()
                start = time.perf_counter()
                profile.enable()
                generated_source = namespace["build_DataclassModule"](
                    container
                ).emit_commented()
                profile.disable()
                timings["build_dataclass_module_emit_commented"] = (
                    time.perf_counter() - start
                )
                profile_path.parent.mkdir(parents=True, exist_ok=True)
                profile.dump_stats(profile_path)
                if args.profile_top:
                    stats = pstats.Stats(profile, stream=sys.stderr)
                    stats.strip_dirs().sort_stats("cumulative").print_stats(
                        args.profile_top
                    )
        finally:
            if original_refresh is not None:
                AssemblyScope._refresh_inventory = original_refresh
            materialize_pkg.build_merge = original_build_merge
            materialize_api._make_block_insert_shell = original_shell
            materialize_api.copy.deepcopy = original_deepcopy

        counts["generated_source_bytes"] = len(generated_source.encode("utf-8"))

    summary = {
        "case": "yidl_update_a_dataclasses_split",
        "timings_seconds": timings,
        "counts": dict(counts),
    }
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _configure_import_paths() -> Path:
    astichi_root = Path(__file__).resolve().parents[3]
    workspace_root = astichi_root.parent
    yidl_root = workspace_root / "yidl"
    import_paths = [
        astichi_root / "src",
        yidl_root / "src",
        yidl_root / "tests" / "data" / "gold_src",
    ]
    missing = [path for path in import_paths if not path.exists()]
    if missing:
        formatted = ", ".join(str(path) for path in missing)
        raise SystemExit(f"missing expected import paths: {formatted}")
    for path in reversed(import_paths):
        sys.path.insert(0, str(path))
    return yidl_root


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
