# Python311CompatibilityPlan — Safety-AXIS REVIEW

**Review object:** Astichi `dev-docs/proposals/Python311CompatibilityPlan.md` at `1bc8d2dc0c0978c19ad8d77237718ee690b5857e`, proposed implementation, reviewed 2026-10-13. Controlling draft: `dev-docs/proposals/Python311CompatibilityPlan-ReviewBrief.md` at the same revision. The documentation index is discoverability-only.

**Baseline:** Astichi `1bc8d2dc0c0978c19ad8d77237718ee690b5857e`; reference-only Pyrolyze `092d055294df97666bee473126708c2868379c2d` and YIDL `9d374f88445c426a56d5dd1f96fad112d1ec5417`. Committed sources were read with `git show SHA:PATH`; ignored investigation evidence was read directly.

**Date:** 2026-10-13

**Axis:** Safety — degraded and mixed-version behavior, saved-state fidelity, failure direction, irreversible steps, and scope expansion. Independent, adversarial, read-only. The other axis runs in parallel; nothing here relies on it. Filed verbatim by the lane owner.

**Verdict: GO** — zero P0, P1, P2, or P3 findings. This verdict accepts the proposed plan only; it does not establish implementation completion or Python 3.11 support.

---

## 0. Evidence base

All citations below identify paths relative to their owning repository. Workspace instructions are relative to the GWZ workspace root.

The review inspected:

- Workspace `AGENTS.md` and `AGENTS_GWZ.md`: workspace integrity, member-repository boundaries, path rules, and test-coverage requirements; the supplied standing rules for explicit control-flow and conditional-compilation boundaries.
- Astichi `AGENTS.md`: read-only review authority, authoritative documentation, test-led semantics, and regression requirements.
- Astichi `dev-docs/proposals/Python311CompatibilityPlan.md:1–87`, the complete controlling review brief, and `dev-docs/README.md:18–26`.
- Astichi `dev-docs/AstichiCodingRules.md`, particularly source/provenance rules and testing/process rules; relevant sections of `dev-docs/AstichiSingleSourceSummary.md`, including `:14–32`, `:165–189`, `:195–235`, `:800–821`, and `:1181–1216`.
- Astichi `src/astichi/emit/api.py:15–87`, `tests/test_emit.py:78–167`, and `tests/test_ast_goldens.py:42–113`: current encoding, reconstruction, verification, and golden acceptance behavior.
- Astichi `native_engine/src/parser_ir.rs:280–438` and `:643–717`: construction, locations, and the three version-sensitive declaration constructors; `native_engine/Cargo.toml:12–16`.
- Astichi `tests/test_native_engine_parser_ir.py:26–185`, `tests/conftest.py:19–89`, `tests/test_lifecycle_hot_path_python_gate.py:28–84`, and `tests/test_native_success_path_guards.py:51–143`.
- Astichi `docs/validation/perf/yidl_lifecycle_import_baseline.py:24–211`: the integration workload and native-engine checks.
- Astichi `pyproject.toml:1–118` and committed CI/publication matrix declarations located through source searches.
- Pyrolyze `AGENTS.md`, `dev-docs/README.md`, `src/pyrolyze/api.py:1–15` and `:383–386`, handler/slot test references, and `src/pyrolyze/compiler/kernels/v3_14/rewrite.py:2815–2877`.
- YIDL `pyproject.toml:5–20` and `:45–46`.
- Astichi `scratch/python311-investigation/2026-10-13/REPORT.md`, `summary.json`, `reference-snapshots.json`, the diagnostic constructor patch, baseline/diagnostic XML headers and failure messages, build-log completion records, and `diagnostic-all-tests.log:924–949` and `:1018`.
- The invoked review-loop skill and canonical reviewer template, as read-only process references.

The XML records confirm 2,662 collected cases, zero collection errors, 604 baseline failures and 106 skips; the complete diagnostic run records 68 failures and 16 skips. The diagnostic log records **2,578 passed, 68 failed, 16 skipped**. Its remaining golden failures reach `pickle.loads`; its twelve integration skips reach the Pyrolyze PEP 695 declaration. Build logs record successful release builds.

At both review start and review end, `git rev-parse HEAD` returned `1bc8d2dc0c0978c19ad8d77237718ee690b5857e`, and `git status --short` returned no entries. No files were changed, and no tests, builds, installations, network operations, or Git mutations were performed. No current peer prompt or report was inspected.

## Problem, requirement provenance, and scope

The original operator request was to run all Astichi tests on Python 3.11, permitting setup workarounds to discover actual failures. The subsequent authority permits a small compatibility plan and its review; it does not authorize production implementation or publication. This distinction is explicit in Astichi `dev-docs/proposals/Python311CompatibilityPlan-ReviewBrief.md`, under “Original authority” and “Scope and reference material.”

The observed problem is concrete: ordinary declarations fail in native AST construction because the converter supplies the newer `type_params` positional argument, and checked-in newer-runtime provenance fails during unpickling. The disposable adapter exposes the second problem without regenerating fixtures. These observations support localized constructor and decoder remedies; they do not establish a need for dependency upgrades or compiler redesign. The existing PyO3 configuration built successfully on 3.11, consistent with Astichi `native_engine/Cargo.toml:13` and the recorded build logs.

The plan appropriately distinguishes three routes:

1. Source execution with setup workarounds supplied diagnostic evidence.
2. Localized compatibility changes are proposed to address the demonstrated failures.
3. Normal installation requires separate wheel and metadata verification before support is advertised.

A source-path workaround therefore cannot satisfy the installed-wheel criterion. Conversely, packaging limitations are not used to justify dependency changes before testing the existing build route. See Astichi `dev-docs/proposals/Python311CompatibilityPlan.md:23–33` and `:65–76`.

The Pyrolyze syntax blocker is evidenced at its pinned `src/pyrolyze/api.py:383–386`. Replacing its two declarations is a proposed bounded compatibility approach, not a proven prerequisite for Astichi’s standalone runtime support. The plan requires a disposable feasibility probe and preserves marker and subscription behavior before proceeding. Further consumer/compiler blockers require separate findings and a boundary check; consumer package minimums must remain unchanged on this evidence alone. See Astichi `dev-docs/proposals/Python311CompatibilityPlan.md:12–19` and `:56–63`.

Currently editable components are documentation records only. The proposed future boundary covers Astichi conversion, decoding, packaging, matrix, tests and documentation, plus the bounded Pyrolyze alias correction. YIDL, Lifecycle, Cache, Undoable and Dataclass remain reference-only. Nothing in this review supplies implementation permission.

No unsupported blocking prerequisite or unauthorized implementation expansion was established. Full consumer Python 3.11 support remains a separately scoped limitation rather than a blocker to this plan’s acceptance.

## 2. Invariant analysis

**Saved provenance cannot be replaced by an apparently equivalent reparse.** The current golden harness verifies generated and checked-in provenance separately, then checks materialized outputs; payload normalization only removes encoding differences from the source comparison. See Astichi `tests/test_ast_goldens.py:64–103`. A remedy that reparsed the emitted body or regenerated the canonical payloads could conceal lost locations or metadata. The plan explicitly prohibits both shortcuts and requires constructor/state restoration coverage, metadata preservation, and runtime defaults. That attack fails against Astichi `dev-docs/proposals/Python311CompatibilityPlan.md:45–54`.

**Representable syntax must survive version crossings without silent loss.** The review attacked both newer-writer/3.11-reader and 3.11-writer/newer-reader sequences. The current decoder simply unpickles and checks the root type, while `verify_round_trip` compares runtime AST dumps; these checks alone do not prove private-metadata fidelity. See Astichi `src/astichi/emit/api.py:33–40` and `:75–79`. The proposed acceptance requirements add state-restoration tests, required runtime defaults, and ordinary round trips in both directions. An implementation that merely trims constructor arguments would not satisfy those requirements.

**Unsupported syntax must fail explicitly rather than become weaker syntax.** The diagnostic patch establishes constructor-arity feasibility, not support for newer syntax. The native plan requires explicit rejection of unsupported syntax and forbids silently dropping nonempty type parameters. The decoder is limited to syntax representable on 3.11 and must report unsupported nodes explicitly. See Astichi `dev-docs/proposals/Python311CompatibilityPlan.md:37–54`. The two existing TypeAlias exclusions remain visible rather than becoming evidence of success.

**Native verification must use the matching extension.** The plan requires rebuilding the matching extension and verifying native paths. This agrees with the active handoff’s prohibition on stale-binary fallback, Astichi `dev-docs/AstichiSingleSourceSummary.md:16–23`. Existing integration helpers request native execution and counters. A successful Python fallback cannot establish the planned native acceptance.

**Blocked integration cannot be laundered into passing compatibility evidence.** The integration helpers currently skip when their subprocess fails, regardless of the cause; see Astichi `tests/test_lifecycle_hot_path_python_gate.py:53–57` and `tests/test_native_success_path_guards.py:76–80`. Consequently, a green suite total alone would be inadequate. The plan requires exact remaining-skip records and separately evidenced consumer blockers, expressly forbidding blocked integrations from being counted as successes. See Astichi `dev-docs/proposals/Python311CompatibilityPlan.md:72–87`. This closes the misleading-success path at plan level.

**Alias changes cannot silently broaden consumer-support claims.** The plan requires both aliases, their `Annotated` markers, generic subscription, and the typo compatibility alias to retain behavior. The pinned compiler recognizes slot annotations through source names and runtime `Annotated` metadata, supporting the need for focused compiler checks rather than import-only validation. See Pyrolyze `src/pyrolyze/compiler/kernels/v3_14/rewrite.py:2815–2877`. The required feasibility probe and boundary check prevent a failed alias approach from automatically authorizing compiler or consumer redesign.

**Support declarations and publication remain gated.** The existing package minimum is 3.12; the diagnostic experiment bypassed it. The plan requires a clean 3.11 wheel installation without metadata bypass or source-path tricks and forbids publishing or changing release versions. See Astichi `pyproject.toml:10` and `dev-docs/proposals/Python311CompatibilityPlan.md:65–70`. No irreversible release action is authorized by this checkpoint.

**Source remains authoritative.** Reconstruction is scoped to existing AST/provenance restoration. The plan does not authorize hidden builder-state persistence or changes to the source-authority contract in Astichi `dev-docs/AstichiSingleSourceSummary.md:224–229` and `dev-docs/AstichiCodingRules.md`, §6.

No NEW ARCHITECTURAL root cause was identified.

## 3. Risks and next action

Compatibility implementation remains unproven. In particular, the current AST-dump checks do not establish location/private-metadata fidelity, and the proposed alias representation has not yet passed its disposable feasibility probe. Those are explicit implementation obligations, not evidence supporting a present support claim.

Existing pickle decoding and source-location metadata retain their current security and disclosure characteristics. This plan provides no provenance-security guarantee and does not require the deferred provenance redesign.

The next action is for the lane owner to file this report verbatim and merge the independent verdicts against the exact reviewed revision. Any resulting acceptance must remain plan acceptance only; production implementation requires its own authorization and verification.
