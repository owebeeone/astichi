# Python 3.11 compatibility design

Status: **accepted at `6dec499894cdcbdb232159def78949757e45f01e` after
[Consistency](Python311CompatibilityDesign-ReviewConsistency-2.md) and
[Safety](Python311CompatibilityDesign-ReviewSafety-2.md) reported GO; this accepts
the design only**. Production implementation has not started. The
[review checkpoint](Python311CompatibilityDesign-ReviewCheckpoint.md) records
the bounded reader redesign and independently verified closure. The
[accepted plan](Python311CompatibilityPlan.md) remains controlling; neither
review authorizes the additional compiler component identified below.

## Deliverable and boundary

This design step adds documentation and isolated probes only. Astichi conversion,
provenance, packaging and tests are the proposed implementation components.
Pyrolyze's two API aliases remain a bounded proposed integration change. YIDL,
Lifecycle, Cache, Undoable and Dataclass remain reference-only. No dependency,
workspace, release or publication changes are proposed.

The probe confirmed that replacing the aliases alone changes imported-event
recognition. A correction to one existing Pyrolyze compiler helper is therefore
proposed explicitly in the [findings record](Python311CompatibilityFindings.md).
That component lies outside the accepted plan's API-only Pyrolyze boundary and
requires an authorized scope amendment before production edits. It does not
block the Astichi-only changes.

Source references: Astichi `3d31bd729ef09472526237cef8d7c62c23a07d55`,
Pyrolyze `092d055294df97666bee473126708c2868379c2d`. Current production behavior
and supported-version declarations are unchanged.

## Provenance contract

Keep the existing base64 → zlib → pickle representation and public
`encode_provenance`, `decode_provenance`, `extract_provenance` and
`verify_round_trip` signatures. Encoding remains unchanged; existing readers and
fixtures are not migrated to a new format. The work adds a compatible reader
for existing AST pickles, not a new persistence system or security guarantee.

For syntax representable on the receiving runtime:

- Restore node classes and field values, ordering, source locations, private
  Astichi metadata and pickle memo references. Preserve shared objects rather
  than substituting a freshly parsed tree.
- Supply only understood runtime defaults, notably `type_params=[]` when an
  ordinary 3.11 declaration is read on 3.12+. Never invent names, bodies,
  mandatory field values or source coordinates.
- Accept an absent or empty newer `type_params` field on 3.11. Reject nonempty
  type parameters, including values restored later through pickle state.
- Reject an unavailable AST node or an unsupported constructor layout with a
  contextual `TypeError` identifying the node/runtime. Unknown semantic field
  additions must not be silently treated as harmless metadata. Ordinary private
  metadata remains opaque and retains its existing restoration behavior.
- Keep the existing root-type check and source/provenance mismatch check.
  Successful decoding never substitutes for `verify_round_trip`.

The verified exchange is ordinary class/function/async-function syntax between
3.11 and existing newer runtimes. This does not promise that newer grammar can
run on older interpreters, or establish every generic/type-parameter exchange.
Newer nodes and semantic fields need an explicit compatibility rule or rejection.

### Reconstruction mechanism

Use a private reduction-aware reader, factored into a cohesive helper under
`src/astichi/emit/`, called by `decode_provenance`. **Global resolution always
returns real classes, never constructor helpers or proxies.** AST class objects
used as metadata therefore retain receiving-runtime identity.

The concrete mechanism is a subclass of CPython's Python-level
`pickle._Unpickler`, with a copied subclass-local dispatch table and an overridden
`REDUCE` handler. This is an explicit private stdlib dependency, isolated in the
compatibility helper: check the required base/dispatch/stack hooks on supported
runtimes and fail clearly if unavailable. Do not modify Python's global dispatch
or AST classes. The full runtime matrix must exercise that adapter; 3.13 remains
a pending gate. This does not introduce a new package dependency.

At `REDUCE`, inspect the actual callable on the stack. Adapt only actual standard
AST class constructors; preserve global loading and memo references. Delegate
non-AST reductions unchanged, including opaque restore hooks receiving AST class
arguments. Other pickle operations retain normal handling; unsupported AST
constructor forms need explicit rejection or a tested compatibility rule.
For an adapted AST reduction:

1. Resolve the receiving runtime's node class and reject unavailable classes.
2. Map positional declaration arguments by the two known layouts: functions
   have six fields on 3.11 and a seventh `type_params` on 3.12+; classes have
   five and six respectively. Handle legacy zero-argument/state reductions too.
   Other nodes retain their known runtime layouts; unsupported arities fail.
3. Allocate through the AST class's `__new__`, assign understood constructor
   fields, and replace only that reduction's stack result with the new node.
   The memoized class object remains unchanged. Let standard pickle restore
   saved state and references; avoid incomplete constructors before state arrives.
4. After loading the complete graph, normalize understood missing defaults and
   check unsupported semantic additions in both constructor arguments and saved
   state. Only then return the module.

The post-load check is necessary: pickle state can replace constructor fields,
and 3.11's `ast.walk` ignores `type_params` because it is absent from `_fields`.
Check that attribute explicitly on affected declarations. A compatibility field
must not be silently lost merely because the runtime traversal ignores it.

For example, a global `ast.Module` can be memoized, invoked by a node reduction,
and later loaded into `tree._node_types`. The adapted invocation yields a module,
while the global memo slot still yields `ast.Module`. A non-AST reduction calling
`restore_token(ast.Name)` likewise sees the real class before it executes. A
post-load proxy repair is prohibited: it would be too late for that hook.

Normalization uses visited identities for structural AST nodes, preserving shared
nodes and avoiding unbounded revisits. Invalid structural cycles fail clearly;
opaque metadata cycles are retained rather than rewritten. AST class references
are values, not nodes to normalize. The compatibility path must not change
non-AST hook semantics. Decoder timing should be recorded on representative
inputs because the Python-level reader can cost more than C unpickling; no speed
claim or new performance prerequisite follows from the design probes.

The first probe used normal incomplete constructors and emitted deprecation
warnings on newer readers. The allocation/state approach removed those warnings
and passed with warnings treated as errors. Production code must also validate
known layouts and semantic additions; the exploratory script is not a complete
implementation or a replacement for negative tests.

The initial global-substitution probe also failed Safety's class-reference and
opaque-hook counterexamples. Its evidence remains retained, but that mechanism
is superseded. The reduction-dispatch probe passed those cases across the same
four runtimes without changing the provenance format or metadata contract.

Canonical golden files stay unchanged. Source re-parsing remains the existing
round-trip verification step, not a repair path for failed provenance decoding.

## Native conversion

The three declaration converters in `native_engine/src/parser_ir.rs` must select
the receiving AST layout before supplying `type_params`. Determine the runtime
capability once per converter context where practical; keep existing direct
constructor paths and location handling. On 3.11, reject nonempty type parameters
before conversion rather than omitting their semantics. Newer-only AST nodes
also need explicit unsupported-runtime diagnostics.

This is separate from provenance decoding: native conversion builds a new AST,
whereas the compatible reader restores an already saved graph. Both follow the
same empty-versus-nonempty type-parameter rule. Neither requires changes to
PyO3, RustPython or a compiler-wide representation.

## Pyrolyze alias representation

Remove raw PEP 695 declarations from `src/pyrolyze/api.py` so 3.11 can parse the
module. Keep the public `PyrolyzeHandler`, `SlotCallable` and `PyrolyteHandler`
names, two-parameter subscription and existing `Annotated` marker instances.

On 3.12+, construct the named aliases with the standard-library `TypeAliasType`
constructor, using separate `ParamSpec("P")`/`TypeVar("T")` pairs for each alias.
This retains the named-alias representation and avoids importing a backport.
On 3.11, use the corresponding `Annotated[Callable[P, T], marker]` aliases with
separate parameter pairs. Select the representation through ordinary runtime
control flow; do not evaluate PEP 695 source strings during production imports.

The cross-runtime public contract is subscription, callable parameter/result
types and event/slot markers. Exact alias object types, lazy-value internals and
newer-only typing introspection are not promised on 3.11. On newer runtimes,
preserve alias names, type-parameter names/order and marker values. Retain the
existing supported-runtime compiler tests before accepting this representation.

### Required recognition adjustment

The existing `_runtime_annotation_matches` helper in
`src/pyrolyze/compiler/kernels/v3_14/rewrite.py` returns immediately after
unwrapping `Annotated`; it ignores its metadata. A resolved 3.11 event annotation
therefore becomes an ordinary `Callable` and loses event recognition.

The proposed bounded correction checks the `Annotated` metadata for the marker
types the caller already requests before examining the underlying type. Preserve
the existing named-alias, string, origin and fallback paths. Unmarked callables
and slot-only annotations must not become event handlers. No kernel selection,
rewrite architecture or runtime event mechanism changes are proposed.

This exact helper adjustment is an authorization boundary, not an implicit
prerequisite for every Astichi fix. See the separate findings record.

## Feasibility evidence and remaining gates

Isolated probes ran on CPython 3.11.14, 3.12.12, 3.14.3 and 3.15.0a5:

| Probe | Result |
| --- | --- |
| Four ordinary-AST writers × four readers | 16 exchanges passed; restored samples compiled |
| Location/private-state and shared-node identity | Preserved in all 16 samples |
| Existing pre-materialized golden payloads | All 42 decoded and matched their source AST on each reader |
| Newer `TypeAlias` payloads read on 3.11 | Explicit rejection for writers 3.12, 3.14 and 3.15 |
| Nonempty unsupported type parameters in saved state | Explicit rejection on 3.11 |
| Ordinary alias subscription and marker retention | Passed on all four runtimes |
| Existing helper recognizes resolved ordinary event alias | False on all four runtimes: confirmed incompatibility |
| Metadata-aware isolated event check | Recognized event only; plain and slot-only callables stayed negative |
| Standard `TypeAliasType` construction on newer runtimes | Name, parameter tuple, marker and existing recognition checks passed |

Remediation probes reproduced the initial reader's class-as-data corruption and
non-AST hook failure, then checked the revised reduction-dispatch reader in
16 same/cross-runtime exchanges. Real AST class references, opaque hook arguments
and class memo identity were preserved; all 42 goldens and the existing 3.11
unsupported-state/node negatives still passed on the exercised readers.

These are focused reconstruction and helper probes, not full compiler, API-import,
native, installed-wheel or suite results. Python 3.13 was not probed in this
design step; 3.15 was an alpha interpreter. Raw scripts/logs are local exploratory
evidence under `scratch/python311-design/`, not committed test dependencies.

Implementation must use RED/GREEN coverage in the existing canonical harness:
retain all 42 golden cases and the native parser cases; add narrow state/layout
and unsupported-node negatives; exchange ordinary provenance across the complete
runtime matrix. Include class-as-data, a non-AST restore hook receiving a real
AST class before execution, and one class global shared by node reconstruction
and metadata. Add structural/opaque cycle coverage and private-unpickler hook
compatibility checks. For aliases, exercise actual API imports, resolved imported
helper hints and the existing exactly-one-event-wrapper regression, plus slot
and plain-callable cases. Use a disposable full-compiler probe before any scope
amendment is applied. Then complete the accepted plan's native build, full suite,
snapshot, packaging, clean-wheel and support-documentation gates. Record every
remaining consumer blocker separately and do not lower consumer package floors
based on these probes.
