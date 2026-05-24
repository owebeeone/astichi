# Verification And Goldens

Status: detailed design draft.

This document defines how the refactor stays verifiable while replacing the
intermediate representation. The core policy is simple: successful behavior is
covered by canonical goldens; bespoke tests are reserved for mechanics,
diagnostics, and failure cases that goldens cannot express clearly.

## Coverage Policy

Use golden or snapshot coverage for:

- successful source transformation;
- successful materialization;
- successful structural assembly state;
- successful inventory projection;
- successful YIDL generation output.

Use bespoke tests for:

- parser/recognizer edge cases;
- invalid marker diagnostics;
- ambiguous or missing candidate diagnostics;
- direct round-trip parser/writer mechanics for the snapshot format;
- counters and gates that are not user-visible output;
- narrow regression cases that cannot be represented as a fixture script.

Do not duplicate the same successful behavior in both a bespoke unit test and a
golden case. If a success-path unit test breaks only because the intermediate
representation changed, prefer replacing it with a structural golden.

## Existing Golden Harness

Astichi already has a versioned golden harness:

- fixture scripts: `tests/data/gold_src/`
- pre-materialized goldens: `tests/data/goldens/pre_materialized/`
- materialized goldens: `tests/data/goldens/materialized/`
- actual outputs: `tests/actual_test_results/<runtime>/goldens/`

The refactor should extend this harness rather than add a parallel bespoke
success-path harness.

## New Structural Golden Phase

Add a structural phase:

```text
tests/data/goldens/structural/
tests/actual_test_results/<runtime>/goldens/structural/
```

The structural phase contains canonical snapshots emitted from the lower engine.
Recommended file extension is `.json` if the snapshot is canonical JSON, or
`.snap` if the writer uses line-oriented records.

Slice 2 uses canonical JSON and adds the phase to the versioned harness without
making source-fixture regeneration produce structural files yet. Until lower
engine routing exists, structural goldens are hand-built contract fixtures and
round-trip through `astichi.structural_snapshot`.

The existing fixture helper can be extended so each fixture may write:

```text
pre_materialized output
materialized output
structural output
```

Migration can be staged:

1. make the third output path optional;
2. add structural output for lower-engine-backed cases;
3. make the structural output required once all relevant cases use the lower
   engine.

## Canonical Snapshot Shape

The writer should produce deterministic text with an explicit schema version.

```text
schema: astichi.structural-inventory.v1
surface_bundle
templates
occurrences
records
edges
overlays
hygiene
materialization
diagnostics
```

The `surface_bundle` section should include the registered pattern catalog, not
just surface names. That catalog is the golden-visible proof that all current
Astichi patterns are represented by consolidated templates.

Snapshot data must avoid:

- absolute filesystem paths;
- Python object reprs;
- process ids;
- memory addresses;
- hash-order-dependent map ordering;
- raw external Python objects.

External values should be represented by stable slots and debug labels:

```text
external_slot:
  slot_id
  stable_label
  value_kind_summary
```

The actual object remains in the facade object table and is not serialized into
the structural golden.

Surface and operation ids are process-local and must not be snapshotted as the
only identity. Structural goldens should write stable keys:

```text
surface_bundle:
  schema_version
  bundle_signature
  surfaces:
    - surface_key
      version
  patterns:
    - pattern_key
      template_key
      version
  operations:
    - operation_key
      version
```

The dynamic id assigned by Python or native code may appear in diagnostic-only actual
output, but canonical comparisons should normalize or omit it.

Runtime calls into native code use the registered handles returned when the surface
bundle was loaded. Goldens do not try to prove handle identity across processes;
they prove that the same stable surface contract was registered and then
round-tripped.

## Round Trip Contract

The snapshot format must round trip independently of AST materialization.

Required checks:

```text
snapshot = lower_engine.structural_snapshot(state)
text = write_snapshot(snapshot)
parsed = read_snapshot(text)
rewritten = write_snapshot(parsed)
assert rewritten == text
```

For selected cases, add a stronger check:

```text
snapshot -> parsed snapshot -> debug inventory projection
```

The projection from parsed snapshot is for verification only. It does not need
to become a supported runtime API.

## Golden Success Path

The success path for this refactor should be:

1. existing Astichi final-output goldens still pass;
2. new structural goldens match lower-engine intermediate state;
3. YIDL materialized goldens still pass for generated output;
4. lifecycle import smoke tests prove generated classes still execute.

Do not keep broad success assertions in bespoke tests when a golden covers the
same behavior. Bespoke tests should explain one mechanic or one diagnostic.

For lower-backed composables, tests may explicitly request copied CPython AST
nodes or rendered source as artifact outputs. That is acceptable for final-output
and compatibility checks. It should not become the intermediate success path;
structural goldens remain the canonical way to validate lower assembly state.

## Tests To Replace Or Reframe

Tests that inspect current Python `Inventory` internals, builder graph
internals, or pre-materialized AST structure will be the most likely to break.
When they represent successful assembly behavior, move them to structural
goldens.

Likely replacement categories:

- inventory string/debug output success cases;
- assembly-scope success cases that assert exact intermediate records;
- staged build success traces;
- successful hygiene/materialization intermediate shape;
- successful pyimport insertion plans.

Keep bespoke tests for:

- duplicate instance name errors;
- invalid identifier binding errors;
- unresolved mandatory hole errors;
- ambiguous candidate diagnostics;
- malformed snapshot parser errors;
- exact validation timing where a golden cannot identify the failure point.

## Structural Fixture Strategy

Start with a small set of structural fixtures:

- single root with one block hole;
- scalar expression insert;
- identifier bind overlay;
- external bind overlay;
- single-add hole satisfaction;
- staged composable insertion;
- pyimport marker;
- hygiene collision and rename;
- parameter hole;
- elif target.
- one extension-surface fixture once the registry exists, preferably the first
  implemented future surface such as match/case or exception handlers.
- one registry catalog fixture that snapshots the current surface, pattern, and
  operation bundle independently of any particular composable.

After the lower engine handles all existing fixture families, the structural
phase should be emitted for every `tests/data/gold_src/*.py` fixture that uses
the assembly path.

## Engine Parity Goldens

Once a native engine exists, the same fixture should run against both engines:

```text
python lower engine -> structural golden
native lower engine -> structural golden
```

The canonical text should be identical except for an optional explicitly
normalized engine field. Prefer omitting engine identity from the canonical
comparison; write it only to actual diagnostic output when debugging.

Surface, pattern, and operation ids must also compare by stable keys, not by
dynamic engine-local ids.

## Transient Differential Harness

During route-through, the legacy assembler and lower engine should run
side-by-side for a constrained generated subset. This is drift detection, not a
replacement for golden success-path coverage.

The harness should:

- generate small composable graphs from a bounded grammar;
- include block holes, expression inserts, identifier binds, external binds,
  and single-add satisfaction before expanding to parameter holes, pyimports,
  and hygiene cases;
- run the legacy assembler and lower engine on the same generated structure;
- compare projected inventory when both engines expose one;
- compare final source or AST for supported materialized cases;
- record the seed and minimized fixture for any mismatch.

This harness may be deleted once the legacy route is removed, but it should
exist while Slices 8 through 12 are migrating behavior. Fixture goldens remain
the success path; the differential harness is a temporary semantic-drift alarm.

## Regeneration Rules

Structural golden regeneration should be explicit:

```bash
uv run python tests/versioned_test_harness.py regen-goldens --python 3.14
```

If structural goldens require a separate command during migration, that command
must be temporary and named in the slice plan.

Golden changes should be reviewed as semantic changes. A bulk update is
acceptable only when the structural format intentionally changes and final
behavior goldens still prove user-visible parity.
