# Astichi V2 test augments

Plan to add PyRolyze-style multi-version and golden-output testing to
Astichi.

Target paths below are relative to the Astichi repository root. PyRolyze source
paths are shown relative to the PyRolyze repository root.

## Goal

- Run the Astichi test suite under every supported Python minor version.
- Check canonical pre-materialized and materialized emitted-code corpora against
  every supported runtime.
- Keep actual run artifacts local and disposable.
- Avoid committing absolute machine paths in docs, tests, fixtures, goldens, or
  generated reports.

Non-goal: introduce version-specific Astichi semantics. If a runtime produces
different emitted source, that is a regression until the design explicitly says
otherwise.

## PyRolyze pieces to port

Copy the structure, then adapt for Astichi:

| PyRolyze source | Astichi target | Notes |
|---|---|---|
| `tests/versioned_test_harness.py` | `tests/versioned_test_harness.py` | Keep `uv` venv setup, `run-tests`, `run-tests-all`, captured stdout/stderr, junit output. Remove AST-kernel discovery and kernel-tag routing. |
| `tests/test_versioned_test_harness.py` | `tests/test_versioned_test_harness.py` | Adapt assertions to Astichi paths and avoid absolute path literals. |
| `tests/test_ast_goldens.py` | `tests/test_ast_goldens.py` | Compare Astichi pre-materialized and materialized outputs to canonical goldens. |
| `tests/data/gold_cases.toml` | do not copy | Astichi should discover executable fixture scripts from `tests/data/gold_src/*.py`. |
| `tests/data/gold_src/` | `tests/data/gold_src/` | New independently runnable Astichi fixture scripts; do not copy PyRolyze cases. |
| `tests/data/v3_14/goldens/` | `tests/data/goldens/` | Astichi uses canonical `pre_materialized/` and `materialized/` golden directories, not versioned kernel directories. |
| `tests/README.md` | `tests/README.md` | Add versioned-run and golden-regeneration instructions. |

Also update:

- `.gitignore`
  - add `tests/.uv-venvs/`
  - add `tests/actual_test_results/`
- `pyproject.toml`
  - add `[tool.astichi.test-matrix]`
  - initial value: `python = ["3.12", "3.13", "3.14", "3.15"]`
  - `3.15` is the current alpha/pre-release runtime; keep Python `3.14` as the
    canonical golden-regeneration runtime until there is a stable newer choice.
  - either add a `test` optional dependency group or make the harness install
    the existing `dev` group.

## Target layout

```text
tests/
  versioned_test_harness.py
  test_versioned_test_harness.py
  test_ast_goldens.py
  README.md
  data/
    gold_src/
      support/
        golden_case.py
      compile_basic.py
      bind_external_literal.py
      inline_insert_block.py
      call_argument_payload.py
      identifier_bind.py
      boundary_pass_export.py
      hygiene_scope_collision.py
      hygiene_boundary_isolation.py
      provenance_absorb_roundtrip.py
      unroll_literal.py
      unroll_bind_domain.py
      staged_build_trace.py
    goldens/
      pre_materialized/
        compile_basic.py
        bind_external_literal.py
        inline_insert_block.py
        call_argument_payload.py
        identifier_bind.py
        boundary_pass_export.py
        hygiene_scope_collision.py
        hygiene_boundary_isolation.py
        provenance_absorb_roundtrip.py
        unroll_literal.py
        unroll_bind_domain.py
        staged_build_trace.py
      materialized/
        compile_basic.py
        bind_external_literal.py
        inline_insert_block.py
        call_argument_payload.py
        identifier_bind.py
        boundary_pass_export.py
        hygiene_scope_collision.py
        hygiene_boundary_isolation.py
        provenance_absorb_roundtrip.py
        unroll_literal.py
        unroll_bind_domain.py
        staged_build_trace.py
  actual_test_results/
    py3_12/
      goldens/
        pre_materialized/
        materialized/
    py3_13/
      goldens/
        pre_materialized/
        materialized/
    py3_14/
      goldens/
        pre_materialized/
        materialized/
    py3_15/
      goldens/
        pre_materialized/
        materialized/
  .uv-venvs/
    py3_12/
    py3_13/
    py3_14/
    py3_15/
```

Only `tests/data/gold_src/` and `tests/data/goldens/` are checked in.
`tests/actual_test_results/` and `tests/.uv-venvs/` stay ignored.

## Harness shape

Adapt `tests/versioned_test_harness.py` around these Astichi concepts:

- `runtime_tag((3, 14)) -> "py3_14"`
- `actual_results_dir(project_root, runtime_version=...)`
  - `tests/actual_test_results/<runtime>/`
- `data_gold_src_dir(project_root)`
  - `tests/data/gold_src/`
- `data_golden_dir(project_root, phase=...)`
  - `tests/data/goldens/pre_materialized/`
  - `tests/data/goldens/materialized/`
- `discover_golden_cases(project_root)`
  - discovers every `tests/data/gold_src/*.py`
- `run_golden_case(script_path, pre_materialized_output, materialized_output)`
  - runs the fixture script with exactly two output-path arguments
  - invokes the script with `sys.executable` from the active test runtime
- `load_supported_runtime_specs(pyproject_path)`
  - reads `[tool.astichi.test-matrix].python`
- `load_install_requirements(pyproject_path)`
  - includes build-system requirements, runtime dependencies, and the chosen
    test/dev optional dependency group.

Keep these commands:

```bash
uv run python tests/versioned_test_harness.py run-tests --python 3.14 --pytest-args -q
uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q
uv run python tests/versioned_test_harness.py run-tests-all --show-output --pytest-args -q
```

Add this command:

```bash
uv run python tests/versioned_test_harness.py regen-goldens --python 3.14
```

`regen-goldens` writes both canonical output sets under `tests/data/goldens/`
using one chosen interpreter. Use the newest configured stable runtime, which is
Python `3.14` while `3.15` is still alpha/pre-release. Then `run-tests-all`
proves every configured runtime emits the same code.

## Golden test contract

`tests/test_ast_goldens.py` should:

1. Discover every `tests/data/gold_src/*.py` fixture script.
2. Verify discovered fixture scripts and both golden directories have the same
   case set.
3. For each case, run the fixture script with two output paths:
   - actual pre-materialized source
   - actual materialized source
4. Require the script to exit successfully and create both files.
   - Fixture scripts may perform internal assertions before writing outputs.
   - Use internal assertions for semantic contracts that are not visible from
     plain emitted source diffs alone.
5. Write actual output to
   - `tests/actual_test_results/<runtime>/goldens/pre_materialized/<case>.py`
   - `tests/actual_test_results/<runtime>/goldens/materialized/<case>.py`
6. Compare actual output to:
   - `tests/data/goldens/pre_materialized/<case>.py`
   - `tests/data/goldens/materialized/<case>.py`
7. Compile both emitted sources with `compile(..., "exec")` as smoke checks.

Pre-materialized golden output should use `emit(provenance=True)` so
marker-bearing source also locks the provenance trailer and round-trip surface.
Materialized golden output should use `emit(provenance=False)` so the runnable
result remains plain source. The golden test should parse pre-materialized
marker-bearing output, not bytecode-compile it; some marker directive forms are
valid AST/source surfaces but are not intended to execute before materialize.

Because the current provenance payload is an opaque pickle-based encoding, its
bytes are not expected to be stable across Python minor versions. The golden
test should verify that both expected and actual pre-materialized outputs contain
valid round-trippable provenance, then compare the source with the payload bytes
normalized. Materialized outputs still compare byte-for-byte.

Use virtual file names such as `gold_src/<case>.py` when fixture scripts call
`astichi.compile(...)`. Do not pass absolute fixture paths into
`astichi.compile(...)`.

## Fixture contract

Every `tests/data/gold_src/*.py` file is an independently runnable golden-case
script and is tested by default. Shared fixture utilities live under
`tests/data/gold_src/support/`; discovery only treats top-level `*.py` files as
cases.

Each script must accept exactly two positional arguments:

```bash
python tests/data/gold_src/<case>.py <pre-materialized-output.py> <materialized-output.py>
```

For either output argument, `-` means write that phase to stdout instead of a
file. The harness should use real file paths for golden comparison and reserve
`-` for manual inspection.

The script owns the case setup: source strings, `astichi.compile(...)`,
builder wiring, binds, identifier binds, unroll options, and any staged-build
steps. It should write:

- pre-materialized source to the first path
- materialized source to the second path

Recommended shape:

```python
from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    ...


if __name__ == "__main__":
    raise SystemExit(run_case("case.py", build_case))
```

Cases that need only `compile(...)` can still be scripts; do not add a second
declarative fixture format. Human comments are fine, but test behavior should
come from the script, not from metadata comments.

## Initial corpus

Start with a small corpus that exercises the surfaces most likely to drift
across Python versions:

- `compile_basic.py`
  - simple statements and function/class syntax.
- `bind_external_literal.py`
  - `astichi_bind_external(...)`, tuple/list/dict literal insertion.
- `inline_insert_block.py`
  - `astichi_hole(...)` plus block-form `@astichi_insert(...)`.
- `call_argument_payload.py`
  - `astichi_funcargs(...)` lowering and materialized call output.
- `identifier_bind.py`
  - `__astichi_arg__`, `__astichi_keep__`, and `bind_identifier(...)`.
- `boundary_pass_export.py`
  - `astichi_import(...)`, `astichi_pass(...)`, `astichi_export(...)`.
- `hygiene_scope_collision.py`
  - same spelling defined in outer/root and inserted inner scopes; locks
    rename-on-collision and `__astichi_scoped_<n>` stability where it is part
    of emitted source.
- `hygiene_boundary_isolation.py`
  - sibling roots, nested insert shells, `astichi_import(...)`, and
    `astichi_pass(...)`; proves free names do not silently capture outer names
    and explicitly wired names do thread across scopes.
- `provenance_absorb_roundtrip.py`
  - emit a pre-materialized composable with `provenance=True`, verify it with
    `astichi.emit.verify_round_trip(...)`, recompile the provenance-bearing
    source through `astichi.compile(...)`, and write the absorbed
    pre-materialized output with `provenance=True` and materialized output with
    `provenance=False`.
  - The fixture should also edit or regenerate a harmless source detail before
    recompiling if needed to prove source authority: provenance may restore AST
    location information, but must not preserve hidden semantic state.
- `unroll_literal.py`
  - literal `astichi_for(...)` domain with indexed hole output.
- `unroll_bind_domain.py`
  - `astichi_bind_external(...)` feeding an unroll domain.
- `staged_build_trace.py`
  - one scripted case for build-stage reuse, ordering, and `builder.assign`.

Keep each case narrow. These are output-stability sentinels, not replacements
for the existing focused unit tests. The scoping/hygiene cases are not optional:
they cover one of Astichi's core semantic promises and should land in the first
usable corpus.

## Rollout shape

This can be implemented in one coding pass, but it should not be treated as one
undifferentiated checkpoint.

Recommended checkpoints:

1. Infrastructure
   - harness, ignored output paths, test-matrix config, and one trivial script
     fixture.
   - proves the two-output executable-fixture contract works.
2. Core semantic corpus
   - add bind, insert, call-argument, identifier, boundary, scoping/hygiene, and
     provenance-absorption scripts.
   - regenerate both golden directories and run the golden test on one runtime.
3. Cross-version gate
   - run `run-tests-all`, inspect per-runtime actual outputs, and only then
     treat the corpus as stable.

Do not land a large corpus before the harness has passed at least one small
fixture end to end; otherwise failures blur harness bugs, fixture bugs, and real
Astichi regressions.

## Implementation order

1. Add `.gitignore` entries and `[tool.astichi.test-matrix]`.
2. Copy/adapt `tests/versioned_test_harness.py`.
3. Copy/adapt `tests/test_versioned_test_harness.py`.
4. Add `tests/test_ast_goldens.py`.
5. Add initial `tests/data/gold_src/` scripts and empty
   `tests/data/goldens/pre_materialized/` and
   `tests/data/goldens/materialized/`.
6. Run `regen-goldens --python 3.14`.
7. Run `run-tests --python 3.14 --pytest-args tests/test_ast_goldens.py -q`.
8. Run `run-tests-all --pytest-args -q`.
9. Document the commands in `tests/README.md`.

## Exit criteria

- `uv run --with pytest pytest -q` passes in the local default environment.
- `uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q`
  passes for every configured runtime.
- Golden actual outputs are written under
  `tests/actual_test_results/<runtime>/goldens/pre_materialized/` and
  `tests/actual_test_results/<runtime>/goldens/materialized/`.
- No checked-in file contains absolute filesystem paths.
- The canonical `tests/data/goldens/pre_materialized/` and
  `tests/data/goldens/materialized/` directories are the only checked-in
  expected output sets.
