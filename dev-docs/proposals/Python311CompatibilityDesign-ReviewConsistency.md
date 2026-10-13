# Python311CompatibilityDesign — Consistency-AXIS REVIEW

**Review object:** `dev-docs/proposals/Python311CompatibilityDesign.md` and `dev-docs/proposals/Python311CompatibilityFindings.md` at Astichi `9829790d9a9183cc99a56490e4a26eaf5b0e0eb2`. Committed design draft; production implementation has not started.

**Baseline:** Astichi `9829790d9a9183cc99a56490e4a26eaf5b0e0eb2`; reference-only Pyrolyze `092d055294df97666bee473126708c2868379c2d`; reference-only YIDL `9d374f88445c426a56d5dd1f96fad112d1ec5417`. Committed documents and production sources were inspected with `git show` at these revisions. Existing ignored probe evidence was read directly.

**Date:** 2026-10-13

**Axis:** Consistency — internal agreement, controlling-document compatibility, evidence accuracy, satisfiable acceptance gates and authorized component boundaries. Independent, adversarial, read-only. The other axis runs in parallel; nothing here relies on it. Filed verbatim by the lane owner.

**Verdict: GO** — zero P0, P1, P2 or P3 findings. This verdict accepts the design’s consistency, not production implementation or a completed compatibility matrix. The public-surface inspection order limitation is disclosed below.

---

## 0. Evidence base

Inspection commands only were used: `cat`, `rg`, `git show`, `git grep`, `git diff --stat`, `git rev-parse HEAD` and `git status --short`. No files were written, no tests or probes were executed, and no builds, installs, network operations or Git mutations were performed.

The settled tuple was verified at review start and end:

| Repository | Start and end HEAD | Working-tree result |
| --- | --- | --- |
| Astichi | `9829790d9a9183cc99a56490e4a26eaf5b0e0eb2` | Clean |
| Pyrolyze | `092d055294df97666bee473126708c2868379c2d` | Clean |
| YIDL | `9d374f88445c426a56d5dd1f96fad112d1ec5417` | Same four unrelated untracked developer documents at both checks; their contents were not read |

The controlling graph inspected included:

- Workspace `AGENTS.md`, `AGENTS_GWZ.md` and the supplied standing scope/control-flow instructions.
- Astichi `AGENTS.md`, `dev-docs/AstichiSingleSourceSummary.md`, and `dev-docs/AstichiCodingRules.md`. Relevant contracts include source authority and provenance limitations at `AstichiSingleSourceSummary.md:224–228`, round-trip behavior at `251–264` and `800–820`, and delivery/testing discipline at `1179–1194`.
- The review-loop skill and canonical review-prompt template supplied by the lane owner.
- `dev-docs/proposals/Python311CompatibilityDesign-ReviewBrief.md:1–72`.
- `dev-docs/proposals/Python311CompatibilityPlan.md:1–90`, its `ReviewCheckpoint:1–75`, and its `ReviewBrief:1–65`.
- The complete design at `Python311CompatibilityDesign.md:1–169` and findings record at `Python311CompatibilityFindings.md:1–38`.
- Pyrolyze `AGENTS.md:1–95`, its developer-documentation index, and `dev-docs/ApiDesignRules.md:1–83`.

Public support and provenance surfaces inspected were Astichi `README.md:27–33,333–368`, `docs/reference/public-api.md:130–140`, `docs/reference/materialize-and-emit.md:35–73`, and the provenance walkthrough in `docs/guide/using-the-api.md`. The public documents were read before production implementation source, but **after** the controlling and design documents. The mandated cold-first reading order was therefore not met. This procedural limitation is disclosed rather than represented as a defect in the reviewed documents.

Production-source traces included:

- Astichi `src/astichi/emit/api.py:15–87`, `src/astichi/ast_provenance.py:22–38,68–98`, `tests/test_emit.py:78–167`, and the provenance assertions in `tests/test_ast_goldens.py:66–103`.
- Astichi `native_engine/src/parser_ir.rs:592–598,643–719,1147–1173`; `native_engine/Cargo.toml:13–15`; and `pyproject.toml:5–33,73–82`.
- Pyrolyze `src/pyrolyze/api.py:77–84,383–386`; `src/pyrolyze/compiler/kernels/v3_14/rewrite.py:2461–2628,2655–2700,2815–2877`; and `tests/test_ast_phase7_native_call_rewrite.py:12–46`.
- YIDL `pyproject.toml:5–20,45–46`, confirming that its existing support floor remains separate.

Existing evidence inspected included:

- `scratch/python311-design/summary.json`, the reconstruction and alias scripts, extracted annotation helpers, all four writer logs, and all eight final reader/alias logs.
- `scratch/python311-investigation/2026-10-13/summary.json`, diagnostic failure evidence and the disposable native-constructor adapter patch.

The final logs agree with the design’s table: four readers each consumed four ordinary writer payloads and all 42 existing golden payloads; the 3.11 reader rejected the recorded newer `TypeAlias` payloads and nonempty unsupported restored state. Alias logs report ordinary-alias recognition failure in the unchanged helper, successful isolated metadata-aware event recognition, and named-alias construction/recognition on the newer probed runtimes. These are previously recorded results, not independently rerun results.

`git diff --stat` between the design’s Astichi source reference and the reviewed revision produced no changes for production source, native code, tests, public docs or package metadata.

## Problem, requirement provenance, and scope

The original operator request was to run Astichi’s full tests on Python 3.11 and discover actual failures. The subsequent planning and short design phase authorized documentation work; the present directive authorizes the design review loop. These boundaries are recorded in `Python311CompatibilityPlan-ReviewBrief.md:7–16` and `Python311CompatibilityDesign-ReviewBrief.md:7–23`. Neither the accepted plan nor this design authorizes production edits.

The concrete compatibility problem is established by the existing investigation. The unchanged 3.11 run recorded 604 failures. The disposable native constructor adapter reduced the diagnostic run to 68 failures while enabling all 90 normally gated structural snapshots; the remaining failures involved expected golden provenance. The accepted plan correctly identifies the native declaration arities and saved AST reconstruction as localized problems rather than evidence that PyO3, RustPython or the dependency graph must change (`Python311CompatibilityPlan.md:26–36,40–57`).

The design preserves that supported route:

- Adapt the three existing declaration conversions to the receiving runtime’s layout.
- Restore compatible saved AST state without changing the public provenance format or replacing provenance with reparsed source.
- Remove the two observed Pyrolyze PEP 695 syntax declarations using existing standard-library typing facilities.
- Retain package, wheel, full-suite and runtime-matrix gates before advertising support.

The alias feasibility evidence establishes a failure of the proposed ordinary alias with one unchanged recognition helper. It does **not** establish that full consumer support is impossible or that broader compiler work is required. The design and findings make this distinction explicitly (`Python311CompatibilityDesign.md:123–137,155–169`; `Python311CompatibilityFindings.md:33–38`).

The proposed additional helper correction is component-level scope expansion even though it preserves public API names. It is correctly recorded as a proposed amendment requiring authorization, and the design requires a disposable full compiler probe before applying that amendment. It is not made a prerequisite for standalone Astichi changes.

Current editable scope belongs to the lane owner and consists of Astichi design/findings/brief/index and review/remediation records. This reviewer’s task is read-only. YIDL, Lifecycle, Cache, Undoable and Dataclass remain reference-only. No dependency upgrade or infrastructure replacement is asserted as necessary.

No blocking authority or necessity gap was found. Broader consumer package floors and unproven consumer execution remain separate matters; they are not silently converted into current deliverables.

## 2. Invariant analysis

### Public provenance and source authority remain aligned

The public surface currently exposes `encode_provenance`, `decode_provenance`, `extract_provenance`, `verify_round_trip` and `RoundTripError`; emission defaults to provenance enabled (`docs/reference/public-api.md:130–140`; `docs/reference/materialize-and-emit.md:35–62`).

The design preserves the representation and signatures and retains root checking and source/provenance verification (`Python311CompatibilityDesign.md:29–50`). This agrees with the actual encoding pipeline and mismatch check in `src/astichi/emit/api.py:26–40,56–87`.

The attack that decoding success might replace source verification failed: the design expressly forbids that substitution and keeps reparsing as verification rather than provenance repair (`Python311CompatibilityDesign.md:49–50,87–88`). Source remains authoritative, as required by `AstichiCodingRules.md:192–210` and the active summary.

No new public callable, option, default or lifecycle operation is introduced. The existing documented way to discard stale provenance remains removing the trailing provenance comment (`docs/reference/materialize-and-emit.md:48–53`).

### Constructor mapping and restored-state checks describe distinct stages

The declaration field counts agree with the existing writer logs and native conversion source. Functions and async functions use six ordinary fields on 3.11; classes use five. The newer layouts append `type_params`.

The design distinguishes mapping reduction arguments from validating the completed saved graph (`Python311CompatibilityDesign.md:64–79`). That distinction matters because saved state can replace constructor values. It explicitly checks the 3.11-invisible `type_params` attribute instead of relying only on `_fields` traversal.

The design permits only understood defaults and requires rejection of unavailable nodes, unsupported layouts and unknown semantic additions (`Python311CompatibilityDesign.md:40–48,72–85`). Its promise is ordinary syntax representable on the receiver, not arbitrary newer grammar. These provisions are mutually satisfiable; no contradictory acceptance requirement was found.

The exploratory reader checks fewer negative cases than the normative design requires. The document accurately identifies that limitation instead of treating the script as accepted implementation (`Python311CompatibilityDesign.md:81–85`).

### Native conversion remains a localized implementation boundary

The actual native converters unconditionally pass the newer declaration argument at `native_engine/src/parser_ir.rs:643–719`. The design’s receiving-runtime layout selection directly addresses that observed failure.

Native conversion and saved-graph reconstruction remain separate responsibilities. Both reject nonempty unsupported type parameters; neither silently removes their semantics (`Python311CompatibilityDesign.md:90–102`). The proposed location preserves existing direct construction and location handling without requiring a compiler-wide representation change.

The design contains no modified Rust declarations or conditional-compilation examples that violate the standing explicit-boundary rules. The accepted plan retains inspection of modified Rust boundaries as an implementation gate.

### The alias finding agrees with actual callers

The findings record’s cited helper location is accurate. At Pyrolyze `rewrite.py:2686–2688`, `Annotated` is unwrapped and the result returned without examining its metadata. The event caller requests the public alias names and `PyrolyzeEventParam` at `2692–2700`.

Imported helper discovery resolves hints with `include_extras=True` (`rewrite.py:2615–2628`) and uses the event helper to select event parameters (`2495–2531`). Thus the isolated resolved-annotation failure attacks a real caller seam.

The proposed correction checks requested marker metadata while retaining existing paths and keeping plain or slot-only callables negative (`Python311CompatibilityDesign.md:130–134`). The separate slot classification path already examines `PyrolyzeSlottedParam` metadata at `rewrite.py:2863–2869`; the design does not assert that this needs another correction.

The exactly-one-wrapper citation is also accurate: `tests/test_ast_phase7_native_call_rewrite.py:18–46` covers imported and local helper forms and checks one event wrapper while preserving the plain formatter callable.

The documents do not inflate helper evidence into full compiler evidence. The full compiler outcome remains an explicit gate.

### Evidence and completion criteria are compatible

The design explicitly discloses that 3.13 was not probed and that 3.15 was an alpha interpreter (`Python311CompatibilityDesign.md:155–158`). It requires subsequent exchange across the complete runtime matrix and the accepted plan’s native, suite, snapshot, packaging, clean-wheel and documentation gates (`160–169`).

Keeping all 42 canonical cases is compatible with the plan’s use of the 34 failing cases: one describes retained coverage, the other the observed failing subset. No fixture rewrite or duplicate bespoke success harness is required.

The design refines the accepted plan without claiming to supersede its completion criteria. Its newer-runtime `TypeAliasType` construction still uses `ParamSpec`/`TypeVar` pairs and preserves the public alias contract; the proposed compiler-helper amendment is explicitly outside the prior API-only boundary. No omitted superseded-clause list was found.

## 3. Risks and next action

Implementation proof remains outstanding for unknown semantic fields, unsupported constructor layouts, complete saved-graph normalization, actual API imports, full compiler behavior and the complete runtime/wheel matrix. The existing shared-reference probe covers one private reference to an ordinary declaration; it does not exhaust opaque metadata or graph shapes. These limits are acknowledged by the design and do not constitute contradictory design requirements.

The public-surface inspection was not performed cold-first. The lane owner should retain that process limitation when merging the verdict.

The next action is to file this report verbatim and merge the two independent verdicts on the settled revision. Any resulting acceptance must remain design acceptance only; the proposed compiler-helper change still requires its stated feasibility gate and explicit scope authorization before production edits.
