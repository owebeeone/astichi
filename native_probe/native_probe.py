from __future__ import annotations

import argparse
import ast
import json
import platform
import subprocess
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent


def _load_native() -> ModuleType:
    try:
        import _native_ast_probe_ext as native
    except ImportError as exc:
        raise RuntimeError(
            "native probe extension is not built; run "
            "`uv run python native_probe/build.py` from the astichi repo"
        ) from exc
    return native


_native_cache: ModuleType | None = None


def _native_module() -> ModuleType:
    global _native_cache
    if _native_cache is None:
        _native_cache = _load_native()
    return _native_cache


def __getattr__(name: str) -> Any:
    if name == "LowerComposable":
        return _native_module().LowerComposable
    raise AttributeError(name)


def parse_module(
    source: str,
    filename: str = "<astichi-probe>",
    *,
    location_policy: str = "native",
) -> ast.Module:
    return _native_module().parse_module(source, filename, location_policy)


def compile_composable(
    source: str,
    filename: str = "<astichi-probe>",
) -> Any:
    return _native_module().compile_composable(source, filename)


def copy_to_python_ast(
    composable: Any,
    *,
    location_policy: str = "native",
) -> ast.Module:
    return _native_module().copy_to_python_ast(composable, location_policy)


def to_source(
    composable: Any,
    *,
    location_policy: str = "native",
) -> str:
    return _native_module().to_source(composable, location_policy)


def minimal_template_scan(source: str) -> dict[str, int]:
    markers = (
        "astichi_",
        "__astichi_",
        "astichi_hole",
        "astichi_insert",
        "astichi_bind_external",
    )
    lines = source.splitlines()
    return {
        "line_count": len(lines),
        "source_bytes": len(source.encode()),
        "marker_mentions": sum(source.count(marker) for marker in markers),
        "def_mentions": sum(1 for line in lines if line.lstrip().startswith("def ")),
        "class_mentions": sum(1 for line in lines if line.lstrip().startswith("class ")),
    }


def _time_loop(iterations: int, fn) -> float:
    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    return time.perf_counter() - start


def bench_parse_convert(
    source: str,
    iterations: int = 100,
    filename: str = "<astichi-probe>",
    *,
    location_policy: str = "native",
    include_exec: bool = False,
) -> dict[str, Any]:
    if iterations <= 0:
        raise ValueError("iterations must be greater than zero")

    ast_parse_seconds = _time_loop(iterations, lambda: ast.parse(source, filename=filename))
    scan_seconds = _time_loop(iterations, lambda: minimal_template_scan(source))
    combined_seconds = _time_loop(
        iterations,
        lambda: (ast.parse(source, filename=filename), minimal_template_scan(source)),
    )

    facade_start = time.perf_counter()
    composable = None
    for _ in range(iterations):
        composable = compile_composable(source, filename)
    facade_seconds = time.perf_counter() - facade_start
    assert composable is not None

    native_mod = _native_module()
    native = native_mod.bench_parse_convert(source, iterations, filename, location_policy)
    module = copy_to_python_ast(composable, location_policy=location_policy)

    compile_seconds = _time_loop(iterations, lambda: compile(module, filename, "exec"))
    exec_seconds = None
    if include_exec:
        code = compile(module, filename, "exec")
        exec_seconds = _time_loop(iterations, lambda: exec(code, {}))

    result = {
        "python_version": platform.python_version(),
        "parser_backend": native_mod.parser_backend(),
        "native_module_build_profile": "cargo release",
        "iterations": iterations,
        "source_bytes": len(source.encode()),
        "location_policy": location_policy,
        "ast_parse_seconds": ast_parse_seconds,
        "minimal_python_scan_seconds": scan_seconds,
        "ast_parse_plus_minimal_scan_seconds": combined_seconds,
        "lower_composable_facade_seconds": facade_seconds,
        "compile_seconds": compile_seconds,
        "exec_seconds": exec_seconds,
    }
    result.update(native)
    return result


def constructor_compatibility_table() -> list[dict[str, Any]]:
    samples: dict[str, Any] = {
        "body": [],
        "type_ignores": [],
        "value": ast.Constant(value=None),
        "targets": [ast.Name(id="x", ctx=ast.Store())],
        "target": ast.Name(id="x", ctx=ast.Store()),
        "id": "x",
        "ctx": ast.Load(),
        "func": ast.Name(id="f", ctx=ast.Load()),
        "args": [],
        "keywords": [],
        "attr": "name",
        "name": "name",
        "names": [ast.alias(name="sys", asname=None)],
        "module": None,
        "level": 0,
        "returns": None,
        "type_comment": None,
        "type_params": [],
        "decorator_list": [],
        "bases": [],
        "posonlyargs": [],
        "vararg": None,
        "kwonlyargs": [],
        "kw_defaults": [],
        "kwarg": None,
        "defaults": [],
        "arg": "x",
        "annotation": None,
        "test": ast.Constant(value=True),
        "orelse": [],
        "items": [ast.withitem(context_expr=ast.Name(id="cm", ctx=ast.Load()), optional_vars=None)],
        "handlers": [],
        "finalbody": [],
        "exc": None,
        "cause": None,
        "msg": None,
        "lineno": 1,
        "tag": "",
    }
    classes = [
        ast.Module,
        ast.Expr,
        ast.Assign,
        ast.Name,
        ast.Constant,
        ast.Call,
        ast.Attribute,
        ast.FunctionDef,
        ast.arguments,
        ast.arg,
        ast.Return,
        ast.ClassDef,
        ast.Import,
        ast.ImportFrom,
        ast.If,
        ast.With,
        ast.Try,
        ast.Raise,
        ast.Assert,
        ast.alias,
        ast.keyword,
        ast.withitem,
        ast.TypeIgnore,
    ]
    table: list[dict[str, Any]] = []
    for cls in classes:
        fields = tuple(getattr(cls, "_fields", ()))
        attrs = tuple(getattr(cls, "_attributes", ()))
        kwargs = {field: samples[field] for field in fields if field in samples}
        full = _constructor_outcome(cls, kwargs)
        missing: dict[str, str] = {}
        for field in fields:
            partial = dict(kwargs)
            partial.pop(field, None)
            missing[field] = _constructor_outcome(cls, partial)["status"]
        unknown = _constructor_outcome(cls, {**kwargs, "_astichi_probe_unknown": None})
        table.append(
            {
                "class": cls.__name__,
                "fields": fields,
                "attributes": attrs,
                "full_constructor": full,
                "missing_field_status": missing,
                "unknown_keyword_status": unknown["status"],
                "location_required_for_compile": bool(set(attrs) & {"lineno", "col_offset"}),
                "notes": _compat_notes(cls.__name__),
            }
        )
    return table


def _constructor_outcome(cls: type, kwargs: dict[str, Any]) -> dict[str, str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("error", DeprecationWarning)
        try:
            cls(**kwargs)
        except DeprecationWarning as exc:
            return {"status": "deprecation-warning", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 - probe records constructor behavior
            return {"status": type(exc).__name__, "detail": str(exc)}
    if caught:
        return {"status": "warning", "detail": "; ".join(str(item.message) for item in caught)}
    return {"status": "ok", "detail": ""}


def _compat_notes(class_name: str) -> str:
    if class_name in {"FunctionDef", "AsyncFunctionDef", "ClassDef"}:
        return "Python 3.12+ exposes type_params; the probe populates [] when converting."
    if class_name in {"Module"}:
        return "compile(..., mode='exec') requires body and type_ignores."
    if class_name in {"Name", "Attribute"}:
        return "ctx must be a valid Load/Store/Del instance for compile validation."
    return ""


@dataclass
class FixtureProbeResult:
    path: str
    parse: str
    convert: str
    compile: str
    fallback: str | None


def scan_gold_fixtures(location_policy: str = "native") -> list[FixtureProbeResult]:
    results: list[FixtureProbeResult] = []
    for path in sorted((REPO_ROOT / "tests" / "data" / "gold_src").glob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        source = path.read_text()
        try:
            composable = compile_composable(source, rel)
        except Exception as exc:  # noqa: BLE001 - probe report
            try:
                ast.parse(source, filename=rel)
            except Exception as fallback_exc:  # noqa: BLE001
                results.append(
                    FixtureProbeResult(rel, type(exc).__name__, "skipped", "skipped", type(fallback_exc).__name__)
                )
            else:
                results.append(FixtureProbeResult(rel, type(exc).__name__, "skipped", "fallback-ok", "ast.parse"))
            continue

        try:
            module = copy_to_python_ast(composable, location_policy=location_policy)
        except Exception as exc:  # noqa: BLE001
            ast.parse(source, filename=rel)
            results.append(FixtureProbeResult(rel, "native-ok", type(exc).__name__, "fallback-ok", "ast.parse"))
            continue

        try:
            compile(module, rel, "exec")
        except Exception as exc:  # noqa: BLE001
            ast.parse(source, filename=rel)
            results.append(FixtureProbeResult(rel, "native-ok", "native-ok", type(exc).__name__, "ast.parse"))
        else:
            results.append(FixtureProbeResult(rel, "native-ok", "native-ok", "native-ok", None))
    return results


def _sample_source() -> str:
    return """\
import math
from collections import deque

class Box:
    def __init__(self, value: int = 1):
        self.value = value

def compute(items, *extra, scale=2, **kw):
    total = 0
    for item in items:
        if item:
            total = total + item
    try:
        return math.sqrt(total * scale)
    except ValueError as exc:
        return kw.get("fallback", 0)
"""


def verify() -> dict[str, Any]:
    source = _sample_source()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        module = parse_module(source, location_policy="native")
        code = compile(module, "<native-probe-verify>", "exec")
        ns: dict[str, Any] = {}
        exec(code, ns)
        value = ns["compute"]([1, 3], fallback=10)
        composable = compile_composable(source)
        copied = copy_to_python_ast(composable)
        compile(copied, "<native-probe-copy>", "exec")
        rendered = to_source(composable)
    fixtures = scan_gold_fixtures()
    return {
        "sample_compute_result": value,
        "sample_node_counts": composable.node_counts(),
        "rendered_source_prefix": rendered.splitlines()[:5],
        "fixture_count": len(fixtures),
        "fixture_native_compile_ok": sum(1 for result in fixtures if result.fallback is None),
        "fixture_fallback_count": sum(1 for result in fixtures if result.fallback is not None),
        "fixture_fallbacks": [result.__dict__ for result in fixtures if result.fallback is not None],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["verify", "bench", "compat", "fixtures"])
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--location-policy", choices=["native", "fix_missing"], default="native")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "verify":
        data = verify()
    elif args.command == "bench":
        data = bench_parse_convert(_sample_source(), args.iterations, location_policy=args.location_policy)
    elif args.command == "compat":
        data = constructor_compatibility_table()
    else:
        data = [result.__dict__ for result in scan_gold_fixtures(args.location_policy)]

    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
