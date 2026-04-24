# Astichi multi-bind fix plan

Status: implementation plan

## Summary

Astichi currently treats `builder.<Target>.<hole>.add.<Source>(arg_names=..., keep_names=...)`
as if those bindings are edge-local, but the implementation mutates the shared
registered source instance. That breaks reuse of one source instance across
multiple edges when each edge needs different identifier bindings.

This is not a call-argument-only bug. It affects every target surface that can
consume a reused source instance:

- block holes
- expression holes
- call-argument payload holes
- parameter holes

The required fix is to make source specialization an **edge overlay**, not an
instance mutation. The builder graph should keep one registered source instance
and record per-edge binding overrides on the additive edge. Build/materialize
should derive an edge-scoped temporary source composable from the base instance
before validating ports, extracting payloads, and generating insert wrappers.

This plan is test-first. Successful behavior should live primarily in
`tests/data/gold_src`; bespoke pytest should stay focused on narrow recognition,
graph mechanics, and rejection paths.

Important scope boundary:

- **Phase 1** fixes the general multi-bind bug family for edge-local
  `arg_names=...` / `keep_names=...`.
- **Phase 1 does not make** the single-shared-instance
  `lambda_dict_wrapper_v2.py` ATTEMPT_A green as written, because that shape
  also needs edge-local external value binds.
- The current positive witness for Phase 1 is ATTEMPT_C in
  `scratch/lambda_dict_wrapper_v2.py`: distinct registered instances plus
  edge-local `arg_names=...`.
- The true "one shared payload instance across N edges" lambda shape is a
  **Phase 2** witness and needs both edge-local identifier binds and edge-local
  external value binds.

## Problem

Today, target-adder `arg_names=` / `keep_names=` flows through
`builder/handles.py` by calling `.bind_identifier(...)` / `.with_keep_names(...)`
on the registered source composable and then replacing the instance record.

That means:

1. one source instance cannot be added to two edges with different
   `arg_names=...`;
2. a later edge mutates the meaning of the earlier edge instead of carrying its
   own overlay;
3. payload validators that inspect source text before final materialize see the
   wrong binding state.

Observed consequences:

- call-argument payloads can fail duplicate explicit-keyword validation because
  multiple contributions still read as the same unresolved
  `name__astichi_arg__` kwarg;
- parameter payloads have the same issue for reused parameter-name slots;
- any reused block/expression source that relies on edge-local
  `astichi_import(...)` / `astichi_pass(...)` rewiring is conceptually unsafe,
  even when current tests only cover identical bindings.

There is a related but distinct ergonomic gap:

- one shared source instance also cannot vary `astichi_bind_external(...)`
  values per edge, because target-adder does not have an edge-local value-bind
  surface.

That second point is real, but it is not required to fix the current
identifier/keep rebinding bug family.

## Required behavior

After this fix:

- `builder.add.Name(piece, arg_names=..., keep_names=...)` remains
  **instance-level** specialization at registration time.
- `builder.<Target>.<hole>.add.Name(arg_names=..., keep_names=...)` becomes
  truly **edge-local**.
- Existing registration-time `.bind(...)` / `.bind_identifier(...)` behavior
  stays semantically unchanged. The overlay model changes only what
  `target.<hole>.add.<Source>(...)` does with `arg_names=` / `keep_names=...`.
- Reusing the same source instance on multiple edges with different
  `arg_names=...` must work across all target surfaces.
- Duplicate final names must still reject after resolution:
  - duplicate explicit kwargs in call-argument payloads
  - duplicate final parameter names
  - duplicate inserted `*args` / `**kwargs`
- Hygiene behavior does not change: edge-local bindings resolve names before the
  existing hygiene pipeline runs.
- Binding precedence is explicit:
  - registration-level specialization applies first;
  - edge overlay applies second;
  - same key + same value is idempotent;
  - same key + different value rejects;
  - `keep_names` unions.
- Precedence/conflict evaluation must happen on binding metadata before any
  eager `__astichi_arg__` rewrite is applied to the derived edge-scoped tree.
  A registration-level eager rewrite must not cause an edge-level conflicting
  binding to silently no-op just because the authored suffix text is already
  gone from the tree.

## Proposed model

### 1. Add an edge overlay object

Extend `AdditiveEdge` with a typed edge-local source overlay object, for
example:

```python
@dataclass(frozen=True)
class EdgeSourceOverlay:
    arg_names: tuple[tuple[str, str], ...] = ()
    keep_names: frozenset[str] = frozenset()
```

`AdditiveEdge` then carries:

```python
overlay: EdgeSourceOverlay = EdgeSourceOverlay()
```

The key rule is that the overlay belongs to the edge, not the registered
instance.

Normalization rule:

- `arg_names` should preserve user insertion order through normalization, while
  rejecting duplicate keys with conflicting values.
- Equal overlays should therefore stay deterministic without introducing an
  artificial sort order that the user did not write.

### 2. Stop mutating source instances from target adders

`builder.<Target>.<hole>.add.<Source>(...)` should no longer call
`replace_instance(...)` for `arg_names=` / `keep_names=...`.

Instead, it should validate and normalize those inputs, place them into the
edge overlay, and append the edge unchanged with respect to the source instance
record.

### 3. Derive an edge-scoped source piece during merge

When materialize/build-merge processes one additive edge, it should:

1. load the base source instance;
2. apply the edge overlay to derive a temporary source composable;
3. use that derived piece for:
   - demand/supply port checks
   - payload extraction
   - wrapper generation
   - source-body copying

That derived piece is transient. The registered instance stays canonical.

Authoritative-state rule:

- merge/materialize correctness must come from the edge-specialized source tree,
  not from metadata on the unspecialized registered instance record alone.
- In particular, demand/supply closure should be judged from the merged tree
  after edge specialization has been applied.
- Hygiene must run against the already edge-specialized merged tree. The
  hygiene algorithm itself is not being redesigned in this slice; the fix is
  that hygiene sees the correct per-edge-resolved names and per-edge keep state.
- Final merged hygiene-related metadata (`arg_bindings`, `keep_names`, and any
  equivalent derived state used by resolver/hygiene setup) must be computed
  from the edge-specialized contributions that were actually inserted, not by
  unioning only the unspecialized registered instance records.

### 4. Keep the fix general across all target surfaces

Do not patch only `astichi_funcargs(...)` or only parameter payloads.

The overlay application point should sit high enough in merge that the same
edge-scoped source piece is used for:

- block contributions
- expression contributions
- call-argument payload extraction
- parameter payload extraction

That gives one fix for the whole bug family.

Concrete merge order:

1. start from the registered source instance;
2. apply registration-level specialization already attached to that instance;
3. compose registration-level metadata with the edge overlay, including
   precedence/conflict checks, before applying identifier rewrites to the
   derived tree;
4. apply the combined specialization to derive the edge-scoped piece;
5. if the source participates in root-wrapper transparency or staged-build
   unwrap logic, do that against the already-derived edge-scoped tree;
6. run source-side port checks and payload extraction against the edge-scoped
   piece;
7. run duplicate-name validators against resolved names from that piece;
8. build the merged tree and merged hygiene-related metadata from the
   edge-specialized contributions actually inserted;
9. continue with normal merge finalization and hygiene on that merged result.

Performance note:

- the straightforward implementation derives one temporary edge-scoped piece per
  edge, so large fan-in is `O(edges × tree-size)`. That is acceptable for this
  fix unless measurement shows a real problem; correctness comes first.

## Scope split

### Required in this slice

- edge-local `arg_names=...`
- edge-local `keep_names=...`
- call-argument payload correctness under repeated source reuse
- parameter payload correctness under repeated source reuse
- one simple non-payload proof that block/expression contributors also respect
  the same edge-local binding model
- explicit proof that ATTEMPT_C-style usage is supported in one stage

### Optional follow-on

Edge-local external value binds for `astichi_bind_external(...)`, for example a
surface like:

```python
builder.Root.kwargs.add.Kw(bind={"field_key": "a"}, arg_names={"field": "a"})
```

This is what the single-shared-source lambda wrapper case wants. It should be
treated as a separate decision unless we explicitly choose to broaden this
slice. The identifier/keep rebinding bug does not require it.

Clarification:

- registration-time value binding is already supported today via
  `piece.bind(...)` before `builder.add.Name(piece)` or at `builder.add.Name(...)`
  time;
- Phase 2 is specifically about adding an edge-local `bind={...}` surface on
  `target.<hole>.add.<Source>(...)`.

## Implementation plan

1. Write red tests first.
   - Add gold-source success coverage for reused-source multi-bind behavior.
   - Add thin bespoke tests for the graph/builder mechanics and rejection
     paths.

2. Add an edge overlay representation to the builder graph.
   - Extend `AdditiveEdge`.
   - Normalize overlays at edge creation time.
   - Keep the raw graph readable and explicit.

3. Change target-adder behavior in `builder/handles.py`.
   - `builder.add.Name(...)` keeps its current instance-level behavior.
   - `target.add.Name(...)` stops mutating the registered instance.
   - It emits an edge with overlay metadata instead.

4. Add one merge helper that applies an edge overlay to a base source piece.
   - Start from the registered `BasicComposable`.
   - Apply `.with_keep_names(...)` and `.bind_identifier(...)` to build a
     temporary edge-scoped piece.
   - Apply registration-level state first, then edge-level overlay, with the
     precedence/rejection rules above.
   - Reuse this helper from the main merge loop.

5. Route every contribution path through the derived edge-scoped piece.
   - block contribution body copy
   - expression contribution extraction
   - call-argument payload extraction / duplicate explicit-keyword validation
   - parameter payload extraction / duplicate final-name validation
   - merged `arg_bindings` / `keep_names` accumulation for the final composable

6. Keep emitted-source and provenance behavior unchanged unless a test proves
   otherwise.
   - This is a builder/merge correctness fix, not a source-format redesign.

7. If we choose to include edge-local external binds in the same rollout, add
   them after the identifier/keep overlay path is green.

## Test plan

### Gold-source success tests

Use `tests/data/gold_src` for most successful behavior.

Add or expand goldens for:

- reused source instance into one call-argument hole with different
  edge-local `arg_names=...`, producing distinct explicit kwargs;
- reused source instance into one parameter hole with different edge-local
  `arg_names=...`, producing distinct parameter names;
- mixed authored + inserted parameter ordering with reused payload sources;
- reused block/body contributor with different edge-local `arg_names=...` into
  two edges, proving the fix is not payload-specific;
- staged build reuse where a built composable is re-added with edge-local
  bindings in a later stage, including a root-wrapper-transparency case;
- one provenance-pinning golden for reused-source multi-bind so we notice if
  edge-specialized temporary pieces disturb emitted/source-location behavior.
- one golden or focused test that proves final merged `keep_names` /
  `arg_bindings` behavior comes from edge-specialized contributions rather than
  only from unspecialized instance records.

If the optional external-bind extension is included, add one gold source that
reuses a single shared payload instance with both edge-local value and
identifier specialization.

### Bespoke targeted tests

Keep these narrow:

- `AdditiveEdge` overlay storage / normalization;
- target-adder no longer mutates the registered instance record;
- registration-level + edge-level precedence and conflict rejection;
- registration-level + edge-level same-key / same-value idempotence;
- conflicting or invalid `arg_names=` still reject with the same diagnostics;
- registration-level + edge-level same-key / different-value conflict raises a
  distinct diagnostic from "unknown slot" and duplicate-name failures;
- real duplicate resolved kwargs still reject;
- real duplicate resolved parameter names still reject.

### Verification order

1. focused pytest for touched units
2. golden harness
3. full pytest
4. Python-version matrix

## Docs

If this remains an internal builder-correctness fix with no new public surface:

- update `dev-docs/AstichiSingleSourceSummary.md`
- update reference docs only where they currently imply that edge-local
  `arg_names=` works by mutating the source instance

If we also add edge-local external value binds, update:

- builder API reference
- scoping/hygiene reference where binding surfaces are listed
- any relevant snippets that should show the preferred surface

## TDD notes

- Start with the failing gold-source cases, not with a graph refactor.
- Success-path assertions belong in goldens.
- Bespoke tests should exist only where the golden harness cannot express the
  failure or where a low-level graph invariant needs to be pinned.
- Do not silently change public semantics to satisfy a test; if the slice grows
  into edge-local external value binds, document that surface explicitly before
  implementation.

## Recommended rollout

Phase 1: required fix

- edge-local `arg_names=...`
- edge-local `keep_names=...`
- general merge helper
- goldens for args + params + one non-payload path

Phase 2: optional extension

- edge-local external value binds
- single-shared-source lambda wrapper style examples

If Phase 1 lands cleanly, it already fixes the parameter-hole and call-argument
multi-bind bug family.
