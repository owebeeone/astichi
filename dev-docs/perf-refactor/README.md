# Astichi Perf Refactor — Doc Index

Status: index only.

## Active plan (implement here)

**[`HotPathNoPythonPlan.md`](HotPathNoPythonPlan.md)** — fool-proof gate:
`tests/test_lifecycle_hot_path_python_gate.py` + counter table (`native_compile_parse`
must be 0 on lifecycle import; `copy_python_ast` == class count). Tags: `rust-hot/*`.

**[`FullSelfNativeRustAstPlan.md`](../history/perf-refactor/FullSelfNativeRustAstPlan.md)** — historical
`rust-fsn/*` slice work (routing/oracles); did not clear the hot-path gate.

## Retained Contracts And Follow-Up

- [Engine selection](EngineSelectionContract.md)
- [Surface extension](SurfaceExtensionContract.md)
- [Verification and goldens](VerificationAndGoldens.md)
- [Lower-template package](LowerTemplatePackageV2.md)
- [Remaining Python rollout](RemainingRollBuildPlan.md): retained because the
  canonical summary still references it. Do not use its older native rollout
  sequence in place of the active hot-path plan.

## Historical Context

Earlier analyses, inventory-first/hybrid plans, full-self-native slice ledgers,
and benchmark snapshots now live in `dev-docs/history/perf-refactor/`.
They are original rationale and evidence, not competing execution plans.
The active hot-path plan controls its current gates; the single-source summary
and coding rules remain authoritative for semantics and implementation rules.
