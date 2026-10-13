# Python 3.11 compatibility plan

Status: **accepted at `1bc8d2dc0c0978c19ad8d77237718ee690b5857e` after
[Consistency](Python311CompatibilityPlan-ReviewConsistency.md) and
[Safety](Python311CompatibilityPlan-ReviewSafety.md) reported GO; this accepts
the plan only**. Production fixes have not started, and supported versions are
unchanged. See the [review checkpoint](Python311CompatibilityPlan-ReviewCheckpoint.md).

## Goal and boundary

Make Astichi install and run on Python 3.11 with both Python and native backends,
preserving the existing supported runtimes. Also remove the observed Pyrolyze
syntax blocker so Astichi's existing integration checks can run from source.

This step changes only this plan and its documentation index. The proposed
implementation boundary is Astichi's AST conversion, provenance decoder,
packaging, version matrix, associated tests and documentation; plus a bounded
Pyrolyze API alias compatibility change and its focused tests. YIDL, Lifecycle,
YIDL Cache, Undoable and Dataclass remain reference-only. No dependency upgrades,
compiler redesign, workspace configuration changes, release or publication.
Full packaged Python 3.11 support for Pyrolyze or the other consumers is separate
work; their current package minimums must not be lowered on this evidence alone.

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
not a completed compatibility implementation.

## Implementation sequence

1. **Native AST construction.** Use the existing parser tests to establish RED
   on Python 3.11 for ordinary classes, functions and async functions. Adapt the
   three constructors in `native_engine/src/parser_ir.rs` to the runtime AST
   layout, including `type_params` only where supported. Preserve newer-runtime
   behavior, locations and private metadata. Reject unsupported newer syntax
   clearly rather than silently dropping nonempty type parameters. Rebuild the
   matching extension and verify the existing native and source golden paths.

2. **Existing provenance compatibility.** Keep the current provenance format
   and canonical goldens. Add narrowly scoped AST reconstruction compatibility
   in `src/astichi/emit/api.py` so existing newer-runtime pickles of syntax
   representable on 3.11 can be decoded correctly. Preserve AST state and
   Astichi metadata, supply required runtime defaults, and report unsupported
   nodes explicitly. Do not reparse the emitted body as a substitute for its
   saved provenance or regenerate fixtures to hide the failure. Use the 34
   failing golden cases for acceptance, with narrow tests for constructor/state
   restoration and unsupported-node diagnostics. Verify ordinary provenance
   round trips in both directions between 3.11 and the existing runtimes.

3. **Pyrolyze integration blocker.** In a disposable feasibility probe first,
   replace both PEP 695 declarations in Pyrolyze's `src/pyrolyze/api.py`:
   `PyrolyzeHandler` and `SlotCallable`. Use older `ParamSpec`/`TypeVar`-based
   aliases while preserving their `Annotated` markers, generic subscription and
   the `PyrolyteHandler` compatibility alias. Establish RED/GREEN with focused
   API and existing handler/slot compiler cases on 3.11 and newer runtimes; then
   rerun the twelve Astichi integration cases. Additional consumer or compiler
   blockers require separate findings and a boundary check before edits.

4. **Advertise support only after behavior works.** Add 3.11 to Astichi's
   `requires-python`, classifiers, local test matrix, CI and release-wheel build
   selection, and update its support documentation. Retain the existing PyO3
   ABI configuration; it already builds on 3.11. Validate wheel tags and a clean
   Python 3.11 wheel installation with no metadata bypass or source-path trick.
   Build locally for verification; do not publish or change release versions.

5. **Final verification.** Run the complete dual-backend suite on 3.11 and the
   existing supported matrix. Recheck all 90 structural snapshots on 3.11 while
   retaining the established 3.14 canonical regeneration policy. Verify normal
   generation, materialization, execution and provenance from the installed
   wheel. Record exact counts, remaining skips, patch scope and elapsed time.
   Inspect modified Rust control-flow and conditional boundaries as required
   by the workspace rules. Update the active handoff with actual results.

## Completion criteria

No Astichi behavior or golden-provenance failures on Python 3.11; no regressions
on the existing supported matrix; a normally installable 3.11 wheel; and each
integration case either passes or has an explicit, separately evidenced consumer
blocker. Keep legitimate newer-syntax and no-mirror-replay exclusions visible.
Blocked integrations must not be counted as successes. Broader serialization,
consumer support or dependency changes require a revised boundary before work.
