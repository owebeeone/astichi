# Astichi Perf Refactor — Doc Index

Status: index only.

## Active plan (implement here)

**[`HotPathNoPythonPlan.md`](HotPathNoPythonPlan.md)** — fool-proof gate:
`tests/test_lifecycle_hot_path_python_gate.py` + counter table (`native_compile_parse`
must be 0 on lifecycle import; `copy_python_ast` == class count). Tags: `rust-hot/*`.

**[`FullSelfNativeRustAstPlan.md`](FullSelfNativeRustAstPlan.md)** — historical
`rust-fsn/*` slice work (routing/oracles); did not clear the hot-path gate.

## Historical context (do not execute)

These documents informed the inventory-first refactor and hybrid native era.
They are retained for background, grep, and archaeology only:

- `AstichiPerfRefactorProposal.md` (parent proposal under `dev-docs/`)
- `StructuralInventoryDesign.md`, `BuildOperationsAnalysis.md`,
  `SurfaceExtensionContract.md`, `VerificationAndGoldens.md`,
  `AssemblyApiLedger.md`, `SnapshotGrammar.md`, `LowerTemplatePackageV2.md`,
  `PythonLowerTemplatePackageV2Plan.md`, `EngineSelectionContract.md` (update
  capability names when F0c/F5 touch selection — do not follow old slice lists),
  `NativeAstProbe.md`, `NativeDecisionProfile.md`,
  `NativeLowerEngineDetailedPlan.md`, `NativePerformancePlan.md`,
  `SlicedBuildPlan.md`, `RemainingRollBuildPlan.md`

When a historical doc disagrees with `FullSelfNativeRustAstPlan.md`, **this plan
wins**.
