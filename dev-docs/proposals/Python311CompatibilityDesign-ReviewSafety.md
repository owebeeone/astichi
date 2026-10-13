# Python311CompatibilityDesign — Safety-AXIS REVIEW

**Review object:** `dev-docs/proposals/Python311CompatibilityDesign.md` and `Python311CompatibilityFindings.md`, controlled by `Python311CompatibilityDesign-ReviewBrief.md`, at Astichi `9829790d9a9183cc99a56490e4a26eaf5b0e0eb2`. Draft design; production implementation has not started.
**Baseline:** Astichi `9829790d9a9183cc99a56490e4a26eaf5b0e0eb2`; reference-only Pyrolyze `092d055294df97666bee473126708c2868379c2d`; reference-only YIDL `9d374f88445c426a56d5dd1f96fad112d1ec5417`. Committed documents and production sources were inspected with `git show SHA:PATH`; existing ignored evidence was read directly.
**Date:** 2026-10-13
**Axis:** Safety — degraded paths, graph fidelity, mixed-version compatibility, silent semantic loss and scope expansion. Independent, adversarial, read-only. The other axis runs in parallel; nothing here relies on it. Filed verbatim by the lane owner.

**Verdict: NO-GO** — one P2 finding blocks. No P0, P1 or P3 findings. I pre-commit to GO on a revision that resolves P2-1 as specified.

---

## 0. Evidence base

Inspection only; no writes, tests, new probes, builds, installs, network access or Git mutations.

- Verified `git rev-parse HEAD` and `git status --short` at the beginning and end. Astichi remained at the reviewed SHA with empty short status. Pyrolyze remained at its pinned SHA with empty short status. YIDL remained at its pinned SHA with the same four unrelated untracked developer documents; their contents were not read.
- Read workspace `AGENTS_GWZ.md`, supplied standing scope/control-flow instructions, Astichi `AGENTS.md`, `dev-docs/AstichiSingleSourceSummary.md` and `dev-docs/AstichiCodingRules.md`.
- Read the review-loop skill and canonical prompt template.
- Read the complete committed design, findings and design review brief; the accepted `Python311CompatibilityPlan.md`, its review brief and review checkpoint.
- Inspected Astichi `src/astichi/emit/api.py:15–87`, `tests/test_emit.py:78–167`, `src/astichi/ast_provenance.py:22–129`, and native declaration/unsupported-node conversion paths in `native_engine/src/parser_ir.rs:437–719`.
- Read `scratch/python311-design/summary.json`, `provenance_probe.py:1–139`, `alias_probe.py:1–85`, `runtime_helpers.py:1–22`, and all four final reader and alias logs.
- Read prior investigation `summary.json`, `REPORT.md`, and final baseline/diagnostic suite summaries. They substantiate the recorded 604 baseline failures and the diagnostic result of 2,578 passes, 68 provenance failures and 16 remaining skips.
- Inspected pinned Pyrolyze `AGENTS.md`, `src/pyrolyze/api.py:383–386`, imported-helper discovery and annotation matching in `src/pyrolyze/compiler/kernels/v3_14/rewrite.py:2486–2700`, and `tests/test_ast_phase7_native_call_rewrite.py:12–46`.
- Inspected pinned Pyrolyze and YIDL package minimum declarations. Both retain Python 3.12 floors.
- `git show --stat` confirms that the reviewed Astichi commit contains developer documentation only.

The counterexample below is a static reconstruction trace. It was not executed, in accordance with the review’s command restrictions.

## Problem, requirement provenance, and scope

The original operator requested a complete Astichi Python 3.11 investigation. The subsequent authority covers a small compatibility plan, a short design phase and this design review loop. It does not authorize production implementation. The traceable directives are recorded in `Python311CompatibilityPlan-ReviewBrief.md:7–16` and `Python311CompatibilityDesign-ReviewBrief.md:7–23`.

The observed Astichi problems are concrete: native declaration constructors supply newer-runtime arities, and the existing provenance decoder invokes ordinary unpickling on newer-runtime AST reductions. The prior disposable adapter demonstrated that the native engine can build and run on 3.11 without dependency upgrades; after the localized arity adjustment, remaining exercised Astichi failures concerned existing golden provenance. That supports localized conversion and reader changes rather than dependency or compiler replacement.

Preserving the existing goldens and provenance representation follows the accepted plan and the source-authority rules. Re-parsing source as a substitute for saved graph state would discard locations, metadata and object identity, so rejecting that alternative is justified. The design’s reader-only remedy addresses the observed problem, subject to P2-1.

The Pyrolyze alias feasibility evidence establishes a narrower result: ordinary `Annotated` aliases retain subscription and markers, but the unchanged matching helper fails to recognize resolved event annotations. It does not establish a full compiler regression. Keeping standard-library named aliases on newer runtimes is a supported localized alternative, evidenced by the existing probes. The proposed helper correction is separately bounded and explicitly requires an authorized scope amendment and a disposable full-compiler check before production editing (`Python311CompatibilityDesign.md:123–137, 160–169`; `Python311CompatibilityFindings.md:28–38`).

Current editable components are Astichi design/review records. Proposed future components are Astichi compatibility and bounded Pyrolyze aliases; the additional compiler helper remains a proposal. YIDL, Lifecycle, Cache, Undoable and Dataclass remain reference-only. No unsupported dependency or infrastructure prerequisite blocks this documentation deliverable.

The separately recorded Pyrolyze recognition shortcoming is an external compatibility finding, not permission to expand implementation. Consumer package floors and complete consumer 3.11 support remain deferred. I found no unauthorized scope expansion in the reviewed checkpoint.

## 1. Findings

### [P2-1] AST-global interception does not distinguish reconstruction from class references in opaque metadata

**Location:** `dev-docs/proposals/Python311CompatibilityDesign.md:59–74`, against its preservation contract at lines 37–48. The concrete interception used as feasibility evidence is `scratch/python311-design/provenance_probe.py:19–52`.

**Classification:** **NEW ARCHITECTURAL root cause** at the reconstruction boundary: the proposed interception point conflates an AST class used as a constructor with the same global used as ordinary saved data. This is local to the compatible reader; it does not require redesigning the persistence format.

**Violated invariant:** Ordinary private metadata must retain its existing restoration behavior, including saved class references. Compatibility reconstruction must not silently transform metadata while successfully restoring the source AST.

**Counterexample and static trace:**

1. Begin with an ordinary, runtime-representable module, for example `ast.parse("x = 1\n")`.
2. Store an AST class in private metadata, such as `tree._node_types = (ast.Module, ast.Name)`, and encode it through the unchanged `encode_provenance`.
3. Pickle records AST class globals for both node reductions and the metadata tuple. Memo references can reuse those same global objects.
4. The demonstrated `find_class` interception returns `construct_declaration(node_type)`, a reconstruction function, whenever an AST class global is encountered (`provenance_probe.py:44–52`). It does not distinguish why the global is being loaded.
5. Node reductions call that function and produce AST instances, but the metadata tuple receives the function itself. Consequently, `restored._node_types[1] is ast.Name` is false.
6. The module root check still succeeds. `verify_round_trip` compares `ast.dump` values, which omit this private metadata (`src/astichi/emit/api.py:37–40, 75–79`), so source verification cannot detect the alteration.

The same boundary affects a non-AST metadata reduction that receives an AST class as an argument: its normal reconstruction callable receives the replacement function rather than the class. Such a callable can fail or make a different decision before any post-load repair runs.

**Impact:** A compatible reader implemented through the demonstrated global substitution can silently change previously preserved metadata even on a same-runtime exchange with ordinary syntax. The design promises opaque metadata preservation but does not specify how its reconstruction mechanism avoids this collision. The existing probes cover string metadata and one shared AST instance, not globals used as data (`provenance_probe.py:88–106`). Their success therefore does not establish this boundary.

The exploratory-script disclaimer at design lines 81–85 correctly prevents treating the script as accepted implementation, but the missing distinction belongs in the design mechanism itself. Merely adding another post-load check does not preserve the behavior of opaque reconstruction hooks that have already executed.

**Required correction:** Specify a reconstruction mechanism that distinguishes AST reduction dispatch from AST globals used as values. Actual class references must reach metadata containers and non-AST reconstruction callables unchanged, while AST instance reductions still receive the layout-compatible allocation behavior. Provide a concrete restoration trace showing that distinction. Do not narrow the metadata contract or claim that source verification supplies this guarantee.

**Closure/regression test:** The revised design must explicitly require:

- Same-runtime and cross-runtime round trips of an ordinary module containing AST class references in private metadata, asserting receiving-runtime class identity.
- A non-AST metadata reduction whose reconstruction callable receives an AST class argument, asserting that it receives the real class before executing.
- Preservation of memo identity when one AST global is used by both a node reduction and metadata.

For this documentation-only review, closure requires a viable revised mechanism and a static retrace of the counterexample. Executable regressions belong to the later authorized implementation gate.

## 2. Invariant analysis

- **No semantic downgrade of unsupported syntax:** The design requires rejection of unavailable nodes, nonempty unsupported type parameters and unknown semantic additions. Its explicit post-state check closes the obvious attack of restoring nonempty `type_params` through pickle state after an initially harmless constructor (`Python311CompatibilityDesign.md:43–79`). Existing final logs demonstrate the saved-state and unavailable-`TypeAlias` negatives on 3.11.
- **State arrives before validation:** Allocation through `__new__` avoids incomplete-constructor warnings and preserves the opportunity for pickle to restore saved state and memo references. Final probe logs support this approach for the exercised ordinary declarations. P2-1 concerns the interception boundary, not that allocation decision.
- **Locations and shared AST instances:** Existing writer/reader samples compare saved node dictionaries and assert that the private shared reference remains identical to the structural class node. All 16 exchanges passed. This is meaningful evidence for those samples, but not proof of every metadata graph.
- **Cycles:** Existing probes do not exercise cycles. The design does not mandate a cycle-unsafe traversal, so I do not infer a separate defect from the exploratory use of `ast.walk`. A production traversal must account for shared identities and distinguish opaque metadata cycles from invalid structural AST cycles.
- **Source remains authoritative:** The design preserves source/provenance mismatch checking and rejects source re-parsing as a decoding repair. No proposed path lets restored provenance override edited source or claim that decoding alone verifies a round trip.
- **Mixed writers and readers:** Encoding and fixtures remain unchanged; the remedy is a compatible reader. The design limits its evidenced exchange to ordinary declarations and requires explicit rules or rejection for newer semantics. It does not claim that older readers acquire newer grammar support.
- **Alias recognition and scope:** The unchanged helper’s early `Annotated` return explains the isolated recognition failure. The proposed correction requires event-only recognition, negative slot/plain-callable coverage and retained newer-runtime compiler tests. Full compiler evidence remains an explicit gate, and the helper change is not silently authorized.
- **Support and irreversible actions:** Support advertisement follows native, full-suite, wheel and integration verification. Blocked integrations cannot count as passes. No publication, release, fixture migration or dependency upgrade is authorized by design acceptance.

## 3. Risks and next action

Remaining implementation risks include unknown-field classification, cyclic/shared graph traversal, complete runtime coverage including 3.13, actual API imports, full compiler recognition, native rebuilding and clean-wheel behavior. The design identifies these as future gates; the focused probes do not satisfy them. The unchanged pickle representation also retains its existing trust model and receives no new security guarantee.

The next action is one bounded design remediation for P2-1, followed by reviewer verification against a new exact committed revision. Production implementation remains outside this review’s authorization.
