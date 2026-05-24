# Astichi Native Engine Skeleton

This directory contains the production native-extension skeleton for the
perf-refactor lower engine. It is intentionally separate from `native_probe/`.

The extension currently exposes version, capability, self-test, and native
engine-handle lifecycle functions only. It does not route
compile/build/materialization behavior to native code yet, and it must not be
selected as a usable native lower engine until it advertises the full
lower-engine capability set from
`dev-docs/perf-refactor/NativeLowerEngineDetailedPlan.md`.

N1 core functions:

- `engine_create(request=None)`
- `engine_close(handle)`
- `engine_snapshot(handle)`
- `engine_assert_same_owner(left, right)`

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
Selection falls back to Python before work starts when the extension is absent
or present but not lower-engine capable.

Use the Python build and focused Python tests as the verification gate. Direct
`cargo test` is not a useful gate for this PyO3 extension skeleton because the
test harness tries to execute the extension crate outside the Python loader.
