"""Measure cold and warm generated-AST cache paths on a synthetic graph."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from collections.abc import Callable
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import TypeVar

import astichi
from astichi.cache import GeneratedAstCache

T = TypeVar("T")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=80)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args(argv)

    if args.cache_dir is None:
        with tempfile.TemporaryDirectory() as temp_dir:
            return _run_probe(width=args.width, cache_dir=Path(temp_dir))
    return _run_probe(width=args.width, cache_dir=args.cache_dir)


def _run_probe(*, width: int, cache_dir: Path) -> int:
    import astichi.materialize as materialize_module

    timings: dict[str, float] = {}
    counts: Counter[str] = Counter()
    builder = _make_builder(width)
    cache = GeneratedAstCache(cache_dir)

    def timed(name: str, func: Callable[[], T]) -> T:
        start = time.perf_counter()
        try:
            return func()
        finally:
            timings[name] = time.perf_counter() - start

    original_build_merge = materialize_module.build_merge

    def build_merge_wrapper(*args: object, **kwargs: object) -> object:
        counts["build_merge_total"] += 1
        return original_build_merge(*args, **kwargs)

    materialize_module.build_merge = build_merge_wrapper
    try:
        timed("cold_uncached_ast", builder.to_executable_ast)
        timed("cold_cache_write_ast", lambda: builder.to_executable_ast(cache=cache))
        warm_in_process = timed(
            "warm_in_process_cache_ast",
            lambda: builder.to_executable_ast(cache=cache),
        )
        warm_disk = timed(
            "warm_disk_cache_ast",
            lambda: builder.to_executable_ast(cache=GeneratedAstCache(cache_dir)),
        )
        source = timed("source_unparse_from_cached_ast", lambda: ast.unparse(warm_disk))
        timed(
            "compile_cached_ast",
            lambda: compile(warm_in_process, "<astichi-cache-profile>", "exec"),
        )
    finally:
        materialize_module.build_merge = original_build_merge

    summary = {
        "case": "generated_ast_cache_synthetic",
        "width": width,
        "counts": dict(counts),
        "timings_seconds": timings,
        "source_bytes": len(source.encode("utf-8")),
    }
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _make_builder(width: int):
    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(body)\n"))
    for index in range(width):
        name = f"Step{index}"
        builder.add(name, astichi.compile(f"value_{index} = {index}\n"))
        builder.Root.body.add(name, order=index)
    return builder


if __name__ == "__main__":
    raise SystemExit(main())
