# Engine Selection Contract

Status: draft gate for the native spike.

The Python lower engine is the first implementation and is the correctness
reference. A native engine is optional and may be Rust, C++, or a hybrid module.
It must run behind the same facade and the same structural golden harness.

## Selection Rules

The facade should select one lower engine at scope creation:

```text
python: default implementation and correctness reference
native: optional native implementation when available and compatible
native-rust: optional explicit Rust-backed implementation, if shipped
native-cpp: optional explicit C++-backed implementation, if shipped
auto: use native only when the active bundle and platform pass compatibility gates
```

The exact public spelling can be finalized in the native spike, but selection
must happen at a coarse engine/scope boundary. The hot path must not bounce
between Python and native code per record.

## Compatibility Gates

Before `native` can be selected, the native engine must accept:

- the active surface bundle;
- every registered operation primitive used by the bundle;
- the snapshot schema version;
- the materialization/hygiene ownership contract;
- the external-slot ownership contract.

If any engine-level gate fails, `auto` falls back before work starts. Explicit
`native` should fail with a diagnostic rather than silently crossing back into
Python per record.

`auto` fallback should be quiet in normal operation but visible in diagnostic
mode through a structured selection event:

```text
EngineSelectionEvent:
  requested_engine
  selected_engine
  fallback_scope
  reason_key
  reason_detail
```

Example:

```text
requested_engine=auto
selected_engine=python
fallback_scope=template
reason_key=native_grammar_unsupported
```

If the native backend uses its own parser and AST IR, it must also accept:

- the supported Python grammar version;
- the native AST-to-CPython AST emission contract;
- the source-location policy required by `compile(...)` and diagnostics;
- the required/default-field population policy for emitted CPython AST nodes;
- the public `ast`/`_ast` plus `compile(...)` artifact boundary.

Internal CPython compiler APIs such as `PyArena` or `_PyAST_Compile` are not
part of the default compatibility contract. A backend that requires them must be
selected explicitly and must have its own version-support spike and maintenance
gate.

## Grammar Fallback Policy

Grammar capability is template-shaped, not just engine-shaped. The selection
policy is:

- `python`: always use the Python lower engine.
- explicit `native`, `native-rust`, or `native-cpp`: fail before template
  registration if the native parser cannot support the host Python grammar or
  the template source shape.
- `auto`: attempt native per template, then fall back to the Python lower engine
  for that whole template when grammar capability fails.

Fallback is never per record and never during candidate lookup. A template is
owned by one engine for its lifetime. Any `auto` fallback must increment a
counter and emit `EngineSelectionEvent` in diagnostic mode so slow-path
selection can be explained.

The native AST probe is successful only if the chosen parser plus this fallback
policy can run all current Astichi `tests/data/gold_src/` fixtures.

## Test Matrix

The same fixture should run against:

- Python lower engine;
- native lower engine, once implemented;
- `auto` selection when native support is installed.

Structural snapshots compare by stable surface, pattern, and operation keys.
Final-output goldens must pass for the same fixture set. Native implementation
is not considered correct because it is faster; it is correct only when it
matches the Python lower engine through the shared verification path.
