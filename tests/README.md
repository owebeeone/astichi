# Astichi Versioned Tests And Goldens

Astichi does AST-level source transformation, so emitted source must stay stable
across supported Python minor versions. The versioned harness runs the suite in
uv-managed interpreter-specific environments and records disposable run output
under `tests/actual_test_results/`.

## Golden Layout

- Fixture scripts:
  - `tests/data/gold_src/`
- Canonical pre-materialized outputs:
  - `tests/data/goldens/pre_materialized/`
- Canonical materialized outputs:
  - `tests/data/goldens/materialized/`
- Canonical structural snapshots:
  - `tests/data/goldens/structural/`
- Local actual outputs:
  - `tests/actual_test_results/<runtime>/goldens/pre_materialized/`
  - `tests/actual_test_results/<runtime>/goldens/materialized/`
  - `tests/actual_test_results/<runtime>/goldens/structural/`

Every `tests/data/gold_src/*.py` file is tested. Each script accepts two output
paths:

```bash
python tests/data/gold_src/<case>.py <pre-materialized-output.py> <materialized-output.py>
```

For either output argument, `-` means stdout.

Fixture scripts should use the shared utilities in
`tests/data/gold_src/support/golden_case.py` for argument parsing, `-` handling,
and output writes.

Pre-materialized outputs include Astichi provenance trailers so marker-bearing
source can be round-tripped. Materialized outputs omit provenance and are plain
Python source. The provenance payload is currently an opaque
pickle-based encoding, so cross-version golden comparison normalizes the payload
bytes after verifying both expected and actual trailers round-trip.

Structural snapshots are canonical JSON fixtures for intermediate lower-engine
state. During migration they are managed by dedicated structural golden tests
instead of the source fixture regeneration command. Those tests run only on the
canonical regeneration runtime (Python 3.14); other matrix runtimes skip them
because ``ast.dump``-derived template keys vary by interpreter version.

## Commands

Run the normal local suite:

```bash
uv run --with pytest pytest -q
```

By default, pytest runs each test twice when the native extension is built:
once with `ASTICHI_LOWER_ENGINE=python` and once with `ASTICHI_LOWER_ENGINE=native`.
Direct native-engine unit modules (`test_native_engine_*`) opt out of the matrix.
Set `ASTICHI_LOWER_ENGINE_MATRIX=0` to disable the dual-engine run.

Regenerate canonical goldens with Python 3.14:

```bash
uv run python tests/versioned_test_harness.py regen-goldens --python 3.14
```

Run just the golden test on one runtime:

```bash
uv run python tests/versioned_test_harness.py run-tests --python 3.14 --pytest-args tests/test_ast_goldens.py -q
```

Run the full suite on every configured runtime:

```bash
uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q
```

Show captured output for passing runs:

```bash
uv run python tests/versioned_test_harness.py run-tests-all --show-output --pytest-args -q
```

The default runtime matrix lives in `pyproject.toml` under
`[tool.astichi.test-matrix]`. It includes Python 3.15 for local `run-tests-all`;
GitHub Actions CI currently runs 3.12–3.14 only (3.15 is not on hosted runners
yet). Canonical goldens are regenerated with Python 3.14 unless that policy
changes.
