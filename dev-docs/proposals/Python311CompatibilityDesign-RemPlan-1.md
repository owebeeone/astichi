# Python 3.11 design remediation — round 1

Status: correction proposed and probed; reviewer closure pending. Production
implementation remains out of scope.

Reviewed revision: `9829790d9a9183cc99a56490e4a26eaf5b0e0eb2`.
Consistency returned GO; Safety returned NO-GO with one P2 architectural finding
local to the reconstruction boundary. Both complete reports are preserved
verbatim. The merge is NO-GO until the finding is independently closed.

| Finding | Disposition | Correction | Closure requirement |
| --- | --- | --- | --- |
| Safety P2-1 | Accept | Preserve real AST class globals; adapt only AST instance reduction dispatch | Retrace class-as-data, non-AST hook arguments and memo identity on the revised committed design |

## Bounded reader redesign

The original `find_class` substitution is discarded. It cannot distinguish a
global loaded as ordinary metadata from the same global used to construct a
node; repairing metadata afterwards cannot undo a hook that already received
the wrong class.

The proposed reader uses CPython's Python-level unpickler and a private,
subclass-local reduction dispatch hook. Class resolution returns actual classes.
Only `REDUCE` calls whose callable is an actual standard-library AST class are
adapted to layout-compatible allocation. Other reductions, global loading,
memo operations and saved-state application retain standard behavior. The
dispatch table is copied, not modified globally. This private stdlib dependency
is explicit and requires capability checks and runtime-matrix coverage; no
dependency package or provenance format is changed.

## Concrete closure trace

For metadata holding `(ast.Module, ast.Name)`, global/memo reads return those
actual classes. A node reduction consumes a stack reference to its class and
replaces only the reduction result with the allocated node; its memoized class
entry is unchanged. Metadata therefore retains receiving-runtime class identity.
A non-AST restore function receives `ast.Name` unchanged and executes through
the normal reduction handler before returning its object. No post-load proxy
replacement or opaque-object traversal is needed for this correction.

## Focused evidence

The lane owner ran isolated design probes; no product code or canonical tests
were changed. The original `provenance_probe.py` and earlier logs remain intact.
`reconstruction_boundary_red.py` reproduced both the class-reference substitution
and the non-AST hook failure on 3.11.14.

The separate `reduction_probe.py` exchanged four writer payloads among four
readers (3.11.14, 3.12.12, 3.14.3 and 3.15.0a5). All 16 exchanges preserved class
data, the class received by the non-AST hook and the class memo identity shared
with node reconstruction. All 42 golden payloads still decoded and matched
source ASTs on each reader with warnings treated as errors. Existing unsupported
node and restored-type-parameter negatives still passed on 3.11. This is probe
evidence, not a completed product implementation or full runtime gate.

Evidence: local ignored files under `scratch/python311-design/`, including
`reconstruction-boundary-red.log`, `reduction-reader-*.log` and the two new probe
scripts. They are not committed dependencies of product tests.

## Re-review and remaining boundaries

Because the reconstruction mechanism changed, two fresh reviewers replace the
original pair for the new revision, as required by the review-loop skill. Safety
must independently retrace all original P2-1 counterexamples; the lane owner
does not self-close the finding. Consistency must also perform the mandated cold
public-surface inspection that its first reviewer disclosed as missed. This
process correction does not erase the original report or its limitation.

No other implementation boundary, provenance format, support claim or Pyrolyze
scope amendment changes. The proposed compiler helper still requires explicit
authorization and its full-compiler feasibility gate before production edits.
