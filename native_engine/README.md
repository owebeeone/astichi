# Astichi Native Engine Skeleton

This directory contains the production native-extension skeleton for the
perf-refactor lower engine. It is intentionally separate from `native_probe/`.

The skeleton exposes version, capability, and self-test functions only. It does
not route Astichi compile/build/materialization behavior to native code.

Build explicitly from the Astichi repo root:

```bash
uv run python native_engine/build.py
```

The build copies an ignored extension artifact into `native_engine/` so
`astichi.lower_engine.native` can discover it during local development.

Run the focused skeleton tests:

```bash
uv run --with pytest pytest tests/test_native_engine_skeleton.py -q
```

Default Astichi imports and tests must pass without building this extension.

Use the Python build and focused Python tests as the verification gate. Direct
`cargo test` is not a useful gate for this PyO3 extension skeleton because the
test harness tries to execute the extension crate outside the Python loader.
