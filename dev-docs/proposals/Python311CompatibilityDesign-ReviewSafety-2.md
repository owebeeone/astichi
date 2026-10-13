# Python311CompatibilityDesign — Safety-AXIS REVIEW

**Review object:** `dev-docs/proposals/Python311CompatibilityDesign.md` and `dev-docs/proposals/Python311CompatibilityFindings.md`, controlled by `dev-docs/proposals/Python311CompatibilityDesign-ReviewBrief.md`, at Astichi `6dec499894cdcbdb232159def78949757e45f01e`. Revised design draft; production implementation has not started.

**Baseline:** Astichi `6dec499894cdcbdb232159def78949757e45f01e`; reference-only Pyrolyze `092d055294df97666bee473126708c2868379c2d`; reference-only YIDL `9d374f88445c426a56d5dd1f96fad112d1ec5417`. Committed documents and production sources were read with `git show SHA:PATH`; existing ignored evidence was inspected directly.

**Date:** 2026-10-13

**Axis:** Safety — graph fidelity, degraded and mixed-version paths, silent semantic loss, restoration boundaries and scope expansion. Independent, adversarial, read-only. The other axis runs in parallel; nothing here relies on it. Filed verbatim by the lane owner.

**Verdict: GO** — Safety P2-1 is closed for the design. Zero open P0, P1, P2 or P3 findings. This verdict accepts the proposed mechanism and its boundaries, not production implementation or completed compatibility coverage.

---

## Prior-finding closure table

This is a fresh replacement Safety review. Closure follows an independent static retrace of every original counterexample, supported by inspection of the existing probe code and recorded results. No probes were rerun.

| ID | Disposition claimed | Verified on corrected tree | Status |
| --- | --- | --- | --- |
| Safety P2-1 | Accept; replace AST-global substitution with AST reduction dispatch | Retraced class-as-data, a non-AST reducer receiving an AST class before execution, and class memo identity shared between reconstruction and metadata. The revised handler changes only the reduction stack result; global and memo resolution retain real classes. See invariant analysis below. | Closed for design acceptance; executable product regressions remain required |

## Changed-range analysis

Compared with `9829790d9a9183cc99a56490e4a26eaf5b0e0eb2`:

- `Python311CompatibilityDesign.md:3–8` identifies the revised draft and remediation record.
- Lines 61–92 replace global substitution with a private Python-level unpickler, subclass-local dispatch and an AST-specific `REDUCE` handler. They explicitly preserve class globals and memo entries.
- Lines 99–111 add the original counterexample traces, prohibit post-load proxy repair, distinguish structural and opaque cycles, and acknowledge the reader’s possible performance cost.
- Lines 119–122 and 192–196 distinguish superseded evidence from the revised reduction probe.
- Lines 203–215 add required class-reference, opaque-hook, memo-identity, cycle and private-hook compatibility coverage.
- The commit adds the remediation plan and verbatim round-1 reports, and updates the discoverability index. The findings record and controlling design brief are unchanged.

These changes address the accepted reconstruction-boundary finding. They introduce an explicit private stdlib dependency within the proposed Astichi reader, rather than a package dependency, writer change or persistence-format redesign. No production source, native code, tests, public documentation or package metadata changed between the design’s source reference and this checkpoint.

No **NEW ARCHITECTURAL root cause** was found.

## 0. Evidence base

Inspection only: no writes, tests, new probes, builds, installs, network access or Git mutations.

The settled tuple was checked at the beginning and end of the relevant repository inspections:

| Repository | Start and end HEAD | Working-tree result |
| --- | --- | --- |
| Astichi | `6dec499894cdcbdb232159def78949757e45f01e` | Clean |
| Pyrolyze | `092d055294df97666bee473126708c2868379c2d` | Clean |
| YIDL | `9d374f88445c426a56d5dd1f96fad112d1ec5417` | Same four unrelated untracked developer documents; contents not read |

Evidence inspected:

- Workspace `AGENTS_GWZ.md`, supplied standing scope/control-flow rules, Astichi `AGENTS.md`, and the applicable source-authority, provenance and delivery sections of `dev-docs/AstichiSingleSourceSummary.md` and `dev-docs/AstichiCodingRules.md`.
- The review-loop skill and canonical reviewer template.
- The complete revised design, findings, design review brief, accepted compatibility plan, plan review brief and checkpoint.
- Both filed round-1 reports and `Python311CompatibilityDesign-RemPlan-1.md:1–71`. No current-round peer prompt or report was inspected.
- Astichi `src/astichi/emit/api.py:15–87`, provenance tests in `tests/test_emit.py:78–167`, and native conversion paths in `native_engine/src/parser_ir.rs:437–719`.
- `scratch/python311-design/provenance_probe.py`, `reconstruction_boundary_red.py:9–47`, `reduction_probe.py:12–178`, `reconstruction-boundary-red.log`, `reconstruction-boundary-summary.json`, and all four `reduction-reader-*.log` files.
- Original design `summary.json`, `alias_probe.py:1–85`, extracted `runtime_helpers.py:1–22`, and all four final alias logs.
- Existing investigation `REPORT.md` and `summary.json`, establishing the baseline and disposable native-adapter results.
- Pinned Pyrolyze `AGENTS.md`, API aliases at `src/pyrolyze/api.py:383–386`, imported annotation discovery and matching at `src/pyrolyze/compiler/kernels/v3_14/rewrite.py:2461–2628,2675–2700`, and `tests/test_ast_phase7_native_call_rewrite.py:12–46`.
- Pinned Pyrolyze and YIDL package declarations, which retain their Python 3.12 minimums.
- Installed CPython stdlib `pickle.py` source for 3.11.14, 3.12.12 and 3.15.0a5: dispatch selection, global resolution, reduction, memo access and saved-state application. These inspected sources confirm the proposed hook’s stack mechanics.

The recorded reader logs report all sixteen ordinary writer/reader exchanges and all 42 golden payloads passing on each exercised reader. These are previously recorded results, not independently executed results.

## Problem, requirement provenance, and scope

The original operator requested a full Astichi Python 3.11 investigation, followed by a small compatibility plan, a short design phase and the design review loop. The authority and boundaries are recorded in `Python311CompatibilityPlan-ReviewBrief.md:7–16,33–46` and `Python311CompatibilityDesign-ReviewBrief.md:7–23`. Current permission covers documentation review/remediation and records; it does not authorize production implementation.

The observed problem is concrete. The unchanged 3.11 investigation recorded 604 failures. A disposable native constructor-arity adapter reduced the complete diagnostic run to 68 provenance failures, with 2,578 passes and 16 skips. The native extension built without dependency changes. This supports localized native conversion and provenance-reader corrections; it does not justify dependency upgrades or compiler replacement.

The existing decoder uses `pickle.loads`, and the unchanged writer uses the highest supported pickle protocol (`src/astichi/emit/api.py:26–40`). The original global-substitution approach addressed constructor arity but corrupted class references. The revised private reader provides a viable localized alternative: ordinary global loading remains intact, while AST instance reductions receive compatible allocation. Source reparsing remains verification, because using it as restoration would discard saved locations, metadata and identity.

The private `_Unpickler` choice is an implementation choice supported by concrete feasibility evidence. Its private status is explicit, capability checks and full runtime coverage are required, and failure must be clear (`Python311CompatibilityDesign.md:66–78`). It creates no unsupported infrastructure prerequisite for this documentation deliverable.

Proposed future scope remains Astichi conversion, provenance, packaging and tests, plus bounded Pyrolyze aliases. The additional compiler helper is expressly outside the accepted API-only boundary and requires separate authorization. YIDL, Lifecycle, Cache, Undoable and Dataclass remain reference-only.

The Pyrolyze finding is appropriately separate. The existing helper ignores `Annotated` metadata, and the isolated probe confirms event-recognition failure for the proposed ordinary alias. Actual imported discovery uses this helper, but full compiler behavior has not been demonstrated. `Python311CompatibilityFindings.md:28–38` records the suggested bounded remedy and its blocking status; `Python311CompatibilityDesign.md:203–215` retains the full-compiler gate before the amendment is applied. Discovery has not become edit permission.

No unauthorized component expansion or unsupported prerequisite blocks design acceptance.

## 2. Invariant analysis

### Original P2-1: class-as-data

The original counterexample places `(ast.Module, ast.Name)` in `tree._node_types`. The old `find_class` returns reconstruction functions for those globals, so metadata receives functions even though node reconstruction succeeds. The red script reproduces precisely this failure (`reconstruction_boundary_red.py:32–36`).

The revised reader returns real globals (`reduction_probe.py:65–69`). Loading a class into a tuple therefore retains its receiving-runtime identity. Adaptation occurs only when that class is the actual callable of a `REDUCE` operation (`71–79`). The writer includes class-valued metadata, and reader assertions compare it with actual receiving-runtime classes (`124–126,140–143`).

This attack fails against the revised mechanism.

### Original P2-1: opaque reducer argument

`ClassToken.__reduce__` returns a non-AST restore function with `ast.Name` as its argument. That function rejects a substitute before constructing the token (`reduction_probe.py:48–59`). The original reader fails this sequence, as recorded in `reconstruction-boundary-red.log`.

With the revised reader, global and memo reads supply real `ast.Name`. At the token’s `REDUCE`, the callable is `restore_class_token`, not an AST class; execution delegates to the ordinary handler. The identity check therefore occurs before the hook returns, with the real class already present. No post-load repair is involved.

The probe asserts the restored token’s class identity alongside the metadata references (`reduction_probe.py:143`). All four reader logs report this case passing.

This attack fails against the revised mechanism.

### Original P2-1: class memo identity

Let memo entry *m* hold `ast.Module`. A memo read pushes that class, followed by the constructor arguments. The revised handler pops the arguments and replaces only the class reference on the stack with the new node. It never assigns to memo entry *m*. A later memo read still returns `ast.Module`.

The inspected stdlib handlers support this trace: memo operations retain object references, while ordinary reduction replaces the stack callable with its result. The subclass mirrors that stack effect for AST allocation and copies the dispatch table locally (`reduction_probe.py:62–79`).

The probe checks that metadata’s `ast.Module` is the restored module’s type, that `ast.FunctionDef` matches the reconstructed declaration, and that repeated `ast.Name` references remain identical (`140–143`). The private structural reference also remains identical to `tree.body[0]` (`139`).

This attack fails against the revised mechanism. The design now requires all three original regressions (`Python311CompatibilityDesign.md:206–208`).

### State, unsupported semantics and defaults

Allocation through `__new__` leaves ordinary saved-state application intact. Constructor checks and post-load checks remain distinct, preventing saved state from bypassing the unsupported-type-parameter rule. The design explicitly checks `type_params` on 3.11 rather than relying on `_fields` traversal (`Python311CompatibilityDesign.md:81–97`).

The existing 3.11 logs record rejection of nonempty restored type parameters and unavailable `TypeAlias` nodes. Unknown semantic fields and unsupported constructor forms require rejection or an explicit tested rule. The exploratory reader implements fewer checks than this contract; the design expressly identifies that limitation (`113–117`).

Only understood defaults may be supplied. Mandatory names, bodies and source coordinates must not be invented (`39–50`). No silent downgrade is authorized.

### Cycles, shared nodes and opaque state

The revised design requires identity-aware structural traversal, explicit rejection of invalid structural cycles and retention of opaque metadata cycles (`105–108`). Shared identities are preserved rather than reconstructed independently.

The exploratory script still uses `ast.walk` and does not prove cycle handling. It is not accepted product code, and cycle coverage is an explicit implementation gate (`208–209`). I found no design clause permitting an endless traversal or rewriting opaque cycles.

### Mixed versions, source authority and blast radius

Encoding, fixtures and public signatures remain unchanged. The reader promise is limited to syntax representable on the receiver; newer syntax needs a compatibility rule or rejection. Decoder success does not replace source/provenance verification (`29–57,124–125`).

The production verifier compares structural dumps and would not detect the original private-metadata corruption (`src/astichi/emit/api.py:75–79`). The revised reduction boundary supplies the missing identity guarantee directly.

The dispatch table is subclass-local, custom non-AST reductions retain ordinary execution, and Python’s global dispatch and AST classes must remain unchanged. The correction therefore avoids global mutation and a wider persistence redesign.

Support advertisement still depends on the accepted native, suite, snapshot, wheel and integration gates. Blocked consumer integrations remain visible, and consumer package floors cannot be lowered from these probes (`Python311CompatibilityDesign.md:198–215`).

## 3. Risks and next action

Remaining implementation risks are explicit: private-hook compatibility across the complete runtime matrix, including unprobed 3.13; final rather than alpha 3.15 behavior; unknown-field classification; alternative constructor forms; structural/opaque cycles; actual API imports; full compiler recognition; and clean-wheel/native behavior. The Python-level reader’s performance also needs measurement. None is represented as already proven.

The existing provenance trust model remains unchanged, with no new security guarantee claimed.

The next action is to file this report verbatim and merge the independent verdicts on `6dec499894cdcbdb232159def78949757e45f01e`. Any acceptance must remain design acceptance only. Production work and the proposed Pyrolyze compiler-helper amendment require their stated authorization and gates.
