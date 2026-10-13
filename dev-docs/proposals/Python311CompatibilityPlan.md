# Python 3.11 compatibility plan

Status: **scope narrowed by the user on 2026-10-14; production implementation
has not started**. This amendment replaces the cross-version provenance and
Pyrolyze implementation steps in the previously reviewed plan. The original
[Consistency](Python311CompatibilityPlan-ReviewConsistency.md),
[Safety](Python311CompatibilityPlan-ReviewSafety.md) and
[review checkpoint](Python311CompatibilityPlan-ReviewCheckpoint.md) remain
historical evidence for their exact reviewed revision, not independent review
of this amendment. Supported versions remain unchanged.

## Goal and boundary

Make Astichi install and run on Python 3.11 with both Python and native backends,
preserving the existing supported runtimes. Provenance must round-trip within
the same Python minor version; cross-version AST pickle portability is outside
this work. Pyrolyze-dependent integration tests are explicitly skipped on 3.11
and retained on their existing supported runtimes.

This amendment changes documentation only. The proposed implementation boundary
is Astichi's native AST conversion, golden/test harness, packaging, version
matrix, CI and associated documentation. The existing provenance encoder and
standard pickle decoder remain unchanged. Pyrolyze, YIDL, Lifecycle, YIDL Cache,
Undoable and Dataclass are reference-only; no production edits in those members
are required. No dependency upgrades, compiler redesign, workspace configuration
changes, release or publication. This amendment does not authorize implementation.

## Evidence

At Astichi commit `3e2e54ef232b01065e28aa6478f0eca7c6e8ae09`, the unchanged
Python 3.11.14 suite reported **1,952 passed, 604 failed, 106 skipped**.
554 failures reached native AST construction and 50 reached golden-provenance
unpickling. The native engine built and loaded without dependency changes.

With a disposable constructor-arity adapter and all 90 normally gated
structural snapshots enabled, the full suite reported **2,578 passed, 68 failed,
16 skipped**. All 68 failures decoded newer-runtime AST pickles in expected
goldens. Twelve integration skips reached Pyrolyze's Python 3.12 syntax; the
other four were explicit feature exclusions. This is diagnostic evidence,
not a completed compatibility implementation. Astichi has no runtime dependency
on Pyrolyze; the affected tests use it as a downstream integration workload.

## Implementation sequence

1. **Native AST construction.** Use the existing parser tests to establish RED
   on Python 3.11 for ordinary classes, functions and async functions. Adapt the
   three constructors in `native_engine/src/parser_ir.rs` to the runtime AST
   layout, including `type_params` only where supported. Preserve newer-runtime
   behavior, locations and private metadata. Reject unsupported newer syntax
   clearly rather than silently dropping nonempty type parameters. Rebuild the
   matching extension and verify the existing native and source golden paths.

2. **Same-version provenance and canonical source.** Keep the current format,
   public functions and ordinary pickle decoder. Adapt the golden harness to
   select expected provenance produced on the receiving Python minor version.
   Retain the canonical pre-materialized source body and materialized source
   comparisons; runtime-specific payloads must match those canonical bodies.
   Generate fixture payloads through the original authored golden cases on the
   target runtime, preserving their AST locations and private metadata. Do not
   derive replacement provenance by reparsing a golden's emitted body. Verify
   actual output and matching expected fixtures independently, including emitted
   source recompile/materialize checks and existing mismatch diagnostics. Keep
   all golden cases; do not skip a whole case merely because its original pickle
   came from a newer runtime. Cross-version pickle exchanges are not an
   acceptance gate. See the [design](Python311CompatibilityDesign.md).

3. **Gate downstream integration tests.** Add explicit Python 3.11 skips only
   at test entry points that require Pyrolyze. Keep unrelated native hot-path
   checks enabled, and retain the affected integrations on existing supported
   runtimes. Use a clear consumer-version reason before importing or launching
   Pyrolyze; do not catch broad exceptions or silently count a blocked workload
   as a pass. No Pyrolyze alias or compiler-helper changes are in scope.

4. **Advertise support only after behavior works.** Add 3.11 to Astichi's
   `requires-python`, classifiers, local test matrix, CI and release-wheel build
   selection, and update its support documentation. Retain the existing PyO3
   ABI configuration; it already builds on 3.11. Validate wheel tags and a clean
   Python 3.11 wheel installation with no metadata bypass or source-path trick.
   Build locally for verification; do not publish or change release versions.

5. **Final verification.** Run the complete dual-backend suite on 3.11 and the
   existing supported matrix. Recheck all 90 structural snapshots on 3.11 while
   retaining the established 3.14 canonical regeneration policy. Verify normal
   generation, materialization, execution and same-version provenance from the
   installed wheel. Record exact counts, remaining skips, patch scope and elapsed
   time. Inspect modified Rust control-flow and conditional boundaries as required
   by the workspace rules. Update the active handoff with actual results.

## Completion criteria

No in-scope Astichi behavior, canonical-source or same-version provenance failures
on Python 3.11; no regressions on the existing supported matrix; and a normally
installable 3.11 wheel. Pyrolyze integrations must be explicitly skipped on 3.11
and remain exercised on existing supported runtimes. Keep legitimate newer-syntax
and no-mirror-replay exclusions visible. Report skips separately from passes.
Cross-version provenance portability and Python 3.11 support for downstream
consumers are separate work, not blockers for this deliverable.
