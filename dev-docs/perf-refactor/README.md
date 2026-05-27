# Astichi Perf Refactor — Doc Index

Status: index only.

## Active plan (implement here)

**[`FullSelfNativeRustAstPlan.md`](FullSelfNativeRustAstPlan.md)** — canonical
roll-build for full self-native: Rust through materialize, one `copy_python_ast`
handoff, hybrid Python AST work removed from the production path. Tags:
`rust-fsn/*`. F0 sign-off: 2026-05-27.

Roll-build **F0c–F5** complete (`rust-fsn/*` tags). **F6** (handoff perf) is
optional. Do not open new work from the historical files below.

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
