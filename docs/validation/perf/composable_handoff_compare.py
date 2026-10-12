"""Paired, fresh-process YIDL generation and native-binding timing probe."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout
import functools
import io
import json
import os
from pathlib import Path
import runpy
import statistics
import subprocess
import sys
import time


def worker(root: Path, engine: str) -> dict[str, object]:
    os.environ["ASTICHI_LOWER_ENGINE"] = engine
    sys.path.insert(0, str(root / "src"))
    import astichi
    from astichi.model import basic
    from astichi.perf_counters import collect_perf_counters

    calls: Counter[str] = Counter()
    for name in ("_native_reproject_specialized", "_native_specialization_session", "_rebuild_composable"):
        original = getattr(basic, name)

        def counted(*args, _function=original, _name=name, **kwargs):
            calls[_name] += 1
            return _function(*args, **kwargs)

        setattr(basic, name, functools.wraps(original)(counted))
    script = root / "docs/validation/perf/yidl_split_dataclass_profile.py"
    output = io.StringIO()
    profile = runpy.run_path(str(script))
    with collect_perf_counters() as counters, redirect_stdout(output):
        profile["main"]([])
    result = json.loads(output.getvalue())
    result["handoff_calls"] = dict(calls)
    result["astichi_counters"] = counters.snapshot()
    result["generation_seconds"] = sum(result["timings_seconds"].values())
    piece = astichi.compile("result = first__astichi_arg__ + second__astichi_arg__\n")
    started = time.perf_counter()
    for _ in range(100):
        piece.bind_identifier(first="a").bind_identifier(second="b")
    result["binding_100_seconds"] = time.perf_counter() - started
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--engine", choices=("python", "native"), default="native")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker.resolve(), args.engine)))
        return
    if args.baseline is None or args.candidate is None or args.samples < 2:
        parser.error("provide baseline, candidate, and at least two samples")
    roots = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    rows: dict[str, list[dict[str, object]]] = {key: [] for key in roots}
    # Discard one warm-up per variant; alternate pair order to reduce drift.
    for trial in range(args.samples + 1):
        order = tuple(roots) if trial % 2 else tuple(reversed(roots))
        for variant in order:
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(roots[variant]), "--engine", args.engine]
            row = json.loads(subprocess.check_output(command, cwd=roots[variant], text=True))
            if trial:
                rows[variant].append(row)
    summary = {}
    for variant, samples in rows.items():
        summary[variant] = {
            metric: {"median": statistics.median(float(row[metric]) for row in samples),
                     "min": min(float(row[metric]) for row in samples),
                     "max": max(float(row[metric]) for row in samples)}
            for metric in ("generation_seconds", "binding_100_seconds")
        }
    print(json.dumps({"engine": args.engine, "samples": rows, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
