# Python311CompatibilityDesign — Consistency-AXIS REVIEW

**Review object:** `dev-docs/proposals/Python311CompatibilityDesign.md` and `dev-docs/proposals/Python311CompatibilityFindings.md`, controlled by `dev-docs/proposals/Python311CompatibilityDesign-ReviewBrief.md`, at Astichi `6dec499894cdcbdb232159def78949757e45f01e`. Revised committed design draft; production implementation has not started.

**Baseline:** Astichi `6dec499894cdcbdb232159def78949757e45f01e`; reference-only Pyrolyze `092d055294df97666bee473126708c2868379c2d`; reference-only YIDL `9d374f88445c426a56d5dd1f96fad112d1ec5417`. Repository documents and production sources were read using `git show SHA:PATH`; existing ignored evidence was read directly.

**Date:** 2026-10-13

**Axis:** Consistency — internal agreement, controlling contracts, public provenance surface, evidence accuracy, satisfiable acceptance gates and component authorization. Independent, adversarial, read-only. The other axis runs in parallel; nothing here relies on it. Filed verbatim by the lane owner.

**Verdict: GO** — zero P0, P1, P2 or P3 findings. This accepts the revised design’s consistency only; it does not establish production compatibility or authorize implementation.

---

## Prior-finding closure table

This is a fresh replacement Consistency review. The original Consistency report contained no numbered findings. The inherited process correction and the required retrace of the prior Safety architectural finding are recorded explicitly.

| ID | Disposition claimed | Verified on corrected tree | Status |
| --- | --- | --- | --- |
| Prior Consistency review: no P0–P3 findings | Retain GO subject to fresh review | Rechecked the controlling graph, evidence, public surface and revised mechanism independently. No finding established. | No finding to close |
| Prior Consistency cold-first inspection limitation | Repeat public inspection before design, plan and authority reads | After reading the generated task prompt and checking Astichi HEAD/status, the first object read was `README.md`, followed by public materialize/emit, composable and provenance walkthrough documentation. Authority, design, plan and prior reports followed. | Process limitation corrected in this review |
| Prior Safety P2-1: AST globals confused with reconstruction helpers | Replace global substitution with private AST reduction dispatch | Independently retraced class-as-data, opaque-hook argument and shared class-memo counterexamples through revised design lines 61–103 and `scratch/python311-design/reduction_probe.py:62–79,119–145`. Examined the retained red log and four corrected reader logs. | Design-level counterexample resolved; executable product regressions remain required |

The last row is this reviewer’s independent consistency assessment of the inherited counterexample, not a substitute for the current Safety reviewer’s verdict.

## Changed-range analysis

`git diff 9829790d9a9183cc99a56490e4a26eaf5b0e0eb2 6dec499894cdcbdb232159def78949757e45f01e` shows:

- Revised status and remediation provenance at `Python311CompatibilityDesign.md:3–8`.
- Replacement of AST-global substitution with real-class resolution and subclass-local reduction dispatch at lines 61–103.
- Explicit structural identity/cycle handling, opaque metadata preservation and decoder timing considerations at lines 105–111.
- Disclosure that the original mechanism failed and was superseded at lines 119–122.
- Corrected probe evidence at lines 192–196.
- Added class-data, opaque-hook, memo identity, cycle and private-unpickler acceptance coverage at lines 206–209.
- Addition of the remediation plan and verbatim round-1 reports, plus discoverability changes in `dev-docs/README.md`.

The findings record and review brief did not change. The patch is documentation only. A separate diff from the design’s production-source reference to the reviewed checkpoint showed no changes in `src`, `native_engine`, `tests`, `docs` or `pyproject.toml`.

The reconstruction mechanism changed materially, supporting the fresh-reviewer replacement required by `Python311CompatibilityDesign-RemPlan-1.md:60–67`. Its added cycle and private-hook gates address the changed reader boundary; they do not expand the product-component scope. No new architectural root cause was established.

## 0. Evidence base

Only inspection commands were used: `cat`, `rg`, `sed`, `nl`, `git show`, `git diff`, `git rev-parse HEAD` and `git status --short`. No files were written; no tests, probes, builds, installs, network operations or Git mutations were performed. The current-round peer prompt and report were not read.

The tuple was checked at the beginning and end:

| Repository | Start and end HEAD | Working-tree result |
| --- | --- | --- |
| Astichi | `6dec499894cdcbdb232159def78949757e45f01e` | Clean |
| Pyrolyze | `092d055294df97666bee473126708c2868379c2d` | Clean |
| YIDL | `9d374f88445c426a56d5dd1f96fad112d1ec5417` | Same four unrelated untracked developer documents; contents not read |

Actual reading order began with the generated review prompt and Astichi tuple check. The first object reads were:

1. Astichi `README.md`.
2. `docs/reference/materialize-and-emit.md:1–91`.
3. `docs/reference/composable-api.md:1–82`.
4. `docs/guide/using-the-api.md:1–270`.

Only afterwards were the repository authority, design, accepted plan and prior reports read. The cold-first Surface mandate was satisfied.

The controlling and review material inspected included:

- Workspace `AGENTS.md`, `AGENTS_GWZ.md` and supplied standing scope/control-flow rules.
- Astichi `AGENTS.md`; relevant summary sections including `dev-docs/AstichiSingleSourceSummary.md:195–276,800–820,1179–1194`; `dev-docs/AstichiCodingRules.md`.
- The review-loop skill and canonical reviewer template.
- Complete design, findings, design review brief, accepted plan, plan review brief and plan review checkpoint.
- Complete round-1 Safety report, prior Consistency report and remediation plan.
- Pinned Pyrolyze `AGENTS.md`, developer-documentation precedence and `dev-docs/ApiDesignRules.md`.

Production and acceptance traces included:

- Astichi `src/astichi/emit/api.py:15–87`, `src/astichi/ast_provenance.py:22–130`, `tests/test_emit.py:78–167` and `tests/test_ast_goldens.py:65–103`.
- Astichi `native_engine/src/parser_ir.rs:437–460,592–598,643–719,1147–1173` and relevant package/support declarations.
- Pyrolyze `src/pyrolyze/api.py:383–386`, imported-helper discovery and annotation matching in `src/pyrolyze/compiler/kernels/v3_14/rewrite.py:2480–2700,2839–2877`, and `tests/test_ast_phase7_native_call_rewrite.py:12–46`.
- Pinned Pyrolyze and YIDL package minimum declarations.
- Installed CPython 3.11.14, 3.12.12 and 3.15.0a5 Python-level unpickler source: dispatch, global loading, `REDUCE`, memo-preserving stack behavior and saved-state application.

Existing exploratory evidence inspected included `scratch/python311-design/summary.json`, `provenance_probe.py`, `alias_probe.py`, `runtime_helpers.py`, all four ordinary writer logs, all four final reader logs and all four final alias logs. Remediation evidence included `reconstruction_boundary_red.py`, `reconstruction-boundary-red.log`, `reconstruction-boundary-summary.json`, `reduction_probe.py` and all four `reduction-reader-*.log` files.

The prior investigation’s `summary.json`, `REPORT.md` and disposable native-constructor patch were also inspected. Recorded results were checked against their scripts and static source traces; they were not rerun.

## Problem, requirement provenance, and scope

The original operator requested a full Astichi Python 3.11 test investigation, followed by a small compatibility plan, a short design phase and the design review loop. Authority is recorded in `Python311CompatibilityPlan-ReviewBrief.md:7–16` and `Python311CompatibilityDesign-ReviewBrief.md:7–23`. Current permission covers documentation review/remediation and records, not production editing.

The observed problem is concrete. The unchanged investigation recorded 1,952 passes, 604 failures and 106 skips. The native engine built and loaded on 3.11 without dependency changes. A disposable constructor-arity adapter reduced the complete diagnostic run, including all 90 structural snapshots, to 2,578 passes, 68 provenance failures and 16 skips. These results support localized native conversion and provenance reconstruction changes rather than dependency replacement (`Python311CompatibilityPlan.md:26–36`).

The existing supported route was therefore tested before broader prerequisites were proposed. Reconstructing the saved graph preserves information that reparsing cannot supply: original coordinates, private metadata and shared identities. Preserving the encoding and canonical fixtures follows the accepted plan’s explicit requirements at lines 48–57.

The alias probe establishes a narrower external shortcoming: an ordinary `Annotated` alias retains its subscription and marker, but the unchanged recognition helper discards event metadata. It does not establish a full compiler regression or require broad consumer support. The finding records observation, evidence, impact, suggested correction and blocking scope accurately (`Python311CompatibilityFindings.md:6–38`).

The proposed compiler helper is outside the accepted API-only Pyrolyze boundary. The design expressly requires separate authorization and a disposable full-compiler feasibility gate, and states that this does not block standalone Astichi changes (`Python311CompatibilityDesign.md:18–23,160–174,209–215`). Neither discovery nor prior GO supplies implementation permission.

The private unpickler adapter remains local to Astichi’s existing provenance component. Its necessary hooks exist in inspected runtime sources and the retained probe exercises the proposed adapter without changing encoding or package dependencies. Runtime capability checks and complete matrix coverage remain gates, not completed evidence.

No blocking scope or necessity gap was found. YIDL, Lifecycle, Cache, Undoable and Dataclass remain reference-only. Broader consumer support, package-floor changes, dependency upgrades and publication remain separate work.

## 2. Invariant analysis

### Public provenance and source authority

The cold public surface gives a coherent first-use path: compile, compose, materialize, emit and verify. `emit` defaults to `provenance=True`; removing the trailing provenance comment is the documented way to discard stale provenance (`docs/reference/materialize-and-emit.md:35–62`). No new command, option, default or lifecycle operation is proposed.

The design preserves the encoding and public helper signatures, the module-root check and source/provenance mismatch checking (`Python311CompatibilityDesign.md:29–52`). These agree with `src/astichi/emit/api.py:26–40,56–87` and the source-authority rules in `AstichiCodingRules.md:190–215`.

The attack that successful decoding could override edited source failed: reparsing remains verification, explicitly excluded as a repair for failed decoding (`Python311CompatibilityDesign.md:124–125`).

### Reconstruction boundary and original counterexamples

The revised interception point distinguishes a class value from its invocation:

1. Global loading resolves a real receiving-runtime AST class.
2. Memo entries retain that class object.
3. An AST `REDUCE` invocation replaces only its stack result with the allocated node.
4. A later metadata memo read still yields the real class.
5. A non-AST reduction delegates normally and receives real AST-class arguments before execution.

This follows the specified mechanism at design lines 61–103 and the probe’s copied dispatch table and stack handling at `reduction_probe.py:62–79`. The ordinary unpickler’s `REDUCE` implementation replaces the invocation result on the stack, without changing its class memo entry.

Consequently, the original `_node_types` substitution and opaque-hook failure no longer follow from the design. The probe separately asserts class identity, class/node correspondence, opaque-hook identity and shared class references at lines 139–143. Its retained logs report all 16 writer/reader exchanges passing.

This is a viable localized consumer change. No post-load proxy repair, metadata rewrite or wire-format redesign is needed.

### Layout, saved state and normalization

Declaration layouts agree with the writer logs and native source: six function fields and five class fields on 3.11, with `type_params` appended on newer runtimes. The design distinguishes positional constructor mapping from validation after saved state arrives (`Python311CompatibilityDesign.md:79–97`).

The explicit restored-state check prevents a nonempty `type_params` attribute from escaping validation merely because 3.11’s `_fields` traversal ignores it. Unknown semantic additions and unsupported layouts require rejection; ordinary private metadata remains opaque. These requirements are compatible with retaining standard saved-state application.

Visited identities and explicit structural-cycle rejection can preserve shared structural nodes while leaving opaque metadata cycles intact (`105–108`). The exploratory probe’s simpler `ast.walk` traversal does not satisfy all production requirements, but the design explicitly requires additional negative/cycle coverage and does not present that script as accepted code (`113–117,203–209`).

### Native and alias behavior

The native proposal directly addresses the three unconditional newer-layout constructor calls at `native_engine/src/parser_ir.rs:643–719`. It retains construction/location handling and requires rejection before unsupported semantics are omitted. No broader compiler representation change is necessary.

The Pyrolyze citation is exact: `_runtime_annotation_matches` unwraps `Annotated` and returns without examining metadata at `rewrite.py:2686–2688`. Imported discovery resolves hints with `include_extras=True` and uses the event predicate (`2495–2531,2615–2628,2692–2700`). The alias probe therefore attacks a real caller seam.

The separate slot classification already inspects `PyrolyzeSlottedParam` metadata at `rewrite.py:2863–2869`. The proposed event correction preserves existing paths and requires plain/slot negatives. The exactly-one-event-wrapper acceptance citation is accurate (`tests/test_ast_phase7_native_call_rewrite.py:18–46`).

### Evidence and completion criteria

The design’s 42 retained golden cases and the plan’s 34 failing cases are compatible: the latter is the observed failing subset. Both preserve canonical fixtures.

The revised logs support the stated focused reconstruction results. They do not establish full API imports, compiler behavior, native conversion, installed wheels or complete runtime coverage. The design accurately distinguishes those pending gates, discloses missing 3.13 coverage and the alpha 3.15 runtime, and retains the accepted plan’s completion criteria (`Python311CompatibilityDesign.md:198–215`).

The reconstruction subsection explicitly supersedes the earlier global-substitution mechanism. It does not supersede the accepted plan’s support or completion criteria. No omitted controlling-clause amendment was established.

## 3. Risks and next action

Production proof remains outstanding for semantic-field classification, unsupported constructor forms, cyclic/shared graphs, private-unpickler capability checks, Python 3.13, actual alias imports, full compiler recognition, native builds and installed-wheel behavior. The Python-level reader may affect decoder timing; the design requires measurement without claiming a performance result. These acknowledged gates are not contradictory design requirements.

The next action is to file this report verbatim and merge the two independent verdicts on `6dec499894cdcbdb232159def78949757e45f01e`. Any acceptance must remain design-only. Production implementation and the additional Pyrolyze compiler-helper amendment retain their stated authorization boundaries.
