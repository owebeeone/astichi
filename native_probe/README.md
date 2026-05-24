# Native AST Probe

Scratch proof-of-concept for `dev-docs/perf-refactor/NativeAstProbe.md`.

The probe uses `rustpython-parser` through a PyO3 extension. The Rust side keeps
the parsed module as the working graph inside `LowerComposable`; CPython
`ast` objects are only built by explicit artifact-copy calls.

Build from the Astichi repo root. The produced extension is specific to the
Python interpreter used for the build:

```bash
uv run --python 3.12 python native_probe/build.py
```

Run verification:

```bash
uv run --python 3.12 python native_probe/native_probe.py verify --json
```

Run the benchmark sample:

```bash
uv run --python 3.12 python native_probe/native_probe.py bench --iterations 200 --json
```

Inspect constructor compatibility for the current interpreter. This command does
not import the native extension, so it can run across the Astichi Python matrix:

```bash
uv run python native_probe/native_probe.py compat --json
uv run --python 3.13 python native_probe/native_probe.py compat --json
uv run --python 3.14 python native_probe/native_probe.py compat --json
uv run --python 3.15 python native_probe/native_probe.py compat --json
```

Fixture probing parses every `tests/data/gold_src/*.py` file with the native
parser, then attempts conversion and compile validation. Unsupported converter
surfaces fall back to `ast.parse` and are reported explicitly:

```bash
uv run --python 3.12 python native_probe/native_probe.py fixtures --json
```

Current boundaries:

- native parser backend: `rustpython-parser 0.4.0`;
- parse runs through `Python::detach`, so other Python threads can run while the
  native parser works;
- CPython AST object construction necessarily holds the GIL;
- implemented converter surface covers the minimal probe set plus `If`, `With`,
  `For`, `While`, `Try`, annotations/defaults, starred call arguments,
  keywords, imports, and common expression nodes;
- unsupported syntax reports `NotImplementedError` and is handled by the
  fixture fallback probe.
