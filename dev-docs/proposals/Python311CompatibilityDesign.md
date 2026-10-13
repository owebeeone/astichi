# Python 3.11 compatibility design

Status: **scope narrowed by the user on 2026-10-14; production implementation
has not started**. This design supersedes the previously reviewed reader and
Pyrolyze proposals. The [review checkpoint](Python311CompatibilityDesign-ReviewCheckpoint.md)
preserves both historical rounds and their exact revisions; those verdicts do
not constitute independent review of this amendment. The amended
[plan](Python311CompatibilityPlan.md) controls the remaining work.

## Deliverable and boundary

The current deliverable is a documentation amendment only. Proposed implementation
is confined to Astichi's three native declaration converters, golden/test
harness, packaging, CI, version matrix and support documentation. Provenance
encoding and decoding stay unchanged. Pyrolyze and the other workspace consumers
are reference-only. No alias replacement, Pyrolyze compiler correction, dependency
upgrade, workspace change, release or publication is included. This document
and prior review acceptance do not authorize production implementation.

The user removed cross-Python-version provenance portability from the requirement
and selected explicit 3.11 gating for integration tests that use Pyrolyze. These
are scope choices, not claims that the earlier compatibility probes failed.

## Provenance contract

Keep the existing base64 → zlib → pickle representation and public
`encode_provenance`, `decode_provenance`, `extract_provenance` and
`verify_round_trip` signatures. Keep the standard pickle decoder, root-type
check and source/provenance mismatch check. No custom unpickler, private stdlib
hook, constructor adapter or format migration is required in the emit layer.

Acceptance requires provenance written and read on the same supported Python
minor version. Preserve AST values, source locations, private metadata and shared
references under that existing path. Cross-minor pickle portability is outside
this compatibility project; an incidental successful exchange is not a promise
of support. Do not add a new production version-rejection mechanism solely for
this scope amendment. Emitted Python source remains authoritative; portability
of source without embedded provenance is a separate concern from pickle layout.

### Golden harness

The current `tests/test_ast_goldens.py` verifies both actual output provenance
and the checked-in expected pre-materialized source's provenance. The latter
can contain an AST pickle written on another Python minor version. It currently
fails on 3.11 even when actual output round-trips on that interpreter.

Separate the expected source baseline from its version-specific pickle:

- Preserve the canonical source body in
  `tests/data/goldens/pre_materialized/` and the complete materialized baseline
  in `tests/data/goldens/materialized/`. Continue normalized pre-source and exact
  materialized-source comparisons for every existing case and both backends.
- Provide expected provenance fixtures keyed by producing Python minor version
  under `tests/data/goldens/provenance/<major.minor>/`, associated with the same
  authored case names. Select only the target runtime's payload when assembling
  an expected source for provenance verification. Missing required fixtures fail
  clearly; do not silently fall back to a different minor version's pickle.
- Generate the runtime-specific payloads from the original cases in
  `tests/data/gold_src/` through their existing build/emit path, not by parsing
  canonical emitted source or copying the current test result into the expected
  baseline. Before accepting fixtures, require their emitted source bodies and
  materialized outputs to match the canonical baselines. Source changes require
  the normal canonical review; payload regeneration cannot bless source drift.
- Keep verification of actual provenance on every runtime. Independently verify
  the matching expected fixture and its emitted-source recompile/materialize
  behavior. Preserve existing comment-marker handling and tampered-source tests.
- Add narrow harness coverage for version selection, missing fixture diagnostics
  and refusing source drift during fixture generation. Existing canonical cases
  remain the end-to-end success coverage.

Retain the established 3.14 canonical source/structural snapshot regeneration
policy. Runtime-specific payload generation is a separate harness operation
that must not overwrite the canonical source or structural snapshots. Add the
payload sets needed by the declared supported matrix during implementation.
All fixtures and generator configuration use repository-relative paths.

This is test-fixture adaptation to the revised requirement. It does not repair
cross-version provenance in production or skip source correctness checks.

## Native conversion

The declaration converters in `native_engine/src/parser_ir.rs` must select the
receiving AST layout before supplying `type_params`: functions and async functions
have six constructor fields on 3.11 and seven on 3.12+; classes have five and six
respectively. Determine runtime capability once per converter context where
practical, retaining direct constructors and location handling.

Reject nonempty type parameters on 3.11 before conversion rather than dropping
semantics. Newer-only AST nodes need explicit unsupported-runtime diagnostics.
This builds a fresh native-converted AST; it does not change provenance decoding.
No PyO3, RustPython or compiler-wide representation change is required by the
observed arity failures. Apply workspace control-flow/conditional-boundary rules
in modified Rust and inspect disabled branches with suitable source checks.

## Downstream integration gating

Astichi has no runtime dependency on Pyrolyze. Some native/Lifecycle performance
and guard tests use it as a realistic downstream workload. Pyrolyze currently
requires Python 3.12 and contains PEP 695 aliases that cannot parse on 3.11.

Apply explicit 3.11 skips to the Pyrolyze-dependent cases in
`tests/test_lifecycle_hot_path_python_gate.py`,
`tests/test_native_success_path_guards.py` and
`tests/test_native_hot_path_no_pydict_h2.py`. Place the gate before the relevant
import or subprocess workload. Verify the final collected set rather than assume
these references are exhaustive. Keep all independent checks in those modules
running; a module-wide skip is appropriate only if every case needs that consumer.

State the consumer's unsupported runtime as the skip reason. Keep these cases
running on their existing supported runtimes; do not remove the workload or
convert unexpected integration failures into skips. Report collected skip IDs
and counts separately from successful Astichi tests. Pyrolyze aliases and
`_runtime_annotation_matches` remain untouched. The earlier helper observation
is retained as a [separate finding](Python311CompatibilityFindings.md), not an
Astichi implementation prerequisite.

## Packaging and acceptance gates

After native and harness behavior works, update Astichi's package minimum,
classifiers, test matrix, CI/release-wheel build selection and support docs.
Retain the existing PyO3 ABI configuration. Build matching native extensions for
the tested source; validate Python 3.11 wheel tags and a clean install without
metadata bypasses, source-path overrides or consumer package-floor changes.

Use RED/GREEN in the existing parser and golden harnesses, with narrow negatives
for unsupported syntax and fixture selection. Run the full dual-backend suite on
3.11 and the existing supported matrix, all 90 structural snapshots on 3.11,
and installed-wheel generation/materialization/execution/same-version provenance.
Retain source/provenance mismatch rejection. Record exact counts, skip reasons,
versions, patch scope and elapsed time. No cross-version pickle exchanges,
private-unpickler-hook tests or Pyrolyze porting tests are acceptance gates.

## Retained exploratory evidence

The constructor-adapted diagnostic suite reported **2,578 passed, 68 failed,
16 skipped** on 3.11. All 68 failures concerned expected provenance written on
newer runtimes; twelve skips reached Pyrolyze's newer syntax. These results
predate production implementation and do not establish packaged support.

Earlier isolated reader/alias probes exercised 3.11.14, 3.12.12, 3.14.3 and
3.15.0a5. The reader redesign preserved AST class references and opaque restore
hooks in sixteen writer/reader exchanges, and decoded 42 golden payloads on each
reader. The alias probe exposed an event-recognition limitation. That evidence
remains in local `scratch/python311-design/` and the historical review records.
It is not a committed test dependency and no longer defines required production
work. No new test matrix or native build has been run for this amendment.
