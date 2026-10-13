# Python311CompatibilityPlan — Consistency-AXIS REVIEW

**Review object:** `dev-docs/proposals/Python311CompatibilityPlan.md` at `1bc8d2dc0c0978c19ad8d77237718ee690b5857e`; proposed implementation, draft-stage acceptance review; 2026-10-13.  
**Baseline:** Astichi `1bc8d2dc0c0978c19ad8d77237718ee690b5857e`; reference-only Pyrolyze `092d055294df97666bee473126708c2868379c2d`; reference-only YIDL `9d374f88445c426a56d5dd1f96fad112d1ec5417`. Committed documents and source were read using `git show SHA:PATH`; ignored experiment evidence was read directly.  
**Date:** 2026-10-13  
**Axis:** Consistency with controlling documents, requirement provenance, component scope, compatibility consumers and satisfiable acceptance criteria. Independent, adversarial, read-only. The other axis runs in parallel; nothing here relies on it. Filed verbatim by the lane owner.

**Verdict: GO** — zero P0, P1, P2 or P3 findings. This accepts the plan document only. It does not authorize production implementation or establish Python 3.11 support.

---

## 0. Evidence base

All citations below are relative to the owning repository, identified explicitly where necessary.

Read and inspected:

- Workspace `AGENTS.md` and `AGENTS_GWZ.md`, including membership integrity, search behavior and committed-path rules; the supplied standing scope and explicit-boundary instructions.
- Astichi `AGENTS.md`, including read-only review instructions, authoritative-document precedence, semantic-change guardrails and coverage rules.
- Astichi `dev-docs/AstichiSingleSourceSummary.md`, particularly lines 14–32, 195–276, 800–821, 1082–1096 and 1172–1216; `dev-docs/AstichiCodingRules.md`, including layering, provenance, supported syntax, verification and scratch-dependency rules.
- Public documentation read before the plan: Astichi `README.md`, including installation, quick start, native selection and supported runtimes; `docs/reference/materialize-and-emit.md:3–81`; `docs/reference/composable-api.md:3–66`. Also inspected `docs/reference/compile-api.md:5–58`.
- Astichi `dev-docs/proposals/Python311CompatibilityPlan.md:1–87`, its committed `Python311CompatibilityPlan-ReviewBrief.md:1–65`, and `dev-docs/README.md:18–25`.
- Astichi `native_engine/src/parser_ir.rs:643–719`; `native_engine/Cargo.toml:1–15`; `src/astichi/emit/api.py:15–87`; `src/astichi/ast_provenance.py:22–85`.
- Astichi `tests/test_native_engine_parser_ir.py:26–188`; `tests/test_ast_goldens.py:43–113`; `tests/test_ast_provenance.py:24–132`; `tests/conftest.py:19–89`; `tests/lower_engine_matrix.py:9–53`; `tests/versioned_test_harness.py:44–86`; `tests/README.md:36–88`.
- Astichi `pyproject.toml:5–33,73–118`; `hatch_build.py:57–107`; `.github/workflows/ci.yml:20–81`; `.github/workflows/publish.yml:15–150`.
- Pinned Pyrolyze `AGENTS.md`, `dev-docs/README.md`, `pyproject.toml:5–17,40–53`, `src/pyrolyze/api.py:7–15,383–386`, `src/pyrolyze/compiler/kernel_loader.py:15–44`, and compiler recognition in `src/pyrolyze/compiler/kernels/v3_14/rewrite.py:2461–2628,2675–2699,2815–2876`.
- Pinned Pyrolyze existing handler and slot cases in `tests/test_ast_phase7_native_call_rewrite.py:12–46`, `tests/test_ast_phase5_component_call_rewrite.py:116–213`, and `tests/test_ast_phase3_base_rewrite.py:153–201`.
- Pinned YIDL `pyproject.toml:5–20`.
- Astichi ignored evidence under `scratch/python311-investigation/2026-10-13/`: `REPORT.md:1–71`, summary and reference-revision JSON, diagnostic patch, native build log, diagnostic final log and JUnit suite headers.

The JUnit headers corroborate the reported collection and outcomes: baseline 2,662 cases with 604 failures and 106 skips; diagnostic complete suite 2,662 cases with 68 failures and 16 skips; forced structural run 90 cases with no failures or skips. The diagnostic final log reports `68 failed, 2578 passed, 16 skipped`.

`git diff --stat` between the investigation baseline and reviewed Astichi revision showed only the plan, review brief and index change. No product implementation changed.

Start and end `git rev-parse HEAD` and `git status --short` checks confirmed the exact three reference revisions remained unchanged. Astichi and Pyrolyze were clean. YIDL had the same four unrelated untracked developer documents at both checks; none was read or included in the review.

No builds, tests, installations, network calls, file writes or Git mutations were performed. The current peer prompt and report were not inspected.

## Problem, requirement provenance, and scope

The original authority is recorded in Astichi `dev-docs/proposals/Python311CompatibilityPlan-ReviewBrief.md:7–16`: run all Astichi tests on Python 3.11, permit setup workarounds to expose actual failures, then sketch and review a small compatibility plan. Current authorization covers review records and plan remediation; it excludes production implementation and publication.

The experiment identifies two concrete Astichi defects rather than a dependency-build failure:

1. Native conversion supplies the newer positional `type_params` argument to Python 3.11 AST constructors.
2. Checked-in provenance pickles reconstruct newer AST layouts during decoding.

The unchanged constructors substantiate the first issue at Astichi `native_engine/src/parser_ir.rs:643–719`; the existing decoder directly uses `pickle.loads` at `src/astichi/emit/api.py:33–40`. The successful native build and diagnostic adapter establish that changing PyO3, RustPython or infrastructure is unnecessary for the observed workload. The evidence does not establish complete persistence or packaged consumer support.

The plan chooses localized constructor adaptation and decoder reconstruction compatibility, retains canonical fixtures, and requires verification on existing runtimes. Regenerating expected provenance or reparsing the body to replace saved provenance would conceal the observed defect or discard retained information; the plan expressly excludes both routes at `dev-docs/proposals/Python311CompatibilityPlan.md:45–54`.

Pyrolyze’s two PEP 695 declarations are confirmed source-import blockers at pinned Pyrolyze `src/pyrolyze/api.py:383–386`. Their proposed correction is conditional on a disposable feasibility probe and existing compiler regressions. That condition matters: ordinary `Annotated` aliases have a downstream recognition risk described below. The proposal does not authorize widening into compiler implementation when that probe reveals additional work.

The current editable boundary remains Astichi documentation. Future proposed scope is bounded Astichi compatibility work and a Pyrolyze alias correction, subject to implementation authorization. YIDL, Lifecycle, Cache, Undoable and Dataclass remain references. Package minimums in pinned Pyrolyze and YIDL are both Python 3.12; the plan correctly refuses to infer full consumer support from source experiments.

No unsupported dependency prerequisite or unauthorized current implementation expansion was found.

## 2. Invariant analysis

**Evidence and status remain distinct.** The plan calls the adapter diagnostic and identifies the checkpoint as a proposal. Its counts agree with the preserved logs and JUnit headers. The index lists it under unimplemented proposals. No diagnostic success is presented as completed compatibility.

**Source remains authoritative.** The plan retains the provenance format, preserves AST state and metadata, and requires explicit unsupported-node diagnostics. This agrees with Astichi’s source/provenance rules. Compatibility reconstruction is not permission to restore hidden builder semantics or accept edited-source mismatches.

**Native conversion remains runtime-sensitive without silently dropping semantics.** The affected constructors are correctly identified. The plan requires rejecting unsupported newer syntax rather than discarding nonempty type parameters. Existing parser cases exercise ordinary functions, async functions, classes and newer syntax; the diagnostic patch is not treated as the final implementation.

**Golden acceptance is real.** Astichi `tests/test_ast_goldens.py:75–102` verifies both actual and expected provenance before normalizing trailer bytes. Therefore fixing generated output alone cannot satisfy the existing harness. The plan explicitly targets decoding the 34 failing golden cases and retains the fixtures.

**Structural verification and regeneration are separate.** The existing harness gates structural snapshots to Python 3.14 because interpreter-dependent template keys can vary. The plan requires checking the 90 snapshots on 3.11 while retaining the canonical regeneration policy. A verification gate adjustment can satisfy both requirements; no forced regeneration or fixture rewrite is implied.

**The support declaration follows behavior and packaging verification.** Astichi’s metadata, local matrix, CI and wheel selection currently omit 3.11. The plan names those surfaces and requires a normal clean wheel installation without metadata bypass or source-path substitution. The existing `abi3-py38` configuration and successful 3.11 build provide concrete grounds for retaining the native dependency configuration.

**Integration failures remain visible.** Existing lifecycle helpers can skip failed subprocesses, including syntax failures. The plan’s separate evidence requirement for each blocked integration prevents a green pytest exit alone from certifying integration success.

**Controlling contracts remain controlling.** The proposal contains no superseded-clause list or purported override of active design rules. Its future documentation updates agree with the active-handoff requirements. Its Rust inspection requirement applies to modified code; it does not claim a repository-wide conditional-compilation migration.

### Surface inspection

The public workflow remains install → compile/build → materialize → emit or obtain executable AST. `emit(provenance=True)` remains the documented default; `provenance=False` removes the tail. Marker-bearing recompilation continues to use `source_kind="astichi-emitted"`.

The public edited-source recovery route is documented: remove the provenance trailer when it no longer matches the edited body. The plan introduces no new command family, option, persistent installation hook or lifecycle operation.

The installation and use walkthrough was inspected from documentation and implementation only. Actual wheel installation, generation, execution and cross-runtime exchange remain future gates and were not performed during this read-only review.

## 3. Risks and next action

The Pyrolyze alias probe has a concrete risk to test. A straightforward replacement with `Annotated[Callable[P, T], PyrolyzeEventParam()]` preserves the metadata but changes its runtime representation. Pinned Pyrolyze `src/pyrolyze/compiler/kernels/v3_14/rewrite.py:2675–2689` unwraps `Annotated` and checks its underlying callable, ignoring the metadata. Imported handler classification uses that helper at lines 2495–2531. Existing `tests/test_ast_phase7_native_call_rewrite.py:18–46` includes an imported native helper and requires exactly one event wrapper.

Consequently, ordinary alias replacement cannot be assumed safe merely because subscription and metadata inspection work. This is a predicted compatibility failure from a static call trace, not a newly executed test. It does not block plan acceptance: step 3 explicitly places existing handler/slot compiler cases inside the disposable RED/GREEN feasibility gate and requires separate findings and a boundary check before additional compiler edits. That gate must retain its force.

Cross-runtime provenance fidelity, native availability in every test environment, and clean-wheel behavior remain unproven implementation obligations. The diagnostic counts do not close them.

The next action is to record Consistency GO for this exact plan revision only. Any later implementation must preserve the stated feasibility and scope gates; this verdict supplies no additional implementation authority.
