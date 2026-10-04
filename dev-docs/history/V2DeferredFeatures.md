# V2 deferred features

This is the active deferred-features register for Astichi V2. It is the
V2-era successor to `historical/V1DeferredFeatures.md`, which is frozen
at V1 close and must not be edited.

Purpose:

- Record which V1-deferred items have been reinstated as V2 scope, and
  where to find the normative spec for each.
- Record which V1-deferred items remain deferred past V2, so the V2
  scope discipline in `V2StartHere.md §6` has a concrete reference.
- Hold any new deferred items that surface during V2 implementation.

Format:

- Each entry links to the originating section in
  `historical/V1DeferredFeatures.md` (the frozen V1 list).
- Reinstated items also link to the V2 design addendum and the
  `V2Plan.md` phase that implements them.

Related documents:

- `astichi/dev-docs/historical/V1DeferredFeatures.md` (frozen V1 list)
- `astichi/dev-docs/V2Plan.md`
- `astichi/dev-docs/V2ProgressRegister.md`

## 1. Reinstated as V2 scope

These items are shipping in V2. Their entry in the frozen V1 list
remains for historical provenance but should be treated as superseded
by the references below.

### 1.1 `astichi_bind_external` value supply

Source: `historical/V1DeferredFeatures.md §4.1`.

Reinstated in:

- Design: `AstichiApiDesignV1-BindExternal.md`
- Plan: `V2Plan.md §3` (Phase 1)

### 1.2 Post-bind literal loop domains

Source: `historical/V1DeferredFeatures.md §5.1` (partial — only the
post-bind literal variant is reinstated; runtime-supplied
`build(unroll={...})` parameter dicts remain deferred, see §2.4 below).

Reinstated in:

- Design: `AstichiApiDesignV1-UnrollRevision.md §10` (under "In scope
  for V2"), `AstichiApiDesignV1-BindExternal.md §8`
- Plan: `V2Plan.md §4` (Phase 2)

### 1.3 Marker-preserving (skeleton) emission

Source: `historical/V1DeferredFeatures.md §3.1`.

Reinstated in:

- Design: `AstichiApiDesignV1-MarkerPreservingEmit.md`
- Plan: `V2Plan.md §5` (Phase 3f)

### 1.4 Emission-vs-compile adapter

Source: `historical/V1DeferredFeatures.md §7.4`.

Reinstated in:

- Plan: `V2Plan.md §5` (Phase 3g) — thin `compile_to_code` wrapper over
  `compile(emit(), filename, "exec")`. No standalone addendum; the
  surface is small enough to lock inline.

### 1.5 Diagnostics citing source origins

Source: `historical/V1DeferredFeatures.md §9.2`.

Reinstated in:

- Plan: `V2Plan.md §5` (Phase 3d) — thread `CompileOrigin` through
  user-visible error messages. Polish pass, no semantic change.

### 1.6 Unified error-timing contract

Source: `historical/V1DeferredFeatures.md §9.1`.

Reinstated in:

- Plan: `V2Plan.md §5` (Phase 3e) — new doc
  `AstichiErrorTimingContract.md` will become the normative matrix.

## 2. Still deferred past V2

The following items remain deferred after V2. Their rationale is
unchanged from the V1 list unless noted.

### 2.1 Effect tags

Source: `historical/V1DeferredFeatures.md §1.1`. Still deferred.

### 2.2 Typed IO on ports

Source: `historical/V1DeferredFeatures.md §1.2`. Still deferred.

### 2.3 Composition kernel / plug / sequence / batched

Source: `historical/V1DeferredFeatures.md §2.1–§2.4`. Still deferred.
V2 keeps the incremental builder surface.

### 2.4 Edge effect-ordering semantics

Source: `historical/V1DeferredFeatures.md §2.5`. Still deferred.

### 2.5 `build(unroll={...})` parameter dict

Source: subset of `historical/V1DeferredFeatures.md §5.1`. The
post-bind literal variant is reinstated in §1.2 above; the
runtime-supplied parameter-dict form remains deferred. The
all-or-nothing rule sketched in `UnrollRevision.md §8.2` applies when
the feature is picked up.

### 2.6 Comprehension / runtime / arbitrary-call loop domains

Source: `historical/V1DeferredFeatures.md §5.2–§5.4`. Still deferred.

### 2.7 Constant folding of substituted bodies

Source: `historical/V1DeferredFeatures.md §5.5`. Still deferred.

### 2.8 Same-scope loop-variable rebind as supported pattern

Source: `historical/V1DeferredFeatures.md §5.6`. Still deferred. V2
rejects same-scope rebind (`UnrollRevision.md §5.3`). Note:
cross-scope shadowing via inner function / lambda / comprehension /
for-target is supported by V2's scope-aware substitution; only
same-scope rebind is rejected.

### 2.9 Deep descendant / cross-composable addressing

Source: `historical/V1DeferredFeatures.md §6.1–§6.2`. Still deferred.

### 2.10 Marker-grammar round-trip and marker grammar specification

Source: `historical/V1DeferredFeatures.md §3.2, §7.3`. Still deferred.
V2 marker-preserving emission (§1.3) provides the runtime-practical
round-trip without committing to a formal grammar.

### 2.11 `Source` / `Compiled` carrier types

Source: `historical/V1DeferredFeatures.md §3.3`. Still deferred. The
Phase 3g `compile_to_code` adapter returns a plain `types.CodeType`
rather than a typed carrier.

### 2.12 Formatter policy / `__future__` / line tables

Source: `historical/V1DeferredFeatures.md §3.4`. Still deferred. V2
continues to rely on `ast.unparse` defaults.

### 2.13 `ComposeContext`

Source: `historical/V1DeferredFeatures.md §4.2`. Still deferred. Bind
ships without an ambient-context layer; a future `ComposeContext` can
layer on top (see `BindExternal.md §11`).

### 2.14 Operator taxonomy / public scope-graph API

Source: `historical/V1DeferredFeatures.md §7.1–§7.2`. Still deferred.

### 2.15 Replacement semantics / per-target materialize shapes / optional-offer

Source: `historical/V1DeferredFeatures.md §8.1–§8.3`. Still deferred.
Additive-only composition remains the V2 surface.

## 3. New V2-era deferrals

Items discovered during V2 implementation that are explicitly deferred
past V2 are recorded here. None yet.

## 4. Re-instatement policy

Same process as the V1 re-instatement policy in
`historical/V1DeferredFeatures.md §10`:

1. Draft an addendum design doc that resolves ambiguity and locks
   semantics.
2. Add execution steps to `V2Plan.md` and `V2ProgressRegister.md`
   with exit criteria and verification targets.
3. Move the item from §2 of this document into §1, preserving the
   original rationale in commit history.

When V3 opens, this document should be archived into `historical/`
alongside its V1 predecessor and a fresh `V3DeferredFeatures.md`
spun up from whatever remains deferred at that point.
